"""Filesystem helpers for the installed `livepi` package.

Two roots matter:
  * PACKAGE_ROOT — where the package code + vendored prompt_injection_lab/
    + data/scripts/ + data/docker/ live (read-only, in site-packages).
  * workdir() — the user's workspace where secrets.env, .env, results/ live
    (read-write, defaults to current working directory).
"""
from __future__ import annotations

import os
from importlib.resources import files
from pathlib import Path

__all__ = [
    "PACKAGE_ROOT",
    "package_data_root",
    "artifacts_root",
    "scripts_root",
    "docker_root",
    "lab_root",
    "workdir",
    "run_in_docker_script",
    "setup_script",
    "aggregate_script",
    "secrets_example_path",
    "dockerfile_path",
]


PACKAGE_ROOT: Path = Path(str(files("livepi"))).resolve()


def package_data_root() -> Path:
    """`livepi/data/` inside the installed package."""
    return PACKAGE_ROOT / "data"


def artifacts_root() -> Path:
    """`livepi/data/artifacts/` — published per-(agent, model) JSON results."""
    return package_data_root() / "artifacts"


def scripts_root() -> Path:
    """`livepi/data/scripts/` — vendored shell + python helpers."""
    return package_data_root() / "scripts"


def docker_root() -> Path:
    """`livepi/data/docker/` — vendored Dockerfile."""
    return package_data_root() / "docker"


def lab_root() -> Path:
    """`prompt_injection_lab/` — sibling top-level package vendored with livepi."""
    return PACKAGE_ROOT.parent / "prompt_injection_lab"


def workdir(override: str | os.PathLike[str] | None = None) -> Path:
    """User's writable workspace.

    Precedence: explicit arg > $LIVEPI_WORKDIR > CWD.
    """
    if override is not None:
        return Path(override).expanduser().resolve()
    env = os.environ.get("LIVEPI_WORKDIR")
    if env:
        return Path(env).expanduser().resolve()
    return Path.cwd().resolve()


def run_in_docker_script() -> Path:
    return scripts_root() / "run_in_docker.sh"


def setup_script() -> Path:
    return scripts_root() / "setup_openclaw_benchmark_env.py"


def aggregate_script() -> Path:
    return scripts_root() / "aggregate_results.py"


def secrets_example_path() -> Path:
    return package_data_root() / "secrets.example.env"


def dockerfile_path() -> Path:
    return docker_root() / "Dockerfile"
