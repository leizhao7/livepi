#!/usr/bin/env python3
"""Report which LivePI env values are still missing.

The script never prints secret values. It only reports present/missing keys.
"""

from __future__ import annotations

import argparse
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = REPO_ROOT / "secrets.env"

PROVIDER_KEYS = (
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
    "MOONSHOT_API_KEY",
    "MODELSTUDIO_API_KEY",
    "ZAI_API_KEY",
    "GOOGLE_API_KEY",
    "OPENAI_API_KEY",
)

AGENT_ENV_PREFIXES = {
    "hermes": "HERMES",
    "codex": "CODEX",
    "claude_code": "CLAUDE_CODE",
}

GROUPS: dict[str, tuple[str, ...]] = {
    "core": (
        "OPENCLAW_BENCHMARK_RECIPIENT_EMAIL",
    ),
    "hermes": (
        "LIVEPI_AGENT",
    ),
    "codex": (
        "LIVEPI_AGENT",
    ),
    "claude_code": (
        "LIVEPI_AGENT",
    ),
    "scan_py": (
        "OPENCLAW_BENCHMARK_SCAN_PY_URL",
    ),
    "email": (
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USER",
        "SMTP_PASS",
        "SMTP_FROM",
        "IMAP_HOST",
        "IMAP_PORT",
        "IMAP_USER",
        "IMAP_PASS",
    ),
    "telegram": (),
    "slack": (
        "SLACK_BOT_TOKEN",
        "SLACK_APP_TOKEN",
        "SLACK_CHANNEL_ID",
    ),
    "whatsapp": (
        "WHATSAPP_API_URL",
        "WHATSAPP_GROUP_ID",
        "WHATSAPP_AGENT_MENTION",
    ),
    "gist": (
        "GITHUB_GIST_TOKEN",
    ),
    "web_link": (),
    "github_supply_chain": (
        "GITHUB_SUPPLY_CHAIN_REPO",
    ),
    "reddit": (
        "REDDIT_CLIENT_ID",
        "REDDIT_CLIENT_SECRET",
        "REDDIT_USERNAME",
        "REDDIT_PASSWORD",
    ),
    "x": (
        "X_API_KEY",
        "X_API_SECRET",
        "X_ACCESS_TOKEN",
        "X_ACCESS_SECRET",
    ),
    "solana": (
        "SOLANA_PRIVATE_KEY",
        "SOLANA_RPC_URL",
    ),
}

SCAN_PY_SOURCE_DEFAULT = ""  # auto-resolved by setup using GITHUB_TOKEN -> https://github.com/<your-user>/safety_scan/blob/main/scan.py


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'").strip('"')
    return values


def is_set(values: dict[str, str], key: str) -> bool:
    value = values.get(key, "").strip()
    if not value:
        return False
    if value in {"recipient@example.com", "attacker@example.com", "agent-inbox@example.com"}:
        return False
    if value.startswith("your-") or "your-org-or-user" in value:
        return False
    return True


def selected_agent(values: dict[str, str]) -> str:
    return values.get("LIVEPI_AGENT", "").strip().lower() or "openclaw"


def agent_env_names(values: dict[str, str], suffix: str, *shared_names: str) -> tuple[str, ...]:
    names: list[str] = []
    prefix = AGENT_ENV_PREFIXES.get(selected_agent(values))
    if prefix:
        names.append(f"{prefix}_{suffix}")
    names.extend(shared_names)
    return tuple(names)


def first_set_key(values: dict[str, str], *keys: str) -> str:
    for key in keys:
        if is_set(values, key):
            return key
    return ""


def missing(values: dict[str, str], keys: tuple[str, ...]) -> list[str]:
    return [key for key in keys if not is_set(values, key)]


def report_group(values: dict[str, str], name: str, env_path: Path | None = None) -> bool:
    if name == "core":
        misses = missing(values, GROUPS[name])
        if misses:
            print(f"{name}: missing {', '.join(misses)}")
            return False
        recipient = values.get("OPENCLAW_BENCHMARK_RECIPIENT_EMAIL", "").strip().lower()
        agent_mailboxes = {
            values.get("IMAP_USER", "").strip().lower(),
            values.get("SMTP_USER", "").strip().lower(),
            values.get("SMTP_FROM", "").strip().lower(),
        }
        attacker_email = (
            values.get("OPENCLAW_BENCHMARK_ATTACKER_EMAIL", "").strip()
            or values.get("ATTACKER_SMTP_FROM", "").strip()
            or values.get("ATTACKER_SMTP_USER", "").strip()
        )
        if recipient and recipient in agent_mailboxes and attacker_email:
            print("core: ok (recipient matches agent mailbox; runner will use attacker email fallback)")
        else:
            alias_mode = values.get("OPENCLAW_BENCHMARK_RECIPIENT_PLUS_ALIAS", "auto").strip() or "auto"
            print(f"core: ok (recipient plus-alias={alias_mode})")
        return True
    if name == "hermes":
        agent = values.get("LIVEPI_AGENT", "").strip().lower() or "openclaw"
        if agent != "hermes":
            print("hermes: skipped (LIVEPI_AGENT is not hermes)")
            return True
        command = values.get("HERMES_COMMAND", "").strip() or "hermes"
        require_api_key = values.get("HERMES_REQUIRE_API_KEY", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        api_present = is_set(values, "HERMES_API_KEY") or is_set(values, "OPENROUTER_API_KEY")
        if require_api_key and not api_present:
            print("hermes: missing HERMES_API_KEY or OPENROUTER_API_KEY")
            return False
        workdir = values.get("HERMES_WORKDIR", "").strip() or "<per-run auto>"
        skills_dir = values.get("HERMES_SKILLS_DIR", "").strip() or "<per-run auto>"
        install_skills = values.get("HERMES_INSTALL_BUNDLED_SKILLS", "true").strip() or "true"
        query_flag = values.get("HERMES_QUERY_FLAG", "-q").strip() or "-q"
        provider = values.get("HERMES_PROVIDER", "openrouter").strip() or "openrouter"
        model = values.get("HERMES_MODEL", "").strip() or "<hermes default>"
        api_status = "present" if api_present else "not required"
        print(
            f"hermes: ok (command={command}, api_key={api_status}, "
            f"query_flag={query_flag}, provider={provider}, model={model}, "
            f"workdir={workdir}, skills={skills_dir}, bundled_skills={install_skills})"
        )
        return True
    if name == "codex":
        agent = values.get("LIVEPI_AGENT", "").strip().lower() or "openclaw"
        if agent != "codex":
            print("codex: skipped (LIVEPI_AGENT is not codex)")
            return True
        command = values.get("CODEX_COMMAND", "").strip() or "codex"
        require_api_key = values.get("CODEX_REQUIRE_API_KEY", "true").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        api_present = (
            is_set(values, "OPENAI_API_KEY")
            or is_set(values, "CODEX_API_KEY")
            or is_set(values, "OPENROUTER_API_KEY")
        )
        if require_api_key and not api_present:
            print("codex: missing OPENAI_API_KEY, CODEX_API_KEY, or OPENROUTER_API_KEY")
            return False
        workdir = values.get("CODEX_WORKDIR", "").strip() or "<per-run auto>"
        skills_dir = values.get("CODEX_SKILLS_DIR", "").strip() or "<per-run auto>"
        model = values.get("CODEX_MODEL", "").strip() or "<codex default>"
        api_status = "present" if api_present else "not required"
        print(
            f"codex: ok (command={command}, model={model}, api_key={api_status}, "
            f"workdir={workdir}, skills={skills_dir})"
        )
        return True
    if name == "claude_code":
        agent = values.get("LIVEPI_AGENT", "").strip().lower() or "openclaw"
        if agent != "claude_code":
            print("claude_code: skipped (LIVEPI_AGENT is not claude_code)")
            return True
        command = values.get("CLAUDE_CODE_COMMAND", "").strip() or "claude"
        require_api_key = values.get("CLAUDE_CODE_REQUIRE_API_KEY", "true").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        api_present = is_set(values, "ANTHROPIC_API_KEY") or is_set(values, "CLAUDE_CODE_API_KEY")
        if require_api_key and not api_present:
            print("claude_code: missing ANTHROPIC_API_KEY or CLAUDE_CODE_API_KEY")
            return False
        workdir = values.get("CLAUDE_CODE_WORKDIR", "").strip() or "<per-run auto>"
        skills_dir = values.get("CLAUDE_CODE_SKILLS_DIR", "").strip() or "<per-run auto>"
        model = values.get("CLAUDE_CODE_MODEL", "").strip() or "<claude default>"
        api_status = "present" if api_present else "not required"
        print(
            f"claude_code: ok (command={command}, model={model}, api_key={api_status}, "
            f"workdir={workdir}, skills={skills_dir})"
        )
        return True
    if name == "scan_py":
        if is_set(values, "OPENCLAW_BENCHMARK_SCAN_PY_URL"):
            if is_set(values, "GITHUB_TOKEN"):
                print("scan_py: ok (bootstrap will update existing OPENCLAW_BENCHMARK_SCAN_PY_URL)")
            else:
                print("scan_py: ok (using existing OPENCLAW_BENCHMARK_SCAN_PY_URL)")
            return True
        if is_set(values, "GITHUB_TOKEN"):
            source = values.get("OPENCLAW_BENCHMARK_SCAN_PY_SOURCE_URL", "").strip() or SCAN_PY_SOURCE_DEFAULT
            repo = values.get("OPENCLAW_BENCHMARK_SCAN_PY_REPO", "").strip() or "safety_scan"
            print(f"scan_py: ok (bootstrap will create one persistent GitHub repo {repo}; source={source})")
            return True
        print("scan_py: missing OPENCLAW_BENCHMARK_SCAN_PY_URL or GITHUB_TOKEN")
        return False
    if name == "telegram":
        misses: list[str] = []
        agent_bot_key = first_set_key(
            values,
            *agent_env_names(values, "TELEGRAM_BOT_TOKEN", "TELEGRAM_AGENT_BOT_TOKEN", "TELEGRAM_BOT_TOKEN"),
        )
        group_key = first_set_key(values, *agent_env_names(values, "TELEGRAM_GROUP_ID", "TELEGRAM_GROUP_ID"))
        mention_key = first_set_key(
            values,
            *agent_env_names(
                values,
                "TELEGRAM_AGENT_MENTION",
                "TELEGRAM_AGENT_MENTION",
                "TELEGRAM_AGENT_USERNAME",
            ),
            *agent_env_names(values, "TELEGRAM_AGENT_USERNAME"),
        )
        if not agent_bot_key:
            misses.append("agent TELEGRAM_BOT_TOKEN, TELEGRAM_AGENT_BOT_TOKEN, or TELEGRAM_BOT_TOKEN")
        if not group_key and not is_set(values, "TELEGRAM_GROUP_IDS"):
            misses.append("agent TELEGRAM_GROUP_ID or TELEGRAM_GROUP_ID/TELEGRAM_GROUP_IDS")
        if not mention_key:
            misses.append("agent TELEGRAM_AGENT_MENTION/USERNAME or TELEGRAM_AGENT_MENTION/USERNAME")

        session_file_ok = False
        if is_set(values, "TELEGRAM_USER_SESSION_FILE"):
            session_file = Path(values["TELEGRAM_USER_SESSION_FILE"]).expanduser()
            if not session_file.is_absolute() and env_path is not None:
                session_file = env_path.parent / session_file
            session_file_ok = session_file.exists()
        user_sender_requested = any(
            is_set(values, key)
            for key in (
                "TELEGRAM_USER_API_ID",
                "TELEGRAM_USER_API_HASH",
                "TELEGRAM_USER_SESSION",
                "TELEGRAM_USER_SESSION_FILE",
            )
        )
        user_sender = (
            is_set(values, "TELEGRAM_USER_API_ID")
            and is_set(values, "TELEGRAM_USER_API_HASH")
            and (is_set(values, "TELEGRAM_USER_SESSION") or session_file_ok)
        )
        bot_sender = (
            is_set(values, "TELEGRAM_BENCHMARK_BOT_TOKEN")
            or is_set(values, "TELEGRAM_BOT_TOKEN")
            or bool(agent_bot_key)
        )
        if user_sender_requested and not user_sender:
            misses.append("complete Telegram user session config (run scripts/telegram_user_login.py)")
        elif not (user_sender or bot_sender):
            if is_set(values, "TELEGRAM_USER_API_ID") and is_set(values, "TELEGRAM_USER_API_HASH") and is_set(values, "TELEGRAM_USER_SESSION_FILE"):
                misses.append("TELEGRAM_USER_SESSION_FILE exists, or TELEGRAM_USER_SESSION, or TELEGRAM_BENCHMARK_BOT_TOKEN")
            else:
                misses.append(
                    "TELEGRAM_USER_API_ID/TELEGRAM_USER_API_HASH plus "
                    "TELEGRAM_USER_SESSION or TELEGRAM_USER_SESSION_FILE, or TELEGRAM_BENCHMARK_BOT_TOKEN"
                )
        if misses:
            print(f"{name}: missing {', '.join(misses)}")
            return False
        sender = "user account" if user_sender else "benchmark bot"
        print(f"{name}: ok (agent={selected_agent(values)}, sender={sender}, channel={group_key}, bot={agent_bot_key})")
        return True
    if name == "slack":
        misses: list[str] = []
        slack_bot_key = first_set_key(values, *agent_env_names(values, "SLACK_BOT_TOKEN", "SLACK_BOT_TOKEN"))
        channel_key = first_set_key(values, *agent_env_names(values, "SLACK_CHANNEL_ID", "SLACK_CHANNEL_ID"))
        mention_key = first_set_key(values, *agent_env_names(values, "SLACK_AGENT_MENTION", "SLACK_AGENT_MENTION"))
        username_key = first_set_key(values, *agent_env_names(values, "SLACK_AGENT_USERNAME", "SLACK_AGENT_USERNAME"))
        if not slack_bot_key:
            misses.append("agent SLACK_BOT_TOKEN or SLACK_BOT_TOKEN")
        if not channel_key:
            misses.append("agent SLACK_CHANNEL_ID or SLACK_CHANNEL_ID")
        if not (mention_key or username_key):
            misses.append("agent SLACK_AGENT_MENTION/USERNAME or SLACK_AGENT_MENTION/USERNAME")
        if selected_agent(values) == "openclaw" and not is_set(values, "SLACK_APP_TOKEN"):
            misses.append("SLACK_APP_TOKEN")
        if misses:
            print(f"{name}: missing {', '.join(misses)}")
            return False
        if mention_key and username_key:
            configured_as = "mention+username"
        elif mention_key:
            configured_as = "mention"
        else:
            configured_as = "username"
        if is_set(values, "SLACK_SENDER_TOKEN"):
            sender = "sender token"
        elif is_set(values, "SLACK_ATTACKER_USER_TOKEN"):
            sender = "attacker user"
        elif is_set(values, "SLACK_BENCHMARK_USER_TOKEN"):
            sender = "benchmark user"
        else:
            sender = "bot"
        print(
            f"{name}: ok (agent={selected_agent(values)}, handle={configured_as}, "
            f"sender={sender}, channel={channel_key}, bot={slack_bot_key})"
        )
        return True
    if name == "email":
        misses = missing(values, GROUPS[name])
        attacker_keys = (
            "ATTACKER_SMTP_HOST",
            "ATTACKER_SMTP_PORT",
            "ATTACKER_SMTP_USER",
            "ATTACKER_SMTP_PASS",
            "ATTACKER_SMTP_FROM",
        )
        attacker_requested = any(is_set(values, key) for key in attacker_keys)
        if attacker_requested:
            misses.extend(key for key in attacker_keys if not is_set(values, key))
            sender = "attacker SMTP"
        else:
            sender = "fallback SMTP"
        if misses:
            print(f"{name}: missing {', '.join(dict.fromkeys(misses))}")
            return False
        agent_user = values.get("IMAP_USER", "").strip()
        smtp_user = values.get("SMTP_USER", "").strip()
        if not attacker_requested and smtp_user == agent_user:
            sender = "fallback SMTP (same as agent)"
        print(f"{name}: ok (agent={agent_user or 'configured'}, attack_sender={sender})")
        return True
    if name == "whatsapp":
        selected = selected_agent(values)
        if values.get("OPENCLAW_ENABLE_WHATSAPP", "").strip().lower() != "true" and not any(
            first_set_key(values, key)
            for key in agent_env_names(values, "WHATSAPP_API_URL", "WHATSAPP_API_URL")
        ):
            print(f"{name}: skipped (OPENCLAW_ENABLE_WHATSAPP is not true)")
            return True
        misses: list[str] = []
        api_key = first_set_key(values, "WHATSAPP_API_URL")
        group_key = first_set_key(values, *agent_env_names(values, "WHATSAPP_GROUP_ID", "WHATSAPP_GROUP_ID"))
        mention_key = first_set_key(
            values,
            *agent_env_names(values, "WHATSAPP_AGENT_MENTION", "WHATSAPP_AGENT_MENTION"),
        )
        agent_api_key = first_set_key(values, *agent_env_names(values, "WHATSAPP_API_URL", "WHATSAPP_API_URL"))
        if not api_key:
            misses.append("WHATSAPP_API_URL (benchmark attacker bridge)")
        if not group_key:
            misses.append("agent WHATSAPP_GROUP_ID or WHATSAPP_GROUP_ID")
        if not mention_key:
            misses.append("agent WHATSAPP_AGENT_MENTION or WHATSAPP_AGENT_MENTION")
        if misses:
            print(f"{name}: missing {', '.join(misses)}")
            return False
        api_url = values.get("WHATSAPP_API_URL", "").strip().lower()
        if "127.0.0.1" in api_url or "localhost" in api_url:
            sender = "local bridge"
        else:
            sender = "external bridge"
        auth = "token" if is_set(values, "WHATSAPP_ACCESS_TOKEN") else "no token"
        agent_endpoint = "agent-specific" if agent_api_key != "WHATSAPP_API_URL" else "shared fallback"
        print(
            f"{name}: ok (agent={selected}, sender={sender}, auth={auth}, "
            f"group={group_key}, mention={mention_key}, agent_endpoint={agent_endpoint})"
        )
        return True
    if name == "gist":
        if is_set(values, "GIST_TUTORIAL_FIXED_URL"):
            if is_set(values, "GITHUB_GIST_TOKEN") or is_set(values, "GITHUB_TOKEN"):
                print("gist: ok (updating fixed GIST_TUTORIAL_FIXED_URL)")
                return True
            print("gist: missing GITHUB_GIST_TOKEN or GITHUB_TOKEN for fixed Gist")
            return False
        if is_set(values, "GITHUB_GIST_TOKEN"):
            print("gist: ok (using GITHUB_GIST_TOKEN)")
            return True
        if is_set(values, "GITHUB_TOKEN"):
            print("gist: configured (using GITHUB_TOKEN; token must include Gists write permission)")
            return True
        print("gist: missing GIST_TUTORIAL_FIXED_URL, GITHUB_GIST_TOKEN, or GITHUB_TOKEN with Gists write permission")
        return False
    if name == "web_link":
        token = is_set(values, "GITHUB_TOKEN")
        file_url = values.get("GITHUB_FILE_URL", "").strip()
        parsed_url = bool(file_url and "github.com/" in file_url and "/blob/" in file_url)
        owner_repo = is_set(values, "GITHUB_OWNER") and is_set(values, "GITHUB_REPO")
        if not token:
            print("web_link: missing GITHUB_TOKEN")
            return False
        if not (parsed_url or owner_repo):
            print("web_link: missing GITHUB_FILE_URL or GITHUB_OWNER/GITHUB_REPO")
            return False
        branch = values.get("GITHUB_BRANCH", "").strip() or "main"
        file_path = values.get("GITHUB_FILE_PATH", "").strip() or "<from GITHUB_FILE_URL or README.md>"
        source = "GITHUB_FILE_URL" if parsed_url else "GITHUB_OWNER/GITHUB_REPO"
        print(f"web_link: ok ({source}, branch={branch}, file_path={file_path})")
        return True
    if name == "github_supply_chain":
        token = is_set(values, "GITHUB_SUPPLY_CHAIN_TOKEN") or is_set(values, "GITHUB_TOKEN")
        if not token:
            print("github_supply_chain: missing GITHUB_TOKEN or GITHUB_SUPPLY_CHAIN_TOKEN")
            return False
        repo = values.get("GITHUB_SUPPLY_CHAIN_REPO", "").strip() or "openclaw-devkit"
        owner = values.get("GITHUB_SUPPLY_CHAIN_OWNER", "").strip()
        if not owner or owner.startswith("your-") or "your-org-or-user" in owner:
            owner = "<token login>"
        share = values.get("GITHUB_SUPPLY_CHAIN_SHARE_LINK", "").strip()
        if not share or "your-org-or-user" in share:
            print(f"github_supply_chain: ok (bootstrap will create/update {owner}/{repo} and derive share link)")
        else:
            print(f"github_supply_chain: ok ({owner}/{repo})")
        return True
    if name == "solana":
        misses = missing(values, GROUPS[name])
        if not (
            is_set(values, "OPENCLAW_BENCHMARK_SOLANA_RECIPIENT_ADDRESS")
            or is_set(values, "SOLANA_ATTACKER_ADDRESS")
            or is_set(values, "TEST_SOLANA_RECIPIENT_ADDRESS")
        ):
            misses.append(
                "OPENCLAW_BENCHMARK_SOLANA_RECIPIENT_ADDRESS or SOLANA_ATTACKER_ADDRESS"
            )
        if misses:
            print(f"{name}: missing {', '.join(misses)}")
            return False
        print(f"{name}: ok (agent wallet + attacker recipient address)")
        return True
    misses = missing(values, GROUPS[name])
    if misses:
        print(f"{name}: missing {', '.join(misses)}")
        return False
    print(f"{name}: ok")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Check LivePI secrets.env completeness.")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE), help="Env file to inspect.")
    parser.add_argument(
        "--groups",
        nargs="+",
        choices=("all", *GROUPS.keys()),
        default=["core"],
        help="Config groups to check.",
    )
    args = parser.parse_args()

    env_path = Path(args.env_file).expanduser()
    if not env_path.exists():
        raise SystemExit(f"env file not found: {env_path}")

    values = load_env(env_path)
    provider_count = sum(1 for key in PROVIDER_KEYS if is_set(values, key))
    ok = True
    print(f"env_file: {env_path}")
    if provider_count:
        print("model_provider: ok")
    else:
        print(f"model_provider: missing one of {', '.join(PROVIDER_KEYS)}")
        ok = False

    selected = list(GROUPS.keys()) if "all" in args.groups else args.groups
    for group in selected:
        ok = report_group(values, group, env_path) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
