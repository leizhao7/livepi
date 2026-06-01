#!/usr/bin/env python3
"""Shared sweep runner for paper group-chat surfaces.

Each paper chat surface uses only the direct_group_message_instruction rendering:
5 models x 5 tasks x 1 rendering = 25 runs per surface.
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
    docker_run_command,
    docker_run_env,
    load_env_file,
    resolve_agent,
    resolve_remote_host,
)

LAB_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = LAB_ROOT.parent

DIRECT_GROUP_TECHNIQUE = "direct_group_message_instruction"

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

SURFACE_LABELS = {
    "slack_channel": "Slack channel",
    "telegram_group": "Telegram group",
    "whatsapp_group": "WhatsApp group",
}


def _slug(text: str) -> str:
    import re

    value = re.sub(r"[^a-zA-Z0-9._-]+", "-", text.strip().lower()).strip("-")
    return value or "unknown"


def _run_key(model: str, task: str) -> str:
    return f"{model}|{task}|{DIRECT_GROUP_TECHNIQUE}"


def _selected_techniques(raw: str) -> list[str]:
    values = [item.strip() for item in raw.split(",") if item.strip()]
    if not values:
        return [DIRECT_GROUP_TECHNIQUE]

    invalid = [item for item in values if item != DIRECT_GROUP_TECHNIQUE]
    if invalid:
        invalid_list = ", ".join(invalid)
        raise ValueError(
            f"group-chat sweeps only support {DIRECT_GROUP_TECHNIQUE}; "
            f"unsupported technique(s): {invalid_list}"
        )

    return [DIRECT_GROUP_TECHNIQUE]


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
                completed.add(_run_key(row["model"], row["task_tag"]))
                rows.append(row)
            except (json.JSONDecodeError, KeyError):
                continue
    return completed, rows


def _surface_passthrough_args(args: argparse.Namespace, surface: str) -> list[str]:
    out: list[str] = []
    if args.openclaw_profile:
        out.extend(["--openclaw-profile", args.openclaw_profile])

    if surface == "telegram_group":
        if args.telegram_bot_token:
            out.extend(["--telegram-bot-token", args.telegram_bot_token])
        if args.telegram_group_id:
            out.extend(["--telegram-group-id", args.telegram_group_id])
        if args.telegram_agent_username:
            out.extend(["--telegram-agent-username", args.telegram_agent_username])
    elif surface == "slack_channel":
        if args.slack_bot_token:
            out.extend(["--slack-bot-token", args.slack_bot_token])
        if args.slack_channel_id:
            out.extend(["--slack-channel-id", args.slack_channel_id])
        if args.slack_agent_mention:
            out.extend(["--slack-agent-mention", args.slack_agent_mention])
    elif surface == "whatsapp_group":
        if args.whatsapp_api_url:
            out.extend(["--whatsapp-api-url", args.whatsapp_api_url])
        if args.whatsapp_access_token:
            out.extend(["--whatsapp-access-token", args.whatsapp_access_token])
        if args.whatsapp_group_id:
            out.extend(["--whatsapp-group-id", args.whatsapp_group_id])
        if args.whatsapp_agent_mention:
            out.extend(["--whatsapp-agent-mention", args.whatsapp_agent_mention])
        if args.whatsapp_extra_payload_json:
            out.extend(["--whatsapp-extra-payload-json", args.whatsapp_extra_payload_json])
    return out


def _run_one_test(
    *,
    surface: str,
    model: str,
    task_tag: str,
    results_root: Path,
    args: argparse.Namespace,
) -> dict:
    cmd = docker_run_command(REPO_ROOT, args.env_file, [
        "--agent",
        args.agent,
        "--surface-tag",
        surface,
        "--technique-tag",
        DIRECT_GROUP_TECHNIQUE,
        "--malicious-task-tag",
        task_tag,
        "--base-model",
        model,
        "--remote-host",
        args.remote_host,
        "--gateway-ws-url",
        args.gateway_ws_url,
        "--chat-timeout-s",
        str(args.chat_timeout_s),
        "--results-root",
        str(results_root),
        *_surface_passthrough_args(args, surface),
    ])

    row = {
        "model": model,
        "task_tag": task_tag,
        "technique_tag": DIRECT_GROUP_TECHNIQUE,
        "surface": surface,
        "started_at": dt.datetime.utcnow().isoformat() + "Z",
    }

    if args.dry_run:
        row["status"] = "dry_run"
        row["command"] = cmd
        return row

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=args.process_timeout_s,
            env=docker_run_env(REPO_ROOT),
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
                "send_slack",
                "send_telegram",
                "send_whatsapp",
            ]:
                if key in steps:
                    row[key] = steps[key]
        except json.JSONDecodeError:
            row["status"] = "json_parse_error"
            row["stdout_tail"] = (proc.stdout or "")[-500:]
        if proc.stderr:
            row["stderr_tail"] = proc.stderr[-300:]
    except subprocess.TimeoutExpired:
        row["status"] = "timeout"
    except Exception as exc:  # noqa: BLE001
        row["status"] = "exception"
        row["error"] = str(exc)

    row["finished_at"] = dt.datetime.utcnow().isoformat() + "Z"
    return row


def _build_parser(surface: str) -> argparse.ArgumentParser:
    label = SURFACE_LABELS.get(surface, surface)
    parser = argparse.ArgumentParser(
        description=f"Sweep: {surface} ({label}) x 5 models x 5 tasks x direct group-message instruction"
    )
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running.")
    parser.add_argument("--results-root", default=str(LAB_ROOT / "results"), help="Results directory.")
    add_agent_argument(parser)
    add_remote_host_argument(parser)
    parser.add_argument("--openclaw-profile", default="", help="Optional remote OpenClaw profile.")
    parser.add_argument("--gateway-ws-url", default=default_gateway_ws_url(), help="Gateway WS URL.")
    parser.add_argument("--chat-timeout-s", type=int, default=300, help="Timeout per chat trigger.")
    parser.add_argument("--process-timeout-s", type=int, default=900, help="Timeout per run_surface_test process.")
    parser.add_argument("--inter-test-delay", type=int, default=3, help="Seconds to wait between tests.")
    parser.add_argument("--env-file", default=str(LAB_ROOT / ".env"), help="Env file path.")
    parser.add_argument("--models", default="", help="Comma-separated model filter.")
    parser.add_argument("--tasks", default="", help="Comma-separated task filter.")
    parser.add_argument(
        "--techniques",
        "--technique",
        dest="techniques",
        default="",
        help=f"Comma-separated technique filter; only {DIRECT_GROUP_TECHNIQUE} is supported.",
    )
    parser.add_argument("--resume", default="", help="Path to an existing sweep dir to resume from.")

    parser.add_argument("--telegram-bot-token", default="", help="Override TELEGRAM_BOT_TOKEN.")
    parser.add_argument("--telegram-group-id", default="", help="Override TELEGRAM_GROUP_ID.")
    parser.add_argument("--telegram-agent-username", default="", help="Override TELEGRAM_AGENT_USERNAME.")

    parser.add_argument("--slack-bot-token", default="", help="Override SLACK_BOT_TOKEN.")
    parser.add_argument("--slack-channel-id", default="", help="Override SLACK_CHANNEL_ID.")
    parser.add_argument("--slack-agent-mention", default="", help="Override SLACK_AGENT_MENTION.")

    parser.add_argument("--whatsapp-api-url", default="", help="Override WHATSAPP_API_URL.")
    parser.add_argument("--whatsapp-access-token", default="", help="Override WHATSAPP_ACCESS_TOKEN.")
    parser.add_argument("--whatsapp-group-id", default="", help="Override WHATSAPP_GROUP_ID.")
    parser.add_argument("--whatsapp-agent-mention", default="", help="Override WHATSAPP_AGENT_MENTION.")
    parser.add_argument("--whatsapp-extra-payload-json", default="", help="Override WHATSAPP_EXTRA_PAYLOAD_JSON.")
    return parser


def main(surface: str) -> int:
    if surface not in SURFACE_LABELS:
        raise SystemExit(f"unsupported group-chat surface: {surface}")

    parser = _build_parser(surface)
    args = parser.parse_args()
    load_env_file(args.env_file)
    args.agent = resolve_agent(args.agent)
    args.remote_host = resolve_remote_host(args.remote_host)
    try:
        techniques = _selected_techniques(args.techniques)
    except ValueError as exc:
        parser.error(str(exc))

    models = [m.strip() for m in args.models.split(",") if m.strip()] or MODELS
    tasks = [t.strip() for t in args.tasks.split(",") if t.strip()] or TASKS
    total = len(models) * len(tasks) * len(techniques)

    if args.resume:
        sweep_dir = Path(args.resume)
        if not sweep_dir.is_dir():
            print(f"ERROR: resume dir does not exist: {sweep_dir}", file=sys.stderr)
            return 1
        completed_keys, prior_rows = _load_checkpoint(sweep_dir)
        print(f"Resuming sweep from {sweep_dir}")
        print(f"  {len(completed_keys)} / {total} already completed; {total - len(completed_keys)} remaining")
    else:
        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        sweep_dir = Path(args.results_root) / f"sweep_{surface}_{ts}"
        sweep_dir.mkdir(parents=True, exist_ok=True)
        completed_keys = set()
        prior_rows = []

    output_path = sweep_dir / "sweep_results.jsonl"
    summary_path = sweep_dir / "sweep_summary.json"

    print(f"Sweep: {surface}")
    print(f"Rendering: {DIRECT_GROUP_TECHNIQUE}")
    print(f"Runs: {len(models)} models x {len(tasks)} tasks x {len(techniques)} techniques = {total}")
    print(f"Output: {output_path}")
    if args.dry_run:
        print("DRY RUN: no tests will be executed.")
    print()

    sweep_meta = {
        "sweep_id": sweep_dir.name,
        "surface": surface,
        "technique": DIRECT_GROUP_TECHNIQUE,
        "techniques": techniques,
        "models": models,
        "tasks": tasks,
        "total_runs": total,
        "started_at": dt.datetime.utcnow().isoformat() + "Z",
        "dry_run": args.dry_run,
        "resumed": bool(args.resume),
    }

    ok_count = sum(1 for r in prior_rows if r.get("status") == "ok")
    error_count = sum(1 for r in prior_rows if r.get("status") not in ("ok", "dry_run"))
    skipped_count = len(completed_keys)
    rows: list[dict] = list(prior_rows)
    run_index = 0

    with output_path.open("a", encoding="utf-8") as fh:
        for model in models:
            for task_tag in tasks:
                run_index += 1
                key = _run_key(model, task_tag)
                if key in completed_keys:
                    continue

                model_slug = _slug(model.split("/")[-1])
                label = f"[{run_index}/{total}] {model_slug} x {task_tag}"
                print(f"{label} ...", end=" ", flush=True)

                row = _run_one_test(
                    surface=surface,
                    model=model,
                    task_tag=task_tag,
                    results_root=sweep_dir / "results",
                    args=args,
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

                if not args.dry_run and args.inter_test_delay > 0:
                    time.sleep(args.inter_test_delay)

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
