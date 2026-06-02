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

__all__ = [
    "run_case",
    "run_sweep",
    "aggregate",
    "bootstrap",
    "build_image",
    "ensure_workspace",
]


def _env_for_subprocess(workdir: Path) -> dict[str, str]:
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
    """Drop a writable prompt_injection_lab/ tree + secrets.example.env into
    the workspace so the Docker harness has somewhere to mount and write to.

    The container always mounts CWD at /workspace and runs
    `python3 prompt_injection_lab/scripts/run_surface_test.py`.
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


def _bootstrap_path_defaults(wd: Path) -> list[str]:
    """Path flags the vendored setup script needs because its REPO_ROOT
    default resolves to the package install dir, not the user's workspace."""
    args: list[str] = []
    secrets = wd / "secrets.env"
    if secrets.is_file():
        args += ["--secrets-file", str(secrets)]
    args += ["--env-file", str(wd / "prompt_injection_lab" / ".env")]
    skill_src = wd / "prompt_injection_lab" / "fixtures" / "skills"
    if not skill_src.is_dir():
        # Fall back to the vendored package copy if workspace lab isn't fully
        # initialised yet (e.g. user passed --no-copy-lab).
        skill_src = paths.lab_root() / "fixtures" / "skills"
    args += ["--skill-source", str(skill_src)]
    args += [
        "--gateway-identity-file",
        str(wd / "prompt_injection_lab" / ".gateway_device_identity.json"),
    ]
    # Default to gateway port == openclaw default so local-only setups
    # don't need a host-to-host tunnel translation.
    args += ["--local-port", "18789"]
    return args


def bootstrap(
    workdir: str | os.PathLike[str] | None = None,
    *,
    apply: bool = False,
    secrets_file: str | None = None,
    extra_args: Iterable[str] = (),
    check: bool = True,
) -> int:
    """Run setup_openclaw_benchmark_env.py against the workspace.

    Default is a dry-run (no --apply). Use apply=True to mutate.
    """
    wd = ensure_workspace(workdir)
    cmd: list[str] = [sys.executable, str(paths.setup_script())]
    extra = list(extra_args)
    flat_extra = " ".join(extra)

    # Only inject path defaults if the caller didn't pass them already.
    path_defaults = _bootstrap_path_defaults(wd)
    if secrets_file:
        path_defaults += ["--secrets-file", str(Path(secrets_file).expanduser().resolve())]
    for flag in ("--secrets-file", "--env-file", "--skill-source", "--gateway-identity-file", "--local-port"):
        if flag in flat_extra:
            # Strip our default for that flag.
            i = 0
            cleaned: list[str] = []
            while i < len(path_defaults):
                if path_defaults[i] == flag:
                    i += 2
                    continue
                cleaned.append(path_defaults[i])
                i += 1
            path_defaults = cleaned
    cmd += path_defaults

    # Skip docker build inside bootstrap; use `livepi build-image` separately.
    if "--skip-build-image" not in flat_extra:
        cmd.append("--skip-build-image")
    if apply:
        cmd.append("--apply")
    cmd += extra
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

    surface -> --surface-tag
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
