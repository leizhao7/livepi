#!/usr/bin/env bash
set -euo pipefail

IMAGE="${IMAGE:-livepi-runner:cpu}"
NETWORK="${LIVEPI_DOCKER_NETWORK:-host}"

docker run --rm \
  --network "${NETWORK}" \
  -v "${PWD}:/workspace" \
  -w /workspace \
  "${IMAGE}" \
  bash -lc '
    set -euo pipefail
    python3 prompt_injection_lab/scripts/audit_techniques.py &&
    python3 prompt_injection_lab/scripts/audit_benchmark_matrix.py &&
    python3 prompt_injection_lab/scripts/validate_tasks.py &&
    python3 prompt_injection_lab/scripts/generate_prompt.py --list-tags

    rm -rf /tmp/livepi-docker-smoke-results /tmp/livepi-docker-smoke-runtime
    common_args=(
      --surface-tag direct_chat_txt
      --technique-tag checklist_handoff_injection
      --malicious-task-tag email_summary_to_external
      --chat-timeout-s 15
      --results-root /tmp/livepi-docker-smoke-results
      --env-file /dev/null
    )

    LIVEPI_AGENT_RUNTIME_ROOT=/tmp/livepi-docker-smoke-runtime \
      HERMES_COMMAND=/bin/echo HERMES_REQUIRE_API_KEY=false \
      HERMES_CLI_ARGS="" HERMES_QUERY_FLAG=-q HERMES_APPEND_QUERY_FLAG=true \
      python3 prompt_injection_lab/scripts/run_surface_test.py \
        --agent hermes --base-model smoke-hermes "${common_args[@]}" >/tmp/livepi-hermes-smoke.json

    LIVEPI_AGENT_RUNTIME_ROOT=/tmp/livepi-docker-smoke-runtime \
      CODEX_COMMAND=/bin/echo CODEX_REQUIRE_API_KEY=false \
      CODEX_CLI_ARGS="exec --skip-git-repo-check --ephemeral" CODEX_APPEND_QUERY_FLAG=true \
      python3 prompt_injection_lab/scripts/run_surface_test.py \
        --agent codex --base-model smoke-codex "${common_args[@]}" >/tmp/livepi-codex-smoke.json

    LIVEPI_AGENT_RUNTIME_ROOT=/tmp/livepi-docker-smoke-runtime \
      CLAUDE_CODE_COMMAND=/bin/echo CLAUDE_CODE_REQUIRE_API_KEY=false \
      CLAUDE_CODE_CLI_ARGS="--bare --no-session-persistence" CLAUDE_CODE_QUERY_FLAG=-p \
      CLAUDE_CODE_APPEND_QUERY_FLAG=true \
      python3 prompt_injection_lab/scripts/run_surface_test.py \
        --agent claude_code --base-model smoke-claude-code "${common_args[@]}" >/tmp/livepi-claude-code-smoke.json

    python3 - <<PY
import json
from pathlib import Path

for name in ("hermes", "codex", "claude-code"):
    path = Path(f"/tmp/livepi-{name}-smoke.json")
    data = json.loads(path.read_text())
    assert data["status"] == "ok", data
    runtime = data["steps"]["cli_agent_runtime"]
    assert runtime["openclaw_gateway_used"] is False, runtime
    assert runtime.get("model", "").startswith("smoke-"), runtime
print("CLI adapter smoke checks passed.")
PY
  '
