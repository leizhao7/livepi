from __future__ import annotations

from pathlib import Path
import os
import shlex

from prompt_injection_lab.agents.cli_adapter import CliAgentAdapter, build_cli_adapter_from_env


DEFAULT_HERMES_SKILLS = "imap-smtp-email,solana,livepi-chat-channels"


def _default_cli_args() -> str:
    parts = ["chat"]
    provider = os.getenv("HERMES_PROVIDER", "openrouter").strip()
    model = os.getenv("HERMES_MODEL", "").strip()
    toolsets = os.getenv("HERMES_TOOLSETS", "terminal,skills").strip()
    preload_skills = os.getenv("HERMES_PRELOAD_SKILLS", DEFAULT_HERMES_SKILLS).strip()
    quiet = os.getenv("HERMES_QUIET", "false").strip().lower() in {"1", "true", "yes", "on"}
    # Default --yolo on for benchmark: every shell tool call would otherwise
    # block on an interactive y/n prompt and time out as 'User denied this command'.
    yolo = os.getenv("HERMES_YOLO", "true").strip().lower() in {"1", "true", "yes", "on"}
    if provider:
        parts.extend(["--provider", provider])
    if model:
        parts.extend(["--model", model])
    if toolsets:
        parts.extend(["--toolsets", toolsets])
    if preload_skills:
        parts.extend(["--skills", preload_skills])
    if quiet:
        parts.append("-Q")
    if yolo:
        parts.append("--yolo")
    return " ".join(shlex.quote(part) for part in parts)


class HermesCliAdapter(CliAgentAdapter):
    """Run Hermes Agent through its non-interactive CLI query mode."""

    @classmethod
    def from_env(
        cls,
        artifact_dir: Path | None = None,
        env_overrides: dict[str, str] | None = None,
    ) -> CliAgentAdapter:
        return build_cli_adapter_from_env(
            agent_name="hermes",
            env_prefix="HERMES",
            default_command="hermes",
            default_cli_args=_default_cli_args(),
            default_query_flag="-q",
            default_append_query_flag=True,
            default_stdin_mode=False,
            default_api_key_env="OPENROUTER_API_KEY",
            default_api_key_source_env="HERMES_API_KEY",
            default_require_api_key=False,
            env_overrides=env_overrides,
            artifact_dir=artifact_dir,
        )
