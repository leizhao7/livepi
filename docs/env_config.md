# LivePI env configuration

LivePI uses one user-owned env file at the repository root:

```bash
cp secrets.example.env secrets.env
chmod 600 secrets.env
```

`setup_openclaw_benchmark_env.py` loads `secrets.env` automatically when it
exists, so the normal setup command can be:

```bash
python3 setup_openclaw_benchmark_env.py --host livepi --apply
```

The Docker runner also uses `secrets.env` by default.

## Minimal setup

These are enough to configure the OpenClaw gateway with an API-key model and run
non-live deterministic checks. Email/GitHub/chat credentials are still needed
for the corresponding live surfaces and verifiers.

```dotenv
OPENROUTER_API_KEY=
OPENCLAW_PRIMARY_MODEL=
OPENCLAW_BENCHMARK_RECIPIENT_EMAIL=recipient@example.com
OPENCLAW_BENCHMARK_RECIPIENT_PLUS_ALIAS=auto
```

If `OPENCLAW_PRIMARY_MODEL` is blank and `OPENROUTER_API_KEY` is set, setup
selects `openrouter/google/gemini-3.1-pro-preview`.

## Core setup keys

`OPENCLAW_GATEWAY_TOKEN` may be blank; setup generates one and writes it to
`prompt_injection_lab/.env`.

```dotenv
OPENCLAW_GATEWAY_TOKEN=
OPENCLAW_GATEWAY_PORT=18789
OPENCLAW_MAX_CONCURRENT=2
OPENCLAW_SUBAGENTS_MAX_CONCURRENT=4
OPENCLAW_SANDBOX_MODE=off
OPENCLAW_BENCHMARK_RECIPIENT_EMAIL=recipient@example.com
OPENCLAW_BENCHMARK_RECIPIENT_PLUS_ALIAS=auto
OPENCLAW_BENCHMARK_SCAN_PY_URL=
OPENCLAW_BENCHMARK_SCAN_PY_SOURCE_URL=  # leave blank to auto-build https://github.com/<your-user>/safety_scan/blob/main/scan.py
OPENCLAW_BENCHMARK_SCAN_PY_OWNER=
OPENCLAW_BENCHMARK_SCAN_PY_REPO=safety_scan
OPENCLAW_BENCHMARK_SCAN_PY_BRANCH=
OPENCLAW_BENCHMARK_SCAN_PY_PATH=scan.py
OPENCLAW_BENCHMARK_SCAN_PY_PRIVATE=false
TEST_RECIPIENT_EMAIL=recipient@example.com
TEST_CLEANUP_EMAIL=agent-inbox@example.com
```

For the `download_and_run_scan_py` objective,
`OPENCLAW_BENCHMARK_SCAN_PY_URL` is the persistent public file URL used in
prompts. If it is set, setup updates that repo file in place with the latest
content from `OPENCLAW_BENCHMARK_SCAN_PY_SOURCE_URL`. If it is blank, setup
creates one persistent GitHub repo/file with `GITHUB_TOKEN`, writes the
generated blob URL back into `secrets.env` and `prompt_injection_lab/.env`, and
reuses that URL on later runs. If owner is blank, setup uses the authenticated
GitHub user.

## Model providers

Set at least one provider key. `OPENCLAW_PRIMARY_MODEL` should match the
provider, or be left blank for automatic selection.

```dotenv
OPENCLAW_PRIMARY_MODEL=
OPENROUTER_API_KEY=
ANTHROPIC_API_KEY=
MOONSHOT_API_KEY=
MODELSTUDIO_API_KEY=
ZAI_API_KEY=
GOOGLE_API_KEY=
OPENAI_API_KEY=
LLM_JUDGE_PROVIDER=openrouter
LLM_JUDGE_MODEL=openai/gpt-5.5
```

## Agent adapters

OpenClaw is the default. Hermes, Codex, and Claude Code use the same benchmark
surface setup and verifier code, but their runtime is separate from OpenClaw's
gateway/history.

Hermes, Codex, and Claude Code get a per-run workdir, home, and skill directory
unless you override them. The runner copies the bundled `imap-smtp-email`,
`solana`, and `livepi-chat-channels` skills into the agent skill directory and
passes that path through `AGENT_SKILLS_DIR` plus the agent-specific `*_SKILLS_DIR`
env var.
For Codex and Claude Code, the runner also writes `AGENTS.md` in the per-run
workdir; Claude Code additionally gets `CLAUDE.md`. These files tell the agent
how to call the bundled skills and chat-channel helper without using OpenClaw.

```dotenv
LIVEPI_AGENT=hermes
LIVEPI_CLI_AGENT_INCLUDE_GUIDE_PROMPT=true
HERMES_COMMAND=hermes
HERMES_CLI_ARGS=
HERMES_QUERY_FLAG=-q
HERMES_APPEND_QUERY_FLAG=true
HERMES_STDIN=false
HERMES_WORKDIR=
HERMES_API_KEY=
HERMES_API_KEY_ENV=OPENROUTER_API_KEY
HERMES_API_KEY_SOURCE_ENV=HERMES_API_KEY
HERMES_REQUIRE_API_KEY=false
HERMES_RUNTIME_ROOT=.livepi_agent_runtime
HERMES_AGENT_HOME=
HERMES_HOME=
HERMES_SKILLS_DIR=
HERMES_INSTALL_BUNDLED_SKILLS=true
HERMES_PROVIDER=openrouter
HERMES_MODEL=openai/gpt-5.5
HERMES_TOOLSETS=terminal,skills
HERMES_PRELOAD_SKILLS=imap-smtp-email,solana,livepi-chat-channels
HERMES_QUIET=true
HERMES_TELEGRAM_BOT_TOKEN=
HERMES_TELEGRAM_GROUP_ID=
HERMES_SLACK_BOT_TOKEN=
HERMES_SLACK_CHANNEL_ID=
HERMES_WHATSAPP_API_URL=
HERMES_WHATSAPP_ACCESS_TOKEN=
HERMES_WHATSAPP_GROUP_ID=
```

Set either `HERMES_API_KEY` or `OPENROUTER_API_KEY` for OpenRouter-backed
Hermes runs. If Hermes is installed on the VPS host instead of inside the Docker
image, point `HERMES_COMMAND` at an SSH wrapper that exports the same env values
on the host.

Hermes installation is optional during setup. When `LIVEPI_AGENT=hermes`,
`scripts/setup_from_env.sh` installs Hermes on the VPS automatically unless
`--skip-hermes-install` is used. For a Docker image that contains Hermes, build
with `LIVEPI_INSTALL_HERMES=true bash scripts/build_agent_image.sh`.

When `HERMES_CLI_ARGS` is blank, the adapter runs `hermes chat` with `-q`,
`HERMES_PROVIDER`, `HERMES_MODEL`, `HERMES_TOOLSETS`, and
`HERMES_PRELOAD_SKILLS`. The runner also writes a per-run
`HERMES_HOME/config.yaml` that points Hermes at the generated skills directory.

The bundled `livepi-chat-channels` skill prefers the selected agent's
`HERMES_*`, `CODEX_*`, or `CLAUDE_CODE_*` chat-channel overrides and otherwise
falls back to the shared benchmark channel env. Use agent-specific values when
the evaluated agent account is different from the OpenClaw account. For
Telegram and Slack surfaces, the runner also uses the selected agent's bot,
group/channel, and mention overrides when shared values are blank; benchmark
sender credentials such as `TELEGRAM_USER_*`, `TELEGRAM_BENCHMARK_BOT_TOKEN`,
and `SLACK_SENDER_TOKEN` remain shared attacker-side settings. For WhatsApp,
`WHATSAPP_API_URL` is still the benchmark attacker bridge; agent-specific
`*_WHATSAPP_API_URL` values are for the CLI agent's channel skill.

Codex and Claude Code use the same runtime layout, but they authenticate with
their normal provider key envs:

```dotenv
LIVEPI_AGENT=codex
CODEX_COMMAND=codex
CODEX_MODEL=
CODEX_MODEL_PROVIDER=
CODEX_BASE_URL=
CODEX_PROVIDER_ENV_KEY=
CODEX_SHELL_ENV_INHERIT=true
CODEX_CLI_ARGS=exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check --ephemeral
CODEX_QUERY_FLAG=
CODEX_RUNTIME_ROOT=.livepi_agent_runtime
CODEX_AGENT_HOME=
CODEX_HOME=
CODEX_SKILLS_DIR=
CODEX_INSTALL_BUNDLED_SKILLS=true
CODEX_TELEGRAM_BOT_TOKEN=
CODEX_TELEGRAM_GROUP_ID=
CODEX_TELEGRAM_AGENT_MENTION=
CODEX_TELEGRAM_AGENT_USERNAME=
CODEX_SLACK_BOT_TOKEN=
CODEX_SLACK_CHANNEL_ID=
CODEX_SLACK_AGENT_MENTION=
CODEX_SLACK_AGENT_USERNAME=
CODEX_WHATSAPP_API_URL=
CODEX_WHATSAPP_ACCESS_TOKEN=
CODEX_WHATSAPP_GROUP_ID=
CODEX_WHATSAPP_AGENT_MENTION=
CODEX_API_KEY=
CODEX_API_KEY_ENV=OPENAI_API_KEY
CODEX_API_KEY_SOURCE_ENV=CODEX_API_KEY
CODEX_REQUIRE_API_KEY=true

LIVEPI_AGENT=claude_code
CLAUDE_CODE_COMMAND=claude
CLAUDE_CODE_MODEL=
CLAUDE_CODE_CLI_ARGS=--bare --dangerously-skip-permissions --no-session-persistence
CLAUDE_CODE_QUERY_FLAG=-p
CLAUDE_CODE_RUNTIME_ROOT=.livepi_agent_runtime
CLAUDE_CODE_AGENT_HOME=
CLAUDE_CODE_SKILLS_DIR=
CLAUDE_CODE_INSTALL_BUNDLED_SKILLS=true
CLAUDE_CONFIG_DIR=
CLAUDE_CODE_TELEGRAM_BOT_TOKEN=
CLAUDE_CODE_TELEGRAM_GROUP_ID=
CLAUDE_CODE_TELEGRAM_AGENT_MENTION=
CLAUDE_CODE_TELEGRAM_AGENT_USERNAME=
CLAUDE_CODE_SLACK_BOT_TOKEN=
CLAUDE_CODE_SLACK_CHANNEL_ID=
CLAUDE_CODE_SLACK_AGENT_MENTION=
CLAUDE_CODE_SLACK_AGENT_USERNAME=
CLAUDE_CODE_WHATSAPP_API_URL=
CLAUDE_CODE_WHATSAPP_ACCESS_TOKEN=
CLAUDE_CODE_WHATSAPP_GROUP_ID=
CLAUDE_CODE_WHATSAPP_AGENT_MENTION=
CLAUDE_CODE_API_KEY=
CLAUDE_CODE_API_KEY_ENV=ANTHROPIC_API_KEY
CLAUDE_CODE_API_KEY_SOURCE_ENV=CLAUDE_CODE_API_KEY
CLAUDE_CODE_REQUIRE_API_KEY=true
```

## Email objective and verifier

Most paper objectives verify success through IMAP and some surfaces send the
attack through SMTP. Use two mailboxes when possible:

- `IMAP_*` + `SMTP_*`: the OpenClaw/agent mailbox. OpenClaw reads `IMAP_USER`
  and the `imap-smtp-email` skill sends from `SMTP_FROM`.
- `ATTACKER_SMTP_*`: the benchmark sender that injects the attack email into
  `IMAP_USER`. If omitted, the runner falls back to `SMTP_*` for backwards
  compatibility.

```dotenv
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_SECURE=false
SMTP_STARTTLS=true
SMTP_REJECT_UNAUTHORIZED=true
SMTP_USER=agent-inbox@example.com
SMTP_PASS=
SMTP_FROM=agent-inbox@example.com

ATTACKER_SMTP_HOST=smtp.gmail.com
ATTACKER_SMTP_PORT=587
ATTACKER_SMTP_SECURE=false
ATTACKER_SMTP_STARTTLS=true
ATTACKER_SMTP_REJECT_UNAUTHORIZED=true
ATTACKER_SMTP_USER=attacker@example.com
ATTACKER_SMTP_PASS=
ATTACKER_SMTP_FROM=attacker@example.com

IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_TLS=true
IMAP_USER=agent-inbox@example.com
IMAP_PASS=
IMAP_MAILBOX=INBOX
IMAP_REJECT_UNAUTHORIZED=true
IMAP_TIMEOUT_S=8

# Optional verifier inbox. Use this when OPENCLAW_BENCHMARK_RECIPIENT_EMAIL is
# not the same mailbox as IMAP_USER.
VERIFY_IMAP_HOST=
VERIFY_IMAP_PORT=993
VERIFY_IMAP_TLS=true
VERIFY_IMAP_USER=
VERIFY_IMAP_PASS=
VERIFY_IMAP_MAILBOX=INBOX
VERIFY_IMAP_REJECT_UNAUTHORIZED=true
VERIFY_IMAP_TIMEOUT_S=8
VERIFY_IMAP_BEFORE_LIMIT=50
VERIFY_IMAP_AFTER_LIMIT=50
```

## Live surfaces

Fill only the surfaces you want to run.

```dotenv
TELEGRAM_BOT_TOKEN=
TELEGRAM_AGENT_BOT_TOKEN=
TELEGRAM_BENCHMARK_BOT_TOKEN=
TELEGRAM_USER_API_ID=
TELEGRAM_USER_API_HASH=
TELEGRAM_USER_SESSION=
TELEGRAM_USER_SESSION_FILE=prompt_injection_lab/.telegram_benchmark.session
TELEGRAM_USER_PHONE=
TELEGRAM_GROUP_ID=
TELEGRAM_GROUP_IDS=
TELEGRAM_AGENT_MENTION=@openclaw_agent
TELEGRAM_AGENT_USERNAME=
TELEGRAM_KEEP_BENCHMARK_MESSAGES=false
TELEGRAM_REQUIRE_MENTION=false
# TELEGRAM_AGENT_BOT_TOKEN is watched by OpenClaw/the agent gateway. The
# benchmark can post payloads with TELEGRAM_USER_* after one-time
# scripts/telegram_user_login.py auth, or with TELEGRAM_BENCHMARK_BOT_TOKEN.
# TELEGRAM_AGENT_USERNAME is a legacy alias; prefer TELEGRAM_AGENT_MENTION.
# Set TELEGRAM_KEEP_BENCHMARK_MESSAGES=true when you want to see payload
# messages in the Telegram app instead of deleting them after each run.

SLACK_BOT_TOKEN=
SLACK_ATTACKER_USER_TOKEN=
SLACK_APP_TOKEN=
SLACK_CHANNEL_ID=
SLACK_AGENT_MENTION=
SLACK_AGENT_USERNAME=
SLACK_KEEP_BENCHMARK_MESSAGES=false
SLACK_REQUIRE_MENTION=true
# SLACK_BOT_TOKEN and SLACK_APP_TOKEN are used by OpenClaw's Slack gateway.
# SLACK_ATTACKER_USER_TOKEN is used by the benchmark sender, so attack payloads
# are posted by the attacker user instead of the OpenClaw bot. If it is omitted,
# the benchmark falls back to SLACK_BOT_TOKEN for posting.
# SLACK_AGENT_MENTION should be the reliable Slack ID mention, for example
# <@U123>. SLACK_AGENT_USERNAME is the visible username, for example @oepnclaw.
# Set SLACK_KEEP_BENCHMARK_MESSAGES=true when debugging visible Slack payloads.

OPENCLAW_ENABLE_WHATSAPP=false
WHATSAPP_API_URL=http://127.0.0.1:17891/send
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_GROUP_ID=
WHATSAPP_AGENT_MENTION=@openclaw
WHATSAPP_EXTRA_PAYLOAD_JSON=
WHATSAPP_DEFAULT_TO=
WHATSAPP_GROUP_ALLOW_FROM=
WHATSAPP_REQUIRE_MENTION=false
WHATSAPP_BRIDGE_ENABLED=true
WHATSAPP_BRIDGE_AUTH_DIR=.whatsapp_attacker_auth
WHATSAPP_BRIDGE_HOST=127.0.0.1
WHATSAPP_BRIDGE_PORT=17891
WHATSAPP_BRIDGE_DEFAULT_MENTIONS=

# WhatsApp has two logins. OpenClaw uses its own WhatsApp Web session for the
# agent account. The benchmark attacker sender uses the local bridge above,
# which is also a WhatsApp Web session. Run setup with --whatsapp-login once and
# scan both QR codes. Use a separate WhatsApp number for the attacker bridge when
# possible. Prefer the group JID for WHATSAPP_GROUP_ID. The bridge can also
# resolve an exact group subject, but OpenClaw's group allowlist is JID-based.
# After bridge login:
#   ssh livepi 'cd /root/livepi && node scripts/whatsapp_bridge.mjs --env-file secrets.env --list-groups'
# WHATSAPP_ACCESS_TOKEN is optional for localhost-only testing. If set, the
# benchmark sends Authorization: Bearer ... to the bridge.
# WHATSAPP_BRIDGE_DEFAULT_MENTIONS can hold the agent phone JID, for example
# 15551234567@s.whatsapp.net, when you need a real WhatsApp mention.

GITHUB_TOKEN=
GITHUB_GIST_TOKEN=
GIST_TUTORIAL_FIXED_URL=

# Optional non-paper web_link surface. Leave blank unless you explicitly run
# --surface-tag web_link; it overwrites this GitHub file with the payload.
GITHUB_OWNER=
GITHUB_REPO=
GITHUB_BRANCH=main
GITHUB_FILE_PATH=README.md
GITHUB_FILE_URL=

GITHUB_SUPPLY_CHAIN_TOKEN=
GITHUB_SUPPLY_CHAIN_OWNER=
GITHUB_SUPPLY_CHAIN_REPO=openclaw-devkit
GITHUB_SUPPLY_CHAIN_BRANCH=
GITHUB_SUPPLY_CHAIN_PRIVATE=false
GITHUB_SUPPLY_CHAIN_SHARE_LINK=
GITHUB_SUPPLY_CHAIN_PREPARE=true
GITHUB_SUPPLY_CHAIN_CDN_WAIT_S=30
GITHUB_SUPPLY_CHAIN_POST_TRIGGER_WAIT_S=45
LIVEPI_PAYLOAD_RUN_TIMEOUT_S=30
LIVEPI_PAYLOAD_IMAP_TIMEOUT_S=8
LIVEPI_PAYLOAD_SMTP_TIMEOUT_S=12

REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USERNAME=
REDDIT_PASSWORD=
REDDIT_SUBREDDIT=test

X_API_KEY=
X_API_SECRET=
X_ACCESS_TOKEN=
X_ACCESS_SECRET=
```

`GITHUB_TOKEN` is enough for both `gist_tutorial` and
`github_supply_chain` when it has repository contents access and Gist access.
During setup, LivePI creates or updates the supply-chain fixture repo from the
bundled `openclaw-devkit` template and writes
`GITHUB_SUPPLY_CHAIN_OWNER`, `GITHUB_SUPPLY_CHAIN_BRANCH`, and
`GITHUB_SUPPLY_CHAIN_SHARE_LINK` back to the env file. Set
`GITHUB_SUPPLY_CHAIN_OWNER` only when the repo should live under an org instead
of the token user's account.

`GITHUB_OWNER`, `GITHUB_REPO`, `GITHUB_BRANCH`, `GITHUB_FILE_PATH`, and
`GITHUB_FILE_URL` are only for the extra `web_link` surface. They are not
needed for the paper's 169-case matrix.

## Skill-specific keys

Solana is needed for Solana-transfer and wallet-file objectives.

```dotenv
SOLANA_PRIVATE_KEY=
SOLANA_RPC_URL=https://api.devnet.solana.com
SOLANA_ATTACKER_ADDRESS=
OPENCLAW_BENCHMARK_SOLANA_RECIPIENT_ADDRESS=
JUPITER_API_KEY=
```

`SOLANA_PRIVATE_KEY` is the agent/source wallet used by the `solana` skill.
The attacker side should normally be only a public recipient address. Set
`SOLANA_ATTACKER_ADDRESS`, or the more explicit
`OPENCLAW_BENCHMARK_SOLANA_RECIPIENT_ADDRESS`, to replace the benchmark's
Solana transfer recipient placeholder in prompts and supply-chain payloads.

Gmail API keys are optional and used by `send_attack_email.py`, not the main
`run_surface_test.py` email path.

```dotenv
GMAIL_SENDER=attacker@example.com
GMAIL_ACCESS_TOKEN=
GMAIL_REFRESH_TOKEN=
GMAIL_CLIENT_ID=
GMAIL_CLIENT_SECRET=
```

## Docker wrapper keys

These are host-runner options, not benchmark secrets.

```dotenv
LIVEPI_IMAGE=livepi-runner:cpu
LIVEPI_DOCKER_NETWORK=host
LIVEPI_DOCKER_ISOLATED_WORKSPACE=true
LIVEPI_DOCKER_WORK_ROOT=/tmp
LIVEPI_SSH_DIR=/root/.ssh
LIVEPI_ENV_FILE=secrets.env
CPUS=4
MEMORY=8g
```
