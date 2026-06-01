#!/usr/bin/env bash
# Sync the LivePI runner sources into artifacts/ so that
#   pip install ./artifacts
# yields a fully self-contained package.
# Idempotent: safe to re-run after editing repo source.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
ART="${REPO}/artifacts"
PKG="${ART}/livepi"
DATA="${PKG}/data"

echo "[sync] repo=${REPO}"
echo "[sync] artifacts=${ART}"

mkdir -p "${ART}" "${PKG}" "${DATA}/scripts" "${DATA}/docker" "${DATA}/artifacts"

# 1. prompt_injection_lab — vendor sibling next to livepi/ inside artifacts/
echo "[sync] prompt_injection_lab/ -> artifacts/prompt_injection_lab/"
rsync -a --delete \
  --exclude='__pycache__' \
  --exclude='.env' \
  --exclude='results/' \
  --exclude='*.pyc' \
  "${REPO}/prompt_injection_lab/" "${ART}/prompt_injection_lab/"

# 2. data/artifacts — move existing per-(agent,model) JSON into data/artifacts/
#    so data/scripts/ and data/docker/ can sit next to it.
if [ -d "${DATA}" ]; then
  for d in "${DATA}"/*/; do
    [ -d "$d" ] || continue
    name="$(basename "$d")"
    case "$name" in
      scripts|docker|artifacts) ;;
      *)
        mkdir -p "${DATA}/artifacts"
        echo "[sync] move ${name}/ -> artifacts/${name}/"
        rsync -a "$d" "${DATA}/artifacts/${name}/"
        rm -rf "$d"
        ;;
    esac
  done
fi

# 3. shell harness + setup script + dockerfile + helper python
echo "[sync] scripts + docker + helpers -> data/"
install -m 0755 "${REPO}/scripts/run_in_docker.sh"            "${DATA}/scripts/run_in_docker.sh"
install -m 0644 "${REPO}/scripts/aggregate_results.py"        "${DATA}/scripts/aggregate_results.py"
install -m 0755 "${REPO}/scripts/build_agent_image.sh"        "${DATA}/scripts/build_agent_image.sh"
install -m 0644 "${REPO}/scripts/install_hermes_agent.sh"     "${DATA}/scripts/install_hermes_agent.sh"
install -m 0755 "${REPO}/scripts/docker_smoke_checks.sh"      "${DATA}/scripts/docker_smoke_checks.sh"
install -m 0755 "${REPO}/scripts/bootstrap_ubuntu.sh"         "${DATA}/scripts/bootstrap_ubuntu.sh"
install -m 0644 "${REPO}/setup_openclaw_benchmark_env.py"     "${DATA}/scripts/setup_openclaw_benchmark_env.py"
install -m 0644 "${REPO}/create_remote_user_folder.py"        "${DATA}/scripts/create_remote_user_folder.py"
install -m 0644 "${REPO}/docker/runner-cpu/Dockerfile"        "${DATA}/docker/Dockerfile"
install -m 0644 "${REPO}/secrets.example.env"                 "${DATA}/secrets.example.env"
install -m 0644 "${REPO}/docker-compose.yml"                  "${DATA}/docker-compose.yml" || true

echo "[sync] done"
