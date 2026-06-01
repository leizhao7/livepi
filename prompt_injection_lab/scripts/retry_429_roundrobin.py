#!/usr/bin/env python3
"""Retry 429-affected runs with round-robin model rotation.

Rotates across models (kimi, codex, glm5, opus) to avoid hitting
any single provider too hard. Adds delay when only one model remains.

Usage:
    python3 prompt_injection_lab/scripts/retry_429_roundrobin.py
    python3 prompt_injection_lab/scripts/retry_429_roundrobin.py --delay-single 30
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

from sweep_utils import (
    add_agent_argument,
    add_remote_host_argument,
    default_gateway_ws_url,
    resolve_agent,
    resolve_remote_host,
)

LAB_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = LAB_ROOT.parent

MODEL_ORDER = [
    "moonshot/kimi-k2.5",
    "openai/gpt-5.3-codex",
    "zai/glm-5",
    "anthropic/claude-opus-4-6",
]


def _run_one_test(
    *,
    surface: str,
    model: str,
    task_tag: str,
    technique_tag: str,
    results_root: Path,
    remote_host: str,
    gateway_ws_url: str,
    chat_timeout_s: int,
    env_file: str,
    agent: str,
) -> dict:
    cmd = [
        sys.executable,
        str(LAB_ROOT / "scripts" / "run_surface_test.py"),
        "--agent", agent,
        "--surface-tag", surface,
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
        "surface": surface,
        "started_at": dt.datetime.utcnow().isoformat() + "Z",
        "retry_reason": "429_affected",
    }

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        row["returncode"] = proc.returncode
        try:
            result = json.loads(proc.stdout)
            row["status"] = result.get("status", "unknown")
            row["run_dir"] = result.get("run_dir", "")
            row["run_name"] = result.get("run_name", "")
            steps = result.get("steps", {})
            for key in ["system_state_verifier", "wallet_file_verifier", "email_inbox_verifier"]:
                if key in steps:
                    row[key] = steps[key]
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


def _run_key(model: str, task: str, technique: str) -> str:
    return f"{model}|{task}|{technique}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Retry 429-affected runs with round-robin rotation")
    parser.add_argument("--affected-json", default=str(LAB_ROOT / "results" / "429_affected_runs.json"))
    add_agent_argument(parser)
    add_remote_host_argument(parser)
    parser.add_argument("--gateway-ws-url", default=default_gateway_ws_url())
    parser.add_argument("--chat-timeout-s", type=int, default=300)
    parser.add_argument("--env-file", default=str(LAB_ROOT / ".env"))
    parser.add_argument("--delay-single", type=int, default=30,
                        help="Delay in seconds between tests when only one model remains")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    args.agent = resolve_agent(args.agent)
    args.remote_host = resolve_remote_host(args.remote_host)

    with open(args.affected_json) as f:
        affected = json.load(f)

    print(f"Loaded {len(affected)} 429-affected runs to retry")

    # Group by sweep and model
    by_sweep = defaultdict(lambda: defaultdict(list))
    for r in affected:
        by_sweep[r["sweep_name"]][r["model"]].append(r)

    # Process each sweep
    for sweep_name, model_runs in sorted(by_sweep.items()):
        sweep_path = None
        for r in affected:
            if r["sweep_name"] == sweep_name:
                sweep_path = Path(r["sweep"])
                break
        if not sweep_path or not sweep_path.exists():
            print(f"SKIP {sweep_name}: sweep file not found")
            continue

        sweep_dir = sweep_path.parent
        surface = list(model_runs.values())[0][0]["surface"]

        print(f"\n{'='*60}")
        print(f"Sweep: {sweep_name} (surface={surface})")
        total_in_sweep = sum(len(runs) for runs in model_runs.values())
        print(f"Total retries: {total_in_sweep}")
        for m, runs in sorted(model_runs.items()):
            print(f"  {m.split('/')[-1]}: {len(runs)}")

        # Load existing results and build completed keys
        existing_rows = []
        completed_keys = set()
        retried_keys = set()
        with sweep_path.open("r") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    key = _run_key(row["model"], row["task_tag"], row["technique_tag"])
                    existing_rows.append((key, line))
                    completed_keys.add(key)
                except:
                    existing_rows.append((None, line))

        # Build round-robin queue: interleave models
        # Sort each model's runs, then pick one from each model in rotation
        model_queues = {}
        for model in MODEL_ORDER:
            if model in model_runs:
                model_queues[model] = list(model_runs[model])

        round_robin = []
        while any(model_queues.values()):
            for model in MODEL_ORDER:
                if model in model_queues and model_queues[model]:
                    round_robin.append(model_queues[model].pop(0))

        print(f"\nRound-robin order ({len(round_robin)} tests):")
        ok_count = 0
        err_count = 0
        new_results = {}  # key -> new row json

        for i, run in enumerate(round_robin):
            model = run["model"]
            task = run["task_tag"]
            technique = run["technique_tag"]
            key = _run_key(model, task, technique)
            model_slug = model.split("/")[-1]

            # Check how many models still have remaining tests
            remaining_models = set()
            for j in range(i, len(round_robin)):
                rk = _run_key(round_robin[j]["model"], round_robin[j]["task_tag"], round_robin[j]["technique_tag"])
                if rk not in retried_keys:
                    remaining_models.add(round_robin[j]["model"])

            label = f"[{i+1}/{len(round_robin)}] {model_slug} × {task} × {technique}"
            print(f"{label} ...", end=" ", flush=True)

            if args.dry_run:
                print("DRY_RUN")
                retried_keys.add(key)
                continue

            # Add delay if only one model remains
            if len(remaining_models) <= 1 and i > 0:
                print(f"(delay {args.delay_single}s) ", end="", flush=True)
                time.sleep(args.delay_single)

            row = _run_one_test(
                surface=surface,
                model=model,
                task_tag=task,
                technique_tag=technique,
                results_root=sweep_dir / "results_retry",
                remote_host=args.remote_host,
                gateway_ws_url=args.gateway_ws_url,
                chat_timeout_s=args.chat_timeout_s,
                env_file=args.env_file,
                agent=args.agent,
            )

            status = row.get("status", "unknown")
            if status == "ok":
                ok_count += 1
                print("OK")
            else:
                err_count += 1
                print(f"FAIL ({status})")

            new_results[key] = json.dumps(row, ensure_ascii=True)
            retried_keys.add(key)

        if args.dry_run:
            print(f"\nDry run complete for {sweep_name}")
            continue

        # Replace old results with new ones in the JSONL
        # Backup first
        backup = sweep_path.with_suffix(".jsonl.bak_429")
        shutil.copy2(sweep_path, backup)
        print(f"\nBackup: {backup}")

        replaced = 0
        with sweep_path.open("w") as fh:
            for key, line in existing_rows:
                if key and key in new_results:
                    fh.write(new_results[key] + "\n")
                    replaced += 1
                else:
                    fh.write(line + "\n")

        print(f"Replaced {replaced} rows in {sweep_path.name}")
        print(f"Results: {ok_count} ok, {err_count} errors")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
