#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


LAB_ROOT = Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _objective_from_task_id(surface: str, task_id: str) -> str:
    prefix = f"{surface}_"
    value = task_id
    if value.startswith(prefix):
        value = value[len(prefix) :]
    if value.endswith("_001"):
        value = value[:-4]
    return value


def main() -> int:
    matrix = _load_json(LAB_ROOT / "taxonomy" / "benchmark_case_matrix.json")
    surfaces = {row["name"] for row in _load_json(LAB_ROOT / "taxonomy" / "surfaces.json")["surfaces"]}
    techniques = {row["tag"] for row in _load_json(LAB_ROOT / "taxonomy" / "injection_techniques.json")["tags"]}
    objectives = {
        json.loads(line)["malicious_task_tag"]
        for line in (LAB_ROOT / "tasks" / "malicious_tasks.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    task_surfaces = {
        task["injection_surface"]
        for path in (LAB_ROOT / "tasks" / "by_surface").glob("*.jsonl")
        for task in _load_jsonl(path)
    }

    errors: list[str] = []
    if set(matrix["objectives"]) != objectives:
        errors.append("matrix objectives do not match tasks/malicious_tasks.jsonl")

    total = 0
    prompt_level = set(matrix["prompt_level_techniques"])
    if not prompt_level <= techniques:
        errors.append(f"unknown prompt-level techniques: {sorted(prompt_level - techniques)}")

    for row in matrix["surface_matrix"]:
        surface = row["surface"]
        if surface not in surfaces:
            errors.append(f"unknown matrix surface: {surface}")
        if surface not in task_surfaces:
            errors.append(f"matrix surface has no task manifest: {surface}")

        row_objectives = objectives if row["objectives"] == "all" else set(row["objectives"])
        row_techniques = prompt_level if row["techniques"] == "prompt_level_techniques" else set(row["techniques"])
        if not row_objectives <= objectives:
            errors.append(f"{surface}: unknown objectives {sorted(row_objectives - objectives)}")
        if not row_techniques <= techniques:
            errors.append(f"{surface}: unknown techniques {sorted(row_techniques - techniques)}")

        expected = len(row_objectives) * len(row_techniques)
        if int(row["case_count"]) != expected:
            errors.append(f"{surface}: case_count {row['case_count']} != computed {expected}")
        total += expected

        manifest_path = LAB_ROOT / "tasks" / "by_surface" / f"{surface}.jsonl"
        if manifest_path.exists():
            manifest_objectives = {
                _objective_from_task_id(surface, str(task.get("task_id", "")))
                for task in _load_jsonl(manifest_path)
            }
            if manifest_objectives != row_objectives:
                errors.append(
                    f"{surface}: task manifest objectives {sorted(manifest_objectives)} "
                    f"!= matrix objectives {sorted(row_objectives)}"
                )

    if total != int(matrix["total_case_count"]):
        errors.append(f"total_case_count {matrix['total_case_count']} != computed {total}")

    if errors:
        print("Benchmark matrix audit failed:")
        for err in errors:
            print(f"- {err}")
        return 1

    print(f"Benchmark matrix audit passed for {total} paper cases.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
