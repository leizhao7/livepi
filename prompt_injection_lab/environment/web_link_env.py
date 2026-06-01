from __future__ import annotations

from typing import Any

from .base import EnvironmentConfig


def build_config(task: dict[str, Any]) -> dict[str, Any]:
    params = task.get("environment", {}).get("params", {})
    url = params.get("url", "https://attacker.example/prompt.html")
    marker = params.get("seed_secret_marker", "PRIVATE_KEY_MARKER")

    config = EnvironmentConfig(
        environment_id=f"web_link::{url}",
        description="Hosted web-link prompt-injection simulation for OpenClaw.",
        required_skills=task.get("environment", {}).get("required_skills", ["browser"]),
        setup_steps=[
            "openclaw gateway probe",
            f"python3 fixtures/serve_injected_page.py --url {url}",
            f"python3 fixtures/seed_secret_marker.py --marker {marker}",
        ],
        teardown_steps=[
            f"python3 fixtures/stop_injected_page.py --url {url}",
        ],
        fixtures={
            "url": url,
            "seed_secret_marker": marker,
            "surface": "web_link",
        },
    )
    return config.to_dict()

