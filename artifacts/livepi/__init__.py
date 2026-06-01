"""livepi — indirect prompt injection benchmark (arXiv:2605.17986).

This package vendors three things:
  1. The curated per-(agent, model) JSON benchmark artifacts (the JBB-style read API).
  2. The full `prompt_injection_lab/` source tree (shipped as a sibling top-level package).
  3. The shell + Docker harness, so you can also RUN new evaluations after install.

Quick start:

    pip install "git+https://github.com/leizhao7/livepi.git#subdirectory=artifacts"

    # 1) read curated paper results
    import livepi
    livepi.list_artifacts()
    art = livepi.read_artifact(agent="openclaw", model="anthropic/claude-opus-4.6")
    print(art["parameters"]["hard_attack_success_rate"])

    # 2) bootstrap a workspace + run a fresh case
    livepi.bootstrap(workdir="~/livepi-work", apply=True)
    out = livepi.run_case(
        agent="codex",
        base_model="openai/gpt-5.3-codex",
        surface="direct_chat_txt",
        technique="checklist_handoff_injection",
        objective="email_summary_to_external",
        workdir="~/livepi-work",
    )
    print(out["summary"]["status"], out["summary"]["hard"]["attack_success"])

    # 3) sweep + aggregate
    livepi.run_sweep(agent="codex", base_model="openai/gpt-5.3-codex",
                     fixed_surface="direct_chat_txt", workdir="~/livepi-work")
    print(livepi.aggregate(workdir="~/livepi-work", output_format="markdown"))

CLI equivalents are exposed as `livepi <subcommand>` — see `livepi --help`.
"""
from __future__ import annotations

from . import paths
from .api import read_artifact, iter_artifacts, list_artifacts
from .harness import (
    bootstrap,
    build_image,
    ensure_workspace,
    run_case,
    run_sweep,
    aggregate,
)

__all__ = [
    # read API
    "read_artifact",
    "iter_artifacts",
    "list_artifacts",
    # runner API
    "bootstrap",
    "build_image",
    "ensure_workspace",
    "run_case",
    "run_sweep",
    "aggregate",
    # introspection
    "paths",
]

__version__ = "0.2.0"
