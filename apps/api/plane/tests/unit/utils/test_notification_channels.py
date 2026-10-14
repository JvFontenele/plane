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
    def test_html_true_adds_parse_mode(self, mock_request):
        mock_request.return_value = {
            "ok": True,
            "result": {"message_id": 42},
        }
        telegram_send("123:BOT", "chat123", "<b>hello</b>", html=True)
        call_args = mock_request.call_args
        assert call_args[1]["json"]["parse_mode"] == "HTML"

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
    @staticmethod
    def _make_notification(
        receiver_lang="pt",
        triggered_by_first="Ana",
        triggered_by_last="Lima",
        project_name=None,
        workspace_slug="ws",
        identifier="PRJ",
        sequence_id=5,
        name="Test Item",
        field="state",
        old_value="",
        new_value="Doing",
        state_group="backlog",
        sender="in_app:issue_activities:subscribed",
    ):
        """Build a SimpleNamespace notification for testing."""
        from types import SimpleNamespace

        profile = SimpleNamespace(language=receiver_lang)
        receiver = SimpleNamespace(profile=profile)
        triggered = SimpleNamespace(
            first_name=triggered_by_first,
            last_name=triggered_by_last,
            display_name=f"{triggered_by_first} {triggered_by_last}".strip(),
        )
        workspace = SimpleNamespace(slug=workspace_slug)
        proj = SimpleNamespace(name=project_name) if project_name else None
        n = SimpleNamespace(
            receiver=receiver,
            triggered_by=triggered,
            workspace=workspace,
            project=proj,
            sender=sender,
            data={
                "issue": {
                    "identifier": identifier,
                    "sequence_id": sequence_id,
                    "name": name,
                    "state_group": state_group,
                },
                "issue_activity": {
                    "field": field,
                    "old_value": old_value,
                    "new_value": new_value,
                },
            },
        )
        return n

    def test_pt_state_change(self):
        n = self._make_notification(receiver_lang="pt", old_value="Todo", new_value="Doing")
        msg = build_message(n, "https://app.plane.so", "telegram")
        assert "<b>Ana Lima</b> alterou o estado" in msg
        assert "Todo" in msg
        assert "Doing" in msg
        assert "ws/browse/PRJ-5/" in msg

    def test_en_priority(self):
        n = self._make_notification(receiver_lang="en", field="priority", old_value="high", new_value="urgent")
        msg = build_message(n, "https://app.plane.so", "telegram")
        assert "changed the priority" in msg
        assert "Urgent" in msg
        assert "High" in msg

    def test_telegram_escapes_html(self):
        n = self._make_notification(name="<script>alert(1)</script>")
        msg = build_message(n, "https://app.plane.so", "telegram")
        assert "<script>" not in msg
        assert msg.startswith("<b>PRJ-5 · &lt;script&gt;")
        assert '<a href="' in msg

    def test_whatsapp_comment(self):
        n = self._make_notification(
            receiver_lang="pt",
            field="comment",
            new_value="<p>This is <b>bold</b> text</p>",
            triggered_by_first="",
            triggered_by_last="",
        )
        msg = build_message(n, "https://app.plane.so", "whatsapp")
        assert "> " in msg
        assert "<p>" not in msg
        assert "This is bold text" in msg

    def test_triggered_by_none(self):
        from types import SimpleNamespace

        profile = SimpleNamespace(language="pt")
        receiver = SimpleNamespace(profile=profile)
        n = SimpleNamespace(
            receiver=receiver,
            triggered_by=None,
            workspace=SimpleNamespace(slug="ws"),
            project=None,
            sender="in_app:issue_activities:subscribed",
            data={
                "issue": {"identifier": "PRJ", "sequence_id": 5, "name": "Test", "state_group": "backlog"},
                "issue_activity": {"field": "state", "old_value": "", "new_value": "Doing"},
            },
        )
        msg = build_message(n, "https://app.plane.so", "telegram")
        assert "Alguém" in msg

    def test_assignees_removed(self):
        n = self._make_notification(receiver_lang="pt", field="assignees", old_value="Ana", new_value="")
        msg = build_message(n, "https://app.plane.so", "telegram")
        assert "removeu" in msg
        assert "dos responsáveis" in msg
