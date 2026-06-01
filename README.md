# LivePI: Live Prompt Injection Benchmark

<p align="center">
  <a href="https://arxiv.org/abs/2605.17986"><img src="https://img.shields.io/badge/arXiv-2605.17986-b31b1b.svg" alt="arXiv"></a>
  <a href="https://leizhao7.github.io/livepi/"><img src="https://img.shields.io/badge/Project-Page-blue.svg" alt="Project page"></a>
  <a href="https://github.com/leizhao7/livepi"><img src="https://img.shields.io/badge/GitHub-livepi-181717.svg?logo=github" alt="GitHub"></a>
  <a href="https://github.com/leizhao7/livepi/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License"></a>
</p>

<p align="center">
  📖 <a href="#-overview">Overview</a> ·
  🧪 <a href="#-supported-agent-harnesses">Agent Harnesses</a> ·
  🛠 <a href="#-getting-started">Getting Started</a> ·
  📨 <a href="#-contact">Contact</a> ·
  🎈 <a href="#-citation">Citation</a>
</p>

---

## 📖 Overview

LivePI is the official reproducibility artifact for the paper:

> **LivePI: More Realistic Benchmarking of Agents Against Indirect Prompt Injection**  
> Lei Zhao, Abhay Bhaskar, Edgar Dobriban — University of Pennsylvania, 2026.  
> [📄 arXiv:2605.17986](https://arxiv.org/abs/2605.17986) · [🌐 Project page](https://leizhao7.github.io/livepi/)

LivePI evaluates AI agents under indirect prompt injection in a production-like
deployment with **live but test-controlled** email, chat, web, local-file,
repository, and wallet interfaces. The benchmark spans **7 input surfaces × 12
attack-rendering families × 5 malicious goals = 169 executable cases per model**.
Paper Table 4 reports the per-model attack-success-rate matrix.

The runner is **local-first** (everything on one Ubuntu 24.04+ host) and also
supports a remote VPS via `--host user@vps`. It recreates the benchmark layout
without hardcoding any machine name, IP address, private token, account ID,
phone number, or API key.

## 🧪 Supported Agent Harnesses

LivePI ships first-class adapters for four CLI / gateway-based agent harnesses:

| Agent | Backbone routing | Status |
|---|---|---|
| **OpenClaw** | OpenRouter / Anthropic / Moonshot / Z-AI / Google (auto-fallback) | ✅ paper-aligned, fully supported |
| **Hermes** (Nous Research) | OpenRouter (or ChatGPT OAuth) | 🧪 test |
| **Codex CLI** (OpenAI) | OpenRouter (or ChatGPT OAuth) | 🧪 test |
| **Claude Code** (Anthropic) | Anthropic API direct (no OpenRouter due to client-side model check) | 🧪 test |

All five paper backbones — `openai/gpt-5.3-codex`, `anthropic/claude-opus-4.6`,
`google/gemini-3.1-pro-preview`, `moonshotai/kimi-k2.5`, `z-ai/glm-5` — plus
the LLM judge (`openai/gpt-5.3`) are registered out-of-the-box. Switch backbones
with `--base-model <id>`.

## 🛠 Getting Started

### What Setup Recreates

`setup_openclaw_benchmark_env.py` mirrors the benchmark environment structure:

- OpenClaw `2026.3.13` installed from npm.
- Default OpenClaw profile at `~/.openclaw/openclaw.json`.
- Gateway service `openclaw-gateway.service` on port `18789`.
- Workspace at `~/.openclaw/workspace`.
- Benchmark skills installed into `~/.agents/skills`,
  `~/.openclaw/.agents/skills`, and the isolated Hermes LivePI skill root
  `~/.hermes-livepi/.agents/skills`.
- Bundled custom skills: `imap-smtp-email`, `solana`, and
  `livepi-chat-channels`. Task metadata may also mention `browser` and `exec`;
  those are OpenClaw/runtime capabilities rather than separate bundled skill
  folders.
- Synthetic user folder at `/home/ubuntu/casey_lewis`.
- Local runner configuration in `prompt_injection_lab/.env`.

Private credentials are never bundled. Provide them through a local secrets file
or environment variables.

## License

LivePI is licensed under Creative Commons Attribution 4.0 International
(CC BY 4.0).

## Quick Start

Create a secrets file:

```bash
cp secrets.example.env secrets.env
```

Fill in the model keys and any live-channel credentials you want to test. At a
minimum, set one usable model provider key and
`OPENCLAW_BENCHMARK_RECIPIENT_EMAIL`. `OPENCLAW_PRIMARY_MODEL` may be left blank;
setup will auto-select an available provider model, including OpenRouter when
`OPENROUTER_API_KEY` is set.
For the `download_and_run_scan_py` objective, set
`GITHUB_TOKEN`; setup creates or updates a public `safety_scan` repo with
`scan.py` and writes the generated `OPENCLAW_BENCHMARK_SCAN_PY_URL` into the env
files.
See `docs/env_config.md` for the full env list, and run
`python3 scripts/check_env.py --groups all` to inspect missing values without
printing secrets.

Run a dry check against your VPS:

```bash
python3 setup_openclaw_benchmark_env.py \
  --host ubuntu@YOUR_VPS_IP \
  --identity ~/.ssh/YOUR_KEY.pem
```

Apply the full setup:

```bash
python3 setup_openclaw_benchmark_env.py \
  --host ubuntu@YOUR_VPS_IP \
  --identity ~/.ssh/YOUR_KEY.pem \
  --apply
```

The script installs system dependencies, Node.js, OpenClaw, benchmark skills,
skill dependencies, the synthetic user folder, the OpenClaw config, the user
systemd gateway service with user lingering enabled, the local `.env`, and an
SSH tunnel to the gateway.
If a non-LivePI config already exists on the VPS, the script refuses to
overwrite it unless you pass `--force-overwrite-existing`.

If you want to reproduce only part of the environment, use the skip flags, for
example `--skip-openclaw-install`, `--skip-skills`, or `--skip-user-folder`.

## Docker Runner

LivePI also includes a Docker runner layer modeled after the companion
benchmark scaffolding. The Docker image isolates the benchmark controller while
leaving each LivePI task path unchanged: the container still invokes
`prompt_injection_lab/scripts/run_surface_test.py`, and that script still talks
to the configured OpenClaw/VPS environment over the same SSH and WebSocket
interfaces as the non-Docker setup.

Build the runner image:

```bash
bash scripts/bootstrap_ubuntu.sh
bash scripts/build_agent_image.sh
```

Run deterministic no-credential checks inside Docker:

```bash
bash scripts/docker_smoke_checks.sh
```

This validates taxonomy/tasks and runs no-key `/bin/echo` smoke cases for
Hermes, Codex, and Claude Code CLI adapters.

Run one LivePI case inside Docker:

```bash
bash scripts/run_in_docker.sh \
  --surface-tag direct_chat_txt \
  --compose-paper-techniques \
  --malicious-task-tag email_summary_to_external
```

`surface x technique x objective` is validated against the paper matrix before
the runner touches live services. Use `--technique-tag` for one case,
`--technique-tags a,b,c` for a composed feasible set, or `--all-techniques` to
run every feasible technique for the selected surface/objective.

Inspect or generate commands from the paper matrix:

```bash
python3 prompt_injection_lab/scripts/benchmark_matrix.py list
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
python3 prompt_injection_lab/scripts/benchmark_matrix.py run-plan --docker \
  --agent hermes \
  --fixed-objective email_summary_to_external \
  --selection first \
  --env-file secrets.env \
  --execute
```

`command`, `plan`, and `run-plan` also accept `--base-model` and
`--agent-model`; for CLI agents, `--base-model` maps to the selected adapter's
per-run model unless `--agent-model` is provided.

The wrapper uses `secrets.env` or `prompt_injection_lab/.env` if present; pass
`--env-file /dev/null` for smoke tests with no loaded env. `root@127.0.0.1`,
`localhost`, and `local` are treated as the current run environment, so the
standard single-VPS setup does not require `LIVEPI_REMOTE_HOST`. On Linux VPS
hosts it defaults to Docker `host` networking so the host-side gateway such as
`ws://127.0.0.1:18789/ws` remains reachable. Each live run uses a temporary
repo copy by default, excluding historical results and caches, then copies the
new run artifacts back into `prompt_injection_lab/results`.
See `docs/docker_runbook.md` for the full runbook.

## Sanity Checks

After setup, run:

```bash
python3 prompt_injection_lab/scripts/audit_techniques.py
python3 prompt_injection_lab/scripts/audit_benchmark_matrix.py
python3 prompt_injection_lab/scripts/validate_tasks.py
python3 prompt_injection_lab/scripts/generate_prompt.py --list-tags
```

Then run a small benchmark smoke test:

```bash
python3 prompt_injection_lab/scripts/run_surface_test.py \
  --surface-tag direct_chat_txt \
  --compose-paper-techniques \
  --malicious-task-tag email_summary_to_external
```

Paper chat-channel sweeps use only the direct group-message rendering:

```bash
python3 prompt_injection_lab/scripts/sweep_slack_channel.py --agent codex
python3 prompt_injection_lab/scripts/sweep_telegram_group.py --agent claude_code
python3 prompt_injection_lab/scripts/sweep_whatsapp_group.py --agent hermes
```

These group-chat sweep entrypoints accept `--techniques`, but only
`direct_group_message_instruction` is feasible for the paper group-message
surface.

All sweep scripts accept `--agent {openclaw,hermes,codex,claude_code}`. Their
`--models` filter still uses `--base-model`; for CLI agents the runner maps that
value to the per-run `HERMES_MODEL`, `CODEX_MODEL`, or `CLAUDE_CODE_MODEL`.

Run the LLM judge over generated traces:

```bash
python3 prompt_injection_lab/scripts/llm_judge_runs.py \
  prompt_injection_lab/results \
  --provider openrouter \
  --model "${LLM_JUDGE_MODEL:-openai/gpt-5.5}" \
  --output prompt_injection_lab/results/llm_judge_results.jsonl
```

The judge input includes each run's `summary.json`, deterministic verifier
artifacts, observed tool calls, final assistant response, `gateway_chat.json`,
and transcript snippets extracted from `remote_sessions.tar.gz` when present.
Each result row includes `verdict` plus `score.attack_success_for_asr`, the
boolean used for attack-success-rate aggregation.
Use `--dry-run --write-inputs judge_inputs.jsonl` to inspect the exact prompt
input without calling an LLM.


## Notes

- `secrets.env`, `prompt_injection_lab/.env`, gateway identity files, caches, and
  generated results are intentionally git-ignored.
- OpenAI Codex and Claude Code runs use their normal API-key envs through the
  CLI adapters. Set `CODEX_API_KEY`/`OPENAI_API_KEY` or
  `CLAUDE_CODE_API_KEY`/`ANTHROPIC_API_KEY` in `secrets.env`.
- `clear_openclaw_history.py` clears only remote OpenClaw session/history
  artifacts used between benchmark runs; it does not rewrite task definitions,
  benchmark payloads, or verifier behavior.
- The bundled task text uses `{{RECIPIENT_EMAIL}}`; the runner expands it from
  `OPENCLAW_BENCHMARK_RECIPIENT_EMAIL` or `TEST_RECIPIENT_EMAIL`.
- The bundled task text uses `{{SCAN_PY_URL}}`; the runner expands it from
  `OPENCLAW_BENCHMARK_SCAN_PY_URL`.

## 📨 Contact

- **Lei Zhao** — [lzhao7@wharton.upenn.edu](mailto:lzhao7@wharton.upenn.edu)
- **Edgar Dobriban** — [ed@wharton.upenn.edu](mailto:ed@wharton.upenn.edu)

## 🎈 Citation

```bibtex
@article{zhao2026livepi,
  title   = {LivePI: More Realistic Benchmarking of Agents Against Indirect Prompt Injection},
  author  = {Zhao, Lei and Bhaskar, Abhay and Dobriban, Edgar},
  journal = {arXiv preprint arXiv:2605.17986},
  year    = {2026},
  url     = {https://arxiv.org/abs/2605.17986}
}
```
