from __future__ import annotations

import os
from pathlib import Path
import argparse
import sys


def load_env_file(path: str | Path) -> None:
    """Load KEY=VALUE lines into os.environ without overriding exported vars."""
    env_path = Path(path).expanduser()
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def default_remote_host() -> str:
    return (
        os.getenv("LIVEPI_REMOTE_HOST", "").strip()
        or os.getenv("OPENCLAW_SSH_HOST", "").strip()
        or "root@127.0.0.1"
    )


def default_gateway_ws_url() -> str:
    configured = os.getenv("OPENCLAW_GATEWAY_WS_URL", "").strip()
    if configured:
        return configured
    port = os.getenv("OPENCLAW_TUNNEL_LOCAL_PORT", "").strip() or "18789"
    return f"ws://127.0.0.1:{port}/ws"


def add_remote_host_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--remote-host",
        "--vps-host",
        dest="remote_host",
        default="",
        help="SSH host for the VPS running OpenClaw (default: this VPS, root@127.0.0.1).",
    )


def default_agent() -> str:
    return os.getenv("LIVEPI_AGENT", "").strip().lower() or "openclaw"


def add_agent_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--agent",
        default="",
        choices=("openclaw", "hermes", "codex", "claude_code"),
        help="Agent adapter to run (default: LIVEPI_AGENT or openclaw).",
    )


def resolve_remote_host(value: str = "") -> str:
    return value.strip() or default_remote_host()


def resolve_agent(value: str = "") -> str:
    return value.strip().lower() or default_agent()


def docker_run_command(repo_root: Path, env_file: str, surface_args: list[str]) -> list[str]:
    return [
        sys.executable,
        "-m",
        "livepi_bench.cli",
        "docker-run",
        "--repo",
        str(repo_root),
        "--env-file",
        env_file,
        "--image",
        os.getenv("LIVEPI_IMAGE", "livepi-runner:cpu"),
        "--",
        *surface_args,
    ]


def docker_run_env(repo_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    src = str(repo_root / "src")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{src}:{existing}" if existing else src
    return env
