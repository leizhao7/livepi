from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from livepi_bench.config import default_image, default_network


def _existing_env_file(repo: Path, env_file: str | None) -> Path | None:
    if env_file:
        path = Path(env_file).expanduser()
        if not path.is_absolute():
            path = repo / path
        return path if path.exists() else None
    for candidate in ("secrets.env", "prompt_injection_lab/.env"):
        path = repo / candidate
        if path.exists():
            return path
    return None


def _ssh_mount_flags(repo: Path) -> list[str]:
    ssh_dir = Path(os.getenv("LIVEPI_SSH_DIR", str(Path.home() / ".ssh"))).expanduser()
    if ssh_dir.exists():
        return ["-v", f"{ssh_dir}:/root/.ssh:ro"]
    return []


def _truthy(value: str | None, default: bool = False) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _copy_repo_to_isolated_workspace(repo: Path) -> tuple[Path, Path]:
    work_root = Path(os.getenv("LIVEPI_DOCKER_WORK_ROOT", tempfile.gettempdir())).expanduser()
    work_root.mkdir(parents=True, exist_ok=True)
    run_root = Path(tempfile.mkdtemp(prefix="livepi-run.", dir=str(work_root)))
    workspace = run_root / "workspace"
    ignore = shutil.ignore_patterns(
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".livepi_docker_runs",
        ".livepi_agent_runtime",
        ".livepi-agent-home",
        "results",
        "results_*",
    )
    shutil.copytree(repo, workspace, ignore=ignore)
    (workspace / "prompt_injection_lab" / "results").mkdir(parents=True, exist_ok=True)
    return run_root, workspace


def _copy_results_back(workspace: Path, repo: Path) -> None:
    src = workspace / "prompt_injection_lab" / "results"
    if not src.exists():
        return
    dst = repo / "prompt_injection_lab" / "results"
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, dirs_exist_ok=True)


def _docker_env_flags(repo: Path, env_file: str | None) -> list[str]:
    flags: list[str] = [
        "-e",
        "PYTHONUNBUFFERED=1",
        "-e",
        "LIVEPI_BUNDLED_SKILLS_SOURCE=/opt/livepi/prompt_injection_lab/fixtures/skills",
    ]
    resolved = _existing_env_file(repo, env_file)
    if resolved is not None:
        flags.extend(["--env-file", str(resolved)])
    for key in (
        "OPENCLAW_GATEWAY_TOKEN",
        "OPENCLAW_GATEWAY_PASSWORD",
        "LIVEPI_REMOTE_HOST",
        "OPENCLAW_SSH_HOST",
        "OPENCLAW_PROFILE",
        "OPENCLAW_TUNNEL_LOCAL_PORT",
        "OPENCLAW_TUNNEL_REMOTE_PORT",
        "OPENCLAW_GATEWAY_IDENTITY_FILE",
        "OPENCLAW_SSH_OPTIONS",
        "LIVEPI_SSH_OPTIONS",
        "OPENCLAW_PRIMARY_MODEL",
        "OPENCLAW_WORKSPACE",
        "OPENCLAW_BENCHMARK_RECIPIENT_EMAIL",
        "OPENCLAW_BENCHMARK_SCAN_PY_URL",
        "OPENCLAW_BENCHMARK_SCAN_PY_SOURCE_URL",
        "OPENCLAW_BENCHMARK_SCAN_PY_OWNER",
        "OPENCLAW_BENCHMARK_SCAN_PY_REPO",
        "OPENCLAW_BENCHMARK_SCAN_PY_BRANCH",
        "OPENCLAW_BENCHMARK_SCAN_PY_PATH",
        "OPENCLAW_BENCHMARK_SCAN_PY_PRIVATE",
        "OPENCLAW_BENCHMARK_WALLET_FILE_PATH",
        "TEST_RECIPIENT_EMAIL",
        "TEST_CLEANUP_EMAIL",
        "LLM_JUDGE_PROVIDER",
        "LLM_JUDGE_MODEL",
        "OPENAI_BASE_URL",
        "OPENAI_ORG_ID",
        "OPENROUTER_API_KEY",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_AUTH_TOKEN",
        "MOONSHOT_API_KEY",
        "MODELSTUDIO_API_KEY",
        "ZAI_API_KEY",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_SECURE",
        "SMTP_STARTTLS",
        "SMTP_REJECT_UNAUTHORIZED",
        "SMTP_USER",
        "SMTP_PASS",
        "SMTP_FROM",
        "ATTACKER_SMTP_HOST",
        "ATTACKER_SMTP_PORT",
        "ATTACKER_SMTP_SECURE",
        "ATTACKER_SMTP_STARTTLS",
        "ATTACKER_SMTP_REJECT_UNAUTHORIZED",
        "ATTACKER_SMTP_USER",
        "ATTACKER_SMTP_PASS",
        "ATTACKER_SMTP_FROM",
        "GMAIL_SENDER",
        "GMAIL_ACCESS_TOKEN",
        "GMAIL_REFRESH_TOKEN",
        "GMAIL_CLIENT_ID",
        "GMAIL_CLIENT_SECRET",
        "IMAP_HOST",
        "IMAP_PORT",
        "IMAP_TLS",
        "IMAP_USER",
        "IMAP_PASS",
        "IMAP_MAILBOX",
        "IMAP_REJECT_UNAUTHORIZED",
        "IMAP_TIMEOUT_S",
        "VERIFY_IMAP_HOST",
        "VERIFY_IMAP_PORT",
        "VERIFY_IMAP_TLS",
        "VERIFY_IMAP_USER",
        "VERIFY_IMAP_PASS",
        "VERIFY_IMAP_MAILBOX",
        "VERIFY_IMAP_REJECT_UNAUTHORIZED",
        "VERIFY_IMAP_TIMEOUT_S",
        "VERIFY_IMAP_BEFORE_LIMIT",
        "VERIFY_IMAP_AFTER_LIMIT",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_AGENT_BOT_TOKEN",
        "TELEGRAM_BENCHMARK_BOT_TOKEN",
        "TELEGRAM_USER_API_ID",
        "TELEGRAM_USER_API_HASH",
        "TELEGRAM_USER_SESSION",
        "TELEGRAM_USER_SESSION_FILE",
        "TELEGRAM_USER_PHONE",
        "TELEGRAM_GROUP_ID",
        "TELEGRAM_GROUP_IDS",
        "TELEGRAM_AGENT_MENTION",
        "TELEGRAM_AGENT_USERNAME",
        "TELEGRAM_REQUIRE_MENTION",
        "TELEGRAM_GROUP_POLICY",
        "TELEGRAM_KEEP_BENCHMARK_MESSAGES",
        "LIVEPI_KEEP_TELEGRAM_MESSAGES",
        "SLACK_BOT_TOKEN",
        "SLACK_SENDER_TOKEN",
        "SLACK_ATTACKER_USER_TOKEN",
        "SLACK_BENCHMARK_USER_TOKEN",
        "SLACK_APP_TOKEN",
        "SLACK_CHANNEL_ID",
        "SLACK_AGENT_MENTION",
        "SLACK_AGENT_USERNAME",
        "SLACK_REQUIRE_MENTION",
        "SLACK_KEEP_BENCHMARK_MESSAGES",
        "LIVEPI_KEEP_SLACK_MESSAGES",
        "SLACK_WEBHOOK_PATH",
        "SLACK_USER_TOKEN_READ_ONLY",
        "SLACK_GROUP_POLICY",
        "OPENCLAW_ENABLE_WHATSAPP",
        "WHATSAPP_API_URL",
        "WHATSAPP_ACCESS_TOKEN",
        "WHATSAPP_GROUP_ID",
        "WHATSAPP_AGENT_MENTION",
        "WHATSAPP_EXTRA_PAYLOAD_JSON",
        "WHATSAPP_DEFAULT_TO",
        "WHATSAPP_GROUP_ALLOW_FROM",
        "WHATSAPP_REQUIRE_MENTION",
        "WHATSAPP_GROUP_POLICY",
        "WHATSAPP_BRIDGE_ENABLED",
        "WHATSAPP_BRIDGE_AUTH_DIR",
        "WHATSAPP_BRIDGE_HOST",
        "WHATSAPP_BRIDGE_PORT",
        "WHATSAPP_BRIDGE_DEFAULT_MENTIONS",
        "GITHUB_TOKEN",
        "GITHUB_GIST_TOKEN",
        "GIST_TUTORIAL_FIXED_URL",
        "GITHUB_OWNER",
        "GITHUB_REPO",
        "GITHUB_BRANCH",
        "GITHUB_FILE_PATH",
        "GITHUB_FILE_URL",
        "GITHUB_SUPPLY_CHAIN_TOKEN",
        "GITHUB_SUPPLY_CHAIN_OWNER",
        "GITHUB_SUPPLY_CHAIN_REPO",
        "GITHUB_SUPPLY_CHAIN_BRANCH",
        "GITHUB_SUPPLY_CHAIN_PRIVATE",
        "GITHUB_SUPPLY_CHAIN_SHARE_LINK",
        "GITHUB_SUPPLY_CHAIN_PREPARE",
        "GITHUB_SUPPLY_CHAIN_CDN_WAIT_S",
        "GITHUB_SUPPLY_CHAIN_POST_TRIGGER_WAIT_S",
        "SOLANA_PRIVATE_KEY",
        "SOLANA_RPC_URL",
        "SOLANA_ATTACKER_ADDRESS",
        "OPENCLAW_BENCHMARK_SOLANA_RECIPIENT_ADDRESS",
        "TEST_SOLANA_RECIPIENT_ADDRESS",
        "JUPITER_API_KEY",
        "REDDIT_CLIENT_ID",
        "REDDIT_CLIENT_SECRET",
        "REDDIT_USERNAME",
        "REDDIT_PASSWORD",
        "REDDIT_SUBREDDIT",
        "X_API_KEY",
        "X_API_SECRET",
        "X_ACCESS_TOKEN",
        "X_ACCESS_SECRET",
        "LIVEPI_AGENT",
        "LIVEPI_CLI_AGENT_INCLUDE_GUIDE_PROMPT",
        "LIVEPI_BUNDLED_SKILLS_SOURCE",
        "HERMES_COMMAND",
        "HERMES_CLI_ARGS",
        "HERMES_QUERY_FLAG",
        "HERMES_APPEND_QUERY_FLAG",
        "HERMES_STDIN",
        "HERMES_WORKDIR",
        "HERMES_API_KEY",
        "HERMES_API_KEY_ENV",
        "HERMES_API_KEY_SOURCE_ENV",
        "HERMES_REQUIRE_API_KEY",
        "HERMES_RUNTIME_ROOT",
        "HERMES_AGENT_HOME",
        "HERMES_HOME",
        "HERMES_SKILLS_DIR",
        "HERMES_INSTALL_BUNDLED_SKILLS",
        "HERMES_MODEL",
        "HERMES_PROVIDER",
        "HERMES_TOOLSETS",
        "HERMES_PRELOAD_SKILLS",
        "HERMES_QUIET",
        "HERMES_TELEGRAM_BOT_TOKEN",
        "HERMES_TELEGRAM_GROUP_ID",
        "HERMES_TELEGRAM_AGENT_MENTION",
        "HERMES_TELEGRAM_AGENT_USERNAME",
        "HERMES_SLACK_BOT_TOKEN",
        "HERMES_SLACK_CHANNEL_ID",
        "HERMES_SLACK_AGENT_MENTION",
        "HERMES_SLACK_AGENT_USERNAME",
        "HERMES_WHATSAPP_API_URL",
        "HERMES_WHATSAPP_ACCESS_TOKEN",
        "HERMES_WHATSAPP_GROUP_ID",
        "HERMES_WHATSAPP_AGENT_MENTION",
        "LIVEPI_AGENT_RUNTIME_ROOT",
        "CODEX_COMMAND",
        "CODEX_MODEL",
        "CODEX_CLI_ARGS",
        "CODEX_QUERY_FLAG",
        "CODEX_APPEND_QUERY_FLAG",
        "CODEX_STDIN",
        "CODEX_WORKDIR",
        "CODEX_RUNTIME_ROOT",
        "CODEX_AGENT_HOME",
        "CODEX_HOME",
        "CODEX_SKILLS_DIR",
        "CODEX_INSTALL_BUNDLED_SKILLS",
        "CODEX_TELEGRAM_BOT_TOKEN",
        "CODEX_TELEGRAM_GROUP_ID",
        "CODEX_TELEGRAM_AGENT_MENTION",
        "CODEX_TELEGRAM_AGENT_USERNAME",
        "CODEX_SLACK_BOT_TOKEN",
        "CODEX_SLACK_CHANNEL_ID",
        "CODEX_SLACK_AGENT_MENTION",
        "CODEX_SLACK_AGENT_USERNAME",
        "CODEX_WHATSAPP_API_URL",
        "CODEX_WHATSAPP_ACCESS_TOKEN",
        "CODEX_WHATSAPP_GROUP_ID",
        "CODEX_WHATSAPP_AGENT_MENTION",
        "CODEX_API_KEY",
        "CODEX_API_KEY_ENV",
        "CODEX_API_KEY_SOURCE_ENV",
        "CODEX_REQUIRE_API_KEY",
        "CLAUDE_CODE_COMMAND",
        "CLAUDE_CODE_MODEL",
        "CLAUDE_CODE_CLI_ARGS",
        "CLAUDE_CODE_QUERY_FLAG",
        "CLAUDE_CODE_APPEND_QUERY_FLAG",
        "CLAUDE_CODE_STDIN",
        "CLAUDE_CODE_WORKDIR",
        "CLAUDE_CODE_RUNTIME_ROOT",
        "CLAUDE_CODE_AGENT_HOME",
        "CLAUDE_CODE_SKILLS_DIR",
        "CLAUDE_CODE_INSTALL_BUNDLED_SKILLS",
        "CLAUDE_CONFIG_DIR",
        "CLAUDE_CODE_TELEGRAM_BOT_TOKEN",
        "CLAUDE_CODE_TELEGRAM_GROUP_ID",
        "CLAUDE_CODE_TELEGRAM_AGENT_MENTION",
        "CLAUDE_CODE_TELEGRAM_AGENT_USERNAME",
        "CLAUDE_CODE_SLACK_BOT_TOKEN",
        "CLAUDE_CODE_SLACK_CHANNEL_ID",
        "CLAUDE_CODE_SLACK_AGENT_MENTION",
        "CLAUDE_CODE_SLACK_AGENT_USERNAME",
        "CLAUDE_CODE_WHATSAPP_API_URL",
        "CLAUDE_CODE_WHATSAPP_ACCESS_TOKEN",
        "CLAUDE_CODE_WHATSAPP_GROUP_ID",
        "CLAUDE_CODE_WHATSAPP_AGENT_MENTION",
        "CLAUDE_CODE_API_KEY",
        "CLAUDE_CODE_API_KEY_ENV",
        "CLAUDE_CODE_API_KEY_SOURCE_ENV",
        "CLAUDE_CODE_REQUIRE_API_KEY",
    ):
        if os.environ.get(key):
            flags.extend(["-e", key])
    return flags


def _container_env_file_arg(repo: Path, env_path: Path | None) -> str:
    if env_path is None:
        return ""
    try:
        rel = env_path.resolve().relative_to(repo.resolve())
    except ValueError:
        return ""
    return str(Path("/workspace") / rel)


def _container_repo_path_arg(repo: Path, value: str) -> str:
    text = str(value).strip()
    if not text:
        return text
    path = Path(text).expanduser()
    if not path.is_absolute():
        return text
    try:
        rel = path.resolve().relative_to(repo.resolve())
    except ValueError:
        return text
    return str(Path("/workspace") / rel)


def _map_container_path_args(repo: Path, args: list[str]) -> list[str]:
    mapped = list(args)
    path_flags = {"--results-root", "--batch-output-jsonl", "--env-file"}
    idx = 0
    while idx < len(mapped):
        item = mapped[idx]
        if item in path_flags and idx + 1 < len(mapped):
            mapped[idx + 1] = _container_repo_path_arg(repo, mapped[idx + 1])
            idx += 2
            continue
        for flag in path_flags:
            prefix = f"{flag}="
            if item.startswith(prefix):
                mapped[idx] = prefix + _container_repo_path_arg(repo, item[len(prefix) :])
                break
        idx += 1
    return mapped


def _has_cli_flag(args: list[str], flag: str) -> bool:
    return any(item == flag or item.startswith(f"{flag}=") for item in args)


def run_surface_test_in_docker(
    *,
    repo: Path,
    surface_args: list[str],
    image: str | None = None,
    env_file: str | None = None,
    cpus: str = "4",
    memory: str = "8g",
    network: str | None = None,
) -> int:
    repo = repo.resolve()
    logs_dir = repo / "prompt_injection_lab" / "results" / "_docker_runner_logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    isolated_workspace = _truthy(os.getenv("LIVEPI_DOCKER_ISOLATED_WORKSPACE"), default=True)
    run_root: Path | None = None
    mount_repo = repo
    if isolated_workspace:
        run_root, mount_repo = _copy_repo_to_isolated_workspace(repo)
    selected_image = image or default_image()
    selected_network = network or default_network()
    resolved_env_file = _existing_env_file(mount_repo, env_file)
    surface_args_for_container = _map_container_path_args(repo, list(surface_args))
    container_env_file = _container_env_file_arg(mount_repo, resolved_env_file)
    run_surface_env_file = container_env_file or ("/dev/null" if resolved_env_file is not None else "")
    if run_surface_env_file and not _has_cli_flag(surface_args_for_container, "--env-file"):
        surface_args_for_container.extend(["--env-file", run_surface_env_file])
    cmd = [
        "docker",
        "run",
        "--rm",
        "--network",
        selected_network,
        "--cpus",
        cpus,
        "--memory",
        memory,
        "--add-host",
        "host.docker.internal:host-gateway",
        "-v",
        f"{mount_repo}:/workspace",
        "-w",
        "/workspace",
        *_ssh_mount_flags(repo),
        *_docker_env_flags(mount_repo, env_file),
        selected_image,
        "python3",
        "prompt_injection_lab/scripts/run_surface_test.py",
        *surface_args_for_container,
    ]
    log_payload = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "repo": str(repo),
        "image": selected_image,
        "network": selected_network,
        "cpus": cpus,
        "memory": memory,
        "isolated_workspace": isolated_workspace,
        "mount_repo": str(mount_repo),
        "command": cmd,
    }
    (logs_dir / "last_docker_command.json").write_text(
        json.dumps(log_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    try:
        process = subprocess.Popen(cmd)  # noqa: S603
        return_code = process.wait()
        if isolated_workspace:
            _copy_results_back(mount_repo, repo)
        return return_code
    finally:
        if run_root is not None:
            shutil.rmtree(run_root, ignore_errors=True)


def run_smoke_checks_in_docker(
    *,
    repo: Path,
    image: str | None = None,
    network: str | None = None,
) -> int:
    repo = repo.resolve()
    selected_image = image or default_image()
    selected_network = network or default_network()
    script = (
        "set -euo pipefail && "
        "python3 prompt_injection_lab/scripts/audit_techniques.py && "
        "python3 prompt_injection_lab/scripts/audit_benchmark_matrix.py && "
        "python3 prompt_injection_lab/scripts/validate_tasks.py && "
        "python3 prompt_injection_lab/scripts/generate_prompt.py --list-tags && "
        "rm -rf /tmp/livepi-docker-smoke-results /tmp/livepi-docker-smoke-runtime && "
        "LIVEPI_AGENT_RUNTIME_ROOT=/tmp/livepi-docker-smoke-runtime "
        "HERMES_COMMAND=/bin/echo HERMES_REQUIRE_API_KEY=false "
        "HERMES_CLI_ARGS='' HERMES_QUERY_FLAG=-q HERMES_APPEND_QUERY_FLAG=true "
        "python3 prompt_injection_lab/scripts/run_surface_test.py "
        "--agent hermes --base-model smoke-hermes "
        "--surface-tag direct_chat_txt --technique-tag checklist_handoff_injection "
        "--malicious-task-tag email_summary_to_external --chat-timeout-s 15 "
        "--results-root /tmp/livepi-docker-smoke-results --env-file /dev/null "
        ">/tmp/livepi-hermes-smoke.json && "
        "LIVEPI_AGENT_RUNTIME_ROOT=/tmp/livepi-docker-smoke-runtime "
        "CODEX_COMMAND=/bin/echo CODEX_REQUIRE_API_KEY=false "
        "CODEX_CLI_ARGS='exec --skip-git-repo-check --ephemeral' CODEX_APPEND_QUERY_FLAG=true "
        "python3 prompt_injection_lab/scripts/run_surface_test.py "
        "--agent codex --base-model smoke-codex "
        "--surface-tag direct_chat_txt --technique-tag checklist_handoff_injection "
        "--malicious-task-tag email_summary_to_external --chat-timeout-s 15 "
        "--results-root /tmp/livepi-docker-smoke-results --env-file /dev/null "
        ">/tmp/livepi-codex-smoke.json && "
        "LIVEPI_AGENT_RUNTIME_ROOT=/tmp/livepi-docker-smoke-runtime "
        "CLAUDE_CODE_COMMAND=/bin/echo CLAUDE_CODE_REQUIRE_API_KEY=false "
        "CLAUDE_CODE_CLI_ARGS='--bare --no-session-persistence' "
        "CLAUDE_CODE_QUERY_FLAG=-p CLAUDE_CODE_APPEND_QUERY_FLAG=true "
        "python3 prompt_injection_lab/scripts/run_surface_test.py "
        "--agent claude_code --base-model smoke-claude-code "
        "--surface-tag direct_chat_txt --technique-tag checklist_handoff_injection "
        "--malicious-task-tag email_summary_to_external --chat-timeout-s 15 "
        "--results-root /tmp/livepi-docker-smoke-results --env-file /dev/null "
        ">/tmp/livepi-claude-code-smoke.json && "
        "python3 - <<'PY'\n"
        "import json\n"
        "from pathlib import Path\n"
        "for name in ('hermes', 'codex', 'claude-code'):\n"
        "    data = json.loads(Path(f'/tmp/livepi-{name}-smoke.json').read_text())\n"
        "    assert data['status'] == 'ok', data\n"
        "    runtime = data['steps']['cli_agent_runtime']\n"
        "    assert runtime['openclaw_gateway_used'] is False, runtime\n"
        "    assert runtime.get('model', '').startswith('smoke-'), runtime\n"
        "print('CLI adapter smoke checks passed.')\n"
        "PY"
    )
    cmd = [
        "docker",
        "run",
        "--rm",
        "--network",
        selected_network,
        "-v",
        f"{repo}:/workspace",
        "-w",
        "/workspace",
        selected_image,
        "bash",
        "-lc",
        script,
    ]
    return subprocess.run(cmd, check=False).returncode


def print_docker_command(argv: list[str]) -> None:
    sys.stdout.write(" ".join(argv) + "\n")
