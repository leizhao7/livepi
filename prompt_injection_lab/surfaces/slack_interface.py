from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import error, request


SLACK_API_ROOT = "https://slack.com/api"


def _slack_api_json(bot_token: str, method: str, payload: dict[str, Any]) -> dict[str, Any]:
    token = bot_token.strip()
    if not token:
        raise RuntimeError("Slack bot token is required")
    method_name = method.strip()
    if not method_name:
        raise RuntimeError("Slack API method name is required")

    body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    req = request.Request(
        f"{SLACK_API_ROOT}/{method_name}",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    try:
        with request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Slack API HTTP {exc.code} ({method_name}): {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Slack API network error ({method_name}): {exc}") from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Slack API invalid JSON ({method_name}): {raw[:300]}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Slack API unexpected response type ({method_name}): {type(parsed).__name__}")
    if not bool(parsed.get("ok", False)):
        raise RuntimeError(f"Slack API returned ok=false ({method_name}): {parsed}")
    return parsed


@dataclass
class SlackSendResult:
    channel_id: str
    message_ts: str
    text: str
    raw_response: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel_id": self.channel_id,
            "message_ts": self.message_ts,
            "text": self.text,
            "raw_response": self.raw_response,
        }


def send_slack_channel_message(
    *,
    bot_token: str,
    channel_id: str,
    text: str,
) -> SlackSendResult:
    message_text = text.strip()
    if not message_text:
        raise RuntimeError("Slack message text must not be empty")
    channel = channel_id.strip()
    if not channel:
        raise RuntimeError("Slack channel_id must not be empty")

    parsed = _slack_api_json(
        bot_token,
        "chat.postMessage",
        {
            "channel": channel,
            "text": message_text,
            "unfurl_links": False,
            "unfurl_media": False,
        },
    )
    msg = parsed.get("message", {})
    if not isinstance(msg, dict):
        msg = {}
    message_ts = str(parsed.get("ts") or msg.get("ts") or "").strip()
    if not message_ts:
        raise RuntimeError(f"Slack chat.postMessage missing ts: {parsed}")

    return SlackSendResult(
        channel_id=str(parsed.get("channel", channel)).strip() or channel,
        message_ts=message_ts,
        text=str(msg.get("text", message_text)),
        raw_response=parsed,
    )


def get_slack_channel_history(
    *,
    bot_token: str,
    channel_id: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    channel = channel_id.strip()
    if not channel:
        raise RuntimeError("Slack channel_id must not be empty")

    parsed = _slack_api_json(
        bot_token,
        "conversations.history",
        {
            "channel": channel,
            "limit": max(1, min(int(limit), 100)),
            "inclusive": True,
        },
    )
    messages = parsed.get("messages", [])
    if not isinstance(messages, list):
        raise RuntimeError(f"Slack conversations.history returned unexpected messages: {parsed}")
    return [row for row in messages if isinstance(row, dict)]


def delete_slack_message(*, bot_token: str, channel_id: str, message_ts: str) -> bool:
    channel = channel_id.strip()
    ts = message_ts.strip()
    if not channel:
        raise RuntimeError("Slack channel_id must not be empty")
    if not ts:
        raise RuntimeError("Slack message_ts must not be empty")
    parsed = _slack_api_json(
        bot_token,
        "chat.delete",
        {
            "channel": channel,
            "ts": ts,
        },
    )
    return bool(parsed.get("ok", True))
