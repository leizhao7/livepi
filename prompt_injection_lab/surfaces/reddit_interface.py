"""Reddit attack surface for OpenClaw prompt injection lab.

Creates a self-post on a target subreddit containing a realistic tutorial
with a hidden injection payload, then deletes it after the test.

Uses raw HTTP via urllib (no PRAW dependency) with Reddit's OAuth2 "script"
app authentication flow.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request

logger = logging.getLogger(__name__)

REDDIT_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
REDDIT_API_BASE = "https://oauth.reddit.com"
USER_AGENT = "openclaw-injection-lab/0.1 by prompt-injection-research"


@dataclass
class RedditPostResult:
    post_id: str
    post_url: str
    subreddit: str
    title: str


def _get_reddit_token(
    client_id: str,
    client_secret: str,
    username: str,
    password: str,
) -> str:
    """Obtain an OAuth2 bearer token via Reddit's 'script' app flow."""
    data = parse.urlencode({
        "grant_type": "password",
        "username": username,
        "password": password,
    }).encode()

    req = request.Request(REDDIT_TOKEN_URL, data=data, method="POST")
    # Basic auth with client_id:client_secret
    import base64
    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    req.add_header("Authorization", f"Basic {credentials}")
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
    except error.HTTPError as exc:
        err_body = exc.read().decode() if exc.fp else ""
        raise RuntimeError(
            f"Reddit OAuth failed ({exc.code}): {err_body}"
        ) from exc

    token = body.get("access_token")
    if not token:
        raise RuntimeError(f"Reddit OAuth returned no token: {body}")
    logger.info("Reddit OAuth token acquired (expires_in=%s)", body.get("expires_in"))
    return token


def reddit_create_post(
    *,
    client_id: str,
    client_secret: str,
    username: str,
    password: str,
    subreddit: str,
    title: str,
    body_markdown: str,
) -> RedditPostResult:
    """Create a self-post on the target subreddit and return its metadata."""
    token = _get_reddit_token(client_id, client_secret, username, password)

    data = parse.urlencode({
        "kind": "self",
        "sr": subreddit,
        "title": title,
        "text": body_markdown,
        "resubmit": "true",
        "send_replies": "false",
    }).encode()

    req = request.Request(
        f"{REDDIT_API_BASE}/api/submit",
        data=data,
        method="POST",
    )
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
    except error.HTTPError as exc:
        err_body = exc.read().decode() if exc.fp else ""
        raise RuntimeError(
            f"Reddit submit failed ({exc.code}): {err_body}"
        ) from exc

    # Reddit API returns {"success": true, "jquery": [...]} or
    # {"json": {"data": {"url": "...", "id": "...", "name": "t3_..."}}}
    json_data = body.get("json", {}).get("data", {})
    post_url = json_data.get("url", "")
    post_id = json_data.get("id", "") or json_data.get("name", "")

    if not post_url:
        # Fallback: try jquery-style response
        for item in body.get("jquery", []):
            if isinstance(item, list) and len(item) >= 4:
                val = item[3]
                if isinstance(val, list):
                    for v in val:
                        if isinstance(v, str) and v.startswith("http"):
                            post_url = v
                            break

    if not post_id and post_url:
        # Extract ID from URL: .../comments/<id>/...
        parts = post_url.rstrip("/").split("/")
        for i, part in enumerate(parts):
            if part == "comments" and i + 1 < len(parts):
                post_id = parts[i + 1]
                break

    logger.info("Reddit post created: id=%s url=%s", post_id, post_url)
    return RedditPostResult(
        post_id=post_id,
        post_url=post_url,
        subreddit=subreddit,
        title=title,
    )


def reddit_delete_post(
    *,
    client_id: str,
    client_secret: str,
    username: str,
    password: str,
    post_id: str,
) -> dict[str, Any]:
    """Delete a Reddit post by its ID (fullname t3_xxx or bare ID)."""
    token = _get_reddit_token(client_id, client_secret, username, password)

    fullname = post_id if post_id.startswith("t3_") else f"t3_{post_id}"

    data = parse.urlencode({"id": fullname}).encode()

    req = request.Request(
        f"{REDDIT_API_BASE}/api/del",
        data=data,
        method="POST",
    )
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with request.urlopen(req, timeout=30) as resp:
            resp_body = resp.read().decode()
    except error.HTTPError as exc:
        err_body = exc.read().decode() if exc.fp else ""
        logger.warning("Reddit delete failed (%s): %s", exc.code, err_body)
        return {"deleted": False, "error": err_body}

    logger.info("Reddit post deleted: %s", fullname)
    return {"deleted": True, "fullname": fullname, "response": resp_body}
