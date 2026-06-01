#!/usr/bin/env python3
"""Rebuild livepi-artifacts data/*.json from a results directory.

Usage:
    python3 artifacts/scripts/build_artifacts.py \
        --results-root prompt_injection_lab/results \
        --out artifacts/livepi/data
"""
from __future__ import annotations
import argparse, glob, json, os, re
from pathlib import Path


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s or "unknown").strip("_")


def collect(results_root: Path) -> dict[tuple[str, str], list[dict]]:
    groups: dict[tuple[str, str], list[dict]] = {}
    for run in sorted(glob.glob(str(results_root / "*/"))):
        sp = Path(run) / "summary.json"
        if not sp.exists():
            continue
        try:
            d = json.loads(sp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if d.get("status") != "ok":
            continue
        agent = d.get("agent") or "unknown"
        model = d.get("base_model") or "unknown"
        ct = d.get("steps", {}).get("chat_trigger", {}).get("chat_result", {}) or {}
        ev = d.get("steps", {}).get("email_inbox_verifier", {}) or {}
        sh = d.get("steps", {}).get("system_hardening_verifier_after_action", {}) or {}
        wallet = d.get("steps", {}).get("wallet_file_deletion_verifier", {}) or {}
        succ = ev.get("attack_success")
        if succ is None and sh: succ = sh.get("passed")
        if succ is None and wallet: succ = wallet.get("attack_success")
        case = {
            "run_name": d.get("run_name") or run.rstrip("/").split("/")[-1],
            "surface": d.get("surface_tag"),
            "technique": d.get("technique_tag") or (d.get("technique_tags") or [None])[0],
            "objective": d.get("malicious_task_tag"),
            "hard_attack_success": succ,
            "judge_attack_success": None,
            "duration_s": (ct.get("events") or [{}])[0].get("duration_s"),
            "tool_calls_observed": len(ct.get("tool_calls_observed") or []),
            "started_at": d.get("started_at"),
            "finished_at": d.get("finished_at"),
            "assistant_text_snippet": (ct.get("assistant_text") or "")[:1500],
        }
        judge = Path(run) / "judge.json"
        if judge.exists():
            try:
                jd = json.loads(judge.read_text(encoding="utf-8"))
                score = jd.get("score", {}) or {}
                verdict = jd.get("verdict", {}) or {}
                case["judge_attack_success"] = score.get("attack_success_for_asr")
                case["judge_classification"] = verdict.get("classification")
                case["judge_confidence"] = verdict.get("confidence")
                case["judge_rationale"] = (verdict.get("rationale") or "")[:600]
            except Exception:
                pass
        groups.setdefault((agent, model), []).append(case)
    return groups


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--results-root", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    groups = collect(args.results_root)
    args.out.mkdir(parents=True, exist_ok=True)
    n_files = 0
    for (agent, model), cases in sorted(groups.items()):
        agent_dir = args.out / _slug(agent)
        agent_dir.mkdir(exist_ok=True)
        n_total = len(cases)
        n_hard  = sum(1 for c in cases if c["hard_attack_success"] is True)
        n_judge = sum(1 for c in cases if c["judge_attack_success"] is True)
        payload = {
            "parameters": {
                "agent_harness": agent,
                "base_model": model,
                "total_cases": n_total,
                "hard_attack_success_count": n_hard,
                "hard_attack_success_rate": round(n_hard / n_total, 4) if n_total else None,
                "judge_attack_success_count": n_judge,
                "judge_attack_success_rate": round(n_judge / n_total, 4) if n_total else None,
                "evaluation_date": max((c.get("finished_at") or "") for c in cases)[:10] or None,
                "evaluation_provider": "openrouter",
                "paper": "arXiv:2605.17986",
            },
            "cases": cases,
        }
        out = agent_dir / f"{_slug(model)}.json"
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        n_files += 1
    print(f"wrote {n_files} artifacts to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
