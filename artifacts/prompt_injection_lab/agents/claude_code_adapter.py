from __future__ import annotations

import os
import shlex
from pathlib import Path

from prompt_injection_lab.agents.cli_adapter import CliAgentAdapter, build_cli_adapter_from_env


def _default_cli_args() -> str:
    parts = ["--bare", "--dangerously-skip-permissions", "--no-session-persistence"]
    model = os.getenv("CLAUDE_CODE_MODEL", "").strip()
    if model:
        parts.extend(["--model", model])
    return " ".join(shlex.quote(part) for part in parts)


class ClaudeCodeCliAdapter(CliAgentAdapter):
    """Run Claude Code in non-interactive print mode.

    Claude Code is **not** compatible with OpenRouter's Anthropic endpoint
    because the CLI does client-side model existence validation that
    OpenRouter does not satisfy. To run this agent, set ANTHROPIC_API_KEY
    (from https://console.anthropic.com/settings/keys) or complete the
    Claude.ai OAuth flow via `claude setup-token`.
    """

    @classmethod
    def from_env(
        cls,
        artifact_dir: Path | None = None,
        env_overrides: dict[str, str] | None = None,
    ) -> CliAgentAdapter:
        # Set IS_SANDBOX=1 so claude allows --dangerously-skip-permissions
        # while running as root inside the benchmark container.
        merged_overrides: dict[str, str] = {"IS_SANDBOX": "1"}
        if env_overrides:
            merged_overrides.update(env_overrides)
        return build_cli_adapter_from_env(
            agent_name="claude_code",
            env_prefix="CLAUDE_CODE",
            default_command="claude",
            default_cli_args=_default_cli_args(),
            default_query_flag="-p",
            default_append_query_flag=True,
            default_stdin_mode=False,
            default_api_key_env="ANTHROPIC_API_KEY",
            default_api_key_source_env="CLAUDE_CODE_API_KEY",
            # Default False so OAuth (claude setup-token) or any user-provided
            # ANTHROPIC_API_KEY is accepted without forcing the env. claude
            # will fail loudly at first request if neither is configured.
            default_require_api_key=False,
            env_overrides=merged_overrides,
            artifact_dir=artifact_dir,
        )
