# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Notification channel utilities for Telegram and Evolution API (WhatsApp)."""

import requests
from urllib.parse import urlparse

from plane.license.utils.instance_value import get_configuration_value


CHANNELS = ("telegram", "whatsapp")
EVENT_CATEGORIES = (
    "state_change",
    "issue_completed",
    "comment",
    "mention",
    "property_change",
)


class ChannelError(Exception):
    """Error raised by channel operations.

    Attributes:
        transient: True for retryable errors (network, 5xx, 429).
                    False for non-retryable errors (auth, 4xx).
    """

    def __init__(self, message, transient=True):
        self.transient = transient
        super().__init__(message)


def get_channel_config():
    """Return a dict of all notification channel configuration keys."""
    keys = [
        "ENABLE_TELEGRAM_NOTIFICATIONS",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_BOT_USERNAME",
        "ENABLE_WHATSAPP_NOTIFICATIONS",
        "WHATSAPP_PROVIDER_URL",
        "WHATSAPP_API_KEY",
        "WHATSAPP_INSTANCE_NAME",
        "NOTIFICATION_CHANNEL_EVENTS",
    ]
    defaults = {
        "ENABLE_TELEGRAM_NOTIFICATIONS": "0",
        "TELEGRAM_BOT_TOKEN": "",
        "TELEGRAM_BOT_USERNAME": "",
        "ENABLE_WHATSAPP_NOTIFICATIONS": "0",
        "WHATSAPP_PROVIDER_URL": "",
        "WHATSAPP_API_KEY": "",
        "WHATSAPP_INSTANCE_NAME": "plane",
        "NOTIFICATION_CHANNEL_EVENTS": "state_change,issue_completed,comment,mention,property_change",
    }
    values = get_configuration_value([{"key": k, "default": defaults[k]} for k in keys])
    return dict(zip(keys, values))


def allowed_events(config):
    """Return the set of event categories enabled in config."""
    raw = config.get("NOTIFICATION_CHANNEL_EVENTS", "")
    if not raw:
        return set()
    return {e.strip() for e in raw.split(",") if e.strip() in EVENT_CATEGORIES}


def is_channel_ready(channel, config):
    """Return True if the channel is enabled and has required credentials."""
    if channel == "telegram":
        return config.get("ENABLE_TELEGRAM_NOTIFICATIONS") == "1" and bool(config.get("TELEGRAM_BOT_TOKEN"))
    if channel == "whatsapp":
        return (
            config.get("ENABLE_WHATSAPP_NOTIFICATIONS") == "1"
            and bool(config.get("WHATSAPP_PROVIDER_URL"))
            and bool(config.get("WHATSAPP_API_KEY"))
        )
    return False


def _request(method, url, *, headers=None, json=None, params=None):
    """Send an HTTP request. Raise ChannelError on failure."""
    try:
        resp = requests.request(
            method,
            url,
            headers=headers,
            json=json,
            params=params,
            timeout=10,
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        # Never use str(exc): it embeds the URL, which contains the Telegram bot token.
        raise ChannelError(type(exc).__name__, transient=True) from exc

    status = resp.status_code
    if status >= 500 or status == 429:
        raise ChannelError("HTTP " + str(status), transient=True)
    if status >= 400:
        raise ChannelError("HTTP " + str(status), transient=False)

    try:
        return resp.json()
    except (ValueError, KeyError):
        return {}


TELEGRAM_API = "https://api.telegram.org/bot{token}/"


def _telegram_base(token):
    return TELEGRAM_API.format(token=token)


def telegram_get_me(token):
    """Return the result of getMe."""
    resp = _request("GET", _telegram_base(token) + "getMe")
    if not resp.get("ok"):
        raise ChannelError("Telegram getMe failed", transient=False)
    return resp["result"]


def telegram_send(token, chat_id, text):
    """Send a message and return the message_id string."""
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    resp = _request(
        "POST",
        _telegram_base(token) + "sendMessage",
        json=payload,
    )
    if not resp.get("ok"):
        raise ChannelError("Telegram sendMessage failed", transient=False)
    return str(resp["result"]["message_id"])


def telegram_get_updates(token):
    """Return the result list from getUpdates."""
    resp = _request(
        "GET",
        _telegram_base(token) + "getUpdates",
        params={"allowed_updates": '["message"]'},
    )
    if not resp.get("ok"):
        raise ChannelError("Telegram getUpdates failed", transient=False)
    return resp["result"]


def validate_provider_url(url):
    """Return True if url has a valid http(s) scheme and netloc."""
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _whatsapp_base(config):
    return config["WHATSAPP_PROVIDER_URL"].rstrip("/")


def _whatsapp_headers(config):
    return {"apikey": config["WHATSAPP_API_KEY"]}


def _whatsapp_instance(config):
    return config.get("WHATSAPP_INSTANCE_NAME", "plane")


def _whatsapp_assert_ready(config):
    url = config["WHATSAPP_PROVIDER_URL"]
    if not validate_provider_url(url):
        raise ChannelError("Invalid provider URL", transient=False)


def whatsapp_create_instance(config):
    """Create a new WhatsApp instance via Evolution API."""
    _whatsapp_assert_ready(config)
    inst = _whatsapp_instance(config)
    resp = _request(
        "POST",
        _whatsapp_base(config) + "/instance/create",
        headers=_whatsapp_headers(config),
        json={
            "instanceName": inst,
            "integration": "WHATSAPP-BAILEYS",
            "qrcode": True,
        },
    )
    if not resp.get("ok", True):
        raise ChannelError("WhatsApp create instance failed", transient=False)
    return resp


def whatsapp_connect(config):
    """Connect to an existing instance; returns dict with QR or pairing info."""
    _whatsapp_assert_ready(config)
    inst = _whatsapp_instance(config)
    resp = _request(
        "GET",
        _whatsapp_base(config) + "/instance/connect/" + inst,
        headers=_whatsapp_headers(config),
    )
    if not resp.get("ok", True):
        raise ChannelError("WhatsApp connect failed", transient=False)
    return resp


def whatsapp_state(config):
    """Return the connection state string of the instance."""
    _whatsapp_assert_ready(config)
    inst = _whatsapp_instance(config)
    resp = _request(
        "GET",
        _whatsapp_base(config) + "/instance/connectionState/" + inst,
        headers=_whatsapp_headers(config),
    )
    if not resp.get("ok", True):
        raise ChannelError("WhatsApp state check failed", transient=False)
    return resp.get("instance", {}).get("state", "unknown")


def whatsapp_logout(config):
    """Log out (disconnect) the instance."""
    _whatsapp_assert_ready(config)
    inst = _whatsapp_instance(config)
    resp = _request(
        "DELETE",
        _whatsapp_base(config) + "/instance/logout/" + inst,
        headers=_whatsapp_headers(config),
    )
    if not resp.get("ok", True):
        raise ChannelError("WhatsApp logout failed", transient=False)
    return resp


def whatsapp_send(config, number, text):
    """Send a WhatsApp message. Returns the message ID string."""
    _whatsapp_assert_ready(config)
    inst = _whatsapp_instance(config)
    clean_number = number.lstrip("+")
    resp = _request(
        "POST",
        _whatsapp_base(config) + "/message/sendText/" + inst,
        headers=_whatsapp_headers(config),
        json={"number": clean_number, "text": text},
    )
    if not resp.get("ok", True):
        raise ChannelError("WhatsApp send failed", transient=False)
    return resp.get("key", {}).get("id", "")


def categorize(notification):
    """Classify a notification into one of the EVENT_CATEGORIES."""
    sender = getattr(notification, "sender", "")
    data = getattr(notification, "data", {})
    issue_activity = data.get("issue_activity", {})
    issue = data.get("issue", {})

    if "mentioned" in sender:
        return "mention"

    field = issue_activity.get("field", "")

    if field == "comment":
        return "comment"

    if field == "state":
        state_group = issue.get("state_group", "")
        if state_group == "completed":
            return "issue_completed"
        return "state_change"

    return "property_change"


def build_message(notification, web_url):
    """Build a short notification message (max 500 chars)."""
    data = getattr(notification, "data", {})
    issue = data.get("issue", {})
    issue_activity = data.get("issue_activity", {})
    workspace = getattr(notification, "workspace", None)

    identifier = issue.get("identifier", "")
    sequence_id = issue.get("sequence_id", "")
    name = issue.get("name", "")
    new_value = issue_activity.get("new_value", "")
    field = issue_activity.get("field", "")

    if "mentioned" in getattr(notification, "sender", ""):
        description = "You were mentioned"
    elif field == "state":
        state_group = issue.get("state_group", "")
        if state_group == "completed":
            description = "Marked as completed"
        else:
            description = "State changed to " + str(new_value)
    elif field == "comment":
        description = "New comment"
    else:
        description = "Field " + field + " changed"

    title = "[" + identifier + "-" + str(sequence_id) + "] " + name
    if workspace:
        link = web_url + "/" + workspace.slug + "/browse/" + identifier + "-" + str(sequence_id) + "/"
    else:
        link = ""

    parts = [title, description]
    if link:
        parts.append(link)

    message = " ".join(parts)
    return message[:500]
