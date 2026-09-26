"""Minimal Telegram Bot API client (sendMessage / getUpdates) using the standard library."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

API_URL = "https://api.telegram.org/bot{token}/{method}"
MAX_LEN = 4000  # Telegram's limit is 4096 characters per message


class TelegramError(RuntimeError):
    pass


def _call(token: str, method: str, params: dict[str, Any]) -> Any:
    req = urllib.request.Request(
        API_URL.format(token=token, method=method),
        data=json.dumps(params).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise TelegramError(f"Telegram {method} failed ({e.code}): {detail}") from None
    except urllib.error.URLError as e:
        raise TelegramError(f"Cannot reach Telegram: {e.reason}") from None
    if not body.get("ok"):
        raise TelegramError(f"Telegram {method} failed: {body.get('description')}")
    return body["result"]


def split_message(text: str, limit: int = MAX_LEN) -> list[str]:
    chunks, current = [], ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:
            chunks.append(current + line[: limit - len(current)])
            line, current = line[limit - len(current):], ""
        if len(current) + len(line) > limit:
            chunks.append(current)
            current = ""
        current += line
    if current.strip():
        chunks.append(current)
    return chunks


def send_message(token: str, chat_id: str, text: str) -> None:
    for chunk in split_message(text):
        _call(token, "sendMessage", {"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True})


def find_chat_id(token: str) -> str | None:
    """Chat id of the latest message sent to the bot (the user must message it first)."""
    updates = _call(token, "getUpdates", {"timeout": 0})
    for update in reversed(updates):
        msg = update.get("message") or update.get("edited_message")
        if msg and "chat" in msg:
            return str(msg["chat"]["id"])
    return None


def configured() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def notify(text: str) -> bool:
    """Send if Telegram is configured; returns whether it was sent."""
    if not configured():
        return False
    send_message(os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"], text)
    return True
