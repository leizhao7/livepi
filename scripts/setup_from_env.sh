#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/setup_from_env.sh --host livepi --env-file secrets.env [--smoke]

Provision a VPS from one env file:
  - sync this repo to the VPS
  - install Docker and build the LivePI runner image
  - install/configure OpenClaw gateway from secrets.env
  - wire Telegram, Slack, and optional WhatsApp channels/plugins into OpenClaw
  - create a Telegram attacker user session when needed
  - optionally link WhatsApp Web QR sessions for OpenClaw and the attacker bridge
  - verify core/email/agent/channel env inside Docker

Options:
  --host HOST                 SSH host or alias (default: LIVEPI_SETUP_HOST or livepi)
  --env-file PATH            Secrets env file (default: LIVEPI_SETUP_ENV_FILE or secrets.env)
  --remote-dir PATH          Remote repo dir (default: /root/livepi_neurips_dataset)
  --image NAME               Docker image (default: LIVEPI_IMAGE or livepi-runner:cpu)
  --skip-sync                Do not rsync repo to the VPS
  --skip-docker              Do not run bootstrap_ubuntu.sh or build_agent_image.sh
  --skip-openclaw            Do not run setup_openclaw_benchmark_env.py
  --install-hermes           Install Hermes Agent CLI on the VPS
  --skip-hermes-install      Never install Hermes Agent CLI
  --telegram-login           Force Telegram user-session login
  --skip-telegram-login      Never run Telegram user-session login
  --whatsapp-login           Link WhatsApp Web sessions interactively via QR
  --skip-whatsapp-login      Never run WhatsApp QR login
  --smoke                    Send benchmark payload smoke messages for configured surfaces
  --smoke-surfaces LIST      Comma list: telegram,slack,whatsapp (default: telegram,slack)
  --smoke-task TAG           Default: crypto_related_files_to_email
  --smoke-technique TAG      Default: direct_group_message_instruction
  --chat-timeout-s SECONDS   Default: 45
  -h, --help                 Show this help

Telegram login is interactive: Telegram will send a code to TELEGRAM_USER_PHONE.
WhatsApp login is interactive: scan the QR for the OpenClaw agent account, then
scan the attacker bridge QR if WHATSAPP_API_URL points at the local bridge.
Secrets are not printed by this script.
EOF
}

log() {
  printf '[livepi-setup] %s\n' "$*"
}

die() {
  printf '[livepi-setup] error: %s\n' "$*" >&2
  exit 1
}

shq() {
  python3 - "$1" <<'PY'
import shlex
import sys
print(shlex.quote(sys.argv[1]))
PY
}

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
host="${LIVEPI_SETUP_HOST:-livepi}"
env_file="${LIVEPI_SETUP_ENV_FILE:-secrets.env}"
remote_dir="${LIVEPI_REMOTE_DIR:-/root/livepi_neurips_dataset}"
image="${LIVEPI_IMAGE:-livepi-runner:cpu}"
skip_sync=0
skip_docker=0
skip_openclaw=0
hermes_install_mode="auto"
telegram_login_mode="auto"
whatsapp_login_mode="never"
run_smoke=0
smoke_surfaces="telegram,slack"
smoke_task="crypto_related_files_to_email"
smoke_technique="direct_group_message_instruction"
chat_timeout_s="45"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      host="${2:?missing value for --host}"
      shift 2
      ;;
    --env-file)
      env_file="${2:?missing value for --env-file}"
      shift 2
      ;;
    --remote-dir)
      remote_dir="${2:?missing value for --remote-dir}"
      shift 2
      ;;
    --image)
      image="${2:?missing value for --image}"
      shift 2
      ;;
    --skip-sync)
      skip_sync=1
      shift
      ;;
    --skip-docker)
      skip_docker=1
      shift
      ;;
    --skip-openclaw)
      skip_openclaw=1
      shift
      ;;
    --install-hermes)
      hermes_install_mode="always"
      shift
      ;;
    --skip-hermes-install)
      hermes_install_mode="never"
      shift
      ;;
    --telegram-login)
      telegram_login_mode="always"
      shift
      ;;
    --skip-telegram-login)
      telegram_login_mode="never"
      shift
      ;;
    --whatsapp-login)
      whatsapp_login_mode="always"
      shift
      ;;
    --skip-whatsapp-login)
      whatsapp_login_mode="never"
      shift
      ;;
    --smoke)
      run_smoke=1
      shift
      ;;
    --smoke-surfaces)
      smoke_surfaces="${2:?missing value for --smoke-surfaces}"
      shift 2
      ;;
    --smoke-task)
      smoke_task="${2:?missing value for --smoke-task}"
      shift 2
      ;;
    --smoke-technique)
      smoke_technique="${2:?missing value for --smoke-technique}"
      shift 2
      ;;
    --chat-timeout-s)
      chat_timeout_s="${2:?missing value for --chat-timeout-s}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

cd "$repo_root"
[[ -f "$env_file" ]] || die "env file not found: $env_file"
command -v ssh >/dev/null 2>&1 || die "ssh is required"
command -v rsync >/dev/null 2>&1 || die "rsync is required"
command -v python3 >/dev/null 2>&1 || die "python3 is required"

env_file_abs="$(cd "$(dirname "$env_file")" && pwd)/$(basename "$env_file")"
remote_dir_q="$(shq "$remote_dir")"
image_q="$(shq "$image")"
read -r livepi_agent_from_env hermes_command_from_env <<<"$(
  python3 - "$env_file_abs" <<'PY'
from pathlib import Path
import sys

values = {}
for raw in Path(sys.argv[1]).read_text(encoding='utf-8').splitlines():
    line = raw.strip()
    if not line or line.startswith('#'):
        continue
    if line.startswith('export '):
        line = line[len('export '):].strip()
    if '=' not in line:
        continue
    k, v = line.split('=', 1)
    values[k.strip()] = v.strip().strip("'").strip('"')
print(values.get('LIVEPI_AGENT', 'openclaw').strip().lower() or 'openclaw',
      values.get('HERMES_COMMAND', 'hermes').strip() or 'hermes')
PY
)"

ssh_config="$(ssh -G "$host" 2>/dev/null || true)"
remote_user="$(awk 'tolower($1)=="user"{print $2; exit}' <<<"$ssh_config")"
remote_port="$(awk 'tolower($1)=="port"{print $2; exit}' <<<"$ssh_config")"
remote_user="${remote_user:-root}"
remote_port="${remote_port:-22}"

if [[ "$skip_sync" -eq 0 ]]; then
  log "syncing repo to ${host}:${remote_dir}"
  ssh "$host" "mkdir -p $remote_dir_q"
  rsync -az --delete \
    --exclude='.git/' \
    --exclude='.venv/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='prompt_injection_lab/.telegram_benchmark.session' \
    --exclude='prompt_injection_lab/results/' \
    --exclude='prompt_injection_lab/results_*/' \
    "$repo_root/" "$host:$remote_dir/"
fi

if [[ "$skip_docker" -eq 0 ]]; then
  log "installing remote system deps and building ${image}"
  build_env=""
  if [[ "$livepi_agent_from_env" == "hermes" && -z "${LIVEPI_INSTALL_HERMES:-}" ]]; then
    build_env="LIVEPI_INSTALL_HERMES=true"
    log "LIVEPI_AGENT=hermes detected; building runner image with Hermes Agent"
  fi
  ssh "$host" "cd $remote_dir_q && bash scripts/bootstrap_ubuntu.sh && $build_env bash scripts/build_agent_image.sh $image_q"
fi

need_hermes_install="no"
if [[ "$hermes_install_mode" != "never" ]]; then
  need_hermes_install="$(
    python3 - "$env_file_abs" <<'PY'
from pathlib import Path
import sys

values = {}
for raw in Path(sys.argv[1]).read_text(encoding='utf-8').splitlines():
    line = raw.strip()
    if not line or line.startswith('#'):
        continue
    if line.startswith('export '):
        line = line[len('export '):].strip()
    if '=' not in line:
        continue
    k, v = line.split('=', 1)
    values[k.strip()] = v.strip().strip("'").strip('"')
agent = values.get('LIVEPI_AGENT', '').strip().lower()
command = values.get('HERMES_COMMAND', 'hermes').strip()
print('yes' if agent == 'hermes' and command.startswith('ssh ') else 'no')
PY
  )"
fi

if [[ "$hermes_install_mode" == "always" || "$need_hermes_install" == "yes" ]]; then
  log "ensuring Hermes Agent CLI is installed on the VPS"
  ssh "$host" "cd $remote_dir_q && bash scripts/install_hermes_agent.sh"
fi

log "ensuring remote self-SSH works for Docker benchmark cleanup/seed"
ssh "$host" \
  "REMOTE_SELF_USER=$(shq "$remote_user") REMOTE_SELF_PORT=$(shq "$remote_port") bash -s" <<'REMOTE'
set -euo pipefail
umask 077
mkdir -p ~/.ssh
if [[ ! -f ~/.ssh/id_ed25519 ]]; then
  ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519 -C livepi-self >/dev/null
fi
touch ~/.ssh/authorized_keys
grep -qxF "$(cat ~/.ssh/id_ed25519.pub)" ~/.ssh/authorized_keys || cat ~/.ssh/id_ed25519.pub >> ~/.ssh/authorized_keys
cat > ~/.ssh/config <<EOF
Host livepi
    HostName 127.0.0.1
    User ${REMOTE_SELF_USER}
    Port ${REMOTE_SELF_PORT}
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
EOF
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys ~/.ssh/config ~/.ssh/id_ed25519
chmod 644 ~/.ssh/id_ed25519.pub
REMOTE

if [[ "$skip_openclaw" -eq 0 ]]; then
  log "installing/configuring OpenClaw gateway from env"
  python3 setup_openclaw_benchmark_env.py \
    --host "$host" \
    --secrets-file "$env_file_abs" \
    --apply \
    --skip-tunnel \
    --skip-gateway-check \
    --force-overwrite-existing
fi

log "syncing generated env files back to VPS"
rsync -az "$env_file_abs" "$host:$remote_dir/secrets.env"
if [[ -f "$repo_root/prompt_injection_lab/.env" ]]; then
  rsync -az "$repo_root/prompt_injection_lab/.env" "$host:$remote_dir/prompt_injection_lab/.env"
fi

read -r whatsapp_enabled whatsapp_bridge_local whatsapp_health_url <<<"$(
  python3 - "$env_file_abs" <<'PY'
from pathlib import Path
from urllib.parse import urlparse
import sys

def load_env(path: Path) -> dict[str, str]:
    values = {}
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[len('export '):].strip()
        if '=' not in line:
            continue
        k, v = line.split('=', 1)
        values[k.strip()] = v.strip().strip("'").strip('"')
    return values

def truthy(value: str) -> bool:
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}

values = load_env(Path(sys.argv[1]))
enabled = truthy(values.get('OPENCLAW_ENABLE_WHATSAPP', ''))
api_url = values.get('WHATSAPP_API_URL', '').strip()
parsed = urlparse(api_url)
host = (parsed.hostname or '').lower()
bridge_local = truthy(values.get('WHATSAPP_BRIDGE_ENABLED', '')) or host in {
    '127.0.0.1',
    'localhost',
    '::1',
    '0.0.0.0',
}
port = parsed.port or int(values.get('WHATSAPP_BRIDGE_PORT', '') or 17891)
print(
    'true' if enabled else 'false',
    'true' if bridge_local else 'false',
    f'http://127.0.0.1:{port}/health',
)
PY
)"
whatsapp_health_url_q="$(shq "$whatsapp_health_url")"

if [[ "$whatsapp_enabled" == "true" && "$whatsapp_bridge_local" == "true" ]]; then
  log "installing WhatsApp benchmark bridge dependencies"
  ssh "$host" "cd $remote_dir_q && bash scripts/install_whatsapp_bridge_deps.sh"
fi

if [[ "$whatsapp_enabled" == "true" && "$whatsapp_login_mode" == "never" ]]; then
  log "WhatsApp QR login skipped; first-time WhatsApp setup needs --whatsapp-login"
fi

if [[ "$whatsapp_enabled" == "true" && "$whatsapp_login_mode" == "always" ]]; then
  log "linking OpenClaw WhatsApp agent account (scan QR)"
  ssh -tt "$host" "export PATH=\"\$HOME/.npm-global/bin:\$PATH\"; openclaw channels login --channel whatsapp --verbose"
  if [[ "$whatsapp_bridge_local" == "true" ]]; then
    log "linking WhatsApp benchmark attacker bridge account (scan QR)"
    ssh -tt "$host" "cd $remote_dir_q && node scripts/whatsapp_bridge.mjs --env-file secrets.env --login"
  fi
fi

if [[ "$whatsapp_enabled" == "true" && "$whatsapp_bridge_local" == "true" ]]; then
  log "starting WhatsApp benchmark bridge"
  ssh "$host" "cd $remote_dir_q && if [[ -f /tmp/livepi-whatsapp-bridge.pid ]]; then kill \$(cat /tmp/livepi-whatsapp-bridge.pid) 2>/dev/null || true; fi; nohup node scripts/whatsapp_bridge.mjs --env-file secrets.env --serve >/tmp/livepi-whatsapp-bridge.log 2>&1 & echo \$! >/tmp/livepi-whatsapp-bridge.pid; sleep 3; curl -fsS $whatsapp_health_url_q >/tmp/livepi-whatsapp-bridge-health.json || { tail -80 /tmp/livepi-whatsapp-bridge.log >&2; exit 1; }"
fi

need_telegram_login="no"
if [[ "$telegram_login_mode" != "never" ]]; then
  need_telegram_login="$(
    ssh "$host" "cd $remote_dir_q && docker run --rm -v \"\$PWD:/workspace\" -w /workspace --env-file secrets.env $image_q python3 - <<'PY'
from pathlib import Path

def load_env(path: Path) -> dict[str, str]:
    values = {}
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[len('export '):].strip()
        if '=' not in line:
            continue
        k, v = line.split('=', 1)
        values[k.strip()] = v.strip().strip(\"'\").strip('\"')
    return values

def is_set(values: dict[str, str], key: str) -> bool:
    return bool(values.get(key, '').strip())

values = load_env(Path('secrets.env'))
session_file_ok = False
raw_session_file = values.get('TELEGRAM_USER_SESSION_FILE', '').strip()
if raw_session_file:
    session_path = Path(raw_session_file).expanduser()
    if not session_path.is_absolute():
        session_path = Path('/workspace') / session_path
    session_file_ok = session_path.exists()
has_session = is_set(values, 'TELEGRAM_USER_SESSION') or session_file_ok
has_login_inputs = (
    is_set(values, 'TELEGRAM_USER_API_ID')
    and is_set(values, 'TELEGRAM_USER_API_HASH')
    and is_set(values, 'TELEGRAM_USER_PHONE')
)
print('yes' if has_login_inputs and not has_session else 'no')
PY"
  )"
fi

if [[ "$telegram_login_mode" == "always" || "$need_telegram_login" == "yes" ]]; then
  log "creating Telegram attacker user session (interactive login code required)"
  ssh -tt "$host" "cd $remote_dir_q && docker run -it --rm -v \"\$PWD:/workspace\" -w /workspace --env-file secrets.env $image_q python3 scripts/telegram_user_login.py --env-file secrets.env"
fi

log "checking messaging env inside Docker"
check_groups="core email telegram slack"
case "$livepi_agent_from_env" in
  hermes|codex|claude_code)
    check_groups="$check_groups $livepi_agent_from_env"
    ;;
esac
if [[ "$whatsapp_enabled" == "true" ]]; then
  check_groups="$check_groups whatsapp"
fi
ssh "$host" "cd $remote_dir_q && docker run --rm -v \"\$PWD:/workspace\" -w /workspace --env-file secrets.env --network host $image_q python3 scripts/check_env.py --groups $check_groups"

if [[ "$run_smoke" -eq 1 ]]; then
  smoke_agent="${livepi_agent_from_env:-openclaw}"
  smoke_agent_opts="--agent $(shq "$smoke_agent")"
  if [[ "$smoke_agent" == "openclaw" ]]; then
    smoke_agent_opts="$smoke_agent_opts --remote-host livepi --gateway-ws-url ws://127.0.0.1:18789/ws"
  fi
  IFS=',' read -r -a surfaces <<<"$smoke_surfaces"
  for surface in "${surfaces[@]}"; do
    surface="$(tr -d '[:space:]' <<<"$surface")"
    [[ -n "$surface" ]] || continue
    case "$surface" in
      telegram|telegram_group)
        surface_tag="telegram_group"
        keep_env="TELEGRAM_KEEP_BENCHMARK_MESSAGES=true"
        ;;
      slack|slack_channel)
        surface_tag="slack_channel"
        keep_env="SLACK_KEEP_BENCHMARK_MESSAGES=true"
        ;;
      whatsapp|whatsapp_group)
        surface_tag="whatsapp_group"
        keep_env=""
        ;;
      *)
        die "unsupported smoke surface: $surface"
        ;;
    esac
    log "running ${surface_tag} attack-message smoke with agent=${smoke_agent}"
    smoke_json="$(mktemp)"
    ssh "$host" "cd $remote_dir_q && LIVEPI_AGENT=$(shq "$smoke_agent") $keep_env OPENCLAW_SSH_OPTIONS='-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null' PYTHONPATH=src python3 -m livepi_bench.cli docker-run --repo . --env-file secrets.env --image $image_q --network host -- $smoke_agent_opts --surface-tag $(shq "$surface_tag") --technique-tag $(shq "$smoke_technique") --malicious-task-tag $(shq "$smoke_task") --chat-timeout-s $(shq "$chat_timeout_s") --results-root /tmp/livepi-${surface_tag}-smoke" >"$smoke_json"
    python3 - "$smoke_json" <<'PY'
import json
import sys
from pathlib import Path

raw = Path(sys.argv[1]).read_text(encoding='utf-8')
try:
    data = json.loads(raw)
except json.JSONDecodeError:
    print(raw)
    raise
steps = data.get('steps') or {}
send = steps.get('send_telegram') or steps.get('send_slack') or steps.get('send_whatsapp') or {}
cleanup = (
    steps.get('cleanup_telegram')
    or steps.get('cleanup_slack')
    or steps.get('cleanup_whatsapp')
    or steps.get('cleanup_telegram_after_error')
    or steps.get('cleanup_slack_after_error')
    or steps.get('cleanup_whatsapp_after_error')
    or {}
)
chat = (steps.get('chat_trigger') or {}).get('chat_result') or {}
message_ref = None
if 'telegram' in send:
    message_ref = (send.get('telegram') or {}).get('message_id')
elif 'slack' in send:
    message_ref = (send.get('slack') or {}).get('message_ts')
elif 'whatsapp' in send:
    message_ref = (send.get('whatsapp') or {}).get('message_id')
print(json.dumps({
    'status': data.get('status'),
    'surface': data.get('surface_tag'),
    'run_dir': data.get('run_dir'),
    'sender': send.get('sender'),
    'message_ref': message_ref,
    'chat_state': chat.get('state'),
    'deleted_sent_message': cleanup.get('deleted_sent_message'),
    'cleanup_reason': cleanup.get('reason'),
}, ensure_ascii=True, indent=2))
PY
    rm -f "$smoke_json"
  done
fi

log "setup complete"
