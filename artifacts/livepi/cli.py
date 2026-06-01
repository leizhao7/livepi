"""`livepi` console script.

Subcommands:
    livepi bootstrap [--apply] [--workdir DIR] [--secrets-file FILE]
    livepi build-image [--image NAME]
    livepi run --agent A --base-model M --surface S --technique T --objective O
    livepi sweep --agent A --base-model M [--fixed-surface S] [--fixed-objective O]
    livepi aggregate [--workdir DIR] [--format markdown|json|csv]
    livepi list-artifacts
    livepi read-artifact --agent A --model M
    livepi where                       # show package + workspace paths
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from . import paths
from .api import list_artifacts, read_artifact
from .harness import aggregate, bootstrap, build_image, run_case, run_sweep, ensure_workspace


def _cmd_bootstrap(args: argparse.Namespace) -> int:
    ensure_workspace(args.workdir, copy_lab=not args.no_copy_lab)
    return bootstrap(
        workdir=args.workdir,
        apply=args.apply,
        secrets_file=args.secrets_file,
        extra_args=args.extra,
        check=False,
    )


def _cmd_build_image(args: argparse.Namespace) -> int:
    return build_image(image=args.image, check=False)


def _cmd_run(args: argparse.Namespace) -> int:
    result = run_case(
        agent=args.agent,
        base_model=args.base_model,
        surface=args.surface,
        technique=args.technique,
        objective=args.objective,
        workdir=args.workdir,
        judge_model=args.judge_model,
        run_name=args.run_name,
        image=args.image,
        extra_args=args.extra,
        capture_summary=True,
        check=False,
    )
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        rc = result["returncode"]
        summary = result.get("summary")
        print(f"[livepi run] returncode={rc}", file=sys.stderr)
        if summary:
            hard = (summary.get("steps") or {}).get("email_inbox_verifier", {})
            print(f"[livepi run] results_dir={result['results_dir']}", file=sys.stderr)
            print(f"[livepi run] status={summary.get('status')}", file=sys.stderr)
        else:
            for line in result["stderr_tail"]:
                print(line, file=sys.stderr)
    return result["returncode"]


def _cmd_sweep(args: argparse.Namespace) -> int:
    result = run_sweep(
        agent=args.agent,
        base_model=args.base_model,
        fixed_surface=args.fixed_surface,
        fixed_objective=args.fixed_objective,
        workdir=args.workdir,
        judge_model=args.judge_model,
        image=args.image,
        extra_args=args.extra,
        check=False,
    )
    return result["returncode"]


def _cmd_aggregate(args: argparse.Namespace) -> int:
    out = aggregate(
        workdir=args.workdir,
        output_format=args.format,
        check=False,
    )
    sys.stdout.write(out)
    return 0


def _cmd_list_artifacts(args: argparse.Namespace) -> int:
    rows = list_artifacts()
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return 0
    if not rows:
        print("(no artifacts found)", file=sys.stderr)
        return 1
    w_a = max(8, max(len(str(r["agent"])) for r in rows))
    w_m = max(10, max(len(str(r["model"])) for r in rows))
    print(f"{'agent':<{w_a}}  {'model':<{w_m}}  {'cases':>5}  {'hard_ASR':>8}  {'judge_ASR':>9}")
    for r in rows:
        h = r.get("hard_attack_success_rate")
        j = r.get("judge_attack_success_rate")
        h_s = f"{h:.4f}" if isinstance(h, (int, float)) else "-"
        j_s = f"{j:.4f}" if isinstance(j, (int, float)) else "-"
        print(f"{r['agent']:<{w_a}}  {r['model']:<{w_m}}  {r['total_cases']:>5}  {h_s:>8}  {j_s:>9}")
    return 0


def _cmd_read_artifact(args: argparse.Namespace) -> int:
    try:
        payload = read_artifact(agent=args.agent, model=args.model)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1
    if args.summary:
        params = payload.get("parameters", {})
        print(json.dumps(params, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def _cmd_where(args: argparse.Namespace) -> int:
    info = {
        "package_root": str(paths.PACKAGE_ROOT),
        "artifacts_root": str(paths.artifacts_root()),
        "scripts_root": str(paths.scripts_root()),
        "docker_root": str(paths.docker_root()),
        "lab_root": str(paths.lab_root()),
        "workdir": str(paths.workdir(args.workdir)),
        "run_in_docker_script": str(paths.run_in_docker_script()),
        "setup_script": str(paths.setup_script()),
        "aggregate_script": str(paths.aggregate_script()),
        "secrets_example_path": str(paths.secrets_example_path()),
        "dockerfile_path": str(paths.dockerfile_path()),
    }
    print(json.dumps(info, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="livepi", description="LivePI benchmark CLI.")
    p.add_argument("--version", action="store_true", help="Print version and exit.")
    sub = p.add_subparsers(dest="cmd")

    sp = sub.add_parser("bootstrap", help="Prepare a workspace + run setup.")
    sp.add_argument("--workdir", default=None)
    sp.add_argument("--apply", action="store_true", help="Actually mutate the workspace.")
    sp.add_argument("--secrets-file", default=None)
    sp.add_argument("--no-copy-lab", action="store_true",
                    help="Skip copying prompt_injection_lab/ into the workspace.")
    sp.add_argument("extra", nargs=argparse.REMAINDER, help="Forwarded to setup script.")
    sp.set_defaults(func=_cmd_bootstrap)

    sp = sub.add_parser("build-image", help="Build the runner Docker image.")
    sp.add_argument("--image", default="livepi-runner:cpu")
    sp.set_defaults(func=_cmd_build_image)

    sp = sub.add_parser("run", help="Run a single case in Docker.")
    sp.add_argument("--agent", required=True, choices=["openclaw", "hermes", "codex", "claude_code"])
    sp.add_argument("--base-model", required=True)
    sp.add_argument("--surface", required=True)
    sp.add_argument("--technique", required=True)
    sp.add_argument("--objective", required=True)
    sp.add_argument("--workdir", default=None)
    sp.add_argument("--judge-model", default=None)
    sp.add_argument("--run-name", default=None)
    sp.add_argument("--image", default=None)
    sp.add_argument("--json", action="store_true", help="Print full result JSON to stdout.")
    sp.add_argument("extra", nargs=argparse.REMAINDER)
    sp.set_defaults(func=_cmd_run)

    sp = sub.add_parser("sweep", help="Sweep along one axis (or full matrix).")
    sp.add_argument("--agent", required=True, choices=["openclaw", "hermes", "codex", "claude_code"])
    sp.add_argument("--base-model", required=True)
    sp.add_argument("--fixed-surface", default=None)
    sp.add_argument("--fixed-objective", default=None)
    sp.add_argument("--workdir", default=None)
    sp.add_argument("--judge-model", default=None)
    sp.add_argument("--image", default=None)
    sp.add_argument("extra", nargs=argparse.REMAINDER)
    sp.set_defaults(func=_cmd_sweep)

    sp = sub.add_parser("aggregate", help="Aggregate workdir results.")
    sp.add_argument("--workdir", default=None)
    sp.add_argument("--format", choices=["markdown", "json", "csv"], default="markdown")
    sp.set_defaults(func=_cmd_aggregate)

    sp = sub.add_parser("list-artifacts", help="List packaged artifacts.")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=_cmd_list_artifacts)

    sp = sub.add_parser("read-artifact", help="Print one artifact JSON.")
    sp.add_argument("--agent", required=True)
    sp.add_argument("--model", required=True)
    sp.add_argument("--summary", action="store_true",
                    help="Print only the `parameters` block.")
    sp.set_defaults(func=_cmd_read_artifact)

    sp = sub.add_parser("where", help="Show package + workspace paths.")
    sp.add_argument("--workdir", default=None)
    sp.set_defaults(func=_cmd_where)

    return p


def main(argv: Sequence[str] | None = None) -> int:
    p = build_parser()
    args = p.parse_args(argv)
    if args.version:
        from . import __version__
        print(__version__)
        return 0
    if not getattr(args, "cmd", None):
        p.print_help()
        return 2
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
