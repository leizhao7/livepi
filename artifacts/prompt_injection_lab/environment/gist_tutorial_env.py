from __future__ import annotations

from typing import Any

from .base import EnvironmentConfig


def build_config(task: dict[str, Any]) -> dict[str, Any]:
    params = task.get("environment", {}).get("params", {})
    topic = params.get("tutorial_topic", "tutorial")

    config = EnvironmentConfig(
        environment_id=f"gist_tutorial::{topic}",
        description="Public GitHub Gist tutorial surface. The sweep script creates and deletes the live Gist.",
        required_skills=task.get("environment", {}).get("required_skills", ["browser"]),
        setup_steps=[
            "create public GitHub Gist with benign tutorial body and embedded payload",
            "send the Gist URL to OpenClaw as a normal reference task",
        ],
        teardown_steps=[
            "delete the public GitHub Gist through the GitHub API",
        ],
        fixtures={
            "surface": "gist_tutorial",
            "tutorial_topic": topic,
            "creator": "scripts/sweep_gist_tutorial.py",
        },
    )
    return config.to_dict()
