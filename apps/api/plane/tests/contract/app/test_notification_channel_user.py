# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import re
from unittest.mock import patch

import pytest

from plane.db.models import UserNotificationChannel
from plane.utils.notification_channels import ChannelError

BASE = "/api/users/me/notification-channels/"
VIEW = "plane.app.views.notification.channel"
CONFIG = {
    "ENABLE_TELEGRAM_NOTIFICATIONS": "1",
    "TELEGRAM_BOT_TOKEN": "123:ABC",
    "TELEGRAM_BOT_USERNAME": "plane_bot",
    "ENABLE_WHATSAPP_NOTIFICATIONS": "1",
    "WHATSAPP_PROVIDER_URL": "http://evolution:8080",
    "WHATSAPP_API_KEY": "k",
    "WHATSAPP_INSTANCE_NAME": "plane",
    "NOTIFICATION_CHANNEL_EVENTS": "state_change,comment,mention",
}


@pytest.fixture(autouse=True)
def config():
    with patch(f"{VIEW}.get_channel_config", return_value=dict(CONFIG)):
        yield


def start_update(text, chat_id=555, chat_type="private"):
    return {"update_id": 1, "message": {"text": text, "chat": {"id": chat_id, "type": chat_type}}}


@pytest.mark.contract
@pytest.mark.django_db
class TestTelegramLinking:
    def test_links_only_with_own_start_token(self, session_client):
        link = session_client.post(f"{BASE}telegram/link/").data["deep_link"]
        token = link.split("?start=")[1]
        assert link.startswith("https://t.me/plane_bot?start=")

        with patch(f"{VIEW}.telegram_get_updates", return_value=[start_update("/start someone-elses-token")]):
            assert session_client.post(f"{BASE}telegram/verify/").data["error"] == "start_message_not_found"
        with patch(f"{VIEW}.telegram_get_updates", return_value=[start_update(f"/start {token}", chat_type="group")]):
            assert session_client.post(f"{BASE}telegram/verify/").status_code == 400

        with patch(f"{VIEW}.telegram_get_updates", return_value=[start_update(f"/start {token}")]):
            response = session_client.post(f"{BASE}telegram/verify/")
        assert response.status_code == 200 and response.data["linked"] is True
        row = UserNotificationChannel.objects.get(channel="telegram")
        assert row.address == "555" and row.verification_hash == ""
        # Linking alone is not consent.
        assert row.enabled is False and row.consented_at is None

        # The token is single use.
        with patch(f"{VIEW}.telegram_get_updates", return_value=[start_update(f"/start {token}")]):
            assert session_client.post(f"{BASE}telegram/verify/").data["error"] == "link_expired"


@pytest.mark.contract
@pytest.mark.django_db
class TestWhatsAppLinking:
    def send_code(self, client, phone="+55 11 99999-8888"):
        with patch(f"{VIEW}.whatsapp_send") as send:
            response = client.post(f"{BASE}whatsapp/link/", {"phone": phone}, format="json")
        return response, send

    def test_verifies_phone_with_code(self, session_client):
        response, send = self.send_code(session_client)
        assert response.data == {"sent": True}
        assert send.call_args.args[1] == "+5511999998888"
        code = re.search(r"\d{6}", send.call_args.args[2]).group()

        assert (
            session_client.post(
                f"{BASE}whatsapp/verify/", {"code": "000000" if code != "000000" else "111111"}, format="json"
            ).data["error"]
            == "invalid_code"
        )
        response = session_client.post(f"{BASE}whatsapp/verify/", {"code": code}, format="json")
        assert response.status_code == 200 and response.data["linked"] is True
        assert response.data["address"] == "•••• 8888"

    def test_rejects_invalid_phone_and_fast_resend(self, session_client):
        assert self.send_code(session_client, "12345")[0].data["error"] == "invalid_phone"
        self.send_code(session_client)
        assert self.send_code(session_client)[0].status_code == 429

    def test_failed_send_allows_immediate_retry(self, session_client):
        with patch(f"{VIEW}.whatsapp_send", side_effect=ChannelError("ConnectionError")):
            response = session_client.post(f"{BASE}whatsapp/link/", {"phone": "+5511999998888"}, format="json")
        assert response.data["error"] == "ConnectionError"
        assert self.send_code(session_client)[0].data == {"sent": True}

    def test_limits_code_attempts(self, session_client):
        self.send_code(session_client)
        for _ in range(5):
            session_client.post(f"{BASE}whatsapp/verify/", {"code": "bad"}, format="json")
        assert session_client.post(f"{BASE}whatsapp/verify/", {"code": "bad"}, format="json").status_code == 429


@pytest.mark.contract
@pytest.mark.django_db
class TestConsentAndPreferences:
    def test_consent_requires_link_and_is_revocable(self, session_client, create_user):
        assert session_client.patch(f"{BASE}telegram/", {"enabled": True}, format="json").data["error"] == "not_linked"

        UserNotificationChannel.objects.filter(user=create_user, channel="telegram").update(
            address="1", verified_at="2026-01-01T00:00Z"
        )
        response = session_client.patch(f"{BASE}telegram/", {"enabled": True, "events": ["comment"]}, format="json")
        assert response.data["enabled"] is True and response.data["consented_at"] is not None
        assert response.data["events"] == ["comment"]

        # Events outside the admin policy are refused.
        assert (
            session_client.patch(f"{BASE}telegram/", {"events": ["issue_completed"]}, format="json").status_code == 400
        )

        response = session_client.patch(f"{BASE}telegram/", {"enabled": False}, format="json")
        assert response.data["enabled"] is False and response.data["consented_at"] is None

        assert session_client.delete(f"{BASE}telegram/").status_code == 204
        channels = session_client.get(BASE).data["channels"]
        assert [c["linked"] for c in channels if c["channel"] == "telegram"] == [False]

    def test_get_never_exposes_full_address(self, session_client, create_user):
        session_client.get(BASE)
        UserNotificationChannel.objects.filter(user=create_user, channel="whatsapp").update(address="+5511999998888")
        assert "999998888" not in session_client.get(BASE).content.decode()
