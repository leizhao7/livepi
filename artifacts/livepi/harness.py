"""Subprocess wrappers around vendored shell + python scripts.

Public API:
    bootstrap(workdir=..., apply=False)       - prepare workspace + run setup
    run_case(agent, base_model, surface,
             technique, objective, ...)        - one Dockerized case
    run_sweep(agent, base_model, ...)         - sweep wrapper
    aggregate(workdir=..., format=...)        - tabulate results
    build_image(...)                          - docker build of runner-cpu
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

from . import paths

__all__ = ["run_case", "run_sweep", "aggregate", "bootstrap", "build_image", "ensure_workspace"]


def _env_for_subprocess(workdir: Path) -> dict[str, str]:
    """Make vendored prompt_injection_lab importable from the workspace."""
    env = os.environ.copy()
    py_paths = [str(paths.PACKAGE_ROOT.parent)]
    existing = env.get("PYTHONPATH")
    if existing:
        py_paths.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(py_paths)
    env.setdefault("LIVEPI_WORKDIR", str(workdir))
    return env


def _ensure_workdir(workdir: str | os.PathLike[str] | None) -> Path:
    wd = paths.workdir(workdir)
    wd.mkdir(parents=True, exist_ok=True)
    return wd


def ensure_workspace(
    workdir: str | os.PathLike[str] | None = None,
    *,
    copy_lab: bool = True,
) -> Path:
    """Prepare the user's workspace: drop secrets.example.env + a real
    prompt_injection_lab/ folder so the Docker harness has somewhere to mount.

    The container always mounts CWD at /workspace and runs
    `python3 prompt_injection_lab/scripts/run_surface_test.py`, so the workspace
    must have a real (writable) `prompt_injection_lab/` subdir — not a symlink
    into site-packages, otherwise .env/results writes would pollute the install.
    """
    wd = _ensure_workdir(workdir)

    secrets_example = wd / "secrets.example.env"
    if not secrets_example.exists() and paths.secrets_example_path().exists():
        shutil.copy2(paths.secrets_example_path(), secrets_example)

    secrets_env = wd / "secrets.env"
    if not secrets_env.exists() and secrets_example.exists():
        shutil.copy2(secrets_example, secrets_env)

    if copy_lab:
        lab_src = paths.lab_root()
        lab_dst = wd / "prompt_injection_lab"
        if lab_src.is_dir() and not lab_dst.exists():
            shutil.copytree(lab_src, lab_dst, symlinks=False)

    return wd


def bootstrap(
    workdir: str | os.PathLike[str] | None = None,
    *,
    apply: bool = False,
    secrets_file: str | None = None,
    extra_args: Iterable[str] = (),
    check: bool = True,
) -> int:
    """Run setup_openclaw_benchmark_env.py against the workspace.

    Default = dry-run. Pass `apply=True` to mutate the workspace
    (write prompt_injection_lab/.env, configure openclaw, etc.).
    """
    wd = ensure_workspace(workdir)
    cmd: list[str] = [sys.executable, str(paths.setup_script())]
    if apply:
        cmd.append("--apply")
    if secrets_file:
        cmd += ["--secrets-file", str(Path(secrets_file).expanduser().resolve())]
    cmd += list(extra_args)
    proc = subprocess.run(cmd, cwd=str(wd), env=_env_for_subprocess(wd))
    if check and proc.returncode != 0:
        raise SystemExit(proc.returncode)
    return proc.returncode


def build_image(
    *,
    image: str = "livepi-runner:cpu",
    check: bool = True,
) -> int:
    dockerfile = paths.dockerfile_path()
    context = dockerfile.parent
    cmd = ["docker", "build", "-f", str(dockerfile), "-t", image, str(context)]
    proc = subprocess.run(cmd)
    if check and proc.returncode != 0:
        raise SystemExit(proc.returncode)
    return proc.returncode


def run_case(
    agent: str,
    base_model: str,
    surface: str,
    technique: str,
    objective: str,
    *,
    workdir: str | os.PathLike[str] | None = None,
    judge_model: str | None = None,
    run_name: str | None = None,
    image: str | None = None,
    extra_args: Iterable[str] = (),
    capture_summary: bool = True,
    check: bool = True,
) -> dict[str, Any]:
    """Run one Dockerized case.

    Args use the paper-friendly names; internally maps to the flags expected
    by `prompt_injection_lab/scripts/run_surface_test.py`:
        surface   -> --surface-tag
        technique -> --technique-tag
        objective -> --malicious-task-tag
    """
    wd = _ensure_workdir(workdir)
    env = _env_for_subprocess(wd)
    if image:
        env["IMAGE"] = image

    cmd: list[str] = ["bash", str(paths.run_in_docker_script())]
    cmd += [
        "--agent", agent,
        "--base-model", base_model,
        "--surface-tag", surface,
        "--technique-tag", technique,
        "--malicious-task-tag", objective,
    ]
    if judge_model:
        cmd += ["--judge-model", judge_model]
    if run_name:
        cmd += ["--run-name", run_name]
    cmd += list(extra_args)

    proc = subprocess.run(cmd, cwd=str(wd), env=env, capture_output=True, text=True)

    results_dir: Path | None = None
    summary: dict[str, Any] | None = None
    results_root = wd / "prompt_injection_lab" / "results"
    if capture_summary and results_root.is_dir():
        candidates = sorted(
            (p for p in results_root.iterdir() if p.is_dir()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            results_dir = candidates[0]
            summary_path = results_dir / "summary.json"
            if summary_path.is_file():
                try:
                    summary = json.loads(summary_path.read_text(encoding="utf-8"))
                except Exception:
                    summary = None

    out = {
        "returncode": proc.returncode,
        "run_name": run_name,
        "results_dir": str(results_dir) if results_dir else None,
        "summary": summary,
        "stdout_tail": (proc.stdout or "").splitlines()[-50:],
        "stderr_tail": (proc.stderr or "").splitlines()[-50:],
    }
    if check and proc.returncode != 0:
        sys.stderr.write("\n".join(out["stderr_tail"]) + "\n")
        raise SystemExit(proc.returncode)
    return out


def run_sweep(
    agent: str,
    base_model: str,
    *,
    fixed_surface: str | None = None,
    fixed_objective: str | None = None,
    workdir: str | os.PathLike[str] | None = None,
    judge_model: str | None = None,
    image: str | None = None,
    extra_args: Iterable[str] = (),
    check: bool = True,
) -> dict[str, Any]:
    """Sweep the matrix. Exactly one of fixed_surface/fixed_objective fixes one
    axis (varies the other 11/4); set neither to run the full 169-case grid.

    Implementation uses `--all-techniques` per-(surface, objective) loop via
    the underlying script.
    """
    wd = _ensure_workdir(workdir)
    env = _env_for_subprocess(wd)
    if image:
        env["IMAGE"] = image

    cmd: list[str] = ["bash", str(paths.run_in_docker_script())]
    cmd += ["--agent", agent, "--base-model", base_model, "--all-techniques"]
    if fixed_surface:
        cmd += ["--surface-tag", fixed_surface]
    if fixed_objective:
        cmd += ["--malicious-task-tag", fixed_objective]
    if judge_model:
        cmd += ["--judge-model", judge_model]
    cmd += list(extra_args)

    proc = subprocess.run(cmd, cwd=str(wd), env=env)
    out = {"returncode": proc.returncode}
    if check and proc.returncode != 0:
        raise SystemExit(proc.returncode)
    return out


def aggregate(
    workdir: str | os.PathLike[str] | None = None,
    *,
    results_subdir: str = "prompt_injection_lab/results",
    output_format: str = "markdown",
    extra_args: Iterable[str] = (),
    check: bool = True,
) -> str:
    """Aggregate results — returns the script's stdout (markdown / json / csv)."""
    wd = _ensure_workdir(workdir)
    env = _env_for_subprocess(wd)
    results_path = wd / results_subdir
    cmd: list[str] = [sys.executable, str(paths.aggregate_script()), str(results_path)]
    if output_format == "json":
        cmd += ["--json", "/dev/stdout", "--no-markdown"]
    elif output_format == "csv":
        cmd += ["--csv", "/dev/stdout", "--no-markdown"]
    elif output_format == "markdown":
        pass
    else:
        raise ValueError(f"Unknown output_format: {output_format!r}")
    cmd += list(extra_args)
    proc = subprocess.run(cmd, cwd=str(wd), env=env, capture_output=True, text=True)
    if check and proc.returncode != 0:
        sys.stderr.write(proc.stderr or "")
        raise SystemExit(proc.returncode)
    return proc.stdout
