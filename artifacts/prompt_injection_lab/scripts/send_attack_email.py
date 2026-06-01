#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


LAB_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = LAB_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from prompt_injection_lab.prompt_builder import build_prompt_from_task  # noqa: E402
from prompt_injection_lab.surfaces.gmail_interface import send_gmail_email  # noqa: E402
from prompt_injection_lab.surfaces.smtp_interface import (  # noqa: E402
    attacker_smtp_config_from_env,
    send_smtp_email,
)
from prompt_injection_lab.technique_runtime import build_injection_package  # noqa: E402


def _load_task(path: Path) -> dict[str, object]:
    raw = path.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return parsed


def _split_subject_body(payload: str, default_subject: str) -> tuple[str, str]:
    text = payload.strip()
    if not text:
        return default_subject, ""

    lines = text.splitlines()
    first = lines[0].strip() if lines else ""
    if first.lower().startswith("subject:"):
        subject = first.split(":", 1)[1].strip() or default_subject
        rest = lines[1:]
        if rest and not rest[0].strip():
            rest = rest[1:]
        return subject, "\n".join(rest).strip()
    return default_subject, text


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if (value.startswith("'") and value.endswith("'")) or (
            value.startswith('"') and value.endswith('"')
        ):
            value = value[1:-1]
        if key not in os.environ:
            os.environ[key] = value


def _resolve_transport(mode: str) -> str:
    if mode != "auto":
        return mode
    if os.getenv("SMTP_HOST", "").strip() and os.getenv("SMTP_USER", "").strip() and os.getenv(
        "SMTP_PASS", ""
    ).strip():
        return "smtp"
    return "gmail_api"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a prompt-injection email payload and optionally send via SMTP or Gmail API."
    )
    parser.add_argument("--to", required=True, help="Recipient email (agent inbox).")
    parser.add_argument("--from", dest="sender", default="", help="Sender email override.")
    parser.add_argument("--subject", default="", help="Override subject line.")
    parser.add_argument("--tag", help="Technique tag.")
    parser.add_argument("--task", help="Task text for prompt generation.")
    parser.add_argument("--task-json", help="Path to a task JSON object.")
    parser.add_argument("--surface", default="email_gmail", help="Injection surface for generation.")
    parser.add_argument("--target", default="", help="Embedded target value used by prompt generator.")
    parser.add_argument("--context", default="", help="Context value used by prompt generator.")
    parser.add_argument("--query", default="", help="Optional query for LLM-assisted design.")
    parser.add_argument("--constraint", action="append", default=[], help="Optional repeated constraint.")
    parser.add_argument("--use-llm", action="store_true", help="Use OpenAI API for design step.")
    parser.add_argument("--llm-model", default="gpt-5.3-chat-latest", help="LLM model for --use-llm.")
    parser.add_argument(
        "--transport",
        default="auto",
        choices=("auto", "smtp", "gmail_api"),
        help="Send transport. auto prefers SMTP if SMTP_* env vars exist.",
    )
    parser.add_argument(
        "--env-file",
        default=str(LAB_ROOT / ".env"),
        help="Env file to load before auth resolution (default: prompt_injection_lab/.env).",
    )
    parser.add_argument("--send", action="store_true", help="Actually send email. Default is dry-run.")
    parser.add_argument(
        "--output-json",
        default="",
        help="Optional output path for generated package/result JSON.",
    )
    args = parser.parse_args()

    if not args.tag and not args.task_json:
        parser.error("Provide --tag/--task or --task-json.")
    if args.tag and not args.task:
        parser.error("--task is required with --tag.")

    _load_env_file(Path(args.env_file))

    sender = (
        args.sender.strip()
        or os.getenv("SMTP_FROM", "").strip()
        or os.getenv("GMAIL_SENDER", "").strip()
    )

    if args.task_json:
        task_obj = _load_task(Path(args.task_json))
        tag = str(task_obj.get("technique_tags", ["checklist_handoff_injection"])[0])
        task_text = str(
            task_obj.get("task")
            or task_obj.get("malicious_task")
            or task_obj.get("attacker_task")
            or ""
        )
        if not task_text:
            parser.error("task JSON missing task/malicious_task/attacker_task")
        generated_payload = build_prompt_from_task(task_obj)
        package = build_injection_package(
            technique_tag=tag,
            task=task_text,
            query=args.query or None,
            injection_surface=args.surface or None,
            target=args.target or None,
            context=args.context or None,
            constraints=args.constraint or None,
            use_llm=args.use_llm,
            llm_model=args.llm_model,
        )
        package["payload"] = generated_payload
    else:
        package = build_injection_package(
            technique_tag=args.tag,
            task=str(args.task),
            query=args.query or None,
            injection_surface=args.surface or None,
            target=args.target or None,
            context=args.context or None,
            constraints=args.constraint or None,
            use_llm=args.use_llm,
            llm_model=args.llm_model,
        )

    default_subject = "Operations follow-up"
    parsed_subject, parsed_body = _split_subject_body(str(package.get("payload", "")), default_subject)
    subject = args.subject.strip() or parsed_subject
    body = parsed_body

    result: dict[str, object] = {
        "mode": "send" if args.send else "dry_run",
        "sender": sender,
        "to": args.to,
        "subject": subject,
        "technique_tag": package.get("technique_tag"),
        "artifacts_mode": package.get("artifacts", {}).get("mode")
        if isinstance(package.get("artifacts"), dict)
        else None,
        "payload_preview": body[:1200],
    }

    if args.send:
        transport = _resolve_transport(args.transport)
        result["transport"] = transport
        if transport == "smtp":
            cfg = attacker_smtp_config_from_env()
            send_result = send_smtp_email(
                recipient=args.to,
                subject=subject,
                body=body,
                config=cfg,
                sender_override=sender or None,
            )
            result["smtp"] = send_result.to_dict()
            result["sender"] = send_result.sender
        else:
            if not sender:
                parser.error("Sender is required for Gmail API. Set --from or GMAIL_SENDER.")
            send_result = send_gmail_email(
                sender=sender,
                recipient=args.to,
                subject=subject,
                body=body,
            )
            result["gmail"] = send_result.to_dict()
    else:
        result["transport"] = _resolve_transport(args.transport)
        result["note"] = "Dry-run only. Add --send to send via selected transport."

    rendered = json.dumps(result, indent=2, ensure_ascii=True)
    print(rendered)

    if args.output_json:
        out_path = Path(args.output_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
