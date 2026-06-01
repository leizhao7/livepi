"""Read API for the curated benchmark artifacts shipped under data/artifacts/."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterator

from .paths import artifacts_root

__all__ = ["read_artifact", "iter_artifacts", "list_artifacts"]


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s or "unknown").strip("_")


def list_artifacts() -> list[dict[str, Any]]:
    """List every (agent, model) tuple shipped with this package."""
    out: list[dict[str, Any]] = []
    root = artifacts_root()
    if not root.is_dir():
        return out
    for agent_dir in sorted(root.iterdir()):
        if not agent_dir.is_dir():
            continue
        for model_file in sorted(agent_dir.iterdir()):
            if model_file.suffix != ".json":
                continue
            try:
                payload = json.loads(model_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            params = payload.get("parameters", {}) or {}
            out.append({
                "agent": params.get("agent_harness", agent_dir.name),
                "model": params.get("base_model", model_file.stem),
                "path": f"{agent_dir.name}/{model_file.name}",
                "total_cases": params.get("total_cases", 0),
                "hard_attack_success_rate": params.get("hard_attack_success_rate"),
                "judge_attack_success_rate": params.get("judge_attack_success_rate"),
            })
    return out


def read_artifact(agent: str, model: str) -> dict[str, Any]:
    """Load one artifact by (agent, model). Raises FileNotFoundError if absent."""
    path = artifacts_root() / _slug(agent) / f"{_slug(model)}.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"No artifact for agent={agent!r} model={model!r}. "
            f"Call list_artifacts() to see what is shipped."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def iter_artifacts() -> Iterator[dict[str, Any]]:
    """Yield every artifact payload sequentially."""
    for entry in list_artifacts():
        yield read_artifact(agent=entry["agent"], model=entry["model"])
