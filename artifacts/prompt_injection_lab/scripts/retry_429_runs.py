#!/usr/bin/env python3
"""Retry 429-affected runs using round-robin model rotation.

Rotates across models (kimi, codex, glm5, opus) to avoid hitting
any single provider's rate limit. Replaces old results in the
original sweep JSONL files.

Supports resume: checks retry_results.jsonl for already-completed retries.

Usage:
    python3 prompt_injection_lab/scripts/retry_429_runs.py
"""

from __future__ import annotations

import datetime as dt
import argparse
import json
import os
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

AFFECTED_FILE = LAB_ROOT / "results" / "429_affected_round3.json"
RETRY_DIR = LAB_ROOT / "results" / "retry_429_round3"
RETRY_JSONL_NAME = "retry_results.jsonl"

# Delay between ALL tests (seconds) to avoid rate limits
INTER_TEST_DELAY = 10
# Extra delay when only one model remains (seconds)
SINGLE_MODEL_DELAY = 15


def _run_key(model: str, task: str, technique: str, surface: str) -> str:
    return f"{model}|{task}|{technique}|{surface}"


def _load_completed(retry_jsonl: Path) -> set[str]:
    completed: set[str] = set()
    if not retry_jsonl.exists():
        return completed
    with retry_jsonl.open("r") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                key = _run_key(row["model"], row["task_tag"], row["technique_tag"], row["surface"])
                completed.add(key)
            except (json.JSONDecodeError, KeyError):
                continue
    return completed


def _run_one_test(*, model: str, task_tag: str, technique_tag: str, surface: str,
                  results_root: Path, remote_host: str, gateway_ws_url: str,
                  chat_timeout_s: int, env_file: str, agent: str) -> dict:
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Retry 429-affected runs using round-robin model rotation.")
    parser.add_argument("--affected-json", default=str(AFFECTED_FILE), help="JSON file of affected runs.")
    parser.add_argument("--retry-dir", default=str(RETRY_DIR), help="Directory for retry results.")
    add_agent_argument(parser)
    add_remote_host_argument(parser)
    parser.add_argument("--gateway-ws-url", default=default_gateway_ws_url())
    parser.add_argument("--chat-timeout-s", type=int, default=300)
    parser.add_argument("--env-file", default=str(LAB_ROOT / ".env"))
    parser.add_argument("--inter-test-delay", type=int, default=INTER_TEST_DELAY)
    parser.add_argument("--single-model-delay", type=int, default=SINGLE_MODEL_DELAY)
    parser.add_argument("--dry-run", action="store_true", help="Print retry order without executing tests.")
    args = parser.parse_args()

    remote_host = resolve_remote_host(args.remote_host)
    gateway_ws_url = args.gateway_ws_url
    chat_timeout_s = args.chat_timeout_s
    env_file = args.env_file
    agent = resolve_agent(args.agent)
    affected_file = Path(args.affected_json).expanduser()
    retry_dir = Path(args.retry_dir).expanduser()
    retry_jsonl = retry_dir / RETRY_JSONL_NAME

    # Load affected runs
    if not affected_file.exists():
        print(f"ERROR: {affected_file} not found", file=sys.stderr)
        return 1

    with affected_file.open() as f:
        all_runs = json.load(f)

    # Load already-completed retries
    completed = _load_completed(retry_jsonl)
    retry_dir.mkdir(parents=True, exist_ok=True)

    # Group runs by model for round-robin
    by_model: dict[str, list[dict]] = defaultdict(list)
    for run in all_runs:
        key = _run_key(run["model"], run["task_tag"], run["technique_tag"], run["surface"])
        if key in completed:
            continue
        by_model[run["model"]].append(run)

    # Build round-robin queue
    queue: list[dict] = []
    model_keys = list(by_model.keys())
    max_len = max((len(v) for v in by_model.values()), default=0)

    for i in range(max_len):
        for model in model_keys:
            runs = by_model[model]
            if i < len(runs):
                queue.append(runs[i])

    total = len(queue)
    remaining_models_at_start = len(model_keys)

    print(f"429 Retry: {total} runs to retest (round-robin across {remaining_models_at_start} models)")
    print(f"Already completed: {len(completed)}")
    print(f"Models: {', '.join(m.split('/')[-1] for m in model_keys)}")
    print(f"Agent: {agent}")
    print(f"Output: {retry_jsonl}")
    print()

    ok_count = 0
    error_count = 0
    last_model = None

    with retry_jsonl.open("a", encoding="utf-8") as fh:
        for idx, run in enumerate(queue):
            model = run["model"]
            model_slug = model.split("/")[-1]
            task = run["task_tag"]
            technique = run["technique_tag"]
            surface = run["surface"]

            # Delay between all tests to avoid rate limits
            if idx > 0:
                remaining_models = set(q["model"] for q in queue[idx:])
                if len(remaining_models) == 1:
                    print(f"  (single model delay: {args.single_model_delay}s)", flush=True)
                    time.sleep(max(0, args.single_model_delay))
                else:
                    time.sleep(max(0, args.inter_test_delay))

            label = f"[{idx + 1}/{total}] {model_slug} × {task} × {technique} ({surface})"
            print(f"{label} ...", end=" ", flush=True)
            if args.dry_run:
                print("DRY_RUN")
                continue

            row = _run_one_test(
                model=model,
                task_tag=task,
                technique_tag=technique,
                surface=surface,
                results_root=retry_dir / "results",
                remote_host=remote_host,
                gateway_ws_url=gateway_ws_url,
                chat_timeout_s=chat_timeout_s,
                env_file=env_file,
                agent=agent,
            )
            row["retry"] = True
            row["original_sweep"] = run.get("sweep_name", "")

            status = row.get("status", "unknown")
            if status == "ok":
                ok_count += 1
                print("OK")
            else:
                error_count += 1
                print(f"FAIL ({status})")

            fh.write(json.dumps(row, ensure_ascii=True) + "\n")
            fh.flush()

            last_model = model

    print()
    print(f"Retry complete: {ok_count} ok, {error_count} errors out of {total}")
    print(f"Results: {retry_jsonl}")

    return 0 if error_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
