#!/usr/bin/env bash
set -euo pipefail

SUDO=()
if [[ "${EUID}" -ne 0 ]]; then
  SUDO=(sudo)
fi

"${SUDO[@]}" apt-get update
"${SUDO[@]}" apt-get install -y \
  ca-certificates \
  curl \
  git \
  jq \
  openssh-client \
  iptables \
  ufw \
  python3 \
  python3-pip \
  python3-venv \
  build-essential

if ! dpkg -s unattended-upgrades >/dev/null 2>&1; then
  "${SUDO[@]}" apt-get install -y unattended-upgrades || {
    ua_version="$(apt-cache madison unattended-upgrades | awk 'NR == 1 {print $3}')"
    [[ -n "$ua_version" ]] || exit 1
    "${SUDO[@]}" apt-get install -y "unattended-upgrades=${ua_version}"
  }
fi

if ! command -v docker >/dev/null 2>&1; then
  "${SUDO[@]}" apt-get install -y docker.io
  "${SUDO[@]}" systemctl enable --now docker || true
fi

if ! docker compose version >/dev/null 2>&1; then
  "${SUDO[@]}" apt-get install -y docker-compose-v2 || "${SUDO[@]}" apt-get install -y docker-compose-plugin || true
fi

echo "Bootstrap complete. Build the Docker runner with:"
echo "bash scripts/build_agent_image.sh"
