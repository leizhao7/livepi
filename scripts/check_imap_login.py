#!/usr/bin/env python3
"""Check LivePI IMAP credentials without printing secret values."""

from __future__ import annotations

import argparse
import email
import imaplib
import json
import os
import socket
import ssl
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = REPO_ROOT / "prompt_injection_lab" / ".env"


@dataclass(frozen=True)
class ImapConfig:
    host: str
    port: int
    user: str
    password: str
    mailbox: str
    reject_unauthorized: bool


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if (value.startswith("'") and value.endswith("'")) or (
            value.startswith('"') and value.endswith('"')
        ):
            value = value[1:-1]
        os.environ[key] = value


def first_env(keys: Iterable[str], default: str = "") -> str:
    for key in keys:
        value = os.getenv(key, "").strip()
        if value:
            return value
    return default


def bool_env(keys: Iterable[str], default: bool = True) -> bool:
    value = first_env(keys)
    if not value:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def int_env(keys: Iterable[str], default: int) -> int:
    value = first_env(keys, str(default))
    try:
        return int(value)
    except ValueError:
        return default


def config_from_env(verify: bool) -> ImapConfig:
    if verify:
        host_keys = ("VERIFY_IMAP_HOST", "ATTACKER_IMAP_HOST", "IMAP_HOST")
        port_keys = ("VERIFY_IMAP_PORT", "ATTACKER_IMAP_PORT", "IMAP_PORT")
        user_keys = ("VERIFY_IMAP_USER", "ATTACKER_IMAP_USER", "ATTACKER_SMTP_USER", "IMAP_USER")
        pass_keys = ("VERIFY_IMAP_PASS", "ATTACKER_IMAP_PASS", "ATTACKER_SMTP_PASS", "IMAP_PASS")
        mailbox_keys = ("VERIFY_IMAP_MAILBOX", "IMAP_MAILBOX")
        reject_keys = ("VERIFY_IMAP_REJECT_UNAUTHORIZED", "IMAP_REJECT_UNAUTHORIZED")
    else:
        host_keys = ("IMAP_HOST",)
        port_keys = ("IMAP_PORT",)
        user_keys = ("IMAP_USER",)
        pass_keys = ("IMAP_PASS",)
        mailbox_keys = ("IMAP_MAILBOX",)
        reject_keys = ("IMAP_REJECT_UNAUTHORIZED",)

    return ImapConfig(
        host=first_env(host_keys),
        port=int_env(port_keys, 993),
        user=first_env(user_keys),
        password=first_env(pass_keys),
        mailbox=first_env(mailbox_keys, "INBOX") or "INBOX",
        reject_unauthorized=bool_env(reject_keys, True),
    )


def missing_keys(config: ImapConfig) -> list[str]:
    missing: list[str] = []
    if not config.host:
        missing.append("host")
    if not config.user:
        missing.append("user")
    if not config.password:
        missing.append("password")
    return missing


def connect(config: ImapConfig, timeout: float) -> imaplib.IMAP4_SSL:
    context = ssl.create_default_context()
    if not config.reject_unauthorized:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return imaplib.IMAP4_SSL(config.host, config.port, ssl_context=context, timeout=timeout)


def latest_subject(conn: imaplib.IMAP4_SSL) -> str | None:
    typ, data = conn.search(None, "ALL")
    if typ != "OK" or not data or not data[0]:
        return None
    ids = data[0].split()
    latest_id = ids[-1]
    typ, msg_data = conn.fetch(latest_id, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])")
    if typ != "OK" or not msg_data:
        return None
    for item in msg_data:
        if isinstance(item, tuple) and item[1]:
            headers = email.message_from_bytes(item[1])
            return str(headers.get("Subject", ""))
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE), help="Env file to load first.")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Use the verifier fallback order: VERIFY_IMAP_*, ATTACKER_IMAP_*, ATTACKER_SMTP_*, then IMAP_*.",
    )
    parser.add_argument("--timeout-s", type=float, default=30.0, help="Connection/login timeout.")
    args = parser.parse_args()

    load_env_file(Path(args.env_file))
    config = config_from_env(verify=args.verify)
    missing = missing_keys(config)
    if missing:
        print(
            json.dumps(
                {
                    "ok": False,
                    "mode": "verify" if args.verify else "agent",
                    "missing": missing,
                    "env_file": str(Path(args.env_file)),
                },
                indent=2,
            )
        )
        return 2

    socket.setdefaulttimeout(args.timeout_s)
    try:
        conn = connect(config, args.timeout_s)
        try:
            conn.login(config.user, config.password)
            typ, data = conn.select(config.mailbox, readonly=True)
            if typ != "OK":
                raise RuntimeError(f"select {config.mailbox!r} failed: {data!r}")
            count = int(data[0].decode("ascii", errors="ignore") or "0") if data else 0
            subject = latest_subject(conn)
        finally:
            try:
                conn.logout()
            except Exception:
                pass
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "mode": "verify" if args.verify else "agent",
                    "host": config.host,
                    "port": config.port,
                    "user": config.user,
                    "mailbox": config.mailbox,
                    "error": str(exc),
                },
                indent=2,
            )
        )
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "mode": "verify" if args.verify else "agent",
                "host": config.host,
                "port": config.port,
                "user": config.user,
                "mailbox": config.mailbox,
                "message_count": count,
                "latest_subject": subject,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
