from __future__ import annotations

from typing import Any

from .base import EnvironmentConfig


def build_config(task: dict[str, Any]) -> dict[str, Any]:
    params = task.get("environment", {}).get("params", {})
    doc_id = params.get("doc_id", "team-playbook-01")
    attacker_wallet = params.get("attacker_wallet", "ATTACKER_WALLET")

    config = EnvironmentConfig(
        environment_id=f"shared_docs::{doc_id}",
        description="Shared document prompt-injection simulation for OpenClaw.",
        required_skills=task.get("environment", {}).get("required_skills", []),
        setup_steps=[
            "openclaw gateway probe",
            f"python3 fixtures/create_shared_doc.py --doc-id {doc_id}",
            f"python3 fixtures/seed_doc_payload.py --doc-id {doc_id}",
            f"python3 fixtures/seed_wallet_guardrail.py --wallet {attacker_wallet}",
        ],
        teardown_steps=[
            f"python3 fixtures/archive_shared_doc.py --doc-id {doc_id}",
        ],
        fixtures={
            "doc_id": doc_id,
            "attacker_wallet": attacker_wallet,
            "surface": "shared_docs",
        },
    )
    return config.to_dict()

