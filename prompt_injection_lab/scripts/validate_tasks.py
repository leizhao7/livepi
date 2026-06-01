#!/usr/bin/env python3
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any


LAB_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = LAB_ROOT.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


REQUIRED_FIELDS = {
    "task_id",
    "title",
    "injection_surface",
    "surface_action",
    "technique_tags",
    "attacker_task",
    "malicious_task",
    "malicious_goal",
    "environment",
    "verifier",
    "metadata",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for line_num, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            task = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_num} invalid JSON: {exc}") from exc
        if not isinstance(task, dict):
            raise ValueError(f"{path}:{line_num} expected JSON object")
        tasks.append(task)
    return tasks


def validate_module_ref(path: Path, task_id: str, block: dict[str, Any], label: str) -> list[str]:
    errors: list[str] = []
    mod_name = block.get("python_module")
    fn_name = block.get("python_callable")
    if not mod_name or not fn_name:
        return [f"{path} task={task_id}: {label} missing module/callable"]

    try:
        module = importlib.import_module(mod_name)
    except Exception as exc:  # noqa: BLE001
        return [f"{path} task={task_id}: cannot import {label} module {mod_name}: {exc}"]

    if not hasattr(module, fn_name):
        errors.append(f"{path} task={task_id}: {label} callable not found: {mod_name}.{fn_name}")
    return errors


def validate_task(path: Path, task: dict[str, Any], known_tags: set[str], known_surfaces: set[str]) -> list[str]:
    errors: list[str] = []
    task_id = str(task.get("task_id", "<missing>"))

    missing = REQUIRED_FIELDS - set(task.keys())
    if missing:
        errors.append(f"{path} task={task_id}: missing fields: {sorted(missing)}")
        return errors

    if not task["technique_tags"]:
        errors.append(f"{path} task={task_id}: technique_tags must not be empty")
    for tag in task["technique_tags"]:
        if tag not in known_tags:
            errors.append(f"{path} task={task_id}: unknown technique tag: {tag}")

    surface = str(task.get("injection_surface", ""))
    if surface not in known_surfaces:
        errors.append(f"{path} task={task_id}: unknown paper surface: {surface}")

    for section in ("environment", "verifier"):
        block = task.get(section, {})
        if not isinstance(block, dict):
            errors.append(f"{path} task={task_id}: {section} must be an object")
            continue
        errors.extend(validate_module_ref(path, task_id, block, section))

    return errors


def main() -> int:
    techniques = load_json(LAB_ROOT / "taxonomy" / "injection_techniques.json")
    known_tags = {entry["tag"] for entry in techniques.get("tags", [])}
    surfaces = load_json(LAB_ROOT / "taxonomy" / "surfaces.json")
    known_surfaces = {entry["name"] for entry in surfaces.get("surfaces", [])}

    task_files = sorted((LAB_ROOT / "tasks" / "by_surface").glob("*.jsonl"))
    task_files.append(LAB_ROOT / "tasks" / "all_tasks.jsonl")

    all_errors: list[str] = []
    unique_ids: set[str] = set()

    for task_file in task_files:
        tasks = load_jsonl(task_file)
        expected_surface = task_file.stem if task_file.parent.name == "by_surface" else None
        seen_in_file: set[str] = set()
        for task in tasks:
            task_id = str(task.get("task_id", ""))
            if task_id in seen_in_file:
                all_errors.append(f"{task_file}: duplicate task_id in file: {task_id}")
            seen_in_file.add(task_id)
            unique_ids.add(task_id)

            if expected_surface and task.get("injection_surface") != expected_surface:
                all_errors.append(
                    f"{task_file} task={task_id}: injection_surface "
                    f"{task.get('injection_surface')} != {expected_surface}"
                )

            all_errors.extend(validate_task(task_file, task, known_tags, known_surfaces))

    if all_errors:
        print("Validation failed:")
        for err in all_errors:
            print(f"- {err}")
        return 1

    print(f"Validation passed. Checked {len(task_files)} files and {len(unique_ids)} unique task IDs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
