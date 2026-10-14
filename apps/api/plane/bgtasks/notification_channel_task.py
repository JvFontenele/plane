# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Background tasks for channel-based notification delivery (Telegram/WhatsApp)."""

import uuid
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone as dj_timezone

from plane.db.models import (
    Notification,
    NotificationDelivery,
    ProjectMember,
    UserNotificationChannel,
)

from plane.utils.notification_channels import (
    ChannelError,
    allowed_events,
    build_message,
    categorize,
    get_channel_config,
    is_channel_ready,
    telegram_send,
    whatsapp_send,
    CHANNELS,
)


@shared_task
def dispatch_channel_notifications(notification_ids):
    """Create NotificationDelivery rows and enqueue deliver_channel_notification for each."""
    config = get_channel_config()
    ready = [c for c in CHANNELS if is_channel_ready(c, config)]
    if not ready:
        return

    try:
        notifications = Notification.objects.filter(id__in=[uuid.UUID(nid) for nid in notification_ids])
    except ValueError:
        return

    if not notifications.exists():
        return

    receivers = set(n.receiver_id for n in notifications)
    rows = UserNotificationChannel.objects.filter(
        user_id__in=receivers,
        channel__in=ready,
        enabled=True,
        deleted_at__isnull=True,
    )

    for notification in notifications:
        for row in rows:
            if row.user_id != notification.receiver_id:
                continue
            delivery, created = NotificationDelivery.objects.get_or_create(
                notification=notification,
                channel=row.channel,
                defaults={
                    "status": "pending",
                    "attempts": 0,
                    "reason": "",
                    "external_id": "",
                },
            )
            if created:
                deliver_channel_notification.delay(str(delivery.id))


@shared_task(bind=True, max_retries=3)
def deliver_channel_notification(self, delivery_id):
    """Deliver a single NotificationDelivery record through its channel."""
    delivery = (
        NotificationDelivery.objects.select_related("notification", "notification__workspace")
        .filter(id=delivery_id)
        .first()
    )
    if delivery is None or delivery.status in ("sent", "skipped"):
        return

    channel = delivery.channel
    config = get_channel_config()

    n = delivery.notification

    def skip(reason):
        delivery.status = "skipped"
        delivery.reason = reason[:255]
        delivery.save(update_fields=["status", "reason"])

    if not is_channel_ready(channel, config):
        skip("channel_disabled")
        return

    try:
        row = UserNotificationChannel.objects.get(
            user_id=n.receiver_id,
            channel=channel,
            deleted_at__isnull=True,
        )
    except UserNotificationChannel.DoesNotExist:
        skip("not_linked_or_no_consent")
        return

    if not row.enabled or row.consented_at is None or row.verified_at is None or not row.address:
        skip("not_linked_or_no_consent")
        return

    category = categorize(n)
    if category not in allowed_events(config):
        skip("event_disabled_by_admin")
        return

    if row.events and category not in row.events:
        skip("event_disabled_by_user")
        return

    if not ProjectMember.objects.filter(project_id=n.project_id, member_id=n.receiver_id, is_active=True).exists():
        skip("no_project_access")
        return

    # ponytail: fixed 20/min per receiver; use Redis sliding window if throughput matters
    rate_cutoff = dj_timezone.now() - timedelta(seconds=60)
    rate_count = NotificationDelivery.objects.filter(
        notification__receiver_id=n.receiver_id,
        channel=channel,
        status="sent",
        updated_at__gte=rate_cutoff,
    ).count()
    if rate_count >= 20:
        skip("rate_limited")
        return

    web_url = getattr(settings, "WEB_URL", None) or ""

    try:
        if channel == "telegram":
            text = build_message(n, web_url, "telegram")
            external_id = telegram_send(config["TELEGRAM_BOT_TOKEN"], row.address, text, html=True)
        elif channel == "whatsapp":
            text = build_message(n, web_url, "whatsapp")
            external_id = whatsapp_send(config, row.address, text)
        else:
            skip("unknown_channel")
            return

        delivery.status = "sent"
        delivery.external_id = str(external_id)[:128]
        delivery.attempts += 1
        delivery.reason = ""
        delivery.save(
            update_fields=[
                "status",
                "external_id",
                "attempts",
                "reason",
                "updated_at",
            ]
        )
    except ChannelError as e:
        delivery.attempts += 1
        if e.transient and self.request.retries < self.max_retries:
            delivery.save(update_fields=["attempts", "updated_at"])
            raise self.retry(
                exc=e,
                countdown=60 * 2**self.request.retries,
            )
        delivery.status = "failed"
        delivery.reason = str(e)[:255]
        delivery.save(update_fields=["status", "reason", "attempts", "updated_at"])
