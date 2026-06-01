#!/usr/bin/env bash
set -euo pipefail

branch="${HERMES_INSTALL_BRANCH:-main}"
install_url="${HERMES_INSTALL_URL:-https://raw.githubusercontent.com/NousResearch/hermes-agent/${branch}/scripts/install.sh}"
install_dir="${HERMES_INSTALL_DIR:-$HOME/.local/share/hermes-agent}"
hermes_home="${HERMES_HOME:-$HOME/.hermes-livepi/hermes-home}"
skip_setup=1
skip_browser=1
force=0

usage() {
  cat <<'EOF'
Usage:
  scripts/install_hermes_agent.sh [--dir PATH] [--hermes-home PATH] [--branch NAME] [--force]

Installs Hermes Agent using the official NousResearch installer without
interactive browser/setup steps. The benchmark passes API keys and run config
through env, so no global Hermes setup is required here.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir)
      install_dir="${2:?missing value for --dir}"
      shift 2
      ;;
    --hermes-home)
      hermes_home="${2:?missing value for --hermes-home}"
      shift 2
      ;;
    --branch)
      branch="${2:?missing value for --branch}"
      install_url="https://raw.githubusercontent.com/NousResearch/hermes-agent/${branch}/scripts/install.sh"
      shift 2
      ;;
    --with-setup)
      skip_setup=0
      shift
      ;;
    --with-browser)
      skip_browser=0
      shift
      ;;
    --force)
      force=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if command -v hermes >/dev/null 2>&1 && [[ "$force" -ne 1 ]]; then
  echo "hermes already installed: $(command -v hermes)"
  hermes --help >/dev/null 2>&1 || true
  exit 0
fi

args=(--dir "$install_dir" --hermes-home "$hermes_home")
if [[ "$skip_setup" -eq 1 ]]; then
  args+=(--skip-setup)
fi
if [[ "$skip_browser" -eq 1 ]]; then
  args+=(--skip-browser)
fi

curl -fsSL "$install_url" | bash -s -- "${args[@]}"

if ! command -v hermes >/dev/null 2>&1; then
  for candidate in "$HOME/.local/bin/hermes" "$install_dir/.venv/bin/hermes" "$install_dir/venv/bin/hermes"; do
    if [[ -x "$candidate" ]]; then
      mkdir -p "$HOME/.local/bin"
      ln -sf "$candidate" "$HOME/.local/bin/hermes"
      break
    fi
  done
fi

if ! command -v hermes >/dev/null 2>&1; then
  echo "Hermes installer finished, but hermes is not on PATH. Add $HOME/.local/bin to PATH." >&2
  exit 1
fi

echo "hermes installed: $(command -v hermes)"
