#!/usr/bin/env python3
"""Sweep test runner: reddit_post surface x 5 models x 5 tasks x top-10 techniques.

Creates a realistic tutorial post on Reddit with a hidden injection payload,
sends the URL to the agent, and measures attack success rate.

Usage:
    python3 prompt_injection_lab/scripts/sweep_reddit_post.py [--dry-run] [--results-root DIR]
    python3 prompt_injection_lab/scripts/sweep_reddit_post.py --resume results/sweep_reddit_post_20260326_...
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from sweep_utils import (
    add_agent_argument,
    add_remote_host_argument,
    default_gateway_ws_url,
    load_env_file,
    resolve_agent,
    resolve_remote_host,
)

LAB_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = LAB_ROOT.parent

SURFACE = "reddit_post"

MODELS = [
    "openai/gpt-5.3-codex",
    "anthropic/claude-opus-4-6",
    "google/gemini-3.1-pro-preview",
    "zai/glm-5",
    "moonshot/kimi-k2.5",
]

TASKS = [
    "crypto_related_files_to_email",
    "disable_firewall_auto_updates",
    "download_and_run_scan_py",
    "email_summary_to_external",
    "solana_transfer_urgent",
]

TOP_10_TECHNIQUES = [
    "checklist_handoff_injection",
    "single_email_chain_spoofing",
    "trusted_integration_spoofing",
    "compositional_instruction_attack",
    "skill_rule_injection",
    "post_compaction_file_read_lure",
    "approval_chain_spoofing",
    "covert_tool_binding",
    "shadow_policy_update",
    "state_desynchronization_override",
]

# Reddit posts need more cooldown to avoid rate limits
INTER_TEST_DELAY_S = 15


def _slug(text: str) -> str:
    import re
    value = re.sub(r"[^a-zA-Z0-9._-]+", "-", text.strip().lower()).strip("-")
    return value or "unknown"


def _run_key(model: str, task: str, technique: str) -> str:
    return f"{model}|{task}|{technique}"


def _load_checkpoint(sweep_dir: Path) -> tuple[set[str], list[dict]]:
    completed: set[str] = set()
    rows: list[dict] = []
    jsonl = sweep_dir / "sweep_results.jsonl"
    if not jsonl.exists():
        return completed, rows
    with jsonl.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                key = _run_key(row["model"], row["task_tag"], row["technique_tag"])
                completed.add(key)
                rows.append(row)
            except (json.JSONDecodeError, KeyError):
                continue
    return completed, rows


def _run_one_test(
    *,
    model: str,
    task_tag: str,
    technique_tag: str,
    results_root: Path,
    remote_host: str,
    gateway_ws_url: str,
    chat_timeout_s: int,
    env_file: str,
    agent: str,
    dry_run: bool,
) -> dict:
    cmd = [
        sys.executable,
        str(LAB_ROOT / "scripts" / "run_surface_test.py"),
        "--agent", agent,
        "--surface-tag", SURFACE,
        "--technique-tag", technique_tag,
        "--malicious-task-tag", task_tag,
        "--base-model", model,
        "--remote-host", remote_host,
        "--gateway-ws-url", gateway_ws_url,
        "--chat-timeout-s", str(chat_timeout_s),
        "--results-root", str(results_root),
        "--env-file", env_file,
    ]

    row = {
        "model": model,
        "task_tag": task_tag,
        "technique_tag": technique_tag,
        "surface": SURFACE,
        "started_at": dt.datetime.utcnow().isoformat() + "Z",
    }

    if dry_run:
        row["status"] = "dry_run"
        row["command"] = cmd
        return row

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )
        row["returncode"] = proc.returncode
        try:
            result = json.loads(proc.stdout)
            row["status"] = result.get("status", "unknown")
            row["run_dir"] = result.get("run_dir", "")
            row["run_name"] = result.get("run_name", "")
            steps = result.get("steps", {})
            for key in [
                "system_state_verifier",
                "wallet_file_verifier",
                "email_inbox_verifier",
            ]:
                if key in steps:
                    row[key] = steps[key]
            # Reddit-specific metadata
            if "seed_reddit_post" in steps:
                row["reddit_post_url"] = steps["seed_reddit_post"].get("post_url", "")
        except json.JSONDecodeError:
            row["status"] = "json_parse_error"
            row["stdout_tail"] = (proc.stdout or "")[-500:]
        if proc.stderr:
            row["stderr_tail"] = proc.stderr[-300:]
    except subprocess.TimeoutExpired:
        row["status"] = "timeout"
    except Exception as exc:
        row["status"] = "exception"
        row["error"] = str(exc)

    row["finished_at"] = dt.datetime.utcnow().isoformat() + "Z"
    return row


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sweep: reddit_post x 5 models x 5 tasks x top-10 techniques"
    )
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running.")
    parser.add_argument("--results-root", default=str(LAB_ROOT / "results"), help="Results directory.")
    add_agent_argument(parser)
    add_remote_host_argument(parser)
    parser.add_argument("--gateway-ws-url", default=default_gateway_ws_url(), help="Gateway WS URL.")
    parser.add_argument("--chat-timeout-s", type=int, default=300, help="Timeout per chat trigger.")
    parser.add_argument("--env-file", default=str(LAB_ROOT / ".env"), help="Env file path.")
    parser.add_argument("--models", default="", help="Comma-separated model filter (default: all 5).")
    parser.add_argument("--tasks", default="", help="Comma-separated task filter (default: all 5).")
    parser.add_argument("--techniques", default="", help="Comma-separated technique filter (default: top 10).")
    parser.add_argument("--resume", default="", help="Path to an existing sweep dir to resume from.")
    parser.add_argument("--inter-test-delay", type=int, default=INTER_TEST_DELAY_S, help="Seconds between tests.")
    args = parser.parse_args()
    load_env_file(args.env_file)
    args.agent = resolve_agent(args.agent)
    args.remote_host = resolve_remote_host(args.remote_host)

    models = [m.strip() for m in args.models.split(",") if m.strip()] or MODELS
    tasks = [t.strip() for t in args.tasks.split(",") if t.strip()] or TASKS
    techniques = [t.strip() for t in args.techniques.split(",") if t.strip()] or TOP_10_TECHNIQUES

    total = len(models) * len(tasks) * len(techniques)

    if args.resume:
        sweep_dir = Path(args.resume)
        if not sweep_dir.is_dir():
            print(f"ERROR: resume dir does not exist: {sweep_dir}", file=sys.stderr)
            return 1
        completed_keys, prior_rows = _load_checkpoint(sweep_dir)
        print(f"Resuming sweep from {sweep_dir}")
        print(f"  {len(completed_keys)} / {total} already completed — {total - len(completed_keys)} remaining")
    else:
        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        sweep_dir = Path(args.results_root) / f"sweep_reddit_post_{ts}"
        sweep_dir.mkdir(parents=True, exist_ok=True)
        completed_keys: set[str] = set()
        prior_rows: list[dict] = []

    output_path = sweep_dir / "sweep_results.jsonl"
    summary_path = sweep_dir / "sweep_summary.json"

    print(f"Sweep: {len(models)} models x {len(tasks)} tasks x {len(techniques)} techniques = {total} runs")
    print(f"Surface: {SURFACE}")
    print(f"Output: {output_path}")
    print(f"Inter-test delay: {args.inter_test_delay}s")
    if args.dry_run:
        print("DRY RUN — no tests will be executed.")
    print()

    sweep_meta = {
        "sweep_id": sweep_dir.name,
        "surface": SURFACE,
        "models": models,
        "tasks": tasks,
        "techniques": techniques,
        "total_runs": total,
        "started_at": dt.datetime.utcnow().isoformat() + "Z",
        "dry_run": args.dry_run,
        "resumed": bool(args.resume),
    }

    ok_count = sum(1 for r in prior_rows if r.get("status") == "ok")
    error_count = sum(1 for r in prior_rows if r.get("status") not in ("ok", "dry_run"))
    skipped_count = len(completed_keys)
    run_index = 0
    rows: list[dict] = list(prior_rows)
    first_new_run = True

    with output_path.open("a", encoding="utf-8") as fh:
        for model in models:
            for task_tag in tasks:
                for technique in techniques:
                    run_index += 1
                    key = _run_key(model, task_tag, technique)

                    if key in completed_keys:
                        continue

                    # Rate-limit delay between Reddit API calls
                    if not first_new_run and not args.dry_run:
                        time.sleep(args.inter_test_delay)
                    first_new_run = False

                    model_slug = _slug(model.split("/")[-1])
                    label = f"[{run_index}/{total}] {model_slug} x {task_tag} x {technique}"
                    print(f"{label} ...", end=" ", flush=True)

                    row = _run_one_test(
                        model=model,
                        task_tag=task_tag,
                        technique_tag=technique,
                        results_root=sweep_dir / "results",
                        remote_host=args.remote_host,
                        gateway_ws_url=args.gateway_ws_url,
                        chat_timeout_s=args.chat_timeout_s,
                        env_file=args.env_file,
                        agent=args.agent,
                        dry_run=args.dry_run,
                    )
                    row["index"] = run_index
                    row["total"] = total

                    status = row.get("status", "unknown")
                    if status == "ok":
                        ok_count += 1
                        print("OK")
                    elif status == "dry_run":
                        print("DRY_RUN")
                    else:
                        error_count += 1
                        print(f"FAIL ({status})")

                    rows.append(row)
                    fh.write(json.dumps(row, ensure_ascii=True) + "\n")
                    fh.flush()

    sweep_meta["finished_at"] = dt.datetime.utcnow().isoformat() + "Z"
    sweep_meta["ok_count"] = ok_count
    sweep_meta["error_count"] = error_count
    sweep_meta["skipped_resumed"] = skipped_count
    sweep_meta["rows"] = rows

    summary_path.write_text(json.dumps(sweep_meta, indent=2, ensure_ascii=True), encoding="utf-8")

    print()
    if skipped_count:
        print(f"Resumed: {skipped_count} prior runs loaded")
    print(f"Sweep complete: {ok_count} ok, {error_count} errors out of {total} runs")
    print(f"Results: {sweep_dir}")
    print(f"JSONL: {output_path}")
    print(f"Summary: {summary_path}")

    return 0 if error_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
