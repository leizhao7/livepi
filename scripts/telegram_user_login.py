#!/usr/bin/env python3
"""Create a Telethon session for Telegram user-account benchmark posting.

The session is a secret. Keep it in secrets.env as TELEGRAM_USER_SESSION or in
the ignored TELEGRAM_USER_SESSION_FILE path.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = REPO_ROOT / "secrets.env"
DEFAULT_SESSION_FILE = REPO_ROOT / "prompt_injection_lab" / ".telegram_benchmark.session"


def _load_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'").strip('"')
    return values


def _resolve_session_file(raw: str) -> Path:
    value = raw.strip()
    if not value:
        return DEFAULT_SESSION_FILE
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


async def _login(args: argparse.Namespace) -> int:
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except ImportError as exc:
        raise SystemExit("telethon is required. Run: python3 -m pip install telethon") from exc

    env = _load_env(Path(args.env_file).expanduser())
    api_id = str(args.api_id or env.get("TELEGRAM_USER_API_ID") or "").strip()
    api_hash = str(args.api_hash or env.get("TELEGRAM_USER_API_HASH") or "").strip()
    phone = str(args.phone or env.get("TELEGRAM_USER_PHONE") or "").strip()

    if not api_id:
        raise SystemExit("missing TELEGRAM_USER_API_ID")
    if not api_hash:
        raise SystemExit("missing TELEGRAM_USER_API_HASH")
    if not phone:
        raise SystemExit("missing TELEGRAM_USER_PHONE or --phone")

    session_file = _resolve_session_file(args.session_file or env.get("TELEGRAM_USER_SESSION_FILE", ""))
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_arg = StringSession() if args.print_string_session else str(session_file)

    client = TelegramClient(session_arg, int(api_id), api_hash)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            sent = await client.send_code_request(phone)
            code = input("Telegram login code: ").strip()
            password = None
            try:
                await client.sign_in(phone=phone, code=code, phone_code_hash=sent.phone_code_hash)
            except Exception as exc:  # noqa: BLE001
                if exc.__class__.__name__ != "SessionPasswordNeededError":
                    raise
                password = getpass.getpass("Telegram 2FA password: ")
                await client.sign_in(password=password)
        me = await client.get_me()
        username = getattr(me, "username", "") or getattr(me, "first_name", "") or "telegram-user"
        print(f"authorized_as={username}")
        if args.print_string_session:
            print("TELEGRAM_USER_SESSION=" + client.session.save())
        else:
            print(f"TELEGRAM_USER_SESSION_FILE={session_file}")
    finally:
        await client.disconnect()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a Telegram user-account session for LivePI.")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE), help="Env file with Telegram app credentials.")
    parser.add_argument("--api-id", default="", help="Override TELEGRAM_USER_API_ID.")
    parser.add_argument("--api-hash", default="", help="Override TELEGRAM_USER_API_HASH.")
    parser.add_argument("--phone", default="", help="Override TELEGRAM_USER_PHONE.")
    parser.add_argument("--session-file", default="", help="Override TELEGRAM_USER_SESSION_FILE.")
    parser.add_argument(
        "--print-string-session",
        action="store_true",
        help="Print TELEGRAM_USER_SESSION instead of writing a session file.",
    )
    return asyncio.run(_login(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
