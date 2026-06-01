"""livepi-artifacts — curated benchmark results for the LivePI paper.

Usage:
    import livepi_artifacts as lpa
    art = lpa.read_artifact(agent="openclaw", model="anthropic/claude-opus-4.6")
    print(art["parameters"]["hard_attack_success_rate"])
    for case in art["cases"]:
        print(case["surface"], case["objective"], case["hard_attack_success"])

    # iterate all
    for art in lpa.iter_artifacts():
        ...

Artifacts mirror the JailbreakBench/artifacts pattern: one JSON per
(agent_harness, base_model) tuple, with an aggregate `parameters` block and a
`cases` list (one entry per executed benchmark case).
"""
from __future__ import annotations

import json
import re
from importlib.resources import files
from typing import Any, Iterator


__all__ = ["read_artifact", "iter_artifacts", "list_artifacts"]


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s or "unknown").strip("_")


def _data_root():
    return files("livepi_artifacts") / "data"


def list_artifacts() -> list[dict[str, str]]:
    """List every (agent, model) tuple shipped with this package."""
    out: list[dict[str, str]] = []
    for agent_dir in sorted(_data_root().iterdir()):
        if not agent_dir.is_dir():
            continue
        for model_file in sorted(agent_dir.iterdir()):
            if not model_file.name.endswith(".json"):
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
    path = _data_root() / _slug(agent) / f"{_slug(model)}.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"No artifact for agent={agent!r} model={model!r}. "
            f"Call list_artifacts() to see what is shipped."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def iter_artifacts() -> Iterator[dict[str, Any]]:
    """Yield every artifact payload sequentially."""
    for entry in list_artifacts():
        agent, model = entry["agent"], entry["model"]
        yield read_artifact(agent=agent, model=model)
