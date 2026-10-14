# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Notification channel utilities for Telegram and Evolution API (WhatsApp)."""

import html
import re

import requests
from django.utils.html import strip_tags
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


def telegram_send(token, chat_id, text, html=False):
    """Send a message and return the message_id string."""
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if html:
        payload["parse_mode"] = "HTML"
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


T = {
    "pt": {
        "someone": "Alguém",
        "state": "{actor} alterou o estado: {old} → {new}",
        "completed": "{actor} concluiu o item ✅",
        "priority": "{actor} alterou a prioridade: {old} → {new}",
        "assigned": "{actor} atribuiu a {new}",
        "unassigned": "{actor} removeu {old} dos responsáveis",
        "label_added": "{actor} adicionou o rótulo {new}",
        "label_removed": "{actor} removeu o rótulo {old}",
        "name": "{actor} renomeou o item: {old} → {new}",
        "description": "{actor} atualizou a descrição",
        "start_date": "{actor} alterou a data de início: {old} → {new}",
        "target_date": "{actor} alterou o prazo: {old} → {new}",
        "parent": "{actor} alterou o item pai para {new}",
        "cycles": "{actor} moveu para o ciclo {new}",
        "modules": "{actor} adicionou ao módulo {new}",
        "estimate": "{actor} alterou a estimativa: {old} → {new}",
        "comment": "{actor} comentou:",
        "mention": "{actor} mencionou você",
        "attachment": "{actor} adicionou um anexo",
        "link": "{actor} adicionou um link",
        "archived": "{actor} arquivou o item",
        "generic": "{actor} atualizou {field}",
        "open": "Abrir no Plane",
        "project": "Projeto",
    },
    "en": {
        "someone": "Someone",
        "state": "{actor} changed the state: {old} → {new}",
        "completed": "{actor} completed the item ✅",
        "priority": "{actor} changed the priority: {old} → {new}",
        "assigned": "{actor} assigned {new}",
        "unassigned": "{actor} removed {old} from assignees",
        "label_added": "{actor} added the label {new}",
        "label_removed": "{actor} removed the label {old}",
        "name": "{actor} renamed the item: {old} → {new}",
        "description": "{actor} updated the description",
        "start_date": "{actor} changed the start date: {old} → {new}",
        "target_date": "{actor} changed the due date: {old} → {new}",
        "parent": "{actor} set the parent to {new}",
        "cycles": "{actor} moved it to cycle {new}",
        "modules": "{actor} added it to module {new}",
        "estimate": "{actor} changed the estimate: {old} → {new}",
        "comment": "{actor} commented:",
        "mention": "{actor} mentioned you",
        "attachment": "{actor} added an attachment",
        "link": "{actor} added a link",
        "archived": "{actor} archived the item",
        "generic": "{actor} updated {field}",
        "open": "Open in Plane",
        "project": "Project",
    },
}

PRIORITY = {
    "pt": {"urgent": "Urgente", "high": "Alta", "medium": "Média", "low": "Baixa", "none": "Nenhuma"},
    "en": {"urgent": "Urgent", "high": "High", "medium": "Medium", "low": "Low", "none": "None"},
}


def _clean(v):
    s = str(v).strip()
    if s in ("None", "null", ""):
        return ""
    return s


def _fmt_date(v):
    s = _clean(v)
    if not s:
        return "—"
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        parts = s[:10].split("-")
        return f"{parts[2]}/{parts[1]}/{parts[0]}"
    return s


def _excerpt(html_text, limit=300):
    s = strip_tags(html_text)
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > limit:
        s = s[:limit] + "…"
    return s


def _lang(notification):
    try:
        profile = notification.receiver.profile
        raw = getattr(profile, "language", "en") or "en"
        if isinstance(raw, str) and raw.startswith("pt"):
            return "pt"
        return "en"
    except Exception:
        return "en"


def _actor(notification):
    u = getattr(notification, "triggered_by", None)
    if u is None:
        lang = _lang(notification)
        return T[lang]["someone"]
    first = getattr(u, "first_name", "") or ""
    last = getattr(u, "last_name", "") or ""
    name = f"{first} {last}".strip()
    if not name:
        name = getattr(u, "display_name", "Alguém") or "Alguém"
    return name


# _b/_i wrap every dynamic value, so they escape for Telegram's HTML parse mode:
# a "<" in a user, state or item name would otherwise make Telegram reject the message.
def _b(text, channel):
    if channel == "whatsapp":
        return f"*{text}*"
    return f"<b>{html.escape(text)}</b>"


def _i(text, channel):
    if channel == "whatsapp":
        return f"_{text}_"
    return f"<i>{html.escape(text)}</i>"


def _esc(text, channel):
    if channel == "telegram":
        return html.escape(text)
    return text


def _fmt_val(v, channel):
    s = _clean(v)
    if not s:
        return "—"
    return _i(s, channel)


def build_message(notification, web_url, channel="telegram"):
    """Build a formatted notification message for the given channel."""
    lang = _lang(notification)
    t = T[lang]
    actor = _b(_actor(notification), channel)
    data = getattr(notification, "data", {})
    issue = data.get("issue", {})
    issue_activity = data.get("issue_activity", {})
    sender = getattr(notification, "sender", "")
    workspace = getattr(notification, "workspace", None)
    project = getattr(notification, "project", None)

    identifier = _clean(issue.get("identifier", ""))
    sequence_id = _clean(issue.get("sequence_id", ""))
    name = _clean(issue.get("name", ""))
    field = _clean(issue_activity.get("field", ""))
    old_value = issue_activity.get("old_value", "")
    new_value = issue_activity.get("new_value", "")
    state_group = issue.get("state_group", "")

    # Build title line
    title = _b(f"{identifier}-{sequence_id} · {name}", channel)

    # Determine action key and format
    if "mentioned" in sender:
        key = "mention"
        action = t[key].format(actor=actor)
    elif field == "state" and state_group == "completed":
        key = "completed"
        action = t[key].format(actor=actor)
    elif field == "state":
        key = "state"
        old_s = _fmt_val(old_value, channel)
        new_s = _fmt_val(new_value, channel)
        action = t[key].format(actor=actor, old=old_s, new=new_s)
    elif field == "priority":
        key = "priority"
        old_raw = _clean(old_value)
        new_raw = _clean(new_value)
        old_map = PRIORITY.get(lang, {})
        old_s = old_map.get(old_raw, old_raw) if old_raw else "—"
        new_s = old_map.get(new_raw, new_raw) if new_raw else "—"
        old_s = _i(old_s, channel)
        new_s = _i(new_s, channel)
        action = t[key].format(actor=actor, old=old_s, new=new_s)
    elif field == "assignees":
        key = "assigned" if new_value else "unassigned"
        old_s = _fmt_val(old_value, channel)
        new_s = _fmt_val(new_value, channel)
        action = t[key].format(actor=actor, old=old_s, new=new_s)
    elif field == "labels":
        key = "label_added" if new_value else "label_removed"
        old_s = _fmt_val(old_value, channel)
        new_s = _fmt_val(new_value, channel)
        action = t[key].format(actor=actor, old=old_s, new=new_s)
    elif field == "name":
        key = "name"
        old_s = _fmt_val(old_value, channel)
        new_s = _fmt_val(new_value, channel)
        action = t[key].format(actor=actor, old=old_s, new=new_s)
    elif field == "description":
        key = "description"
        action = t[key].format(actor=actor)
    elif field == "start_date":
        key = "start_date"
        old_s = _fmt_val(_fmt_date(old_value), channel)
        new_s = _fmt_val(_fmt_date(new_value), channel)
        action = t[key].format(actor=actor, old=old_s, new=new_s)
    elif field == "target_date":
        key = "target_date"
        old_s = _fmt_val(_fmt_date(old_value), channel)
        new_s = _fmt_val(_fmt_date(new_value), channel)
        action = t[key].format(actor=actor, old=old_s, new=new_s)
    elif field == "parent":
        key = "parent"
        new_s = _fmt_val(new_value, channel)
        action = t[key].format(actor=actor, new=new_s)
    elif field == "cycles":
        key = "cycles"
        new_s = _fmt_val(new_value, channel)
        action = t[key].format(actor=actor, new=new_s)
    elif field == "modules":
        key = "modules"
        new_s = _fmt_val(new_value, channel)
        action = t[key].format(actor=actor, new=new_s)
    elif field.startswith("estimate"):
        key = "estimate"
        old_s = _fmt_val(old_value, channel)
        new_s = _fmt_val(new_value, channel)
        action = t[key].format(actor=actor, old=old_s, new=new_s)
    elif field == "comment":
        key = "comment"
        action = t[key].format(actor=actor)
    elif field == "attachment":
        key = "attachment"
        action = t[key].format(actor=actor)
    elif field == "link":
        key = "link"
        action = t[key].format(actor=actor)
    elif field == "archived_at":
        key = "archived"
        action = t[key].format(actor=actor)
    else:
        key = "generic"
        field_label = _clean(field)
        action = t[key].format(actor=actor, field=_esc(field_label, channel))

    # Build parts
    parts = [title, action]

    # Comment excerpt
    if field == "comment" and new_value:
        excerpt_text = _excerpt(new_value)
        if channel == "telegram":
            parts.append(f"<blockquote>{_esc(excerpt_text, channel)}</blockquote>")
        else:
            parts.append(f"> {excerpt_text}")

    # Project
    if project and project.name:
        parts.append(f"📁 {_esc(project.name, channel)}")

    # Link
    if workspace and identifier and sequence_id:
        url = f"{web_url.rstrip('/')}/{workspace.slug}/browse/{identifier}-{sequence_id}/"
        if channel == "telegram":
            link = f'<a href="{_esc(url, channel)}">{t["open"]}</a>'
        else:
            link = f"🔗 {url}"
        parts.append(link)

    message = "\n".join(parts)

    # Cut excerpt if over 1500 chars (don't cut the link)
    if len(message) > 1500 and field == "comment" and new_value:
        # Rebuild without comment excerpt to find the cutoff point
        base_parts = [title, action]
        if project and project.name:
            base_parts.append(f"📁 {_esc(project.name, channel)}")
        if workspace and identifier and sequence_id:
            url = f"{web_url.rstrip('/')}/{workspace.slug}/browse/{identifier}-{sequence_id}/"
            if channel == "telegram":
                link = f'<a href="{_esc(url, channel)}">{t["open"]}</a>'
            else:
                link = f"🔗 {url}"
            base_parts.append(link)
        base_len = len("\n".join(base_parts)) + 3  # +3 for "\n> "
        if channel == "telegram":
            base_len += 2  # for "<blockquote>"
        avail = 1500 - base_len
        if avail > 0:
            short = _excerpt(new_value, avail)
            if channel == "telegram":
                parts = base_parts + [f"<blockquote>{_esc(short, channel)}</blockquote>"]
            else:
                parts = base_parts + [f"> {short}"]
        else:
            parts = base_parts

    return message
