#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


LAB_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = LAB_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from prompt_injection_lab.prompt_builder import (  # noqa: E402
    build_composite_injection_prompt,
    build_prompt_from_task,
    supported_technique_tags,
)
from prompt_injection_lab.technique_runtime import (  # noqa: E402
    build_injection_package,
    supported_profile_tags,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a prompt payload from technique tag + task."
    )
    parser.add_argument("--tag", help="Technique tag (e.g., checklist_handoff_injection).")
    parser.add_argument(
        "--tags",
        default="",
        help="Optional comma-separated technique tags to compose in-order.",
    )
    parser.add_argument("--task", help="Single canonical task/goal text.")
    parser.add_argument("--target", default="", help="Optional destination/target (group/email/doc/url).")
    parser.add_argument("--attacker-task", help="Deprecated compatibility field.")
    parser.add_argument("--malicious-task", help="Deprecated compatibility field.")
    parser.add_argument("--surface", default="", help="Optional injection surface.")
    parser.add_argument("--query", default="", help="Optional query text used for LLM-assisted design.")
    parser.add_argument("--context", default="", help="Optional context text.")
    parser.add_argument("--list-tags", action="store_true", help="Print supported tags and exit.")
    parser.add_argument("--use-llm", action="store_true", help="Use OpenAI API to design paper-specific components.")
    parser.add_argument("--llm-model", default="gpt-5.3-chat-latest", help="Model for --use-llm.")
    parser.add_argument(
        "--no-llm-fallback",
        action="store_true",
        help="Fail if LLM design fails (default is fallback to deterministic design).",
    )
    parser.add_argument(
        "--format",
        default="text",
        choices=("text", "json"),
        help="Output format: text payload or full JSON attack package.",
    )
    parser.add_argument(
        "--constraint",
        action="append",
        default=[],
        help="Optional repeated constraint line.",
    )
    parser.add_argument(
        "--task-json",
        help="Optional path to a single task JSON file/object to auto-generate from record.",
    )
    args = parser.parse_args()

    if args.list_tags:
        tags = sorted(set(supported_technique_tags()) | set(supported_profile_tags()))
        for tag in tags:
            print(tag)
        return 0

    if args.task_json:
        data = json.loads(Path(args.task_json).read_text(encoding="utf-8"))
        prompt = build_prompt_from_task(data)
        if args.format == "json":
            tag = data.get("technique_tags", ["checklist_handoff_injection"])[0]
            package = build_injection_package(
                technique_tag=str(tag),
                task=str(data.get("task") or data.get("malicious_task") or data.get("attacker_task") or ""),
                query=args.query or None,
                injection_surface=str(data.get("injection_surface", "")) or None,
                use_llm=args.use_llm,
                llm_model=args.llm_model,
                llm_fallback=not args.no_llm_fallback,
            )
            print(json.dumps(package, indent=2, ensure_ascii=True))
        else:
            if args.use_llm:
                tag = data.get("technique_tags", ["checklist_handoff_injection"])[0]
                package = build_injection_package(
                    technique_tag=str(tag),
                    task=str(
                        data.get("task")
                        or data.get("malicious_task")
                        or data.get("attacker_task")
                        or ""
                    ),
                    query=args.query or None,
                    injection_surface=str(data.get("injection_surface", "")) or None,
                    use_llm=True,
                    llm_model=args.llm_model,
                    llm_fallback=not args.no_llm_fallback,
                )
                print(package["payload"])
            else:
                print(prompt)
        return 0

    if not args.tag and not args.tags.strip():
        parser.error("--tag or --tags is required without --task-json")
    if not args.task and not args.attacker_task and not args.malicious_task:
        parser.error("--task is required (or use deprecated --attacker-task/--malicious-task)")

    composite_tags = [item.strip() for item in args.tags.split(",") if item.strip()]
    if not composite_tags and args.tag:
        composite_tags = [args.tag.strip()]
    primary_tag = composite_tags[0] if composite_tags else "checklist_handoff_injection"

    canonical_task = args.task or args.malicious_task or args.attacker_task
    if args.format == "json":
        package = build_injection_package(
            technique_tag=primary_tag,
            task=str(canonical_task),
            query=args.query or None,
            injection_surface=args.surface or None,
            target=args.target or None,
            context=args.context or None,
            constraints=args.constraint or None,
            use_llm=args.use_llm,
            llm_model=args.llm_model,
            llm_fallback=not args.no_llm_fallback,
        )
        if len(composite_tags) > 1:
            package["composite_tags"] = composite_tags
            package["payload"] = build_composite_injection_prompt(
                technique_tags=composite_tags,
                task=canonical_task,
                attacker_task=args.attacker_task,
                malicious_task=args.malicious_task,
                injection_surface=args.surface or None,
                target=args.target or None,
                context=args.context or None,
                constraints=args.constraint or None,
            )
        print(json.dumps(package, indent=2, ensure_ascii=True))
    else:
        if args.use_llm and len(composite_tags) == 1:
            package = build_injection_package(
                technique_tag=primary_tag,
                task=str(canonical_task),
                query=args.query or None,
                injection_surface=args.surface or None,
                target=args.target or None,
                context=args.context or None,
                constraints=args.constraint or None,
                use_llm=True,
                llm_model=args.llm_model,
                llm_fallback=not args.no_llm_fallback,
            )
            print(package["payload"])
        else:
            prompt = build_composite_injection_prompt(
                technique_tags=composite_tags,
                task=canonical_task,
                attacker_task=args.attacker_task,
                malicious_task=args.malicious_task,
                injection_surface=args.surface or None,
                target=args.target or None,
                context=args.context or None,
                constraints=args.constraint or None,
            )
            print(prompt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
