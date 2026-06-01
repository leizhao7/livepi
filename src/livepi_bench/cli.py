from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from livepi_bench.agents.docker_runner import (
    run_smoke_checks_in_docker,
    run_surface_test_in_docker,
)
from livepi_bench.config import default_image, default_network


def _repo_root(value: str) -> Path:
    return Path(value).expanduser().resolve()


def _doctor() -> int:
    for tool in ("docker", "ssh", "python3"):
        print(f"{tool}: {shutil.which(tool) or 'missing'}")
    if shutil.which("docker"):
        subprocess.run(["docker", "--version"], check=False)
    print(f"default_image: {default_image()}")
    print(f"default_network: {default_network()}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="LivePI Docker runner helpers.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="Print host tool availability.")

    smoke = sub.add_parser("smoke", help="Run deterministic LivePI checks inside Docker.")
    smoke.add_argument("--repo", default=".", help="Path to the LivePI repository.")
    smoke.add_argument("--image", default="", help="Docker image name.")
    smoke.add_argument("--network", default="", help="Docker network mode.")

    run = sub.add_parser("docker-run", help="Run run_surface_test.py inside Docker.")
    run.add_argument("--repo", default=".", help="Path to the LivePI repository.")
    run.add_argument("--image", default="", help="Docker image name.")
    run.add_argument("--env-file", default="", help="Env file passed to docker --env-file.")
    run.add_argument("--cpus", default="4", help="Docker CPU limit.")
    run.add_argument("--memory", default="8g", help="Docker memory limit.")
    run.add_argument("--network", default="", help="Docker network mode.")
    run.add_argument("surface_args", nargs=argparse.REMAINDER, help="Arguments for run_surface_test.py.")

    args = parser.parse_args()
    if args.command == "doctor":
        return _doctor()
    if args.command == "smoke":
        return run_smoke_checks_in_docker(
            repo=_repo_root(args.repo),
            image=args.image or None,
            network=args.network or None,
        )
    if args.command == "docker-run":
        surface_args = list(args.surface_args)
        if surface_args and surface_args[0] == "--":
            surface_args = surface_args[1:]
        if not surface_args:
            parser.error("docker-run requires run_surface_test.py arguments after --")
        return run_surface_test_in_docker(
            repo=_repo_root(args.repo),
            surface_args=surface_args,
            image=args.image or None,
            env_file=args.env_file or None,
            cpus=args.cpus,
            memory=args.memory,
            network=args.network or None,
        )
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
