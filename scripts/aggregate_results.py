#!/usr/bin/env python3
"""Aggregate LivePI benchmark results into a single JSON / markdown / CSV.

Scans results/<run>/summary.json for every benchmark run, extracts the
deterministic verifier outcomes ("hard"), optionally joins with the LLM
judge verdicts from results/llm_judge_results.jsonl ("judge"), and emits a
unified report.

Output JSON shape (one entry per run):
{
  "run_name": "...",
  "agent": "...",
  "base_model": "...",
  "agent_model": "...",
  "surface": "...",
  "objective": "...",
  "techniques": ["..."],
  "status": "ok|error",
  "error": "" or "...",
  "duration_s": 12.3,
  "tool_calls_observed": 8,
  "hard": {
    "attack_success": true|false|null,
    "email_inbox": {...},          # full email verifier block when present
    "system_hardening": {...},     # full hardening verifier block when present
    "wallet_file_deletion": {...}, # full wallet verifier block when present
    "evidence": ["..."]
  },
  "judge": null OR {
    "attack_success": ...,
    "objective_achieved": ...,
    "classification": ...,
    "confidence": ...,
    "score_attack_success_for_asr": ...,
    "rationale": "..."
  }
}

Usage:
  python3 scripts/aggregate_results.py [RESULTS_DIR] [--json OUT.json]
                                       [--csv OUT.csv] [--markdown]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any


def _safe(d: Any, *path, default=None):
    for p in path:
        if not isinstance(d, dict):
            return default
        d = d.get(p)
        if d is None:
            return default
    return d


def _extract_hard(steps: dict[str, Any]) -> dict[str, Any]:
    email = steps.get("email_inbox_verifier") or {}
    hardening = steps.get("system_hardening_verifier_after_action") or steps.get("system_hardening_verifier") or {}
    wallet = steps.get("wallet_file_deletion_verifier") or {}

    # Pick the most specific attack_success signal: any verifier that ran wins.
    if email and "attack_success" in email:
        attack_success = email.get("attack_success")
    elif hardening and "passed" in hardening:
        attack_success = hardening.get("passed")
    elif wallet and "attack_success" in wallet:
        attack_success = wallet.get("attack_success")
    else:
        attack_success = None

    evidence: list[str] = []
    if email.get("matched_messages"):
        evidence.append(f"email: {len(email['matched_messages'])} matched msg(s) -> {email.get('expected_recipients')}")
    if hardening.get("evidence"):
        evidence.extend([f"hardening: {e}" for e in hardening.get("evidence", [])])
    if wallet.get("deleted_files"):
        evidence.append(f"wallet: {len(wallet['deleted_files'])} file(s) deleted")
    return {
        "attack_success": attack_success,
        "email_inbox": email or None,
        "system_hardening": hardening or None,
        "wallet_file_deletion": wallet or None,
        "evidence": evidence,
    }


def _read_per_run_judge(run_dir: Path) -> dict[str, Any] | None:
    """Each run directory contains its own judge.json once llm_judge_runs.py has
    scored it. Aggregating just reads that file - the legacy global jsonl is no
    longer required."""
    judge_file = run_dir / "judge.json"
    if not judge_file.exists():
        return None
    try:
        return json.loads(judge_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _build_judge_block(judge_row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not judge_row:
        return None
    verdict = judge_row.get("verdict") or {}
    score = judge_row.get("score") or {}
    return {
        "attack_success": verdict.get("attack_success"),
        "objective_achieved": verdict.get("objective_achieved"),
        "classification": verdict.get("classification"),
        "confidence": verdict.get("confidence"),
        "score_attack_success_for_asr": score.get("attack_success_for_asr"),
        "rationale": (verdict.get("rationale") or "")[:600],
    }


def aggregate(results_dir: Path, judge_path: Path | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for child in sorted(results_dir.iterdir()):
        if not child.is_dir():
            continue
        summary_file = child / "summary.json"
        if not summary_file.exists():
            continue
        try:
            summary = json.loads(summary_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        steps = summary.get("steps", {}) if isinstance(summary.get("steps"), dict) else {}
        ct = steps.get("chat_trigger", {}) if isinstance(steps.get("chat_trigger"), dict) else {}
        chat_result = ct.get("chat_result", {}) if isinstance(ct.get("chat_result"), dict) else {}
        events = chat_result.get("events") or []
        duration = events[0].get("duration_s") if events and isinstance(events[0], dict) else None

        run_name = summary.get("run_name") or child.name
        row = {
            "run_name": run_name,
            "agent": summary.get("agent"),
            "base_model": summary.get("base_model") or "",
            "agent_model": _safe(steps, "cli_agent_runtime", "model") or "",
            "surface": summary.get("surface_tag"),
            "objective": summary.get("malicious_task_tag"),
            "techniques": summary.get("technique_tags") or [summary.get("technique_tag")] if summary.get("technique_tag") else summary.get("technique_tags") or [],
            "status": summary.get("status"),
            "error": (summary.get("error") or "")[:400],
            "duration_s": duration,
            "tool_calls_observed": len(chat_result.get("tool_calls_observed") or []),
            "started_at": summary.get("started_at"),
            "finished_at": summary.get("finished_at"),
            "hard": _extract_hard(steps),
            "judge": _build_judge_block(_read_per_run_judge(child)),
        }
        rows.append(row)
    return rows


def _bool_cell(v: Any) -> str:
    if v is True:
        return "✓"
    if v is False:
        return "✗"
    return "-"


def render_markdown(rows: list[dict[str, Any]]) -> str:
    header = ["agent", "model", "surface", "objective", "technique", "status", "hard", "judge", "dur(s)", "tc"]
    lines = ["| " + " | ".join(header) + " |",
             "|" + "|".join(["---"] * len(header)) + "|"]
    for r in rows:
        techs = ",".join((r.get("techniques") or []) or ["-"])
        lines.append("| " + " | ".join([
            str(r.get("agent") or "-"),
            (r.get("base_model") or r.get("agent_model") or "-")[:35],
            str(r.get("surface") or "-"),
            str(r.get("objective") or "-")[:32],
            techs[:30],
            str(r.get("status") or "-"),
            _bool_cell(_safe(r, "hard", "attack_success")),
            _bool_cell(_safe(r, "judge", "score_attack_success_for_asr")),
            (f"{r.get('duration_s'):.1f}" if isinstance(r.get("duration_s"), (int, float)) else "-"),
            str(r.get("tool_calls_observed") or 0),
        ]) + " |")
    return "\n".join(lines)


def render_csv(rows: list[dict[str, Any]], out: Path) -> None:
    cols = ["run_name", "agent", "base_model", "agent_model", "surface", "objective",
            "techniques", "status", "error", "duration_s", "tool_calls_observed",
            "hard_attack_success", "judge_attack_success", "judge_objective_achieved",
            "judge_classification", "judge_confidence",
            "started_at", "finished_at"]
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([
                r.get("run_name"), r.get("agent"),
                r.get("base_model"), r.get("agent_model"),
                r.get("surface"), r.get("objective"),
                "|".join(r.get("techniques") or []),
                r.get("status"), r.get("error"),
                r.get("duration_s"), r.get("tool_calls_observed"),
                _safe(r, "hard", "attack_success"),
                _safe(r, "judge", "attack_success"),
                _safe(r, "judge", "objective_achieved"),
                _safe(r, "judge", "classification"),
                _safe(r, "judge", "confidence"),
                r.get("started_at"), r.get("finished_at"),
            ])


def _asr_summary(rows: list[dict[str, Any]]) -> str:
    lines = []
    by_agent: dict[str, list[bool]] = {}
    by_agent_judge: dict[str, list[bool]] = {}
    for r in rows:
        agent = r.get("agent") or "unknown"
        h = _safe(r, "hard", "attack_success")
        j = _safe(r, "judge", "score_attack_success_for_asr")
        if h is not None:
            by_agent.setdefault(agent, []).append(bool(h))
        if j is not None:
            by_agent_judge.setdefault(agent, []).append(bool(j))
    lines.append("\n## ASR by agent")
    lines.append("| agent | hard ASR | judge ASR |")
    lines.append("|---|---|---|")
    for agent in sorted(set(by_agent.keys()) | set(by_agent_judge.keys())):
        h = by_agent.get(agent, [])
        j = by_agent_judge.get(agent, [])
        h_str = f"{sum(h)}/{len(h)} = {sum(h)/len(h):.0%}" if h else "-"
        j_str = f"{sum(j)}/{len(j)} = {sum(j)/len(j):.0%}" if j else "-"
        lines.append(f"| {agent} | {h_str} | {j_str} |")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate LivePI benchmark results.")
    parser.add_argument("results_dir", nargs="?", default="prompt_injection_lab/results", type=Path,
                        help="Path to the results directory.")
    parser.add_argument("--json", dest="out_json", type=Path, default=None,
                        help="Write aggregated rows as JSON list.")
    parser.add_argument("--csv", dest="out_csv", type=Path, default=None,
                        help="Write aggregated rows as CSV.")
    parser.add_argument("--no-markdown", action="store_true",
                        help="Suppress stdout markdown table.")
    args = parser.parse_args()

    results_dir = args.results_dir.resolve()
    if not results_dir.is_dir():
        print(f"ERROR: results_dir not found: {results_dir}", file=sys.stderr)
        return 1
    rows = aggregate(results_dir)
    judged = sum(1 for r in rows if r.get("judge") is not None)
    print(f"# Aggregated {len(rows)} run(s) from {results_dir} (judge.json present in {judged})", file=sys.stderr)

    if args.out_json:
        args.out_json.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"# wrote {args.out_json}", file=sys.stderr)
    if args.out_csv:
        render_csv(rows, args.out_csv)
        print(f"# wrote {args.out_csv}", file=sys.stderr)
    if not args.no_markdown:
        print(render_markdown(rows))
        print(_asr_summary(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
