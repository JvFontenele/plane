# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
import hashlib
import hmac
import re
import secrets
from datetime import timedelta

# Django imports
from django.conf import settings
from django.utils import timezone

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.views.base import BaseAPIView
from plane.db.models import UserNotificationChannel
from plane.utils.notification_channels import (
    CHANNELS,
    ChannelError,
    allowed_events,
    get_channel_config,
    is_channel_ready,
    telegram_get_updates,
    whatsapp_send,
)

PHONE_RE = re.compile(r"^\+[1-9]\d{7,14}$")
MAX_CODE_ATTEMPTS = 5


def _digest(user_id, value):
    # Keyed hash: a leaked DB row cannot be brute-forced back into a valid 6-digit code.
    return hmac.new(settings.SECRET_KEY.encode(), f"{user_id}:{value}".encode(), hashlib.sha256).hexdigest()


def _row(user, channel):
    return UserNotificationChannel.objects.get_or_create(user=user, channel=channel)[0]


def _pending(row):
    return (
        bool(row.verification_hash)
        and bool(row.verification_expires_at)
        and row.verification_expires_at > timezone.now()
    )


def _clear_verification(row):
    row.verification_hash = ""
    row.verification_expires_at = None
    row.verification_attempts = 0


def _serialize(row, config):
    return {
        "channel": row.channel,
        "available": is_channel_ready(row.channel, config),
        "linked": row.verified_at is not None,
        "address": f"•••• {row.address[-4:]}" if row.address else "",
        "enabled": row.enabled,
        "consented_at": row.consented_at,
        "events": row.events,
        "pending": _pending(row),
    }


def _error(code, http_status=status.HTTP_400_BAD_REQUEST):
    return Response({"error": code}, status=http_status)


class UserNotificationChannelEndpoint(BaseAPIView):
    def get(self, request):
        config = get_channel_config()
        return Response(
            {
                "channels": [_serialize(_row(request.user, channel), config) for channel in CHANNELS],
                "available_events": sorted(allowed_events(config)),
                "telegram_bot_username": config.get("TELEGRAM_BOT_USERNAME", ""),
            },
            status=status.HTTP_200_OK,
        )

    def patch(self, request, channel):
        if channel not in CHANNELS:
            return _error("invalid_channel", status.HTTP_404_NOT_FOUND)
        config = get_channel_config()
        row = _row(request.user, channel)

        if "events" in request.data:
            events = request.data.get("events")
            if not isinstance(events, list) or not set(events) <= allowed_events(config):
                return _error("invalid_events")
            row.events = events

        if "enabled" in request.data:
            if request.data.get("enabled") is True:
                if row.verified_at is None:
                    return _error("not_linked")
                row.enabled = True
                row.consented_at = timezone.now()
            else:
                # Disabling the channel also revokes consent.
                row.enabled = False
                row.consented_at = None

        row.save()
        return Response(_serialize(row, config), status=status.HTTP_200_OK)

    def delete(self, request, channel):
        if channel not in CHANNELS:
            return _error("invalid_channel", status.HTTP_404_NOT_FOUND)
        UserNotificationChannel.objects.filter(user=request.user, channel=channel).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TelegramLinkEndpoint(BaseAPIView):
    def post(self, request):
        config = get_channel_config()
        username = config.get("TELEGRAM_BOT_USERNAME", "")
        if not is_channel_ready("telegram", config) or not username:
            return _error("channel_unavailable")
        row = _row(request.user, "telegram")
        token = secrets.token_urlsafe(16)
        row.verification_hash = _digest(request.user.id, token)
        row.verification_expires_at = timezone.now() + timedelta(minutes=15)
        row.verification_attempts = 0
        row.save()
        return Response(
            {"deep_link": f"https://t.me/{username}?start={token}", "expires_at": row.verification_expires_at},
            status=status.HTTP_200_OK,
        )


class TelegramVerifyEndpoint(BaseAPIView):
    def post(self, request):
        config = get_channel_config()
        row = _row(request.user, "telegram")
        if not _pending(row):
            return _error("link_expired")
        try:
            updates = telegram_get_updates(config.get("TELEGRAM_BOT_TOKEN", ""))
        except ChannelError as e:
            return _error(str(e))

        # The chat id comes from a /start message carrying a one-time token only this user received,
        # so a user cannot bind someone else's Telegram chat.
        for update in updates:
            message = update.get("message") or {}
            chat = message.get("chat") or {}
            text = message.get("text") or ""
            if chat.get("type") != "private" or not text.startswith("/start "):
                continue
            if hmac.compare_digest(_digest(request.user.id, text[len("/start ") :].strip()), row.verification_hash):
                row.address = str(chat["id"])
                row.verified_at = timezone.now()
                _clear_verification(row)
                row.save()
                return Response(_serialize(row, config), status=status.HTTP_200_OK)
        return _error("start_message_not_found")


class WhatsAppLinkEndpoint(BaseAPIView):
    def post(self, request):
        config = get_channel_config()
        if not is_channel_ready("whatsapp", config):
            return _error("channel_unavailable")
        phone = str(request.data.get("phone") or "").replace(" ", "").replace("-", "")
        if not PHONE_RE.match(phone):
            return _error("invalid_phone")
        row = _row(request.user, "whatsapp")
        now = timezone.now()
        # One code per minute: codes expire in 10 minutes, so an expiry more than 9 minutes away is < 1 minute old.
        if row.verification_expires_at and row.verification_expires_at - timedelta(minutes=9) > now:
            return _error("wait_before_resending", status.HTTP_429_TOO_MANY_REQUESTS)
        code = f"{secrets.randbelow(10**6):06d}"
        row.pending_address = phone
        row.verification_hash = _digest(request.user.id, code)
        row.verification_expires_at = now + timedelta(minutes=10)
        row.verification_attempts = 0
        row.save()
        try:
            whatsapp_send(config, phone, f"Plane: seu código de verificação é {code}")
        except ChannelError as e:
            # Nothing reached the user, so drop the pending code and allow an immediate retry.
            _clear_verification(row)
            row.save()
            return _error(str(e))
        return Response({"sent": True}, status=status.HTTP_200_OK)


class WhatsAppVerifyEndpoint(BaseAPIView):
    def post(self, request):
        config = get_channel_config()
        row = _row(request.user, "whatsapp")
        if not _pending(row) or not row.pending_address:
            return _error("code_expired")
        if row.verification_attempts >= MAX_CODE_ATTEMPTS:
            return _error("too_many_attempts", status.HTTP_429_TOO_MANY_REQUESTS)
        row.verification_attempts += 1
        row.save(update_fields=["verification_attempts"])
        code = str(request.data.get("code") or "").strip()
        if not hmac.compare_digest(_digest(request.user.id, code), row.verification_hash):
            return _error("invalid_code")
        row.address = row.pending_address
        row.pending_address = ""
        row.verified_at = timezone.now()
        _clear_verification(row)
        row.save()
        return Response(_serialize(row, config), status=status.HTTP_200_OK)
