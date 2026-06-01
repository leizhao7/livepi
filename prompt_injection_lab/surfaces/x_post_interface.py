"""X (Twitter) attack surface for OpenClaw prompt injection lab.

Creates a tweet thread on X containing a realistic tutorial with a hidden
injection payload, then deletes all tweets after the test.

Uses raw HTTP via urllib with OAuth 1.0a (HMAC-SHA1) authentication —
no external SDK dependency.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request

logger = logging.getLogger(__name__)

X_API_BASE = "https://api.x.com/2"
USER_AGENT = "openclaw-injection-lab/0.1"


# ---------------------------------------------------------------------------
# OAuth 1.0a signing (stdlib only)
# ---------------------------------------------------------------------------

def _percent_encode(s: str) -> str:
    """RFC 5849 percent-encoding (stricter than urllib default)."""
    return parse.quote(str(s), safe="")


def _build_oauth1_header(
    method: str,
    url: str,
    body_params: dict[str, str] | None,
    consumer_key: str,
    consumer_secret: str,
    token: str,
    token_secret: str,
) -> str:
    """Build an OAuth 1.0a ``Authorization`` header value."""
    oauth_params: dict[str, str] = {
        "oauth_consumer_key": consumer_key,
        "oauth_token": token,
        "oauth_nonce": secrets.token_hex(16),
        "oauth_timestamp": str(int(time.time())),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_version": "1.0",
    }

    # Collect all params for the signature base string.
    # For JSON-body requests (POST /2/tweets) there are no body params in the
    # signature — only query-string + oauth params.  For DELETE with no body
    # the same applies.
    all_params: dict[str, str] = {**oauth_params}
    if body_params:
        all_params.update(body_params)

    # Also include query string params from the URL
    url_parts = parse.urlparse(url)
    if url_parts.query:
        all_params.update(parse.parse_qs(url_parts.query, keep_blank_values=True))

    # Sort and concatenate
    sorted_params = "&".join(
        f"{_percent_encode(k)}={_percent_encode(v)}"
        for k, v in sorted(all_params.items())
    )

    # Base URL (strip query string)
    base_url = f"{url_parts.scheme}://{url_parts.netloc}{url_parts.path}"

    base_string = (
        f"{method.upper()}&{_percent_encode(base_url)}&{_percent_encode(sorted_params)}"
    )
    signing_key = f"{_percent_encode(consumer_secret)}&{_percent_encode(token_secret)}"

    signature = base64.b64encode(
        hmac.new(
            signing_key.encode("utf-8"),
            base_string.encode("utf-8"),
            hashlib.sha1,
        ).digest()
    ).decode("utf-8")

    oauth_params["oauth_signature"] = signature

    header = "OAuth " + ", ".join(
        f'{_percent_encode(k)}="{_percent_encode(v)}"'
        for k, v in sorted(oauth_params.items())
    )
    return header


# ---------------------------------------------------------------------------
# X API v2 helpers
# ---------------------------------------------------------------------------

def _x_api_request(
    method: str,
    url: str,
    *,
    api_key: str,
    api_secret: str,
    access_token: str,
    access_secret: str,
    json_body: dict[str, Any] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """Send an authenticated request to the X API v2."""
    # For JSON body requests the body params are NOT included in the OAuth
    # signature base string — only oauth params + query params.
    auth_header = _build_oauth1_header(
        method=method,
        url=url,
        body_params=None,  # JSON body excluded from signature
        consumer_key=api_key,
        consumer_secret=api_secret,
        token=access_token,
        token_secret=access_secret,
    )

    data: bytes | None = None
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")

    req = request.Request(url, data=data, method=method)
    req.add_header("Authorization", auth_header)
    req.add_header("User-Agent", USER_AGENT)
    if json_body is not None:
        req.add_header("Content-Type", "application/json")

    try:
        with request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            if not body:
                return {}
            return json.loads(body)
    except error.HTTPError as exc:
        err_body = exc.read().decode("utf-8") if exc.fp else ""
        raise RuntimeError(
            f"X API {method} {url} failed ({exc.code}): {err_body}"
        ) from exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@dataclass
class XPostResult:
    post_id: str
    post_url: str
    text: str


def x_create_post(
    *,
    api_key: str,
    api_secret: str,
    access_token: str,
    access_secret: str,
    text: str,
    reply_to_id: str | None = None,
) -> XPostResult:
    """Create a single post (tweet) on X.

    If *reply_to_id* is given the tweet is created as a reply, forming a
    thread when chained.
    """
    body: dict[str, Any] = {"text": text}
    if reply_to_id:
        body["reply"] = {"in_reply_to_tweet_id": reply_to_id}

    resp = _x_api_request(
        "POST",
        f"{X_API_BASE}/tweets",
        api_key=api_key,
        api_secret=api_secret,
        access_token=access_token,
        access_secret=access_secret,
        json_body=body,
    )

    data = resp.get("data", {})
    post_id = data.get("id", "")
    # X API v2 doesn't return a URL directly; construct it.
    post_url = f"https://x.com/i/status/{post_id}" if post_id else ""

    logger.info("X post created: id=%s url=%s", post_id, post_url)
    return XPostResult(post_id=post_id, post_url=post_url, text=text)


def x_create_thread(
    *,
    api_key: str,
    api_secret: str,
    access_token: str,
    access_secret: str,
    tweets: list[str],
    delay_between: float = 1.0,
) -> list[XPostResult]:
    """Post a thread on X (each tweet replies to the previous one).

    Returns a list of :class:`XPostResult` in posting order.  A short delay
    between tweets avoids rate-limit issues.
    """
    if not tweets:
        raise ValueError("tweets list must not be empty")

    results: list[XPostResult] = []
    reply_to: str | None = None

    for i, tweet_text in enumerate(tweets):
        result = x_create_post(
            api_key=api_key,
            api_secret=api_secret,
            access_token=access_token,
            access_secret=access_secret,
            text=tweet_text,
            reply_to_id=reply_to,
        )
        results.append(result)
        reply_to = result.post_id

        if i < len(tweets) - 1 and delay_between > 0:
            time.sleep(delay_between)

    logger.info(
        "X thread created: %d tweets, first=%s",
        len(results),
        results[0].post_url if results else "none",
    )
    return results


def x_delete_post(
    *,
    api_key: str,
    api_secret: str,
    access_token: str,
    access_secret: str,
    post_id: str,
) -> dict[str, Any]:
    """Delete a tweet by its ID."""
    try:
        resp = _x_api_request(
            "DELETE",
            f"{X_API_BASE}/tweets/{post_id}",
            api_key=api_key,
            api_secret=api_secret,
            access_token=access_token,
            access_secret=access_secret,
        )
        deleted = resp.get("data", {}).get("deleted", False)
        logger.info("X post deleted: id=%s deleted=%s", post_id, deleted)
        return {"deleted": deleted, "post_id": post_id}
    except Exception as exc:
        logger.warning("X delete failed for %s: %s", post_id, exc)
        return {"deleted": False, "post_id": post_id, "error": str(exc)}


def x_delete_thread(
    *,
    api_key: str,
    api_secret: str,
    access_token: str,
    access_secret: str,
    post_ids: list[str],
) -> list[dict[str, Any]]:
    """Delete all tweets in a thread (in reverse order)."""
    results: list[dict[str, Any]] = []
    for pid in reversed(post_ids):
        result = x_delete_post(
            api_key=api_key,
            api_secret=api_secret,
            access_token=access_token,
            access_secret=access_secret,
            post_id=pid,
        )
        results.append(result)
        time.sleep(0.5)
    return results
