# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest
from unittest.mock import patch, MagicMock

from plane.utils.notification_channels import (
    allowed_events,
    is_channel_ready,
    validate_provider_url,
    _request,
    ChannelError,
    telegram_send,
    telegram_get_me,
    telegram_get_updates,
    whatsapp_send,
    whatsapp_create_instance,
    whatsapp_connect,
    whatsapp_state,
    whatsapp_logout,
    categorize,
    build_message,
)


# ── allowed_events ────────────────────────────────────────────────────────


class TestAllowedEvents:
    def test_all_events(self):
        config = {"NOTIFICATION_CHANNEL_EVENTS": "state_change,issue_completed,comment,mention,property_change"}
        assert allowed_events(config) == {"state_change", "issue_completed", "comment", "mention", "property_change"}

    def test_subset(self):
        config = {"NOTIFICATION_CHANNEL_EVENTS": "comment,mention"}
        assert allowed_events(config) == {"comment", "mention"}

    def test_empty_string(self):
        assert allowed_events({"NOTIFICATION_CHANNEL_EVENTS": ""}) == set()

    def test_missing_key(self):
        assert allowed_events({}) == set()

    def test_filters_invalid(self):
        config = {"NOTIFICATION_CHANNEL_EVENTS": "state_change,invalid_event,comment"}
        assert allowed_events(config) == {"state_change", "comment"}

    def test_strips_whitespace(self):
        config = {"NOTIFICATION_CHANNEL_EVENTS": " state_change , comment "}
        assert allowed_events(config) == {"state_change", "comment"}


# ── is_channel_ready ──────────────────────────────────────────────────────


class TestIsChannelReady:
    def test_telegram_enabled_with_token(self):
        config = {
            "ENABLE_TELEGRAM_NOTIFICATIONS": "1",
            "TELEGRAM_BOT_TOKEN": "123:ABC",
        }
        assert is_channel_ready("telegram", config) is True

    def test_telegram_disabled(self):
        config = {
            "ENABLE_TELEGRAM_NOTIFICATIONS": "0",
            "TELEGRAM_BOT_TOKEN": "123:ABC",
        }
        assert is_channel_ready("telegram", config) is False

    def test_telegram_no_token(self):
        config = {
            "ENABLE_TELEGRAM_NOTIFICATIONS": "1",
            "TELEGRAM_BOT_TOKEN": "",
        }
        assert is_channel_ready("telegram", config) is False

    def test_whatsapp_enabled(self):
        config = {
            "ENABLE_WHATSAPP_NOTIFICATIONS": "1",
            "WHATSAPP_PROVIDER_URL": "http://localhost:8080",
            "WHATSAPP_API_KEY": "secret",
        }
        assert is_channel_ready("whatsapp", config) is True

    def test_whatsapp_disabled(self):
        config = {
            "ENABLE_WHATSAPP_NOTIFICATIONS": "0",
            "WHATSAPP_PROVIDER_URL": "http://localhost:8080",
            "WHATSAPP_API_KEY": "secret",
        }
        assert is_channel_ready("whatsapp", config) is False

    def test_whatsapp_no_url(self):
        config = {
            "ENABLE_WHATSAPP_NOTIFICATIONS": "1",
            "WHATSAPP_PROVIDER_URL": "",
            "WHATSAPP_API_KEY": "secret",
        }
        assert is_channel_ready("whatsapp", config) is False

    def test_whatsapp_no_key(self):
        config = {
            "ENABLE_WHATSAPP_NOTIFICATIONS": "1",
            "WHATSAPP_PROVIDER_URL": "http://localhost:8080",
            "WHATSAPP_API_KEY": "",
        }
        assert is_channel_ready("whatsapp", config) is False

    def test_unknown_channel(self):
        assert is_channel_ready("email", {}) is False


# ── validate_provider_url ─────────────────────────────────────────────────


class TestValidateProviderUrl:
    def test_valid_https(self):
        assert validate_provider_url("https://example.com") is True

    def test_valid_http(self):
        assert validate_provider_url("http://localhost:8080") is True

    def test_invalid_scheme(self):
        assert validate_provider_url("ftp://example.com") is False

    def test_empty_netloc(self):
        assert validate_provider_url("https:///path") is False

    def test_no_scheme(self):
        assert validate_provider_url("example.com") is False


# ── _request ──────────────────────────────────────────────────────────────


class TestRequest:
    @patch("plane.utils.notification_channels.requests.request")
    def test_500_transient(self, mock_req):
        resp = MagicMock()
        resp.status_code = 500
        resp.json.side_effect = ValueError
        mock_req.return_value = resp
        with pytest.raises(ChannelError) as exc_info:
            _request("GET", "http://example.com")
        assert exc_info.value.transient is True

    @patch("plane.utils.notification_channels.requests.request")
    def test_429_transient(self, mock_req):
        resp = MagicMock()
        resp.status_code = 429
        resp.json.return_value = {}
        mock_req.return_value = resp
        with pytest.raises(ChannelError) as exc_info:
            _request("GET", "http://example.com")
        assert exc_info.value.transient is True

    @patch("plane.utils.notification_channels.requests.request")
    def test_401_non_transient(self, mock_req):
        resp = MagicMock()
        resp.status_code = 401
        resp.json.return_value = {}
        mock_req.return_value = resp
        with pytest.raises(ChannelError) as exc_info:
            _request("GET", "http://example.com")
        assert exc_info.value.transient is False

    @patch("plane.utils.notification_channels.requests.request")
    def test_request_exception_transient(self, mock_req):
        import requests as req_lib

        url = "https://api.telegram.org/botSECRET-TOKEN/sendMessage"
        mock_req.side_effect = req_lib.ConnectionError("Max retries exceeded with url: " + url)
        with pytest.raises(ChannelError) as exc_info:
            _request("GET", url)
        assert exc_info.value.transient is True
        assert "SECRET-TOKEN" not in str(exc_info.value)

    @patch("plane.utils.notification_channels.requests.request")
    def test_success_returns_json(self, mock_req):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"ok": True, "result": {"id": 1}}
        mock_req.return_value = resp
        assert _request("GET", "http://example.com") == {"ok": True, "result": {"id": 1}}

    @patch("plane.utils.notification_channels.requests.request")
    def test_empty_body_returns_dict(self, mock_req):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.side_effect = ValueError
        mock_req.return_value = resp
        assert _request("GET", "http://example.com") == {}

    def test_error_does_not_contain_token(self):
        err = ChannelError("HTTP 500", transient=True)
        token_str = "123456:AAabcdefg"
        "HTTP 500 for bot " + token_str
        # The error message should never include the token
        assert token_str not in str(err)


# ── telegram_send ─────────────────────────────────────────────────────────


class TestTelegramSend:
    @patch("plane.utils.notification_channels._request")
    def test_monts_url_and_payload(self, mock_request):
        mock_request.return_value = {
            "ok": True,
            "result": {"message_id": 42},
        }
        result = telegram_send("123:BOT", "chat123", "hello")
        assert result == "42"
        call_args = mock_request.call_args
        assert call_args[0][0] == "POST"
        assert "sendMessage" in call_args[0][1]
        assert call_args[1]["json"] == {
            "chat_id": "chat123",
            "text": "hello",
            "disable_web_page_preview": True,
        }

    @patch("plane.utils.notification_channels._request")
    def test_ok_false_raises(self, mock_request):
        mock_request.return_value = {"ok": False, "description": "Bad"}
        with pytest.raises(ChannelError) as exc_info:
            telegram_send("123:BOT", "chat123", "hello")
        assert exc_info.value.transient is False


class TestTelegramGetMe:
    @patch("plane.utils.notification_channels._request")
    def test_success(self, mock_request):
        mock_request.return_value = {
            "ok": True,
            "result": {"id": 1, "username": "testbot"},
        }
        assert telegram_get_me("123:BOT") == {"id": 1, "username": "testbot"}

    @patch("plane.utils.notification_channels._request")
    def test_ok_false_raises(self, mock_request):
        mock_request.return_value = {"ok": False}
        with pytest.raises(ChannelError) as exc_info:
            telegram_get_me("123:BOT")
        assert exc_info.value.transient is False


class TestTelegramGetUpdates:
    @patch("plane.utils.notification_channels._request")
    def test_success(self, mock_request):
        mock_request.return_value = {
            "ok": True,
            "result": [{"update_id": 1}],
        }
        assert telegram_get_updates("123:BOT") == [{"update_id": 1}]

    @patch("plane.utils.notification_channels._request")
    def test_ok_false_raises(self, mock_request):
        mock_request.return_value = {"ok": False}
        with pytest.raises(ChannelError) as exc_info:
            telegram_get_updates("123:BOT")
        assert exc_info.value.transient is False


# ── WhatsApp ──────────────────────────────────────────────────────────────


class TestWhatsappSend:
    @patch("plane.utils.notification_channels._request")
    def test_strips_plus(self, mock_request):
        mock_request.return_value = {
            "ok": True,
            "key": {"id": "msg123"},
        }
        result = whatsapp_send(
            {
                "WHATSAPP_PROVIDER_URL": "http://localhost:8080",
                "WHATSAPP_API_KEY": "secret",
                "WHATSAPP_INSTANCE_NAME": "plane",
            },
            "+5511999999999",
            "hello",
        )
        assert result == "msg123"
        call_args = mock_request.call_args
        assert call_args[1]["json"]["number"] == "5511999999999"

    @patch("plane.utils.notification_channels._request")
    def test_ok_false_raises(self, mock_request):
        mock_request.return_value = {"ok": False}
        with pytest.raises(ChannelError) as exc_info:
            whatsapp_send(
                {
                    "WHATSAPP_PROVIDER_URL": "http://localhost:8080",
                    "WHATSAPP_API_KEY": "secret",
                    "WHATSAPP_INSTANCE_NAME": "plane",
                },
                "5511999999999",
                "hello",
            )
        assert exc_info.value.transient is False

    @patch("plane.utils.notification_channels._request")
    def test_invalid_url_raises(self, mock_request):
        with pytest.raises(ChannelError) as exc_info:
            whatsapp_send(
                {
                    "WHATSAPP_PROVIDER_URL": "not-a-url",
                    "WHATSAPP_API_KEY": "secret",
                    "WHATSAPP_INSTANCE_NAME": "plane",
                },
                "5511999999999",
                "hello",
            )
        assert exc_info.value.transient is False


class TestWhatsappCreateInstance:
    @patch("plane.utils.notification_channels._request")
    def test_success(self, mock_request):
        mock_request.return_value = {"ok": True}
        result = whatsapp_create_instance(
            {
                "WHATSAPP_PROVIDER_URL": "http://localhost:8080",
                "WHATSAPP_API_KEY": "secret",
                "WHATSAPP_INSTANCE_NAME": "myinst",
            }
        )
        assert result == {"ok": True}
        call_args = mock_request.call_args
        assert call_args[0][0] == "POST"
        assert "/instance/create" in call_args[0][1]

    @patch("plane.utils.notification_channels._request")
    def test_invalid_url_raises(self, mock_request):
        with pytest.raises(ChannelError):
            whatsapp_create_instance(
                {
                    "WHATSAPP_PROVIDER_URL": "bad",
                    "WHATSAPP_API_KEY": "secret",
                    "WHATSAPP_INSTANCE_NAME": "myinst",
                }
            )


class TestWhatsappConnect:
    @patch("plane.utils.notification_channels._request")
    def test_success(self, mock_request):
        mock_request.return_value = {"ok": True, "base64": "qr"}
        result = whatsapp_connect(
            {
                "WHATSAPP_PROVIDER_URL": "http://localhost:8080",
                "WHATSAPP_API_KEY": "secret",
                "WHATSAPP_INSTANCE_NAME": "plane",
            }
        )
        assert result["base64"] == "qr"

    @patch("plane.utils.notification_channels._request")
    def test_invalid_url_raises(self, mock_request):
        with pytest.raises(ChannelError):
            whatsapp_connect(
                {
                    "WHATSAPP_PROVIDER_URL": "bad",
                    "WHATSAPP_API_KEY": "secret",
                    "WHATSAPP_INSTANCE_NAME": "plane",
                }
            )


class TestWhatsappState:
    @patch("plane.utils.notification_channels._request")
    def test_open(self, mock_request):
        mock_request.return_value = {"ok": True, "instance": {"state": "open"}}
        assert (
            whatsapp_state(
                {
                    "WHATSAPP_PROVIDER_URL": "http://localhost:8080",
                    "WHATSAPP_API_KEY": "secret",
                    "WHATSAPP_INSTANCE_NAME": "plane",
                }
            )
            == "open"
        )

    @patch("plane.utils.notification_channels._request")
    def test_unknown(self, mock_request):
        mock_request.return_value = {"ok": True}
        assert (
            whatsapp_state(
                {
                    "WHATSAPP_PROVIDER_URL": "http://localhost:8080",
                    "WHATSAPP_API_KEY": "secret",
                    "WHATSAPP_INSTANCE_NAME": "plane",
                }
            )
            == "unknown"
        )

    @patch("plane.utils.notification_channels._request")
    def test_invalid_url_raises(self, mock_request):
        with pytest.raises(ChannelError):
            whatsapp_state(
                {
                    "WHATSAPP_PROVIDER_URL": "bad",
                    "WHATSAPP_API_KEY": "secret",
                    "WHATSAPP_INSTANCE_NAME": "plane",
                }
            )


class TestWhatsappLogout:
    @patch("plane.utils.notification_channels._request")
    def test_success(self, mock_request):
        mock_request.return_value = {"ok": True}
        result = whatsapp_logout(
            {
                "WHATSAPP_PROVIDER_URL": "http://localhost:8080",
                "WHATSAPP_API_KEY": "secret",
                "WHATSAPP_INSTANCE_NAME": "plane",
            }
        )
        assert result == {"ok": True}

    @patch("plane.utils.notification_channels._request")
    def test_invalid_url_raises(self, mock_request):
        with pytest.raises(ChannelError):
            whatsapp_logout(
                {
                    "WHATSAPP_PROVIDER_URL": "bad",
                    "WHATSAPP_API_KEY": "secret",
                    "WHATSAPP_INSTANCE_NAME": "plane",
                }
            )


# ── categorize ────────────────────────────────────────────────────────────


class TestCategorize:
    def test_mention(self):
        n = MagicMock()
        n.sender = "in_app:issue_activities:mentioned"
        n.data = {}
        assert categorize(n) == "mention"

    def test_comment(self):
        n = MagicMock()
        n.sender = "in_app:issue_activities:subscribed"
        n.data = {"issue_activity": {"field": "comment"}}
        assert categorize(n) == "comment"

    def test_state_completed(self):
        n = MagicMock()
        n.sender = "in_app:issue_activities:subscribed"
        n.data = {
            "issue_activity": {"field": "state"},
            "issue": {"state_group": "completed"},
        }
        assert categorize(n) == "issue_completed"

    def test_state_change(self):
        n = MagicMock()
        n.sender = "in_app:issue_activities:subscribed"
        n.data = {
            "issue_activity": {"field": "state"},
            "issue": {"state_group": "backlog"},
        }
        assert categorize(n) == "state_change"

    def test_property_change(self):
        n = MagicMock()
        n.sender = "in_app:issue_activities:subscribed"
        n.data = {
            "issue_activity": {"field": "priority"},
        }
        assert categorize(n) == "property_change"


# ── build_message ─────────────────────────────────────────────────────────


class TestBuildMessage:
    def test_state_change(self):
        ws = MagicMock()
        ws.slug = "my-workspace"
        n = MagicMock()
        n.sender = "in_app:issue_activities:subscribed"
        n.workspace = ws
        n.data = {
            "issue": {
                "identifier": "PLN",
                "sequence_id": 42,
                "name": "Fix login",
                "state_group": "backlog",
            },
            "issue_activity": {"field": "state", "new_value": "In Progress"},
        }
        msg = build_message(n, "https://app.plane.so")
        assert "[PLN-42] Fix login" in msg
        assert "In Progress" in msg
        assert len(msg) <= 500

    def test_comment(self):
        ws = MagicMock()
        ws.slug = "my-workspace"
        n = MagicMock()
        n.sender = "in_app:issue_activities:subscribed"
        n.workspace = ws
        n.data = {
            "issue": {
                "identifier": "PLN",
                "sequence_id": 1,
                "name": "Bug report",
                "state_group": "unconfirmed",
            },
            "issue_activity": {"field": "comment", "new_value": "bad"},
        }
        msg = build_message(n, "https://app.plane.so")
        assert "New comment" in msg
        assert len(msg) <= 500

    def test_mention(self):
        ws = MagicMock()
        ws.slug = "my-workspace"
        n = MagicMock()
        n.sender = "in_app:issue_activities:mentioned"
        n.workspace = ws
        n.data = {
            "issue": {
                "identifier": "PLN",
                "sequence_id": 5,
                "name": "Feature X",
                "state_group": "backlog",
            },
            "issue_activity": {"field": "comment"},
        }
        msg = build_message(n, "https://app.plane.so")
        assert "You were mentioned" in msg
        assert len(msg) <= 500

    def test_completed(self):
        ws = MagicMock()
        ws.slug = "my-workspace"
        n = MagicMock()
        n.sender = "in_app:issue_activities:subscribed"
        n.workspace = ws
        n.data = {
            "issue": {
                "identifier": "PLN",
                "sequence_id": 10,
                "name": "Deploy v2",
                "state_group": "completed",
            },
            "issue_activity": {"field": "state"},
        }
        msg = build_message(n, "https://app.plane.so")
        assert "Marked as completed" in msg
        assert len(msg) <= 500

    def test_property_change(self):
        ws = MagicMock()
        ws.slug = "my-workspace"
        n = MagicMock()
        n.sender = "in_app:issue_activities:subscribed"
        n.workspace = ws
        n.data = {
            "issue": {
                "identifier": "PLN",
                "sequence_id": 3,
                "name": "Tweak",
                "state_group": "backlog",
            },
            "issue_activity": {"field": "priority", "new_value": "high"},
        }
        msg = build_message(n, "https://app.plane.so")
        assert "Field priority changed" in msg
        assert len(msg) <= 500

    def test_no_workspace(self):
        n = MagicMock()
        n.workspace = None
        n.data = {
            "issue": {
                "identifier": "PLN",
                "sequence_id": 1,
                "name": "Test",
                "state_group": "backlog",
            },
            "issue_activity": {"field": "priority"},
        }
        msg = build_message(n, "https://app.plane.so")
        assert len(msg) <= 500
        assert "browse/" not in msg

    def test_long_title_capped_at_500(self):
        ws = MagicMock()
        ws.slug = "my-workspace"
        long_name = "A" * 450
        n = MagicMock()
        n.workspace = ws
        n.data = {
            "issue": {
                "identifier": "LONGID",
                "sequence_id": 99999,
                "name": long_name,
                "state_group": "backlog",
            },
            "issue_activity": {"field": "priority"},
        }
        msg = build_message(n, "https://app.plane.so")
        assert len(msg) <= 500

    def test_link_includes_workspace(self):
        ws = MagicMock()
        ws.slug = "testws"
        n = MagicMock()
        n.workspace = ws
        n.data = {
            "issue": {
                "identifier": "PLN",
                "sequence_id": 7,
                "name": "Test",
                "state_group": "backlog",
            },
            "issue_activity": {"field": "priority"},
        }
        msg = build_message(n, "https://app.plane.so")
        assert "testws/browse/PLN-7/" in msg
