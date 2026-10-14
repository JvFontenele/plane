# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import uuid
from unittest.mock import patch

import pytest
from django.utils import timezone

from plane.license.models import Instance, InstanceAdmin, InstanceConfiguration
from plane.license.utils.encryption import decrypt_data

BASE = "/api/instances/notification-channel/"
TOKEN = "123456:SUPER-SECRET-TOKEN"


@pytest.fixture
def admin_client(session_client, create_user):
    instance = Instance.objects.create(
        instance_name="Test",
        instance_id=str(uuid.uuid4()),
        current_version="1.0.0",
        domain="http://localhost:8000",
        last_checked_at=timezone.now(),
        is_setup_done=True,
    )
    InstanceAdmin.objects.create(instance=instance, user=create_user, role=20)
    return session_client


@pytest.mark.contract
@pytest.mark.django_db
class TestNotificationChannelAdmin:
    def test_non_admin_is_rejected(self, session_client):
        assert session_client.get(BASE).status_code in (401, 403)

    def test_secret_is_write_only(self, admin_client):
        response = admin_client.patch(
            BASE, {"TELEGRAM_BOT_TOKEN": TOKEN, "ENABLE_TELEGRAM_NOTIFICATIONS": True}, format="json"
        )
        assert response.status_code == 200
        assert response.data["telegram"] == {"enabled": True, "token_set": True, "bot_username": ""}
        assert TOKEN not in admin_client.get(BASE).content.decode()

        # An empty secret keeps the stored one.
        admin_client.patch(BASE, {"TELEGRAM_BOT_TOKEN": ""}, format="json")
        stored = InstanceConfiguration.objects.get(key="TELEGRAM_BOT_TOKEN")
        assert stored.is_encrypted and decrypt_data(stored.value) == TOKEN

        # The generic configuration endpoint returns decrypted secrets, so it must not list these keys.
        generic = admin_client.get("/api/instances/configurations/")
        assert TOKEN not in generic.content.decode()

    @pytest.mark.parametrize(
        "payload,error",
        [
            ({"WHATSAPP_PROVIDER_URL": "ftp://evolution:8080"}, "invalid_provider_url"),
            ({"NOTIFICATION_CHANNEL_EVENTS": ["comment", "nope"]}, "invalid_events"),
        ],
    )
    def test_invalid_values_are_rejected(self, admin_client, payload, error):
        response = admin_client.patch(BASE, payload, format="json")
        assert response.status_code == 400 and response.data["error"] == error

    @patch("plane.license.api.views.notification_channel.whatsapp_send")
    def test_whatsapp_test_validates_number(self, send, admin_client):
        admin_client.patch(
            BASE, {"WHATSAPP_PROVIDER_URL": "http://evolution:8080", "WHATSAPP_API_KEY": "k"}, format="json"
        )
        assert admin_client.post(f"{BASE}whatsapp/test/", {"number": "abc"}, format="json").status_code == 400
        send.assert_not_called()
        assert (
            admin_client.post(f"{BASE}whatsapp/test/", {"number": "+5511999998888"}, format="json").status_code == 200
        )
        send.assert_called_once()

    @patch("plane.license.api.views.notification_channel.telegram_get_me", return_value={"username": "plane_bot"})
    def test_telegram_check_stores_bot_username(self, _me, admin_client):
        admin_client.patch(BASE, {"TELEGRAM_BOT_TOKEN": TOKEN}, format="json")
        response = admin_client.post(f"{BASE}telegram/check/")
        assert response.data == {"ok": True, "bot_username": "plane_bot"}
        assert admin_client.get(BASE).data["telegram"]["bot_username"] == "plane_bot"
