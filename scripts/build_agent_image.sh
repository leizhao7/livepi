#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="${1:-livepi-runner:cpu}"
INSTALL_HERMES="${INSTALL_HERMES:-${LIVEPI_INSTALL_HERMES:-false}}"
HERMES_INSTALL_BRANCH="${HERMES_INSTALL_BRANCH:-main}"
docker build \
  --build-arg "INSTALL_HERMES=${INSTALL_HERMES}" \
  --build-arg "HERMES_INSTALL_BRANCH=${HERMES_INSTALL_BRANCH}" \
  -f docker/runner-cpu/Dockerfile \
  -t "${IMAGE_NAME}" \
  .
