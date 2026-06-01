from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request


TELEGRAM_API_ROOT = "https://api.telegram.org"
LAB_ROOT = Path(__file__).resolve().parents[1]


def _normalize_chat_id(chat_id: str | int) -> str | int:
    if isinstance(chat_id, int):
        return chat_id
    value = str(chat_id).strip()
    if not value:
        raise RuntimeError("Telegram chat_id must not be empty")
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


def _method_url(bot_token: str, method: str) -> str:
    token = bot_token.strip()
    if not token:
        raise RuntimeError("Telegram bot token is required")
    method_name = method.strip()
    if not method_name:
        raise RuntimeError("Telegram method name is required")
    return f"{TELEGRAM_API_ROOT}/bot{token}/{method_name}"


def _telegram_api_json(bot_token: str, method: str, payload: dict[str, Any]) -> Any:
    body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    req = request.Request(
        _method_url(bot_token, method),
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Telegram API HTTP {exc.code} ({method}): {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Telegram API network error ({method}): {exc}") from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Telegram API invalid JSON ({method}): {raw[:300]}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Telegram API unexpected response type ({method}): {type(parsed).__name__}")
    if not bool(parsed.get("ok", False)):
        raise RuntimeError(f"Telegram API returned ok=false ({method}): {parsed}")
    return parsed.get("result")


@dataclass
class TelegramSendResult:
    message_id: int
    chat_id: str | int
    date: int
    text: str
    raw_response: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "chat_id": self.chat_id,
            "date": self.date,
            "text": self.text,
            "raw_response": self.raw_response,
        }


def send_telegram_group_message(
    *,
    bot_token: str,
    chat_id: str | int,
    text: str,
    disable_notification: bool = False,
) -> TelegramSendResult:
    message_text = text.strip()
    if not message_text:
        raise RuntimeError("Telegram message text must not be empty")

    result = _telegram_api_json(
        bot_token,
        "sendMessage",
        {
            "chat_id": _normalize_chat_id(chat_id),
            "text": message_text,
            "disable_notification": bool(disable_notification),
            "disable_web_page_preview": True,
        },
    )
    if not isinstance(result, dict):
        raise RuntimeError(f"Telegram sendMessage returned unexpected result type: {type(result).__name__}")

    msg_id_raw = result.get("message_id")
    if not isinstance(msg_id_raw, int):
        raise RuntimeError(f"Telegram sendMessage missing integer message_id: {result}")

    chat_obj = result.get("chat", {})
    if isinstance(chat_obj, dict) and "id" in chat_obj:
        chat_value = chat_obj["id"]
    else:
        chat_value = _normalize_chat_id(chat_id)

    date_raw = result.get("date", 0)
    date_value = int(date_raw) if isinstance(date_raw, int) else 0
    text_value = str(result.get("text", message_text))

    return TelegramSendResult(
        message_id=msg_id_raw,
        chat_id=chat_value,
        date=date_value,
        text=text_value,
        raw_response=result,
    )


def _resolve_user_session(session: str, session_file: str):
    if session.strip():
        try:
            from telethon.sessions import StringSession
        except ImportError as exc:
            raise RuntimeError("Telethon is required for TELEGRAM_USER_SESSION. Install telethon.") from exc

        return StringSession(session.strip())

    raw_path = session_file.strip() or str(LAB_ROOT / ".telegram_benchmark.session")
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = LAB_ROOT.parent / path
    return str(path)


def _message_date_ts(value: Any) -> int:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return int(value.timestamp())
    return 0


def send_telegram_user_message(
    *,
    api_id: str | int,
    api_hash: str,
    chat_id: str | int,
    text: str,
    session: str = "",
    session_file: str = "",
) -> TelegramSendResult:
    message_text = text.strip()
    if not message_text:
        raise RuntimeError("Telegram message text must not be empty")
    api_hash_value = api_hash.strip()
    if not api_hash_value:
        raise RuntimeError("Telegram user api_hash is required")
    try:
        api_id_value = int(str(api_id).strip())
    except ValueError as exc:
        raise RuntimeError("Telegram user api_id must be an integer") from exc

    try:
        from telethon import TelegramClient
    except ImportError as exc:
        raise RuntimeError("Telethon is required for Telegram user-account sending. Install telethon.") from exc

    async def _send() -> TelegramSendResult:
        session_value = _resolve_user_session(session, session_file)
        client = TelegramClient(session_value, api_id_value, api_hash_value)
        await client.connect()
        try:
            if not await client.is_user_authorized():
                raise RuntimeError(
                    "Telegram user session is not authorized. Run scripts/telegram_user_login.py first "
                    "or set TELEGRAM_USER_SESSION."
                )
            message = await client.send_message(_normalize_chat_id(chat_id), message_text)
            message_id = int(getattr(message, "id", 0) or 0)
            if message_id <= 0:
                raise RuntimeError("Telegram user send_message did not return a message id")
            raw = {
                "id": message_id,
                "chat_id": str(chat_id),
                "peer_id": str(getattr(message, "peer_id", "")),
                "date": getattr(getattr(message, "date", None), "isoformat", lambda: "")(),
                "sender_id": str(getattr(message, "sender_id", "")),
                "out": bool(getattr(message, "out", False)),
            }
            return TelegramSendResult(
                message_id=message_id,
                chat_id=chat_id,
                date=_message_date_ts(getattr(message, "date", None)),
                text=message_text,
                raw_response=raw,
            )
        finally:
            await client.disconnect()

    return asyncio.run(_send())


def get_telegram_updates(
    *,
    bot_token: str,
    limit: int = 100,
    timeout_s: int = 0,
    offset: int | None = None,
    allowed_updates: list[str] | None = None,
) -> list[dict[str, Any]]:
    payload: dict[str, Any] = {
        "limit": max(1, min(int(limit), 100)),
        "timeout": max(0, int(timeout_s)),
    }
    if offset is not None:
        payload["offset"] = int(offset)
    if allowed_updates:
        payload["allowed_updates"] = [str(item) for item in allowed_updates if str(item).strip()]

    result = _telegram_api_json(bot_token, "getUpdates", payload)
    if result is None:
        return []
    if not isinstance(result, list):
        raise RuntimeError(f"Telegram getUpdates returned unexpected result type: {type(result).__name__}")

    rows: list[dict[str, Any]] = []
    for item in result:
        if isinstance(item, dict):
            rows.append(item)
    return rows


def delete_telegram_message(*, bot_token: str, chat_id: str | int, message_id: int) -> bool:
    result = _telegram_api_json(
        bot_token,
        "deleteMessage",
        {
            "chat_id": _normalize_chat_id(chat_id),
            "message_id": int(message_id),
        },
    )
    return bool(result)


def flush_telegram_update_backlog(*, bot_token: str, batch_limit: int = 100) -> dict[str, int]:
    offset: int | None = None
    cleared = 0
    max_update_id: int | None = None

    while True:
        updates = get_telegram_updates(
            bot_token=bot_token,
            limit=max(1, min(int(batch_limit), 100)),
            timeout_s=0,
            offset=offset,
        )
        if not updates:
            break
        cleared += len(updates)

        last_id = None
        for row in updates:
            raw = row.get("update_id")
            if isinstance(raw, int):
                if last_id is None or raw > last_id:
                    last_id = raw
        if last_id is None:
            break

        max_update_id = last_id
        offset = max_update_id + 1
        if len(updates) < max(1, min(int(batch_limit), 100)):
            break

    # Ensure final offset is acknowledged.
    if offset is not None:
        get_telegram_updates(bot_token=bot_token, limit=1, timeout_s=0, offset=offset)

    return {
        "cleared_updates": cleared,
        "last_update_id": max_update_id if max_update_id is not None else -1,
    }
