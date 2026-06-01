#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
deps_dir="${WHATSAPP_BRIDGE_DEPS_DIR:-$repo_root/.livepi_whatsapp_bridge_deps}"

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required for the WhatsApp benchmark bridge" >&2
  exit 1
fi

mkdir -p "$deps_dir"
if [[ ! -f "$deps_dir/package.json" ]]; then
  cat > "$deps_dir/package.json" <<'JSON'
{
  "private": true,
  "type": "module",
  "dependencies": {}
}
JSON
fi

npm install --omit=dev --prefix "$deps_dir" @whiskeysockets/baileys pino qrcode-terminal
echo "WhatsApp bridge deps installed in $deps_dir"
