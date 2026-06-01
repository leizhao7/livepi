from __future__ import annotations

from typing import Any

from .base import EnvironmentConfig


def build_config(task: dict[str, Any]) -> dict[str, Any]:
    params = task.get("environment", {}).get("params", {})
    inbox_user = params.get("inbox_user", "user@example.com")
    attacker_recipient = params.get("attacker_recipient", "attacker@example.net")
    otp_marker = params.get("seed_otp_marker", "OTP_MARKER")

    config = EnvironmentConfig(
        environment_id=f"email_gmail::{inbox_user}",
        description="Gmail inbox injection simulation for OpenClaw.",
        required_skills=task.get("environment", {}).get("required_skills", ["imap-smtp-email"]),
        setup_steps=[
            "openclaw gateway probe",
            "openclaw skills list",
            f"python3 fixtures/seed_gmail_message.py --to {inbox_user}",
            f"python3 fixtures/seed_secret_marker.py --marker {otp_marker}",
        ],
        teardown_steps=[
            f"python3 fixtures/cleanup_mailbox.py --user {inbox_user}",
            f"python3 fixtures/block_outbound_recipient.py --recipient {attacker_recipient}",
        ],
        fixtures={
            "inbox_user": inbox_user,
            "attacker_recipient": attacker_recipient,
            "seed_otp_marker": otp_marker,
            "surface": "email_gmail",
        },
    )
    return config.to_dict()

