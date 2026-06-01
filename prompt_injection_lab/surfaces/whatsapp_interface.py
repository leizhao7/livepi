from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import error, request


def _whatsapp_bridge_json(api_url: str, access_token: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = api_url.strip()
    if not url:
        raise RuntimeError("WhatsApp API URL is required")

    headers = {
        "Content-Type": "application/json; charset=utf-8",
    }
    token = access_token.strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    req = request.Request(url, data=body, method="POST", headers=headers)
    try:
        with request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"WhatsApp bridge HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"WhatsApp bridge network error: {exc}") from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"WhatsApp bridge invalid JSON: {raw[:300]}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"WhatsApp bridge returned unexpected response type: {type(parsed).__name__}")
    return parsed


def _extract_whatsapp_message_id(payload: dict[str, Any]) -> str:
    direct = str(payload.get("message_id") or payload.get("id") or "").strip()
    if direct:
        return direct
    messages = payload.get("messages", [])
    if isinstance(messages, list) and messages:
        first = messages[0]
        if isinstance(first, dict):
            nested = str(first.get("id", "")).strip()
            if nested:
                return nested
    message = payload.get("message", {})
    if isinstance(message, dict):
        nested = str(message.get("id", "")).strip()
        if nested:
            return nested
    return ""


@dataclass
class WhatsAppSendResult:
    group_id: str
    message_id: str
    text: str
    raw_response: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "message_id": self.message_id,
            "text": self.text,
            "raw_response": self.raw_response,
        }


def send_whatsapp_group_message(
    *,
    api_url: str,
    access_token: str,
    group_id: str,
    text: str,
    extra_payload: dict[str, Any] | None = None,
) -> WhatsAppSendResult:
    target_group = group_id.strip()
    if not target_group:
        raise RuntimeError("WhatsApp group_id must not be empty")
    message_text = text.strip()
    if not message_text:
        raise RuntimeError("WhatsApp message text must not be empty")
    if extra_payload is not None and not isinstance(extra_payload, dict):
        raise RuntimeError("WhatsApp extra_payload must be an object")

    payload: dict[str, Any] = {
        "group_id": target_group,
        "text": message_text,
    }
    if extra_payload:
        payload.update(extra_payload)

    parsed = _whatsapp_bridge_json(api_url, access_token, payload)
    return WhatsAppSendResult(
        group_id=target_group,
        message_id=_extract_whatsapp_message_id(parsed),
        text=message_text,
        raw_response=parsed,
    )
