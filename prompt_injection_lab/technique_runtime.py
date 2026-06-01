from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .prompt_builder import (
    TECHNIQUE_FAMILY_LABELS,
    build_injection_prompt,
    supported_technique_tags,
)


LAB_ROOT = Path(__file__).resolve().parent
PROFILES_PATH = LAB_ROOT / "taxonomy" / "technique_profiles.json"


def _load_profiles() -> dict[str, Any]:
    return json.loads(PROFILES_PATH.read_text(encoding="utf-8"))


def supported_profile_tags() -> list[str]:
    return sorted(_load_profiles().get("profiles", {}).keys())


def build_injection_package(
    *,
    technique_tag: str,
    task: str,
    query: str | None = None,
    injection_surface: str | None = None,
    target: str | None = None,
    context: str | None = None,
    constraints: list[str] | None = None,
    use_llm: bool = False,
    llm_model: str | None = None,
    llm_fallback: bool = True,
) -> dict[str, Any]:
    if use_llm and not llm_fallback:
        raise RuntimeError("LLM-assisted prompt design is not included in the clean LivePI artifact.")
    if technique_tag not in supported_technique_tags():
        raise ValueError(f"unsupported technique_tag: {technique_tag}")

    payload = build_injection_prompt(
        technique_tag=technique_tag,
        task=task,
        injection_surface=injection_surface,
        target=target,
        context=context,
        constraints=constraints,
    )
    profiles = _load_profiles()
    profile = profiles.get("profiles", {}).get(technique_tag, {})
    return {
        "technique_tag": technique_tag,
        "technique_family": TECHNIQUE_FAMILY_LABELS.get(technique_tag, technique_tag),
        "injection_surface": injection_surface,
        "task": task,
        "target": target,
        "context": context,
        "query": query,
        "constraints": constraints or [],
        "core_components": profile.get("core_components", []),
        "source_ids": profile.get("source_ids", []),
        "payload": payload,
        "llm_enabled": False,
        "llm_model": llm_model,
    }
