#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import signal
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


LAB_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = LAB_ROOT.parent
DEFAULT_PLAN_ROOT = LAB_ROOT / "results" / "matrix_plans"
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from sweep_utils import add_agent_argument, resolve_agent


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"Expected JSON object: {path}")
    return data


def _matrix() -> dict[str, Any]:
    return _load_json(LAB_ROOT / "taxonomy" / "benchmark_case_matrix.json")


def _surfaces() -> list[str]:
    return [str(row.get("surface", "")).strip() for row in _matrix().get("surface_matrix", [])]


def _objectives() -> list[str]:
    return [str(item).strip() for item in _matrix().get("objectives", []) if str(item).strip()]


def _techniques() -> list[str]:
    return [
        str(row.get("tag", "")).strip()
        for row in _load_json(LAB_ROOT / "taxonomy" / "injection_techniques.json").get("tags", [])
        if str(row.get("tag", "")).strip()
    ]


def _values_or_all(value: Any, all_values: list[str]) -> list[str]:
    if value == "all":
        return list(all_values)
    if value == "prompt_level_techniques":
        return [str(item).strip() for item in _matrix().get("prompt_level_techniques", []) if str(item).strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _surface_row(surface: str) -> dict[str, Any] | None:
    key = surface.strip().lower()
    for row in _matrix().get("surface_matrix", []):
        if isinstance(row, dict) and str(row.get("surface", "")).strip() == key:
            return row
    return None


def feasible_techniques(surface: str, objective: str) -> list[str]:
    row = _surface_row(surface)
    objective_key = objective.strip()
    if row is None or objective_key not in _objectives():
        return []
    row_objectives = _values_or_all(row.get("objectives"), _objectives())
    if objective_key not in row_objectives:
        return []
    return _values_or_all(row.get("techniques"), _techniques())


def expanded_cases() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for row in _matrix().get("surface_matrix", []):
        if not isinstance(row, dict):
            continue
        surface = str(row.get("surface", "")).strip()
        objectives = _values_or_all(row.get("objectives"), _objectives())
        techniques = _values_or_all(row.get("techniques"), _techniques())
        for objective in objectives:
            for technique in techniques:
                out.append(
                    {
                        "surface_tag": surface,
                        "technique_tag": technique,
                        "malicious_task_tag": objective,
                    }
                )
    return out


def _parse_tags(args: argparse.Namespace) -> list[str]:
    tags: list[str] = []
    if getattr(args, "technique_tag", ""):
        tags.append(args.technique_tag)
    if getattr(args, "technique_tags", ""):
        tags.extend(args.technique_tags.split(","))
    normalized: list[str] = []
    for tag in tags:
        value = str(tag).strip().lower()
        if value and value not in normalized:
            normalized.append(value)
    return normalized


def _case_status(surface: str, objective: str, tags: list[str]) -> dict[str, Any]:
    surface_key = surface.strip().lower()
    objective_key = objective.strip()
    supported_surfaces = _surfaces()
    supported_objectives = _objectives()
    if surface_key not in supported_surfaces:
        return {
            "feasible": False,
            "reason": f"surface {surface_key!r} is not in the LivePI paper matrix",
            "supported_surfaces": supported_surfaces,
        }
    if objective_key not in supported_objectives:
        return {
            "feasible": False,
            "reason": f"objective {objective_key!r} is not in the LivePI paper matrix",
            "supported_objectives": supported_objectives,
        }
    feasible = feasible_techniques(surface_key, objective_key)
    if not feasible:
        feasible_surfaces = [
            item for item in supported_surfaces if feasible_techniques(item, objective_key)
        ]
        return {
            "feasible": False,
            "reason": "surface/objective combination is not feasible",
            "feasible_surfaces_for_objective": feasible_surfaces,
        }
    invalid = [tag for tag in tags if tag not in feasible]
    if invalid:
        return {
            "feasible": False,
            "reason": "one or more technique tags are not feasible for this surface/objective",
            "invalid_techniques": invalid,
            "feasible_techniques": feasible,
        }
    return {
        "feasible": True,
        "surface_tag": surface_key,
        "malicious_task_tag": objective_key,
        "requested_techniques": tags,
        "feasible_techniques": feasible,
    }


def _print_table(rows: list[dict[str, str]]) -> None:
    headers = ("surface_tag", "technique_tag", "malicious_task_tag")
    widths = {
        header: max(len(header), *(len(row[header]) for row in rows))
        for header in headers
    }
    print("  ".join(header.ljust(widths[header]) for header in headers))
    print("  ".join("-" * widths[header] for header in headers))
    for row in rows:
        print("  ".join(row[header].ljust(widths[header]) for header in headers))


def cmd_list(args: argparse.Namespace) -> int:
    rows = expanded_cases()
    if args.surface_tag:
        rows = [row for row in rows if row["surface_tag"] == args.surface_tag.strip().lower()]
    if args.malicious_task_tag:
        rows = [row for row in rows if row["malicious_task_tag"] == args.malicious_task_tag.strip()]
    if args.format == "json":
        print(json.dumps({"case_count": len(rows), "cases": rows}, indent=2, ensure_ascii=True))
    elif args.format == "jsonl":
        for row in rows:
            print(json.dumps(row, ensure_ascii=True))
    else:
        _print_table(rows)
        print(f"\ncase_count: {len(rows)}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    tags = _parse_tags(args)
    payload = _case_status(args.surface_tag, args.malicious_task_tag, tags)
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0 if payload.get("feasible") else 1


def _run_command(args: argparse.Namespace, tags: list[str]) -> list[str]:
    if args.docker:
        cmd = ["bash", "scripts/run_in_docker.sh"]
    else:
        cmd = ["python3", "prompt_injection_lab/scripts/run_surface_test.py"]
    agent = resolve_agent(getattr(args, "agent", ""))
    cmd.extend(["--agent", agent])
    cmd.extend(["--surface-tag", args.surface_tag.strip().lower()])
    if args.all_techniques:
        cmd.append("--all-techniques")
    elif len(tags) > 1:
        cmd.extend(["--technique-tags", ",".join(tags)])
    elif tags:
        cmd.extend(["--technique-tag", tags[0]])
    else:
        cmd.append("--all-techniques")
    cmd.extend(["--malicious-task-tag", args.malicious_task_tag.strip()])
    if not args.docker and getattr(args, "env_file", ""):
        cmd.extend(["--env-file", args.env_file])
    if args.results_root:
        cmd.extend(["--results-root", args.results_root])
    if args.chat_timeout_s:
        cmd.extend(["--chat-timeout-s", str(args.chat_timeout_s)])
    if getattr(args, "base_model", ""):
        cmd.extend(["--base-model", args.base_model])
    if getattr(args, "agent_model", ""):
        cmd.extend(["--agent-model", args.agent_model])
    return cmd


def cmd_command(args: argparse.Namespace) -> int:
    tags = _parse_tags(args)
    status = _case_status(args.surface_tag, args.malicious_task_tag, [] if args.all_techniques else tags)
    if not status.get("feasible"):
        print(json.dumps(status, indent=2, ensure_ascii=True), file=sys.stderr)
        return 1
    if args.all_techniques:
        pass
    elif tags:
        invalid = [tag for tag in tags if tag not in status["feasible_techniques"]]
        if invalid:
            print(json.dumps({**status, "feasible": False, "invalid_techniques": invalid}, indent=2), file=sys.stderr)
            return 1
    cmd = _run_command(args, tags)
    print(_command_display(cmd, args.env_file if args.docker else ""))
    return 0


def _plan_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    surface_filter = args.fixed_surface.strip().lower()
    objective_filter = args.fixed_objective.strip()
    excluded_surfaces = _csv_set(getattr(args, "exclude_surfaces", ""), lower=True)
    excluded_objectives = _csv_set(getattr(args, "exclude_objectives", ""), lower=False)
    for surface in _surfaces():
        if surface_filter and surface != surface_filter:
            continue
        if surface in excluded_surfaces:
            continue
        for objective in _objectives():
            if objective_filter and objective != objective_filter:
                continue
            if objective in excluded_objectives:
                continue
            feasible = feasible_techniques(surface, objective)
            if not feasible:
                continue
            tags = [] if args.selection == "all-techniques" else [feasible[0]]
            command_args = argparse.Namespace(
                docker=args.docker,
                agent=args.agent,
                surface_tag=surface,
                malicious_task_tag=objective,
                technique_tag=tags[0] if tags else "",
                technique_tags="",
                all_techniques=args.selection == "all-techniques",
                env_file=getattr(args, "env_file", ""),
                results_root=args.results_root,
                chat_timeout_s=args.chat_timeout_s,
                base_model=getattr(args, "base_model", ""),
                agent_model=getattr(args, "agent_model", ""),
            )
            rows.append(
                {
                    "surface_tag": surface,
                    "malicious_task_tag": objective,
                    "technique_tags": feasible if args.selection == "all-techniques" else tags,
                    "selection": args.selection,
                    "command": _run_command(command_args, tags),
                }
            )
    return rows


def _csv_set(raw: str, *, lower: bool) -> set[str]:
    values: set[str] = set()
    for item in str(raw or "").split(","):
        value = item.strip()
        if not value:
            continue
        values.add(value.lower() if lower else value)
    return values


def _slice_rows(rows: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    offset = max(0, int(getattr(args, "offset", 0) or 0))
    limit = int(getattr(args, "limit", 0) or 0)
    sliced = rows[offset:]
    if limit > 0:
        sliced = sliced[:limit]
    return sliced


def _command_display(command: list[str], env_file: str = "") -> str:
    prefix: list[str] = []
    if env_file:
        prefix.append(f"LIVEPI_ENV_FILE={shlex.quote(env_file)}")
    return " ".join([*prefix, *(shlex.quote(part) for part in command)])


def cmd_plan(args: argparse.Namespace) -> int:
    if not args.fixed_surface and not args.fixed_objective:
        print("plan requires --fixed-surface or --fixed-objective", file=sys.stderr)
        return 2
    rows = _slice_rows(_plan_rows(args), args)
    if args.format == "json":
        payload = {
            "count": len(rows),
            "fixed_surface": args.fixed_surface,
            "fixed_objective": args.fixed_objective,
            "selection": args.selection,
            "exclude_surfaces": args.exclude_surfaces,
            "exclude_objectives": args.exclude_objectives,
            "commands": rows,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=True))
    else:
        for row in rows:
            print(_command_display(row["command"], args.env_file if args.docker else ""))
    return 0 if rows else 1


def _case_id(row: dict[str, Any]) -> str:
    tags = "-".join(str(tag) for tag in row.get("technique_tags", [])) or "all-techniques"
    return "__".join(
        [
            str(row.get("surface_tag", "")),
            tags,
            str(row.get("malicious_task_tag", "")),
        ]
    )


def _json_from_text(text: str) -> dict[str, Any] | None:
    clean = text.strip()
    if not clean:
        return None
    try:
        data = json.loads(clean)
    except json.JSONDecodeError:
        start = clean.find("{")
        end = clean.rfind("}")
        if start < 0 or end < start:
            return None
        try:
            data = json.loads(clean[start : end + 1])
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


def _load_completed_case_ids(runs_jsonl: Path) -> set[str]:
    completed: set[str] = set()
    if not runs_jsonl.exists():
        return completed
    for raw in runs_jsonl.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if row.get("case_status") == "ok":
            completed.add(str(row.get("case_id", "")))
    return completed


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _plan_dir(args: argparse.Namespace) -> Path:
    if args.resume:
        return Path(args.resume).expanduser().resolve()
    stamp = dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    label_parts = ["matrix_plan"]
    if args.fixed_surface:
        label_parts.append(args.fixed_surface.strip().lower())
    if args.fixed_objective:
        label_parts.append(args.fixed_objective.strip())
    label_parts.append(stamp)
    root = Path(args.plan_root).expanduser() if args.plan_root else DEFAULT_PLAN_ROOT
    return (root / "__".join(label_parts)).resolve()


def _case_status_from_process(returncode: int, parsed: dict[str, Any] | None) -> str:
    if returncode != 0:
        return "error"
    if not parsed:
        return "error"
    if parsed.get("status") != "ok":
        return "error"
    if parsed.get("mode") == "all_techniques" and int(parsed.get("error_count", 0) or 0) != 0:
        return "error"
    return "ok"


def _run_captured(command: list[str], *, cwd: str, env: dict[str, str], timeout_s: int) -> dict[str, Any]:
    process = subprocess.Popen(  # noqa: S603
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=max(1, timeout_s))
        return {
            "timed_out": False,
            "returncode": process.returncode,
            "stdout": stdout or "",
            "stderr": stderr or "",
        }
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            stdout, stderr = process.communicate(timeout=8)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = process.communicate()
        return {
            "timed_out": True,
            "returncode": process.returncode,
            "stdout": stdout or "",
            "stderr": stderr or "",
        }


def cmd_run_plan(args: argparse.Namespace) -> int:
    if not args.fixed_surface and not args.fixed_objective:
        print("run-plan requires --fixed-surface or --fixed-objective", file=sys.stderr)
        return 2
    rows = _slice_rows(_plan_rows(args), args)
    if not rows:
        print("no feasible cases matched this plan", file=sys.stderr)
        return 1

    if not args.execute:
        for row in rows:
            print(_command_display(row["command"], args.env_file if args.docker else ""))
        print("\nDry run only. Add --execute to run the plan.", file=sys.stderr)
        return 0

    plan_dir = _plan_dir(args)
    plan_dir.mkdir(parents=True, exist_ok=True)
    runs_jsonl = plan_dir / "runs.jsonl"
    completed = _load_completed_case_ids(runs_jsonl) if args.resume else set()
    plan_payload = {
        "created_at": dt.datetime.utcnow().isoformat() + "Z",
        "plan_dir": str(plan_dir),
        "fixed_surface": args.fixed_surface,
        "fixed_objective": args.fixed_objective,
        "selection": args.selection,
        "exclude_surfaces": args.exclude_surfaces,
        "exclude_objectives": args.exclude_objectives,
        "agent": resolve_agent(args.agent),
        "docker": args.docker,
        "env_file": args.env_file,
        "case_timeout_s": args.case_timeout_s,
        "count": len(rows),
        "commands": [
            {
                **row,
                "case_id": _case_id(row),
                "display": _command_display(row["command"], args.env_file if args.docker else ""),
            }
            for row in rows
        ],
    }
    _write_json(plan_dir / "plan.json", plan_payload)

    ok_count = 0
    error_count = 0
    skipped_count = 0
    records: list[dict[str, Any]] = []
    env = os.environ.copy()
    if args.env_file and args.docker:
        env["LIVEPI_ENV_FILE"] = args.env_file

    for index, row in enumerate(rows, start=1):
        case_id = _case_id(row)
        if case_id in completed:
            skipped_count += 1
            record = {
                "index": index,
                "case_id": case_id,
                "case_status": "skipped",
                "reason": "already completed in resume runs.jsonl",
                "surface_tag": row["surface_tag"],
                "malicious_task_tag": row["malicious_task_tag"],
                "technique_tags": row["technique_tags"],
            }
            records.append(record)
            continue

        started_at = dt.datetime.utcnow().isoformat() + "Z"
        safe_name = f"{index:03d}_{case_id}".replace("/", "_")
        stdout_path = plan_dir / f"{safe_name}.stdout.txt"
        stderr_path = plan_dir / f"{safe_name}.stderr.txt"
        command = list(row["command"])
        try:
            completed_process = _run_captured(
                command,
                cwd=str(REPO_ROOT),
                env=env,
                timeout_s=max(1, int(args.case_timeout_s)),
            )
            stdout = completed_process["stdout"]
            stderr = completed_process["stderr"]
            stdout_path.write_text(stdout, encoding="utf-8")
            stderr_path.write_text(stderr, encoding="utf-8")
            if completed_process["timed_out"]:
                record = {
                    "index": index,
                    "case_id": case_id,
                    "case_status": "timeout",
                    "surface_tag": row["surface_tag"],
                    "malicious_task_tag": row["malicious_task_tag"],
                    "technique_tags": row["technique_tags"],
                    "selection": row["selection"],
                    "command": command,
                    "display": _command_display(command, args.env_file if args.docker else ""),
                    "returncode": completed_process["returncode"],
                    "started_at": started_at,
                    "finished_at": dt.datetime.utcnow().isoformat() + "Z",
                    "stdout_path": str(stdout_path),
                    "stderr_path": str(stderr_path),
                    "error": f"timed out after {args.case_timeout_s}s; process group was terminated",
                }
            else:
                parsed = _json_from_text(stdout)
                case_status = _case_status_from_process(int(completed_process["returncode"] or 0), parsed)
                record = {
                    "index": index,
                    "case_id": case_id,
                    "case_status": case_status,
                    "surface_tag": row["surface_tag"],
                    "malicious_task_tag": row["malicious_task_tag"],
                    "technique_tags": row["technique_tags"],
                    "selection": row["selection"],
                    "command": command,
                    "display": _command_display(command, args.env_file if args.docker else ""),
                    "returncode": completed_process["returncode"],
                    "started_at": started_at,
                    "finished_at": dt.datetime.utcnow().isoformat() + "Z",
                    "stdout_path": str(stdout_path),
                    "stderr_path": str(stderr_path),
                    "parsed_status": parsed.get("status") if parsed else None,
                    "run_dir": parsed.get("run_dir") if parsed else None,
                    "summary": parsed,
                }
        except Exception as exc:
            record = {
                "index": index,
                "case_id": case_id,
                "case_status": "error",
                "surface_tag": row["surface_tag"],
                "malicious_task_tag": row["malicious_task_tag"],
                "technique_tags": row["technique_tags"],
                "selection": row["selection"],
                "command": command,
                "display": _command_display(command, args.env_file if args.docker else ""),
                "returncode": None,
                "started_at": started_at,
                "finished_at": dt.datetime.utcnow().isoformat() + "Z",
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
                "error": str(exc),
            }

        with runs_jsonl.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=True) + "\n")
        records.append(record)
        if record["case_status"] == "ok":
            ok_count += 1
        else:
            error_count += 1
        print(
            f"[{index}/{len(rows)}] {record['case_status']} {case_id}",
            file=sys.stderr,
            flush=True,
        )
        if args.fail_fast and record["case_status"] != "ok":
            break

    summary = {
        "status": "ok" if error_count == 0 else "error",
        "plan_dir": str(plan_dir),
        "total_cases": len(rows),
        "ok_count": ok_count,
        "error_count": error_count,
        "skipped_count": skipped_count,
        "runs_jsonl": str(runs_jsonl),
        "finished_at": dt.datetime.utcnow().isoformat() + "Z",
        "records": records,
    }
    _write_json(plan_dir / "summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=True))
    return 0 if summary["status"] == "ok" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect LivePI paper surface x technique x objective cases.")
    sub = parser.add_subparsers(dest="command", required=True)

    list_parser = sub.add_parser("list", help="List expanded feasible paper cases.")
    list_parser.add_argument("--surface-tag", default="", help="Optional surface filter.")
    list_parser.add_argument("--malicious-task-tag", default="", help="Optional objective filter.")
    list_parser.add_argument("--format", choices=("table", "json", "jsonl"), default="table")
    list_parser.set_defaults(func=cmd_list)

    check_parser = sub.add_parser("check", help="Check one surface/objective/technique selection.")
    check_parser.add_argument("--surface-tag", required=True)
    check_parser.add_argument("--malicious-task-tag", required=True)
    check_parser.add_argument("--technique-tag", default="")
    check_parser.add_argument("--technique-tags", default="")
    check_parser.set_defaults(func=cmd_check)

    command_parser = sub.add_parser("command", help="Print a run_surface_test command for a feasible case.")
    command_parser.add_argument("--surface-tag", required=True)
    command_parser.add_argument("--malicious-task-tag", required=True)
    command_parser.add_argument("--technique-tag", default="")
    command_parser.add_argument("--technique-tags", default="")
    command_parser.add_argument("--all-techniques", action="store_true")
    add_agent_argument(command_parser)
    command_parser.add_argument("--docker", action="store_true")
    command_parser.add_argument("--env-file", default="")
    command_parser.add_argument("--results-root", default="")
    command_parser.add_argument("--chat-timeout-s", type=int, default=0)
    command_parser.add_argument("--base-model", default="", help="Model for OpenClaw gateway or CLI-agent mapping.")
    command_parser.add_argument("--agent-model", default="", help="Direct CLI-agent model override.")
    command_parser.set_defaults(func=cmd_command)

    plan_parser = sub.add_parser("plan", help="Print commands for a fixed surface and/or objective smoke plan.")
    plan_parser.add_argument("--fixed-surface", default="", help="Run all feasible objectives for this surface.")
    plan_parser.add_argument("--fixed-objective", default="", help="Run all feasible surfaces for this objective.")
    plan_parser.add_argument("--exclude-surfaces", default="", help="Comma-separated surface tags to skip.")
    plan_parser.add_argument("--exclude-objectives", default="", help="Comma-separated objective tags to skip.")
    plan_parser.add_argument("--selection", choices=("first", "all-techniques"), default="first")
    add_agent_argument(plan_parser)
    plan_parser.add_argument("--docker", action="store_true")
    plan_parser.add_argument("--results-root", default="")
    plan_parser.add_argument("--chat-timeout-s", type=int, default=0)
    plan_parser.add_argument("--env-file", default="")
    plan_parser.add_argument("--base-model", default="", help="Model for OpenClaw gateway or CLI-agent mapping.")
    plan_parser.add_argument("--agent-model", default="", help="Direct CLI-agent model override.")
    plan_parser.add_argument("--offset", type=int, default=0)
    plan_parser.add_argument("--limit", type=int, default=0)
    plan_parser.add_argument("--format", choices=("commands", "json"), default="commands")
    plan_parser.set_defaults(func=cmd_plan)

    run_plan_parser = sub.add_parser("run-plan", help="Execute a fixed surface/objective smoke plan.")
    run_plan_parser.add_argument("--fixed-surface", default="", help="Run all feasible objectives for this surface.")
    run_plan_parser.add_argument("--fixed-objective", default="", help="Run all feasible surfaces for this objective.")
    run_plan_parser.add_argument("--exclude-surfaces", default="", help="Comma-separated surface tags to skip.")
    run_plan_parser.add_argument("--exclude-objectives", default="", help="Comma-separated objective tags to skip.")
    run_plan_parser.add_argument("--selection", choices=("first", "all-techniques"), default="first")
    add_agent_argument(run_plan_parser)
    run_plan_parser.add_argument("--docker", action="store_true")
    run_plan_parser.add_argument("--env-file", default="")
    run_plan_parser.add_argument("--results-root", default="")
    run_plan_parser.add_argument("--chat-timeout-s", type=int, default=0)
    run_plan_parser.add_argument("--base-model", default="", help="Model for OpenClaw gateway or CLI-agent mapping.")
    run_plan_parser.add_argument("--agent-model", default="", help="Direct CLI-agent model override.")
    run_plan_parser.add_argument("--case-timeout-s", type=int, default=900)
    run_plan_parser.add_argument("--plan-root", default="")
    run_plan_parser.add_argument("--resume", default="", help="Existing plan directory to resume.")
    run_plan_parser.add_argument("--offset", type=int, default=0)
    run_plan_parser.add_argument("--limit", type=int, default=0)
    run_plan_parser.add_argument("--fail-fast", action="store_true")
    run_plan_parser.add_argument("--execute", action="store_true", help="Actually execute the plan; default prints only.")
    run_plan_parser.set_defaults(func=cmd_run_plan)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
