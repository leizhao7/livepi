from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def split_command(value: str, default: str) -> list[str]:
    text = value.strip() or default
    parts = shlex.split(text)
    if not parts:
        raise RuntimeError(f"Empty command after parsing: {value!r}")
    return parts


def _has_model_arg(args: list[str]) -> bool:
    return any(arg in {"-m", "--model"} or arg.startswith("--model=") for arg in args)


def _extract_tool_calls_codex_jsonl(stdout: str) -> list[dict[str, Any]]:
    """Parse 'codex exec --json' JSONL stream into tool_calls_observed.

    Codex emits one JSON object per line: thread.started, turn.started,
    item.started, item.completed (for each command_execution / agent_message),
    turn.completed (with token usage). We collect command_execution items as
    structured tool calls and drop everything else."""
    import json as _json
    calls: list[dict[str, Any]] = []
    for raw in stdout.splitlines():
        line = raw.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            ev = _json.loads(line)
        except Exception:
            continue
        if ev.get("type") != "item.completed":
            continue
        item = ev.get("item") or {}
        if item.get("type") != "command_execution":
            continue
        calls.append({
            "index": len(calls),
            "source": "codex_json_event",
            "command": (item.get("command") or "")[:1500],
            "output": (item.get("aggregated_output") or "")[:1500],
            "exit_code": item.get("exit_code"),
            "status": item.get("status"),
        })
    return calls


def _extract_tool_calls_from_stdout(agent_name: str, stdout: str) -> list[dict[str, Any]]:
    """Best-effort parse of tool calls from agent CLI stdout.

    Hermes (when not in -Q quiet mode) emits a verbose transcript:
      - one or more tool-preview blocks, each starting with
        "  ┊ <emoji> $         <command>" followed by command body lines,
      - a final response box drawn with ╭/╰ characters,
      - a session footer with "Messages: N (M user, K tool calls)".

    We extract a structured entry per detected block (command head + body),
    and reconcile against the session-summary count. If the parser finds
    no blocks but the summary reports K calls, we return K stub entries
    so downstream consumers still see the count."""
    if not stdout:
        return []
    if agent_name == "codex":
        return _extract_tool_calls_codex_jsonl(stdout)
    if agent_name != "hermes":
        return []

    summary_count: int | None = None
    for raw in stdout.splitlines():
        line = raw.strip()
        if not line.startswith("Messages:") or "tool call" not in line:
            continue
        try:
            tail = line.split("(", 1)[1]
        except IndexError:
            continue
        for part in tail.split(","):
            chunk = part.strip().rstrip(")").strip()
            if chunk.endswith("tool calls") or chunk.endswith("tool call"):
                try:
                    summary_count = int(chunk.split()[0])
                except (ValueError, IndexError):
                    summary_count = None

    BLOCK_PREFIX = "  ┊ "
    FOOTER_PREFIXES = ("Resume this session", "Session:", "Duration:", "Messages:")
    blocks: list[list[str]] = []
    current: list[str] | None = None
    for raw in stdout.splitlines():
        if raw.startswith(BLOCK_PREFIX):
            if current is not None:
                blocks.append(current)
            current = [raw]
            continue
        if current is None:
            continue
        stripped = raw.lstrip()
        if raw.startswith("╭") or raw.startswith("╰") or any(stripped.startswith(p) for p in FOOTER_PREFIXES):
            blocks.append(current)
            current = None
            continue
        current.append(raw)
    if current is not None:
        blocks.append(current)

    tool_calls: list[dict[str, Any]] = []
    for idx, block_lines in enumerate(blocks):
        header = block_lines[0][len(BLOCK_PREFIX):].rstrip()
        if "$" in header:
            tool_type, _, cmd_head = header.partition("$")
            tool_type = tool_type.strip()
            command_head = cmd_head.lstrip()
        else:
            parts = header.split(None, 1)
            tool_type = parts[0] if parts else ""
            command_head = parts[1] if len(parts) > 1 else ""
        body_lines = [line.rstrip() for line in block_lines[1:]]
        command_full = command_head
        if body_lines:
            command_full = command_full + ("\n" if command_full else "") + "\n".join(body_lines)
        tool_calls.append({
            "index": idx,
            "source": "hermes_stdout_parse",
            "tool_type": tool_type,
            "command": command_full[:1500],
        })

    if not tool_calls and summary_count:
        return [
            {"index": i, "source": "hermes_session_summary_fallback"}
            for i in range(summary_count)
        ]
    if summary_count is not None and tool_calls and len(tool_calls) != summary_count:
        tool_calls[0]["expected_total_from_summary"] = summary_count
    return tool_calls


@dataclass
class CliAgentAdapter:
    """Run an agent CLI through one non-interactive benchmark prompt."""

    agent_name: str
    command: list[str]
    cli_args: list[str]
    query_flag: str
    append_query_flag: bool
    stdin_mode: bool
    workdir: Path | None
    artifact_dir: Path | None = None
    api_key_env: str = ""
    api_key_source_env: str = ""
    require_api_key: bool = False
    env_overrides: dict[str, str] | None = None

    def connect(self) -> dict[str, Any]:
        prefix = self.agent_name.upper()
        return {
            "agent": self.agent_name,
            "mode": "cli",
            "command": self.command[0],
            "command_arg_count": max(0, len(self.command) - 1),
            "cli_arg_count": len(self.cli_args),
            "stdin_mode": self.stdin_mode,
            "append_query_flag": self.append_query_flag,
            "query_flag": self.query_flag,
            "workdir": str(self.workdir) if self.workdir else "",
            "model": self._env_value(f"{prefix}_MODEL"),
            "api_key_env": self.api_key_env,
            "api_key_source_env": self.api_key_source_env,
            "api_key_present": self._api_key_present(),
            "agent_home": self._env_value(f"{prefix}_AGENT_HOME"),
            "skills_dir": self._env_value(f"{prefix}_SKILLS_DIR"),
            "env_override_keys": sorted((self.env_overrides or {}).keys()),
        }

    def send_chat_and_wait(
        self,
        *,
        message: str,
        timeout_s: int,
        session_key: str = "",
    ) -> dict[str, Any]:
        env = self._subprocess_env()
        started = time.time()
        run_id = str(uuid.uuid4())
        cmd = [*self.command, *self.cli_args]
        if self.append_query_flag:
            if self.query_flag:
                cmd.extend([self.query_flag, message])
            else:
                cmd.append(message)

        input_text = message if self.stdin_mode else None
        event: dict[str, Any] = {
            "run_id": run_id,
            "session_key": session_key,
            "command": _redact_command(cmd),
            "stdin_mode": self.stdin_mode,
            "api_key_env": self.api_key_env,
            "api_key_present": self._api_key_present(env),
        }

        try:
            completed = subprocess.run(  # noqa: S603
                cmd,
                input=input_text,
                text=True,
                capture_output=True,
                timeout=max(1, int(timeout_s)),
                cwd=str(self.workdir) if self.workdir else None,
                env=env,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"{self.agent_name} command was not found. Install the CLI or set "
                f"{self.agent_name.upper()}_COMMAND to an SSH/wrapper command."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            stdout = (exc.stdout or "").strip() if isinstance(exc.stdout, str) else ""
            stderr = (exc.stderr or "").strip() if isinstance(exc.stderr, str) else ""
            result = {
                "run_id": run_id,
                "state": "timeout",
                "assistant_text": stdout,
                "event_count": 1,
                "events": [
                    {
                        **event,
                        "returncode": None,
                        "duration_s": round(time.time() - started, 3),
                        "stdout": stdout[-2000:],
                        "stderr": stderr[-2000:],
                        "error": f"timed out after {timeout_s}s",
                    }
                ],
                "agent_events": [],
                "agent_event_count": 0,
                "tool_calls_observed": [],
            }
            self._write_artifact(result)
            return result

        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        state = "complete" if completed.returncode == 0 else "error"
        tool_calls_from_stdout = _extract_tool_calls_from_stdout(self.agent_name, stdout)
        event.update(
            {
                "returncode": completed.returncode,
                "duration_s": round(time.time() - started, 3),
                "stdout": stdout[-4000:],
                "stderr": stderr[-4000:],
            }
        )
        agent_events = [
            {
                "state": state,
                "message_text": stdout[-4000:] if stdout else stderr[-1000:],
                "returncode": completed.returncode,
            }
        ]
        result = {
            "run_id": run_id,
            "state": state,
            "assistant_text": stdout,
            "event_count": 1,
            "events": [event],
            "agent_events": agent_events,
            "agent_event_count": len(agent_events),
            "tool_calls_observed": tool_calls_from_stdout,
        }
        self._write_artifact(result)
        return result

    def close(self) -> None:
        return None

    def _subprocess_env(self) -> dict[str, str]:
        env = dict(os.environ)
        if self.env_overrides:
            env.update(self.env_overrides)
        if self.api_key_env:
            source_value = env.get(self.api_key_source_env, "").strip() if self.api_key_source_env else ""
            target_value = env.get(self.api_key_env, "").strip()
            if source_value:
                env[self.api_key_env] = source_value
            elif target_value:
                env[self.api_key_env] = target_value
            elif self.require_api_key:
                accepted = [self.api_key_env]
                if self.api_key_source_env and self.api_key_source_env != self.api_key_env:
                    accepted.append(self.api_key_source_env)
                raise RuntimeError(
                    f"{self.agent_name} requires an API key. Set one of: {', '.join(accepted)}."
                )
        return env

    def _api_key_present(self, env: dict[str, str] | None = None) -> bool:
        values = env or os.environ
        if env is None and self.env_overrides:
            values = {**values, **self.env_overrides}
        return bool(
            (self.api_key_env and values.get(self.api_key_env, "").strip())
            or (self.api_key_source_env and values.get(self.api_key_source_env, "").strip())
        )

    def _env_value(self, key: str) -> str:
        if self.env_overrides and key in self.env_overrides:
            return self.env_overrides[key]
        return os.getenv(key, "")

    def _write_artifact(self, payload: dict[str, Any]) -> None:
        if self.artifact_dir is None:
            return
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{self.agent_name}_cli_result.json"
        (self.artifact_dir / filename).write_text(
            json.dumps(payload, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )


def build_cli_adapter_from_env(
    *,
    agent_name: str,
    env_prefix: str,
    default_command: str,
    default_cli_args: str,
    default_query_flag: str,
    default_append_query_flag: bool,
    default_stdin_mode: bool,
    default_api_key_env: str = "",
    default_api_key_source_env: str = "",
    default_require_api_key: bool = False,
    env_overrides: dict[str, str] | None = None,
    artifact_dir: Path | None = None,
) -> CliAgentAdapter:
    prefix = env_prefix.upper()
    override_values = env_overrides or {}

    def _env_config(name: str, default: str = "") -> str:
        return os.getenv(name, "").strip() or override_values.get(name, "").strip() or default

    stdin_mode = env_bool(f"{prefix}_STDIN", default_stdin_mode)
    append_query_flag = env_bool(f"{prefix}_APPEND_QUERY_FLAG", default_append_query_flag)
    workdir_raw = (
        os.getenv(f"{prefix}_WORKDIR", "").strip()
        or override_values.get(f"{prefix}_WORKDIR", "").strip()
    )
    api_key_env = _env_config(f"{prefix}_API_KEY_ENV", default_api_key_env)
    api_key_source_env = _env_config(f"{prefix}_API_KEY_SOURCE_ENV", default_api_key_source_env)
    require_api_key = env_bool(f"{prefix}_REQUIRE_API_KEY", default_require_api_key)
    cli_args = shlex.split(_env_config(f"{prefix}_CLI_ARGS", default_cli_args))
    model_value = _env_config(f"{prefix}_MODEL")
    if model_value and not _has_model_arg(cli_args):
        cli_args.extend(["--model", model_value])
    return CliAgentAdapter(
        agent_name=agent_name,
        command=split_command(_env_config(f"{prefix}_COMMAND"), default_command),
        cli_args=cli_args,
        query_flag=os.getenv(f"{prefix}_QUERY_FLAG", default_query_flag).strip(),
        append_query_flag=append_query_flag,
        stdin_mode=stdin_mode,
        workdir=Path(workdir_raw).expanduser() if workdir_raw else None,
        artifact_dir=artifact_dir,
        api_key_env=api_key_env,
        api_key_source_env=api_key_source_env,
        require_api_key=require_api_key,
        env_overrides=env_overrides,
    )


def _redact_command(cmd: list[str]) -> list[str]:
    redacted: list[str] = []
    sensitive_next = False
    for part in cmd:
        lowered = part.lower()
        if sensitive_next:
            redacted.append("<redacted>")
            sensitive_next = False
            continue
        redacted.append(part)
        if lowered in {"--api-key", "--token", "--password", "--secret"}:
            sensitive_next = True
    return redacted
