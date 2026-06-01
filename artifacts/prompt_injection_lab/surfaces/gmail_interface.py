from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from email.message import EmailMessage
from urllib import error, parse, request


GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


@dataclass
class GmailSendResult:
    message_id: str
    thread_id: str
    label_ids: list[str]
    raw_response: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "message_id": self.message_id,
            "thread_id": self.thread_id,
            "label_ids": self.label_ids,
            "raw_response": self.raw_response,
        }


def _http_json(
    url: str,
    payload: dict[str, object],
    *,
    headers: dict[str, str] | None = None,
) -> dict[str, object]:
    body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    req = request.Request(
        url=url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with request.urlopen(req, timeout=30) as resp:
            data = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Network error for {url}: {exc}") from exc
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON response from {url}: {data[:300]}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Unexpected JSON response type from {url}: {type(parsed).__name__}")
    return parsed


def _refresh_access_token(refresh_token: str, client_id: str, client_secret: str) -> str:
    form = parse.urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
    ).encode("utf-8")
    req = request.Request(
        url=GOOGLE_TOKEN_URL,
        data=form,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with request.urlopen(req, timeout=30) as resp:
            payload = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Failed to refresh Gmail token (HTTP {exc.code}): {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Network error while refreshing Gmail token: {exc}") from exc

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Bad token response JSON: {payload[:300]}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("Token response must be a JSON object")
    access_token = str(parsed.get("access_token", "")).strip()
    if not access_token:
        raise RuntimeError(f"Token response missing access_token: {parsed}")
    return access_token


def resolve_gmail_access_token() -> str:
    access_token = os.getenv("GMAIL_ACCESS_TOKEN", "").strip()
    if access_token:
        return access_token

    refresh_token = os.getenv("GMAIL_REFRESH_TOKEN", "").strip()
    client_id = os.getenv("GMAIL_CLIENT_ID", "").strip()
    client_secret = os.getenv("GMAIL_CLIENT_SECRET", "").strip()
    if refresh_token and client_id and client_secret:
        return _refresh_access_token(refresh_token, client_id, client_secret)

    raise RuntimeError(
        "Missing Gmail credentials. Set GMAIL_ACCESS_TOKEN or set "
        "GMAIL_REFRESH_TOKEN + GMAIL_CLIENT_ID + GMAIL_CLIENT_SECRET."
    )


def _build_raw_rfc822(*, sender: str, recipient: str, subject: str, body: str) -> str:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(body)
    raw_bytes = msg.as_bytes()
    return base64.urlsafe_b64encode(raw_bytes).decode("ascii")


def send_gmail_email(
    *,
    sender: str,
    recipient: str,
    subject: str,
    body: str,
    access_token: str | None = None,
) -> GmailSendResult:
    token = (access_token or "").strip() or resolve_gmail_access_token()
    raw = _build_raw_rfc822(sender=sender, recipient=recipient, subject=subject, body=body)
    response = _http_json(
        GMAIL_SEND_URL,
        {"raw": raw},
        headers={"Authorization": f"Bearer {token}"},
    )
    return GmailSendResult(
        message_id=str(response.get("id", "")),
        thread_id=str(response.get("threadId", "")),
        label_ids=[str(item) for item in response.get("labelIds", []) if isinstance(item, str)],
        raw_response=response,
    )

