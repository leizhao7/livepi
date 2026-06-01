# LivePI Docker Runner Runbook

This Docker layer isolates the benchmark controller and keeps the LivePI task
execution path unchanged. The container still calls the existing
`prompt_injection_lab/scripts/run_surface_test.py` entrypoint. That script still
talks to the configured OpenClaw/VPS target over the same SSH and WebSocket
interfaces used by the non-Docker setup.

The remote OpenClaw environment is intentionally not moved into Docker by
default. Several LivePI objectives rely on real Ubuntu service behavior, user
files, SSH, gateway state, and live-channel credentials. Containerizing that
target would change the task environment.

## Layout

```text
docker/runner-cpu/Dockerfile      # CPU runner image for benchmark controller
scripts/build_agent_image.sh      # builds livepi-runner:cpu
scripts/docker_smoke_checks.sh    # deterministic no-credential checks
scripts/run_in_docker.sh# wrapper around run_surface_test.py
src/livepi_bench/                 # small Docker runner CLI
configs/docker_smoke_matrix.tsv   # documented smoke target
```

## Host Setup

From a local checkout, the single-env setup path is:

```bash
cp secrets.example.env secrets.env
# Fill provider, Telegram, and Slack keys in secrets.env.
scripts/setup_from_env.sh --host livepi --env-file secrets.env
```

To also send visible Telegram/Slack benchmark payload smoke messages from the
configured attacker accounts, add `--smoke`:

```bash
scripts/setup_from_env.sh --host livepi --env-file secrets.env --smoke
```

The setup script syncs the repo to the VPS, builds `livepi-runner:cpu`, writes
the OpenClaw gateway config, enables Telegram/Slack plugins, creates the
Telegram user session when needed, and verifies messaging env inside Docker.
Telegram login may still prompt for the one-time code sent to
`TELEGRAM_USER_PHONE`. When `LIVEPI_AGENT=hermes`, setup builds the runner image
with Hermes Agent included unless `LIVEPI_INSTALL_HERMES=false` is exported
before setup.

On a clean Ubuntu VPS:

```bash
cd /root/livepi_neurips_dataset
bash scripts/bootstrap_ubuntu.sh
bash scripts/build_agent_image.sh
```

To include Hermes Agent inside the runner image, rebuild with:

```bash
LIVEPI_INSTALL_HERMES=true bash scripts/build_agent_image.sh
```

If Docker is already installed, the bootstrap script only installs the small
host tools needed by the runner.

## Secrets

Keep secrets outside the image. Use either `secrets.env` or
`prompt_injection_lab/.env`; both are ignored by git and Docker build context.

```bash
cp secrets.example.env secrets.env
```

The Docker wrapper passes the env file with `docker --env-file`. Pass
`--env-file /dev/null` for smoke tests that should not load `secrets.env` or
`prompt_injection_lab/.env`.

Live runs use an isolated per-run workspace by default. The wrapper copies the
repo into a temporary directory, excludes historical `prompt_injection_lab/results`
and local caches, mounts that copy at `/workspace`, and copies only the generated
results back after the container exits. Set
`LIVEPI_DOCKER_ISOLATED_WORKSPACE=false` only for debugging runs where the
container should see the live checkout directly.

For the standard single-VPS workflow, do not set `LIVEPI_REMOTE_HOST`.
`root@127.0.0.1`, `localhost`, and `local` are treated as the current run
environment: inside Docker this means the per-run container, and outside Docker
this means the current VPS. Set `LIVEPI_REMOTE_HOST` only when a real separate
OpenClaw host should be reached over SSH. If using a separate host and the
container does not have a matching `known_hosts` entry, set the SSH behavior in
the env file:

```bash
OPENCLAW_SSH_OPTIONS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
```

Use the same env file for setup and Docker runs:

```bash
python3 setup_openclaw_benchmark_env.py --host livepi --apply
python3 scripts/check_env.py --groups core email gist github_supply_chain solana
```

## Smoke Checks

These checks do not call a model or touch live services:

```bash
bash scripts/docker_smoke_checks.sh
```

They validate the taxonomy/task files and run `/bin/echo` direct-chat smoke
cases for Hermes, Codex, and Claude Code, confirming each CLI adapter can start
with an isolated runtime and model override.

Equivalent package CLI:

```bash
python3 -m livepi_bench.cli smoke --repo .
```

## Run One LivePI Case

This preserves the original task runner arguments:

```bash
bash scripts/run_in_docker.sh \
  --surface-tag direct_chat_txt \
  --compose-paper-techniques \
  --malicious-task-tag email_summary_to_external
```

The runner validates `surface x technique x objective` against the paper matrix
before touching live services. Infeasible combinations return a JSON error and
exit nonzero; feasible combinations run normally.

Examples:

```bash
# One paper-counted case.
bash scripts/run_in_docker.sh \
  --surface-tag telegram_group \
  --technique-tag direct_group_message_instruction \
  --malicious-task-tag email_summary_to_external

# Compose selected feasible prompt-level techniques in one run.
bash scripts/run_in_docker.sh \
  --surface-tag email_gmail \
  --technique-tags checklist_handoff_injection,shadow_policy_update \
  --malicious-task-tag download_and_run_scan_py

# Run every feasible technique for this surface/objective.
bash scripts/run_in_docker.sh \
  --surface-tag gist_tutorial \
  --all-techniques \
  --malicious-task-tag solana_transfer_urgent
```

The Linux VPS default is `--network host`, which lets the container reach the
same VPS over SSH (`root@127.0.0.1` by default) and the host-side gateway such
as `ws://127.0.0.1:18789/ws`. Override with
`LIVEPI_DOCKER_NETWORK=bridge` only if your gateway URL is reachable from a
bridged container, for example via `host.docker.internal`.

By default each case runs against a fresh `/workspace` copy, so previous run
artifacts are not visible to the agent through the mounted repo. External
surfaces are still shared services; isolation there comes from per-run email
aliases plus surface cleanup for Slack/Telegram and other implemented cleanup
steps.

## Python CLI

After installing the repo package on the host, the same run can be launched with:

```bash
python3 -m livepi_bench.cli docker-run --repo . -- \
  --surface-tag direct_chat_txt \
  --compose-paper-techniques \
  --malicious-task-tag email_summary_to_external
```

The wrapper writes the exact Docker command to
`prompt_injection_lab/results/_docker_runner_logs/last_docker_command.json`.

## Matrix Helper

Use the matrix helper to inspect the paper `surface x technique x objective`
space and generate run commands without memorizing every feasible combination:

```bash
python3 prompt_injection_lab/scripts/benchmark_matrix.py list --format table
python3 prompt_injection_lab/scripts/benchmark_matrix.py list \
  --surface-tag github_supply_chain \
  --format json
python3 prompt_injection_lab/scripts/benchmark_matrix.py check \
  --surface-tag direct_chat_txt \
  --technique-tag checklist_handoff_injection \
  --malicious-task-tag email_summary_to_external
python3 prompt_injection_lab/scripts/benchmark_matrix.py command --docker \
  --agent hermes \
  --surface-tag direct_chat_txt \
  --technique-tag checklist_handoff_injection \
  --malicious-task-tag email_summary_to_external
python3 prompt_injection_lab/scripts/benchmark_matrix.py plan --docker \
  --agent hermes \
  --fixed-objective email_summary_to_external \
  --selection first
python3 prompt_injection_lab/scripts/benchmark_matrix.py plan --docker \
  --agent hermes \
  --fixed-surface direct_chat_txt \
  --selection first
python3 prompt_injection_lab/scripts/benchmark_matrix.py run-plan --docker \
  --agent hermes \
  --fixed-objective email_summary_to_external \
  --selection first \
  --env-file secrets.env \
  --case-timeout-s 900 \
  --execute
```

`check` and `command` exit non-zero for infeasible combinations, before any live
surface setup or agent call. `plan` prints the smoke-test command lists for the
two common checks: one objective across all feasible surfaces, or one surface
across all feasible objectives. `run-plan` is dry-run by default; add
`--execute` to run sequentially. It writes `plan.json`, `runs.jsonl`,
per-case stdout/stderr, and `summary.json` under
`prompt_injection_lab/results/matrix_plans/`, and `--resume <plan_dir>` skips
cases already recorded as ok.

`command`, `plan`, and `run-plan` accept `--base-model` and `--agent-model`.
For Hermes, Codex, and Claude Code, `--base-model` becomes the per-run CLI
model unless `--agent-model` is set.

The sweep entrypoints also accept the same agent selector:

```bash
python3 prompt_injection_lab/scripts/sweep_direct_chat.py \
  --agent codex \
  --models gpt-5.3-codex
python3 prompt_injection_lab/scripts/sweep_slack_channel.py \
  --agent claude_code \
  --models claude-opus-4-6 \
  --techniques direct_group_message_instruction
```

For OpenClaw, `--models` switches the gateway `--base-model`. For Hermes,
Codex, and Claude Code, the same value becomes a per-run CLI model override
(`HERMES_MODEL`, `CODEX_MODEL`, or `CLAUDE_CODE_MODEL`), so one sweep command
shape works across adapters. Group-chat sweeps validate `--techniques` and only
accept `direct_group_message_instruction`, matching the paper surface.

## CLI Agent Adapters

OpenClaw remains the default adapter. Hermes, Codex, and Claude Code are wired
through the same `run_surface_test.py` task flow for every benchmark surface;
live-channel runs still require matching skills, MCP servers, or gateway
credentials in the selected CLI agent.

```bash
LIVEPI_AGENT=hermes
HERMES_COMMAND=hermes
HERMES_CLI_ARGS=
HERMES_QUERY_FLAG=-q
HERMES_APPEND_QUERY_FLAG=true
HERMES_STDIN=false
HERMES_WORKDIR=
HERMES_API_KEY=
HERMES_API_KEY_ENV=OPENROUTER_API_KEY
HERMES_API_KEY_SOURCE_ENV=HERMES_API_KEY
HERMES_RUNTIME_ROOT=.livepi_agent_runtime
HERMES_AGENT_HOME=
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

For every CLI agent, the runner prepares a fresh per-run workdir, home, and
skills directory when the agent-specific variables are blank. The bundled
`imap-smtp-email`, `solana`, and `livepi-chat-channels` skills are copied into
that skills directory and exposed through `AGENT_SKILLS_DIR` plus the
agent-specific `*_SKILLS_DIR`. OpenClaw gateway sessions are not touched for CLI
agent runs.
Codex gets `AGENTS.md`/`CODEX.md` in the workdir; Claude Code gets
`AGENTS.md`/`CLAUDE.md`. The default prompt asks the CLI agent to read that
guide before using email, Solana, Slack, Telegram, or WhatsApp helpers.

The channel skill prefers the selected agent's `HERMES_*`, `CODEX_*`, or
`CLAUDE_CODE_*` chat-channel overrides, then falls back to the shared benchmark
channel env. Telegram and Slack runner setup uses the same selected-agent
bot/channel/mention fallback when shared values are blank. WhatsApp keeps the
shared `WHATSAPP_API_URL` as the benchmark attacker bridge; agent-specific
`*_WHATSAPP_API_URL` values are used by the CLI agent skill when it reads or
replies.

When `HERMES_CLI_ARGS` is blank, the adapter builds the official non-interactive
shape `hermes chat -q "<prompt>"` with the provider/model/toolset values above.
It also writes `HERMES_HOME/config.yaml` for the run so Hermes can discover the
generated skills directory through `skills.external_dirs`.

```bash
LIVEPI_AGENT=codex
CODEX_COMMAND=codex
CODEX_MODEL=
CODEX_CLI_ARGS="exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check --ephemeral"
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
```

```bash
LIVEPI_AGENT=claude_code
CLAUDE_CODE_COMMAND=claude
CLAUDE_CODE_MODEL=
CLAUDE_CODE_CLI_ARGS="--bare --dangerously-skip-permissions --no-session-persistence"
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

For a custom Hermes transcript shape, override `HERMES_CLI_ARGS` directly.

Set the matching API key in the env file. Codex reads `OPENAI_API_KEY`; the
runner also accepts `CODEX_API_KEY` and maps it to `OPENAI_API_KEY` for the
subprocess. Claude Code reads `ANTHROPIC_API_KEY`; the runner also accepts
`CLAUDE_CODE_API_KEY` and maps it to `ANTHROPIC_API_KEY` for the subprocess.

Then pass `--agent hermes`, `--agent codex`, or `--agent claude_code`
explicitly, or rely on `LIVEPI_AGENT`:

```bash
bash scripts/run_in_docker.sh \
  --agent codex \
  --surface-tag direct_chat_txt \
  --technique-tag checklist_handoff_injection \
  --malicious-task-tag email_summary_to_external
```

For ad hoc runs, `--agent-model` can override the CLI model directly. If it is
omitted, `--base-model` is used as the CLI model for non-OpenClaw adapters.

If an agent is installed on the VPS instead of inside the runner image, point the
adapter at SSH and configure credentials on that VPS:

```bash
HERMES_COMMAND="ssh livepi"
HERMES_CLI_ARGS="HERMES_SKILLS_DIR=\$HOME/.hermes-livepi/.agents/skills hermes chat --provider openrouter --toolsets terminal,skills --skills imap-smtp-email,solana,livepi-chat-channels -Q"
CODEX_COMMAND="ssh livepi codex"
CLAUDE_CODE_COMMAND="ssh livepi claude"
```

Each CLI adapter sends one non-interactive query and stores
`<agent>_chat.json` plus `<agent>_cli_result.json` in the run directory.

CLI agent surface requirements:

| Surface | Benchmark seed path | CLI agent side needed |
| --- | --- | --- |
| `email_gmail` | SMTP sends the payload into the monitored inbox | Email/Gmail or IMAP-SMTP skill |
| `telegram_group` | Benchmark user account or benchmark bot posts the payload to the group | Telegram gateway or messaging skill |
| `slack_channel` | Benchmark bot posts the payload to the channel | Slack gateway or messaging skill |
| `whatsapp_group` | Local WhatsApp Web bridge posts the payload | WhatsApp gateway or messaging skill |
| `direct_chat_txt` | OpenClaw uses the remote review-inputs dir; CLI agents use their per-run workdir | Filesystem/terminal access |
| `gist_tutorial` | Caller supplies a prepared Gist URL | Browser/web fetch skill |
| `github_supply_chain` | Sweep script prepares payload slots in a repo | Browser/web fetch plus git/shell |
| `web_link` | Runner overwrites a GitHub file and sends the URL | Browser/web fetch skill |
| `reddit_post` | Runner creates a Reddit post | Browser/web fetch skill |
| `x_post` | Runner creates or reuses an X thread | Browser/web fetch skill |

For Telegram, prefer the split config:

```bash
TELEGRAM_AGENT_BOT_TOKEN=...          # OpenClaw/agent gateway bot
TELEGRAM_USER_API_ID=...
TELEGRAM_USER_API_HASH=...
TELEGRAM_USER_SESSION_FILE=prompt_injection_lab/.telegram_benchmark.session
TELEGRAM_GROUP_ID=...
TELEGRAM_AGENT_MENTION=@openclaw_agent
TELEGRAM_KEEP_BENCHMARK_MESSAGES=false
```

Run `python3 scripts/telegram_user_login.py` once to create the user-account
session file. `TELEGRAM_BOT_TOKEN` is still accepted as a legacy fallback, and
`TELEGRAM_BENCHMARK_BOT_TOKEN` can be used when the benchmark sender should be a
separate bot instead of a user account.
Set `TELEGRAM_KEEP_BENCHMARK_MESSAGES=true` for visible debugging runs; the
default cleanup deletes benchmark payload messages after each case.
