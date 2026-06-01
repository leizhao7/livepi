from __future__ import annotations

import os
import shlex
from pathlib import Path

from prompt_injection_lab.agents.cli_adapter import CliAgentAdapter, build_cli_adapter_from_env


def _default_cli_args() -> str:
    parts = [
        "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        "--skip-git-repo-check",
        "--ephemeral",
        # NOTE: --json is temporarily removed for an A/B test against the
        # OAuth supply-chain attack=False issue. Re-enable once verified.
        # "--json",
    ]
    model = os.getenv("CODEX_MODEL", "").strip()
    if model:
        parts.extend(["--model", model])
    return " ".join(shlex.quote(part) for part in parts)


class CodexCliAdapter(CliAgentAdapter):
    """Run OpenAI Codex CLI in non-interactive exec mode."""

    @classmethod
    def from_env(
        cls,
        artifact_dir: Path | None = None,
        env_overrides: dict[str, str] | None = None,
    ) -> CliAgentAdapter:
        return build_cli_adapter_from_env(
            agent_name="codex",
            env_prefix="CODEX",
            default_command="codex",
            default_cli_args=_default_cli_args(),
            default_query_flag="",
            default_append_query_flag=True,
            default_stdin_mode=False,
            default_api_key_env="OPENAI_API_KEY",
            default_api_key_source_env="CODEX_API_KEY",
            # Default False so OAuth flows ("codex login --device-auth" -> CODEX_HOME/auth.json)
            # are accepted without forcing OPENAI_API_KEY env. Codex CLI prefers OAuth when present.
            default_require_api_key=False,
            env_overrides=env_overrides,
            artifact_dir=artifact_dir,
        )
