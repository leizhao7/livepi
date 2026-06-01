#!/usr/bin/env python3
"""Clear remote OpenClaw session history for repeatable LivePI runs."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess


REMOTE_CLEARER = r"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import tarfile
from pathlib import Path


def _config_root(home: Path, profile: str) -> Path:
    cleaned = profile.strip()
    if cleaned in {"", "default", ".openclaw"}:
        return home / ".openclaw"
    return home / f".openclaw-{cleaned}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Clear OpenClaw sessions and workspace memory.")
    parser.add_argument("--profile", default="default")
    parser.add_argument(
        "--workspace-repo",
        action="append",
        default=[],
        help="Remove a named repo checkout under ~/.openclaw/workspace/repos.",
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    home = Path.home()
    root = _config_root(home, args.profile)
    targets: list[Path] = []
    if root.exists():
        targets.extend(sorted(root.glob("agents/*/sessions")))
        targets.extend(
            [
                root / "workspace" / "MEMORY.md",
                root / "workspace" / "memory",
            ]
        )
        repos_dir = root / "workspace" / "repos"
        for repo_name in args.workspace_repo:
            safe_name = Path(str(repo_name).strip()).name
            if safe_name:
                targets.append(repos_dir / safe_name)
                targets.append(root / "workspace" / safe_name)
    existing = [path for path in targets if path.exists()]
    backup_path = ""
    if args.apply and existing and not args.no_backup:
        backup_dir = root / "history_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = str(backup_dir / f"openclaw_history_{dt.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.tar.gz")
        with tarfile.open(backup_path, mode="w:gz") as tf:
            for path in existing:
                tf.add(path, arcname=str(path.relative_to(home)))

    removed: list[str] = []
    errors: list[dict[str, str]] = []
    if args.apply:
        for path in existing:
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
                removed.append(str(path))
            except Exception as exc:  # noqa: BLE001
                errors.append({"path": str(path), "error": str(exc)})

    print(
        json.dumps(
            {
                "profile": args.profile,
                "openclaw_root": str(root),
                "apply": bool(args.apply),
                "no_backup": bool(args.no_backup),
                "backup_path": backup_path,
                "targets": [str(path) for path in targets],
                "existing_before": [str(path) for path in existing],
                "removed": removed,
                "errors": errors,
            },
            indent=2,
            ensure_ascii=True,
        )
    )
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
"""


def _host_target(host: str) -> str:
    value = (host or "").strip()
    if "@" in value:
        value = value.rsplit("@", 1)[1]
    if value.startswith("[") and "]" in value:
        value = value[1 : value.index("]")]
    elif ":" in value and value.count(":") == 1:
        value = value.split(":", 1)[0]
    return value.strip().lower()


def _is_local_host(host: str) -> bool:
    if os.getenv("LIVEPI_TREAT_LOCAL_REMOTE_HOST_AS_LOCAL", "").strip().lower() not in {"1", "true", "yes", "on"}:
        return False
    return _host_target(host) in {"", "local", "localhost", "127.0.0.1", "::1", "0.0.0.0"}


def _ssh_prefix(args: argparse.Namespace) -> list[str]:
    if _is_local_host(args.host):
        return []
    cmd = ["ssh"]
    if args.port is not None:
        cmd.extend(["-p", str(args.port)])
    if args.identity:
        cmd.extend(["-i", args.identity])
    for opt in args.ssh_option:
        cmd.extend(["-o", opt])
    cmd.append(args.host)
    return cmd


def main() -> int:
    parser = argparse.ArgumentParser(description="Clear remote OpenClaw session history.")
    parser.add_argument("--host", required=True, help="SSH host alias or user@host.")
    parser.add_argument("--port", type=int, default=None, help="Optional SSH port.")
    parser.add_argument("--identity", default="", help="Optional SSH private key path.")
    parser.add_argument("--ssh-option", action="append", default=[], help="Repeatable ssh -o option.")
    parser.add_argument("--profile", default="default", help="OpenClaw profile name.")
    parser.add_argument(
        "--workspace-repo",
        action="append",
        default=[],
        help="Remove a named repo checkout under ~/.openclaw/workspace/repos.",
    )
    parser.add_argument("--apply", action="store_true", help="Delete files. Default is dry-run.")
    parser.add_argument("--no-backup", action="store_true", help="Do not create a tar.gz backup before deleting.")
    parser.add_argument("--print-command", action="store_true", help="Print SSH command before execution.")
    args = parser.parse_args()

    remote_args = ["--profile", args.profile]
    for repo_name in args.workspace_repo:
        remote_args.extend(["--workspace-repo", repo_name])
    if args.apply:
        remote_args.append("--apply")
    if args.no_backup:
        remote_args.append("--no-backup")

    cmd = [*_ssh_prefix(args), "python3", "-", *remote_args]
    if args.print_command:
        print("Running:", " ".join(shlex.quote(part) for part in cmd))
    proc = subprocess.run(cmd, input=REMOTE_CLEARER, text=True)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
