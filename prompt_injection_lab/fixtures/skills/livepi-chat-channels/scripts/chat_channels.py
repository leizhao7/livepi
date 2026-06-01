#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib import error, parse, request


SLACK_API_ROOT = "https://slack.com/api"
TELEGRAM_API_ROOT = "https://api.telegram.org"


def _load_env_file() -> None:
    skill_root = Path(__file__).resolve().parents[1]
    env_path = skill_root / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def _env(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def _agent_prefixes() -> list[str]:
    mapping = {
        "hermes": "HERMES",
        "codex": "CODEX",
        "claude_code": "CLAUDE_CODE",
        "claude-code": "CLAUDE_CODE",
        "claude": "CLAUDE_CODE",
    }
    raw_agent = os.getenv("LIVEPI_AGENT_NAME", "").strip().lower() or os.getenv("LIVEPI_AGENT", "").strip().lower()
    preferred = mapping.get(raw_agent, "")
    prefixes: list[str] = []
    if preferred:
        prefixes.append(preferred)
    for prefix in ("HERMES", "CODEX", "CLAUDE_CODE"):
        if prefix not in prefixes:
            prefixes.append(prefix)
    return prefixes


def _agent_env_names(suffix: str) -> list[str]:
    return [f"{prefix}_{suffix}" for prefix in _agent_prefixes()]


def _json_http(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    token: str = "",
    bearer: bool = True,
) -> dict[str, Any]:
    headers: dict[str, str] = {"User-Agent": "LivePI-chat-channels/1.0"}
    body: bytes | None = None
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    if token:
        headers["Authorization"] = f"Bearer {token}" if bearer else token
    req = request.Request(url, data=body, method=method, headers=headers)
    try:
        with request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {url}: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Network error {url}: {exc}") from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON from {url}: {raw[:300]}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Unexpected response type from {url}: {type(parsed).__name__}")
    return parsed


def _print(payload: dict[str, Any]) -> int:
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0


def _require(value: str, label: str) -> str:
    if not value:
        raise RuntimeError(f"Missing {label}")
    return value


def _normalize_chat_id(value: str) -> str | int:
    text = value.strip()
    if not text:
        raise RuntimeError("Missing Telegram group id")
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    return text


def _telegram_token() -> str:
    return _require(
        _env(*_agent_env_names("TELEGRAM_BOT_TOKEN"), "TELEGRAM_AGENT_BOT_TOKEN", "TELEGRAM_BOT_TOKEN"),
        "agent TELEGRAM_BOT_TOKEN or TELEGRAM_AGENT_BOT_TOKEN",
    )


def _telegram_group_id() -> str:
    return _require(_env(*_agent_env_names("TELEGRAM_GROUP_ID"), "TELEGRAM_GROUP_ID"), "agent TELEGRAM_GROUP_ID or TELEGRAM_GROUP_ID")


def telegram_history(limit: int) -> dict[str, Any]:
    token = _telegram_token()
    group_id = _normalize_chat_id(_telegram_group_id())
    payload = {"limit": max(1, min(int(limit), 100)), "timeout": 0}
    parsed = _json_http(f"{TELEGRAM_API_ROOT}/bot{token}/getUpdates", method="POST", payload=payload)
    if not parsed.get("ok"):
        raise RuntimeError(f"Telegram getUpdates failed: {parsed}")
    updates = parsed.get("result", [])
    if not isinstance(updates, list):
        updates = []
    filtered: list[dict[str, Any]] = []
    for row in updates:
        if not isinstance(row, dict):
            continue
        message = row.get("message") or row.get("channel_post") or row.get("edited_message") or {}
        if not isinstance(message, dict):
            continue
        chat = message.get("chat") or {}
        chat_id = chat.get("id") if isinstance(chat, dict) else None
        if str(chat_id) == str(group_id):
            filtered.append(row)
    return {"ok": True, "channel": "telegram", "group_id": group_id, "count": len(filtered), "updates": filtered}


def telegram_send(text: str) -> dict[str, Any]:
    token = _telegram_token()
    group_id = _normalize_chat_id(_telegram_group_id())
    parsed = _json_http(
        f"{TELEGRAM_API_ROOT}/bot{token}/sendMessage",
        method="POST",
        payload={"chat_id": group_id, "text": _require(text.strip(), "message text"), "disable_web_page_preview": True},
    )
    if not parsed.get("ok"):
        raise RuntimeError(f"Telegram sendMessage failed: {parsed}")
    return {"ok": True, "channel": "telegram", "group_id": group_id, "message": parsed.get("result")}


def _slack_token() -> str:
    return _require(_env(*_agent_env_names("SLACK_BOT_TOKEN"), "SLACK_BOT_TOKEN"), "agent SLACK_BOT_TOKEN or SLACK_BOT_TOKEN")


def _slack_channel_id() -> str:
    return _require(_env(*_agent_env_names("SLACK_CHANNEL_ID"), "SLACK_CHANNEL_ID"), "agent SLACK_CHANNEL_ID or SLACK_CHANNEL_ID")


def _slack_api(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    token = _slack_token()
    parsed = _json_http(f"{SLACK_API_ROOT}/{method}", method="POST", payload=payload, token=token)
    if not parsed.get("ok"):
        raise RuntimeError(f"Slack {method} failed: {parsed}")
    return parsed


def slack_history(limit: int) -> dict[str, Any]:
    channel = _slack_channel_id()
    parsed = _slack_api("conversations.history", {"channel": channel, "limit": max(1, min(int(limit), 100))})
    messages = parsed.get("messages", [])
    if not isinstance(messages, list):
        messages = []
    return {"ok": True, "channel": "slack", "channel_id": channel, "count": len(messages), "messages": messages}


def slack_send(text: str) -> dict[str, Any]:
    channel = _slack_channel_id()
    parsed = _slack_api(
        "chat.postMessage",
        {
            "channel": channel,
            "text": _require(text.strip(), "message text"),
            "unfurl_links": False,
            "unfurl_media": False,
        },
    )
    return {"ok": True, "channel": "slack", "channel_id": channel, "message": parsed.get("message"), "ts": parsed.get("ts")}


def _whatsapp_api_url(path: str = "") -> str:
    base = _require(_env(*_agent_env_names("WHATSAPP_API_URL"), "WHATSAPP_API_URL"), "agent WHATSAPP_API_URL or WHATSAPP_API_URL")
    if not path:
        return base
    parsed = parse.urlparse(base)
    if parsed.path.endswith("/send"):
        parsed = parsed._replace(path=parsed.path[: -len("/send")] + path)
    else:
        parsed = parsed._replace(path=path)
    return parse.urlunparse(parsed)


def _whatsapp_token() -> str:
    return _env(*_agent_env_names("WHATSAPP_ACCESS_TOKEN"), "WHATSAPP_ACCESS_TOKEN")


def _whatsapp_group_id() -> str:
    return _require(_env(*_agent_env_names("WHATSAPP_GROUP_ID"), "WHATSAPP_GROUP_ID"), "agent WHATSAPP_GROUP_ID or WHATSAPP_GROUP_ID")


def whatsapp_send(text: str) -> dict[str, Any]:
    payload = {"group_id": _whatsapp_group_id(), "text": _require(text.strip(), "message text")}
    parsed = _json_http(_whatsapp_api_url("/send"), method="POST", payload=payload, token=_whatsapp_token())
    return {"ok": bool(parsed.get("ok", True)), "channel": "whatsapp", "group_id": payload["group_id"], "response": parsed}


def whatsapp_groups() -> dict[str, Any]:
    parsed = _json_http(_whatsapp_api_url("/groups"), token=_whatsapp_token())
    return {"ok": bool(parsed.get("ok", True)), "channel": "whatsapp", "groups": parsed.get("groups", [])}


def whatsapp_history(limit: int) -> dict[str, Any]:
    group_id = _whatsapp_group_id()
    url = _whatsapp_api_url("/messages")
    query = parse.urlencode({"group_id": group_id, "limit": max(1, min(int(limit), 100))})
    parsed = _json_http(f"{url}?{query}", token=_whatsapp_token())
    return {
        "ok": bool(parsed.get("ok", True)),
        "channel": "whatsapp",
        "group_id": group_id,
        "count": len(parsed.get("messages", []) if isinstance(parsed.get("messages"), list) else []),
        "messages": parsed.get("messages", []),
    }


def main() -> int:
    _load_env_file()
    parser = argparse.ArgumentParser(description="LivePI chat channel helper.")
    sub = parser.add_subparsers(dest="channel", required=True)
    for channel in ("telegram", "slack", "whatsapp"):
        channel_parser = sub.add_parser(channel)
        actions = channel_parser.add_subparsers(dest="action", required=True)
        history = actions.add_parser("history")
        history.add_argument("--limit", type=int, default=20)
        send = actions.add_parser("send")
        send.add_argument("--text", required=True)
        if channel == "whatsapp":
            actions.add_parser("groups")
    args = parser.parse_args()

    if args.channel == "telegram" and args.action == "history":
        return _print(telegram_history(args.limit))
    if args.channel == "telegram" and args.action == "send":
        return _print(telegram_send(args.text))
    if args.channel == "slack" and args.action == "history":
        return _print(slack_history(args.limit))
    if args.channel == "slack" and args.action == "send":
        return _print(slack_send(args.text))
    if args.channel == "whatsapp" and args.action == "history":
        return _print(whatsapp_history(args.limit))
    if args.channel == "whatsapp" and args.action == "send":
        return _print(whatsapp_send(args.text))
    if args.channel == "whatsapp" and args.action == "groups":
        return _print(whatsapp_groups())
    parser.error("unsupported command")
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, ensure_ascii=True), file=sys.stderr)
        raise SystemExit(1)
