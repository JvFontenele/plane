# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import re

from django.db.models import Q

from rest_framework import status
from rest_framework.response import Response

from plane.db.models import NotificationDelivery, UserNotificationChannel
from plane.license.models import InstanceConfiguration
from .base import BaseAPIView
from plane.license.api.permissions import InstanceAdminPermission
from plane.license.utils.encryption import encrypt_data
from plane.utils.notification_channels import (
    ChannelError,
    EVENT_CATEGORIES,
    get_channel_config,
    telegram_get_me,
    telegram_send,
    validate_provider_url,
    whatsapp_connect,
    whatsapp_create_instance,
    whatsapp_logout,
    whatsapp_send,
    whatsapp_state,
)


SECRET_KEYS = set(["TELEGRAM_BOT_TOKEN", "WHATSAPP_API_KEY"])

ALL_CONFIG_KEYS = (
    "ENABLE_TELEGRAM_NOTIFICATIONS",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_BOT_USERNAME",
    "ENABLE_WHATSAPP_NOTIFICATIONS",
    "WHATSAPP_PROVIDER_URL",
    "WHATSAPP_API_KEY",
    "WHATSAPP_INSTANCE_NAME",
    "NOTIFICATION_CHANNEL_EVENTS",
)


def _save(key, value):
    InstanceConfiguration.objects.update_or_create(
        key=key,
        defaults=dict(
            value=encrypt_data(value) if key in SECRET_KEYS else value,
            category="NOTIFICATIONS",
            is_encrypted=key in SECRET_KEYS,
        ),
    )


def _summary(config):
    return dict(
        telegram=dict(
            enabled=config.get("ENABLE_TELEGRAM_NOTIFICATIONS") == "1",
            token_set=bool(config.get("TELEGRAM_BOT_TOKEN")),
            bot_username=config.get("TELEGRAM_BOT_USERNAME", ""),
        ),
        whatsapp=dict(
            enabled=config.get("ENABLE_WHATSAPP_NOTIFICATIONS") == "1",
            provider_url=config.get("WHATSAPP_PROVIDER_URL", ""),
            api_key_set=bool(config.get("WHATSAPP_API_KEY")),
            instance_name=config.get("WHATSAPP_INSTANCE_NAME", "plane"),
        ),
        events=config.get("NOTIFICATION_CHANNEL_EVENTS", ""),
        available_events=list(EVENT_CATEGORIES),
    )


class NotificationChannelConfigEndpoint(BaseAPIView):
    permission_classes = [InstanceAdminPermission]

    def get(self, request):
        config = get_channel_config()
        return Response(_summary(config), status=status.HTTP_200_OK)

    def patch(self, request):
        data = request.data
        config = get_channel_config()
        for key in ALL_CONFIG_KEYS:
            if key not in data:
                continue
            value = data[key]
            if key in ("ENABLE_TELEGRAM_NOTIFICATIONS", "ENABLE_WHATSAPP_NOTIFICATIONS"):
                if value is True:
                    value = "1"
                elif value is False:
                    value = "0"
                else:
                    value = str(value).strip()
                if value not in ("0", "1"):
                    return Response(
                        dict(error="invalid_value for " + key),
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                _save(key, value)
            elif key == "WHATSAPP_PROVIDER_URL":
                if value == "" or value is None:
                    continue
                if not validate_provider_url(str(value)):
                    return Response(
                        dict(error="invalid_provider_url"),
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                _save(key, str(value))
            elif key == "NOTIFICATION_CHANNEL_EVENTS":
                if value is None:
                    continue
                if isinstance(value, str):
                    items = [v.strip() for v in value.split(",") if v.strip()]
                elif isinstance(value, list):
                    items = [str(v).strip() for v in value if str(v).strip()]
                else:
                    items = []
                invalid = [i for i in items if i not in EVENT_CATEGORIES]
                if invalid:
                    return Response(
                        dict(error="invalid_events"),
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                _save(key, ",".join(items))
            elif key in ("TELEGRAM_BOT_TOKEN", "WHATSAPP_API_KEY"):
                if value is None or str(value).strip() == "":
                    continue
                _save(key, str(value).strip())
            else:
                if value is None or str(value).strip() == "":
                    continue
                _save(key, str(value))
        config = get_channel_config()
        return Response(_summary(config), status=status.HTTP_200_OK)


class TelegramCheckEndpoint(BaseAPIView):
    permission_classes = [InstanceAdminPermission]

    def post(self, request):
        config = get_channel_config()
        token = config.get("TELEGRAM_BOT_TOKEN", "")
        if not token:
            return Response(dict(error="not_configured"), status=status.HTTP_400_BAD_REQUEST)
        try:
            me = telegram_get_me(token)
        except ChannelError as e:
            return Response(dict(error=str(e)), status=status.HTTP_400_BAD_REQUEST)
        username = me.get("username", "")
        _save("TELEGRAM_BOT_USERNAME", username)
        return Response(dict(ok=True, bot_username=username), status=status.HTTP_200_OK)


class TelegramTestEndpoint(BaseAPIView):
    permission_classes = [InstanceAdminPermission]

    def post(self, request):
        config = get_channel_config()
        token = config.get("TELEGRAM_BOT_TOKEN", "")
        if not token:
            return Response(dict(error="not_configured"), status=status.HTTP_400_BAD_REQUEST)
        try:
            row = UserNotificationChannel.objects.get(
                user=request.user,
                channel="telegram",
                verified_at__isnull=False,
                deleted_at__isnull=True,
            )
        except UserNotificationChannel.DoesNotExist:
            return Response(
                dict(error="link_your_account_first"),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            telegram_send(token, row.address, "Plane: mensagem de teste")
        except ChannelError as e:
            return Response(dict(error=str(e)), status=status.HTTP_400_BAD_REQUEST)
        return Response(dict(ok=True), status=status.HTTP_200_OK)


class WhatsAppStatusEndpoint(BaseAPIView):
    permission_classes = [InstanceAdminPermission]

    def get(self, request):
        config = get_channel_config()
        url = config.get("WHATSAPP_PROVIDER_URL", "")
        api_key = config.get("WHATSAPP_API_KEY", "")
        if not url or not api_key:
            return Response(dict(state="not_configured"), status=status.HTTP_200_OK)
        try:
            state = whatsapp_state(config)
        except ChannelError as e:
            return Response(
                dict(state="error", error=str(e)),
                status=status.HTTP_200_OK,
            )
        return Response(dict(state=state), status=status.HTTP_200_OK)


class WhatsAppConnectEndpoint(BaseAPIView):
    permission_classes = [InstanceAdminPermission]

    def post(self, request):
        config = get_channel_config()
        url = config.get("WHATSAPP_PROVIDER_URL", "")
        api_key = config.get("WHATSAPP_API_KEY", "")
        if not url or not api_key:
            return Response(dict(error="not_configured"), status=status.HTTP_400_BAD_REQUEST)
        try:
            whatsapp_create_instance(config)
        except ChannelError:
            pass  # instance usually exists already; connect below reports real failures
        try:
            result = whatsapp_connect(config)
        except ChannelError as e:
            return Response(dict(error=str(e)), status=status.HTTP_400_BAD_REQUEST)
        return Response(
            dict(
                qr_base64=result.get("base64", ""),
                pairing_code=result.get("pairingCode", ""),
            ),
            status=status.HTTP_200_OK,
        )


class WhatsAppLogoutEndpoint(BaseAPIView):
    permission_classes = [InstanceAdminPermission]

    def post(self, request):
        config = get_channel_config()
        try:
            whatsapp_logout(config)
        except ChannelError as e:
            return Response(dict(error=str(e)), status=status.HTTP_400_BAD_REQUEST)
        return Response(dict(ok=True), status=status.HTTP_200_OK)


class WhatsAppTestEndpoint(BaseAPIView):
    permission_classes = [InstanceAdminPermission]

    def post(self, request):
        config = get_channel_config()
        url = config.get("WHATSAPP_PROVIDER_URL", "")
        api_key = config.get("WHATSAPP_API_KEY", "")
        if not url or not api_key:
            return Response(dict(error="not_configured"), status=status.HTTP_400_BAD_REQUEST)
        number = str(request.data.get("number") or "")
        if not number:
            return Response(
                dict(error="invalid_number"),
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not re.match(r"^\+?[1-9]\d{7,14}$", number):
            return Response(
                dict(error="invalid_number"),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            whatsapp_send(config, number, "Plane: mensagem de teste")
        except ChannelError as e:
            return Response(dict(error=str(e)), status=status.HTTP_400_BAD_REQUEST)
        return Response(dict(ok=True), status=status.HTTP_200_OK)


class NotificationDeliveryLogEndpoint(BaseAPIView):
    permission_classes = [InstanceAdminPermission]

    def get(self, request):
        qs = NotificationDelivery.objects.filter(Q(status="failed") | Q(status="skipped")).order_by("-created_at")[:50]
        return Response(
            [
                dict(
                    id=row.id,
                    channel=row.channel,
                    status=row.status,
                    reason=row.reason,
                    attempts=row.attempts,
                    created_at=row.created_at.isoformat() if row.created_at else None,
                )
                for row in qs
            ],
            status=status.HTTP_200_OK,
        )
