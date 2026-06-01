#!/usr/bin/env bash
set -euo pipefail

# Auto-load runtime hints into the *host shell* so users do not need to
# export them before every benchmark run. Source order matters:
#   1) secrets.env             - user-owned keys (OPENROUTER, ANTHROPIC, ...)
#   2) prompt_injection_lab/.env - setup_openclaw_benchmark_env.py outputs
#                                  (OPENCLAW_GATEWAY_TOKEN, *_PORT, *_HOST, ...)
# The second file overrides the first, so setup-managed tokens always win.
# If LIVEPI_ENV_FILE is set explicitly, only that file is sourced (legacy).
if [[ -n "${LIVEPI_ENV_FILE:-}" ]]; then
  _LIVEPI_BOOT_FILES=("${LIVEPI_ENV_FILE}")
else
  _LIVEPI_BOOT_FILES=("secrets.env" "prompt_injection_lab/.env")
fi
for _f in "${_LIVEPI_BOOT_FILES[@]}"; do
  if [[ "${_f}" != "/dev/null" && -f "${PWD}/${_f}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${PWD}/${_f}" 2>/dev/null || true
    set +a
  fi
done
unset _f _LIVEPI_BOOT_FILES

IMAGE="${IMAGE:-livepi-runner:cpu}"
NETWORK="${LIVEPI_DOCKER_NETWORK:-host}"
CPUS="${CPUS:-4}"
MEMORY="${MEMORY:-8g}"
SSH_DIR="${LIVEPI_SSH_DIR:-${HOME}/.ssh}"
ENV_FILE="${LIVEPI_ENV_FILE:-}"
ISOLATED_WORKSPACE="${LIVEPI_DOCKER_ISOLATED_WORKSPACE:-true}"
WORK_ROOT="${LIVEPI_DOCKER_WORK_ROOT:-${TMPDIR:-/tmp}}"
HOST_REPO="${PWD}"
MOUNT_REPO="${HOST_REPO}"
RUN_ROOT=""

truthy() {
  case "$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

cleanup_run_root() {
  if [[ -n "${RUN_ROOT}" && -d "${RUN_ROOT}" ]]; then
    rm -rf "${RUN_ROOT}"
  fi
}

copy_repo_for_run() {
  mkdir -p "${WORK_ROOT}"
  RUN_ROOT="$(mktemp -d "${WORK_ROOT%/}/livepi-run.XXXXXX")"
  MOUNT_REPO="${RUN_ROOT}/workspace"
  mkdir -p "${MOUNT_REPO}"
  rsync -a --delete \
    --exclude='.git/' \
    --exclude='.venv/' \
    --exclude='venv/' \
    --exclude='node_modules/' \
    --exclude='__pycache__/' \
    --exclude='.pytest_cache/' \
    --exclude='.mypy_cache/' \
    --exclude='.ruff_cache/' \
    --exclude='.livepi_agent_runtime/' \
    --exclude='.livepi-agent-home/' \
    --exclude='prompt_injection_lab/results/' \
    --exclude='prompt_injection_lab/results_*/' \
    --exclude='.livepi_docker_runs/' \
    "${HOST_REPO}/" "${MOUNT_REPO}/"
  mkdir -p "${MOUNT_REPO}/prompt_injection_lab/results"
}

copy_results_back() {
  if [[ -z "${RUN_ROOT}" || ! -d "${MOUNT_REPO}/prompt_injection_lab/results" ]]; then
    return 0
  fi
  mkdir -p "${HOST_REPO}/prompt_injection_lab/results"
  rsync -a "${MOUNT_REPO}/prompt_injection_lab/results/" "${HOST_REPO}/prompt_injection_lab/results/"
}

container_repo_path_arg() {
  local value="$1"
  case "${value}" in
    "${HOST_REPO}"/*)
      printf '/workspace/%s' "${value#"${HOST_REPO}/"}"
      ;;
    "${HOST_REPO}")
      printf '/workspace'
      ;;
    *)
      printf '%s' "${value}"
      ;;
  esac
}

map_container_args() {
  CONTAINER_ARGS=("$@")
  local i=0
  while [[ "${i}" -lt "${#CONTAINER_ARGS[@]}" ]]; do
    case "${CONTAINER_ARGS[$i]}" in
      --results-root|--batch-output-jsonl|--env-file)
        if [[ "$((i + 1))" -lt "${#CONTAINER_ARGS[@]}" ]]; then
          CONTAINER_ARGS[$((i + 1))]="$(container_repo_path_arg "${CONTAINER_ARGS[$((i + 1))]}")"
          i=$((i + 2))
          continue
        fi
        ;;
      --results-root=*|--batch-output-jsonl=*|--env-file=*)
        local flag="${CONTAINER_ARGS[$i]%%=*}"
        local value="${CONTAINER_ARGS[$i]#*=}"
        CONTAINER_ARGS[$i]="${flag}=$(container_repo_path_arg "${value}")"
        ;;
    esac
    i=$((i + 1))
  done
}

if truthy "${ISOLATED_WORKSPACE}"; then
  copy_repo_for_run
  trap cleanup_run_root EXIT
fi
CONTAINER_ARGS=()
map_container_args "$@"

malicious_task_tag=""
surface_tag=""
for ((i = 0; i < ${#CONTAINER_ARGS[@]}; i++)); do
  case "${CONTAINER_ARGS[$i]}" in
    --malicious-task-tag)
      if [[ "$((i + 1))" -lt "${#CONTAINER_ARGS[@]}" ]]; then
        malicious_task_tag="${CONTAINER_ARGS[$((i + 1))]}"
      fi
      ;;
    --malicious-task-tag=*)
      malicious_task_tag="${CONTAINER_ARGS[$i]#*=}"
      ;;
    --surface-tag)
      if [[ "$((i + 1))" -lt "${#CONTAINER_ARGS[@]}" ]]; then
        surface_tag="${CONTAINER_ARGS[$((i + 1))]}"
      fi
      ;;
    --surface-tag=*)
      surface_tag="${CONTAINER_ARGS[$i]#*=}"
      ;;
  esac
done

# Surface-level serial lock. Some surfaces use shared upstream state that
# cannot tolerate parallel runs:
#   - github_supply_chain: all runs push to the same repo + slot. Two cases
#     in flight at once would overwrite each other's seed payload and
#     poison both runs (we observed attack=False false negatives during
#     parallel batches). flock here serializes them safely.
# Override with LIVEPI_SUPPLY_CHAIN_SERIAL=false if you really want parallel
# (e.g. you forked a per-worker repo and pinned GITHUB_SUPPLY_CHAIN_REPO).
if [[ "${surface_tag}" == "github_supply_chain" ]]   && truthy "${LIVEPI_SUPPLY_CHAIN_SERIAL:-true}"; then
  _SC_LOCK="${LIVEPI_SUPPLY_CHAIN_LOCKFILE:-${TMPDIR:-/tmp}/livepi_supply_chain.lock}"
  echo "[run_in_docker] waiting on supply-chain serial lock at ${_SC_LOCK}" >&2
  exec 9>"${_SC_LOCK}"
  flock 9
  echo "[run_in_docker] supply-chain lock acquired (run_marker scope)" >&2
fi

docker_extra_flags=()
if [[ "${malicious_task_tag}" == "disable_firewall_auto_updates" ]] \
  && truthy "${LIVEPI_DOCKER_SYSTEM_SANDBOX:-true}"; then
  if [[ -z "${LIVEPI_DOCKER_NETWORK+x}" ]]; then
    NETWORK="${LIVEPI_DOCKER_SYSTEM_SANDBOX_NETWORK:-bridge}"
  fi
  docker_extra_flags+=(--cap-add NET_ADMIN --cap-add NET_RAW)
  env_flags_system_sandbox=(-e LIVEPI_SYSTEM_SANDBOX=real_container)
else
  env_flags_system_sandbox=()
fi

has_run_env_file_arg() {
  local arg
  for arg in "${CONTAINER_ARGS[@]}"; do
    if [[ "${arg}" == "--env-file" || "${arg}" == --env-file=* ]]; then
      return 0
    fi
  done
  return 1
}

env_flags=(-e PYTHONUNBUFFERED=1 -e LIVEPI_BUNDLED_SKILLS_SOURCE=/opt/livepi/prompt_injection_lab/fixtures/skills)
run_surface_env_file=""
if [[ -z "${ENV_FILE}" ]]; then
  if [[ -f "${MOUNT_REPO}/secrets.env" ]]; then
    ENV_FILE="secrets.env"
  elif [[ -f "${MOUNT_REPO}/prompt_injection_lab/.env" ]]; then
    ENV_FILE="prompt_injection_lab/.env"
  fi
fi
if [[ -n "${ENV_FILE}" ]]; then
  if [[ "${ENV_FILE}" == "/dev/null" ]]; then
    run_surface_env_file="/dev/null"
  elif [[ -f "${MOUNT_REPO}/${ENV_FILE}" ]]; then
    env_flags+=(--env-file "${MOUNT_REPO}/${ENV_FILE}")
    run_surface_env_file="$(container_repo_path_arg "${HOST_REPO}/${ENV_FILE}")"
  elif [[ -f "${ENV_FILE}" ]]; then
    env_flags+=(--env-file "${ENV_FILE}")
    run_surface_env_file="/dev/null"
  fi
fi
if [[ -n "${run_surface_env_file}" ]] && ! has_run_env_file_arg; then
  CONTAINER_ARGS+=(--env-file "${run_surface_env_file}")
fi
for key in \
  OPENCLAW_GATEWAY_TOKEN \
  OPENCLAW_GATEWAY_PASSWORD \
  LIVEPI_REMOTE_HOST \
  OPENCLAW_SSH_HOST \
  OPENCLAW_PROFILE \
  OPENCLAW_TUNNEL_LOCAL_PORT \
  OPENCLAW_TUNNEL_REMOTE_PORT \
  OPENCLAW_GATEWAY_IDENTITY_FILE \
  OPENCLAW_PRIMARY_MODEL \
  OPENCLAW_WORKSPACE \
  OPENCLAW_BENCHMARK_RECIPIENT_EMAIL \
  OPENCLAW_BENCHMARK_SCAN_PY_URL \
  OPENCLAW_BENCHMARK_SCAN_PY_SOURCE_URL \
  OPENCLAW_BENCHMARK_SCAN_PY_OWNER \
  OPENCLAW_BENCHMARK_SCAN_PY_REPO \
  OPENCLAW_BENCHMARK_SCAN_PY_BRANCH \
  OPENCLAW_BENCHMARK_SCAN_PY_PATH \
  OPENCLAW_BENCHMARK_SCAN_PY_PRIVATE \
  OPENCLAW_BENCHMARK_WALLET_FILE_PATH \
  TEST_RECIPIENT_EMAIL \
  TEST_CLEANUP_EMAIL \
  LIVEPI_AGENT \
  LIVEPI_CLI_AGENT_INCLUDE_GUIDE_PROMPT \
  LIVEPI_BUNDLED_SKILLS_SOURCE \
  LLM_JUDGE_PROVIDER \
  LLM_JUDGE_MODEL \
  OPENAI_BASE_URL \
  OPENAI_ORG_ID \
  OPENROUTER_BASE_URL \
  OPENROUTER_API_KEY \
  ANTHROPIC_API_KEY \
  ANTHROPIC_BASE_URL \
  ANTHROPIC_AUTH_TOKEN \
  MOONSHOT_API_KEY \
  MODELSTUDIO_API_KEY \
  ZAI_API_KEY \
  GOOGLE_API_KEY \
  OPENAI_API_KEY \
  SMTP_HOST \
  SMTP_PORT \
  SMTP_SECURE \
  SMTP_STARTTLS \
  SMTP_REJECT_UNAUTHORIZED \
  SMTP_USER \
  SMTP_PASS \
  SMTP_FROM \
  HERMES_COMMAND \
  HERMES_CLI_ARGS \
  HERMES_QUERY_FLAG \
  HERMES_APPEND_QUERY_FLAG \
  HERMES_STDIN \
  HERMES_WORKDIR \
  HERMES_API_KEY \
  HERMES_API_KEY_ENV \
  HERMES_API_KEY_SOURCE_ENV \
  HERMES_REQUIRE_API_KEY \
  HERMES_RUNTIME_ROOT \
  HERMES_AGENT_HOME \
  HERMES_HOME \
  HERMES_SKILLS_DIR \
  HERMES_INSTALL_BUNDLED_SKILLS \
  HERMES_MODEL \
  HERMES_PROVIDER \
  HERMES_TOOLSETS \
  HERMES_PRELOAD_SKILLS \
  HERMES_QUIET \
  HERMES_TELEGRAM_BOT_TOKEN \
  HERMES_TELEGRAM_GROUP_ID \
  HERMES_TELEGRAM_AGENT_MENTION \
  HERMES_TELEGRAM_AGENT_USERNAME \
  HERMES_SLACK_BOT_TOKEN \
  HERMES_SLACK_CHANNEL_ID \
  HERMES_SLACK_AGENT_MENTION \
  HERMES_SLACK_AGENT_USERNAME \
  HERMES_WHATSAPP_API_URL \
  HERMES_WHATSAPP_ACCESS_TOKEN \
  HERMES_WHATSAPP_GROUP_ID \
  HERMES_WHATSAPP_AGENT_MENTION \
  LIVEPI_AGENT_RUNTIME_ROOT \
  CODEX_COMMAND \
  CODEX_MODEL \
  CODEX_MODEL_PROVIDER \
  CODEX_PROVIDER \
  CODEX_BASE_URL \
  CODEX_API_BASE_URL \
  CODEX_PROVIDER_ENV_KEY \
  CODEX_SHELL_ENV_INHERIT \
  CODEX_CLI_ARGS \
  CODEX_QUERY_FLAG \
  CODEX_APPEND_QUERY_FLAG \
  CODEX_STDIN \
  CODEX_WORKDIR \
  CODEX_RUNTIME_ROOT \
  CODEX_AGENT_HOME \
  CODEX_HOME \
  CODEX_SKILLS_DIR \
  CODEX_INSTALL_BUNDLED_SKILLS \
  CODEX_TELEGRAM_BOT_TOKEN \
  CODEX_TELEGRAM_GROUP_ID \
  CODEX_TELEGRAM_AGENT_MENTION \
  CODEX_TELEGRAM_AGENT_USERNAME \
  CODEX_SLACK_BOT_TOKEN \
  CODEX_SLACK_CHANNEL_ID \
  CODEX_SLACK_AGENT_MENTION \
  CODEX_SLACK_AGENT_USERNAME \
  CODEX_WHATSAPP_API_URL \
  CODEX_WHATSAPP_ACCESS_TOKEN \
  CODEX_WHATSAPP_GROUP_ID \
  CODEX_WHATSAPP_AGENT_MENTION \
  CODEX_API_KEY \
  CODEX_API_KEY_ENV \
  CODEX_API_KEY_SOURCE_ENV \
  CODEX_REQUIRE_API_KEY \
  CLAUDE_CODE_COMMAND \
  CLAUDE_CODE_MODEL \
  CLAUDE_CODE_CLI_ARGS \
  CLAUDE_CODE_QUERY_FLAG \
  CLAUDE_CODE_APPEND_QUERY_FLAG \
  CLAUDE_CODE_STDIN \
  CLAUDE_CODE_WORKDIR \
  CLAUDE_CODE_RUNTIME_ROOT \
  CLAUDE_CODE_AGENT_HOME \
  CLAUDE_CODE_SKILLS_DIR \
  CLAUDE_CODE_INSTALL_BUNDLED_SKILLS \
  CLAUDE_CONFIG_DIR \
  CLAUDE_CODE_TELEGRAM_BOT_TOKEN \
  CLAUDE_CODE_TELEGRAM_GROUP_ID \
  CLAUDE_CODE_TELEGRAM_AGENT_MENTION \
  CLAUDE_CODE_TELEGRAM_AGENT_USERNAME \
  CLAUDE_CODE_SLACK_BOT_TOKEN \
  CLAUDE_CODE_SLACK_CHANNEL_ID \
  CLAUDE_CODE_SLACK_AGENT_MENTION \
  CLAUDE_CODE_SLACK_AGENT_USERNAME \
  CLAUDE_CODE_WHATSAPP_API_URL \
  CLAUDE_CODE_WHATSAPP_ACCESS_TOKEN \
  CLAUDE_CODE_WHATSAPP_GROUP_ID \
  CLAUDE_CODE_WHATSAPP_AGENT_MENTION \
  CLAUDE_CODE_API_KEY \
  CLAUDE_CODE_API_KEY_ENV \
  CLAUDE_CODE_API_KEY_SOURCE_ENV \
  CLAUDE_CODE_REQUIRE_API_KEY \
  ATTACKER_SMTP_HOST \
  ATTACKER_SMTP_PORT \
  ATTACKER_SMTP_SECURE \
  ATTACKER_SMTP_STARTTLS \
  ATTACKER_SMTP_REJECT_UNAUTHORIZED \
  ATTACKER_SMTP_USER \
  ATTACKER_SMTP_PASS \
  ATTACKER_SMTP_FROM \
  GMAIL_SENDER \
  GMAIL_ACCESS_TOKEN \
  GMAIL_REFRESH_TOKEN \
  GMAIL_CLIENT_ID \
  GMAIL_CLIENT_SECRET \
  IMAP_HOST \
  IMAP_PORT \
  IMAP_TLS \
  IMAP_USER \
  IMAP_PASS \
  IMAP_MAILBOX \
  IMAP_REJECT_UNAUTHORIZED \
  IMAP_TIMEOUT_S \
  VERIFY_IMAP_HOST \
  VERIFY_IMAP_PORT \
  VERIFY_IMAP_TLS \
  VERIFY_IMAP_USER \
  VERIFY_IMAP_PASS \
  VERIFY_IMAP_MAILBOX \
  VERIFY_IMAP_REJECT_UNAUTHORIZED \
  VERIFY_IMAP_TIMEOUT_S \
  VERIFY_IMAP_BEFORE_LIMIT \
  VERIFY_IMAP_AFTER_LIMIT \
  TELEGRAM_BOT_TOKEN \
  TELEGRAM_AGENT_BOT_TOKEN \
  TELEGRAM_BENCHMARK_BOT_TOKEN \
  TELEGRAM_USER_API_ID \
  TELEGRAM_USER_API_HASH \
  TELEGRAM_USER_SESSION \
  TELEGRAM_USER_SESSION_FILE \
  TELEGRAM_USER_PHONE \
  TELEGRAM_GROUP_ID \
  TELEGRAM_GROUP_IDS \
  TELEGRAM_AGENT_MENTION \
  TELEGRAM_AGENT_USERNAME \
  TELEGRAM_REQUIRE_MENTION \
  TELEGRAM_GROUP_POLICY \
  TELEGRAM_KEEP_BENCHMARK_MESSAGES \
  LIVEPI_KEEP_TELEGRAM_MESSAGES \
  SLACK_BOT_TOKEN \
  SLACK_SENDER_TOKEN \
  SLACK_ATTACKER_USER_TOKEN \
  SLACK_BENCHMARK_USER_TOKEN \
  SLACK_APP_TOKEN \
  SLACK_CHANNEL_ID \
  SLACK_AGENT_MENTION \
  SLACK_AGENT_USERNAME \
  SLACK_REQUIRE_MENTION \
  SLACK_KEEP_BENCHMARK_MESSAGES \
  LIVEPI_KEEP_SLACK_MESSAGES \
  SLACK_WEBHOOK_PATH \
  SLACK_USER_TOKEN_READ_ONLY \
  SLACK_GROUP_POLICY \
  OPENCLAW_ENABLE_WHATSAPP \
  WHATSAPP_API_URL \
  WHATSAPP_ACCESS_TOKEN \
  WHATSAPP_GROUP_ID \
  WHATSAPP_AGENT_MENTION \
  WHATSAPP_EXTRA_PAYLOAD_JSON \
  WHATSAPP_DEFAULT_TO \
  WHATSAPP_GROUP_ALLOW_FROM \
  WHATSAPP_REQUIRE_MENTION \
  WHATSAPP_GROUP_POLICY \
  WHATSAPP_BRIDGE_ENABLED \
  WHATSAPP_BRIDGE_AUTH_DIR \
  WHATSAPP_BRIDGE_HOST \
  WHATSAPP_BRIDGE_PORT \
  WHATSAPP_BRIDGE_DEFAULT_MENTIONS \
  GITHUB_TOKEN \
  GITHUB_GIST_TOKEN \
  GIST_TUTORIAL_FIXED_URL \
  GITHUB_OWNER \
  GITHUB_REPO \
  GITHUB_BRANCH \
  GITHUB_FILE_PATH \
  GITHUB_FILE_URL \
  GITHUB_SUPPLY_CHAIN_TOKEN \
  GITHUB_SUPPLY_CHAIN_OWNER \
  GITHUB_SUPPLY_CHAIN_REPO \
  GITHUB_SUPPLY_CHAIN_BRANCH \
  GITHUB_SUPPLY_CHAIN_PRIVATE \
  GITHUB_SUPPLY_CHAIN_SHARE_LINK \
  GITHUB_SUPPLY_CHAIN_PREPARE \
  GITHUB_SUPPLY_CHAIN_CDN_WAIT_S \
  GITHUB_SUPPLY_CHAIN_POST_TRIGGER_WAIT_S \
  LIVEPI_PAYLOAD_RUN_TIMEOUT_S \
  LIVEPI_PAYLOAD_IMAP_TIMEOUT_S \
  LIVEPI_PAYLOAD_SMTP_TIMEOUT_S \
  SOLANA_PRIVATE_KEY \
  SOLANA_RPC_URL \
  SOLANA_ATTACKER_ADDRESS \
  OPENCLAW_BENCHMARK_SOLANA_RECIPIENT_ADDRESS \
  TEST_SOLANA_RECIPIENT_ADDRESS \
  JUPITER_API_KEY \
  REDDIT_CLIENT_ID \
  REDDIT_CLIENT_SECRET \
  REDDIT_USERNAME \
  REDDIT_PASSWORD \
  REDDIT_SUBREDDIT \
  X_API_KEY \
  X_API_SECRET \
  X_ACCESS_TOKEN \
  X_ACCESS_SECRET \
  OPENCLAW_SSH_OPTIONS \
  LIVEPI_SSH_OPTIONS; do
  if [[ -n "${!key:-}" ]]; then
    env_flags+=(-e "${key}")
  fi
done

ssh_flags=()
if [[ -d "${SSH_DIR}" ]]; then
  ssh_flags=(-v "${SSH_DIR}:/root/.ssh:ro")
fi

# Optional: mount a host Hermes home into the container so OAuth credentials
# (e.g. ChatGPT account via 'hermes auth add openai-codex') persist across
# runs. Activated only when HERMES_HOME points to an existing host directory.
hermes_home_flags=()
if [[ -n "${HERMES_HOME:-}" && -d "${HERMES_HOME}" ]]; then
  hermes_home_flags=(-v "${HERMES_HOME}:${HERMES_HOME}")
fi

# Same conditional mount for Codex CLI OAuth state (~/.codex/auth.json).
codex_home_flags=()
if [[ -n "${CODEX_HOME:-}" && -d "${CODEX_HOME}" ]]; then
  codex_home_flags=(-v "${CODEX_HOME}:${CODEX_HOME}")
fi

# Same conditional mount for Claude Code OAuth state (~/.claude/) when set
# via 'claude setup-token'. CLAUDE_CONFIG_DIR points at it on the host.
claude_home_flags=()
if [[ -n "${CLAUDE_CONFIG_DIR:-}" && -d "${CLAUDE_CONFIG_DIR}" ]]; then
  claude_home_flags=(-v "${CLAUDE_CONFIG_DIR}:${CLAUDE_CONFIG_DIR}")
fi

set +e
docker run --rm \
  --network "${NETWORK}" \
  --cpus "${CPUS}" \
  --memory "${MEMORY}" \
  --add-host host.docker.internal:host-gateway \
  "${docker_extra_flags[@]}" \
  -v "${MOUNT_REPO}:/workspace" \
  -w /workspace \
  "${ssh_flags[@]}" \
  "${hermes_home_flags[@]}" \
  "${codex_home_flags[@]}" \
  "${claude_home_flags[@]}" \
  "${env_flags_system_sandbox[@]}" \
  "${env_flags[@]}" \
  "${IMAGE}" \
  python3 prompt_injection_lab/scripts/run_surface_test.py "${CONTAINER_ARGS[@]}"
status=$?
set -e

copy_results_back
exit "${status}"
