from __future__ import annotations

from typing import Any

from .base import EnvironmentConfig


def build_config(task: dict[str, Any]) -> dict[str, Any]:
    params = task.get("environment", {}).get("params", {})
    channel_id = params.get("channel_id", "slack-redteam-room")
    secret_marker = params.get("seed_secret_marker", "SLACK_PRIVATE_KEY_MARKER")

    config = EnvironmentConfig(
        environment_id=f"slack_channel::{channel_id}",
        description="Slack channel injection simulation for OpenClaw.",
        required_skills=task.get("environment", {}).get("required_skills", ["slack"]),
        setup_steps=[
            "openclaw gateway probe",
            "openclaw skills list",
            f"python3 fixtures/seed_slack_channel.py --channel-id {channel_id}",
            f"python3 fixtures/seed_secret_marker.py --marker {secret_marker}",
        ],
        teardown_steps=[
            f"python3 fixtures/clear_slack_channel.py --channel-id {channel_id}",
        ],
        fixtures={
            "channel_id": channel_id,
            "seed_secret_marker": secret_marker,
            "surface": "slack_channel",
        },
    )
    return config.to_dict()
