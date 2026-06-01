# LivePI: Live Prompt Injection Benchmark

<p align="center">
  <a href="https://arxiv.org/abs/2605.17986"><img src="https://img.shields.io/badge/arXiv-2605.17986-b31b1b.svg" alt="arXiv"></a>
  <a href="https://leizhao7.github.io/livepi/"><img src="https://img.shields.io/badge/Project-Page-blue.svg" alt="Project page"></a>
  <a href="https://github.com/leizhao7/livepi"><img src="https://img.shields.io/badge/GitHub-livepi-181717.svg?logo=github" alt="GitHub"></a>
  <a href="https://github.com/leizhao7/livepi/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License"></a>
</p>

<p align="center">
  📖 <a href="#-overview">Overview</a> ·
  🛠 <a href="#-getting-started">Getting Started</a> ·
  📨 <a href="#-contact">Contact</a> ·
  🎈 <a href="#-citation">Citation</a>
</p>

---

## 📖 Overview

<p align="center">
  <img src="https://raw.githubusercontent.com/leizhao7/livepi/gh-pages/assets/img/overview.png" alt="LivePI overview" width="850">
</p>

LivePI is the official reproducibility artifact for the paper:

> **LivePI: More Realistic Benchmarking of Agents Against Indirect Prompt Injection**  
> Lei Zhao, Abhay Bhaskar, Edgar Dobriban — University of Pennsylvania, 2026.  
> [📄 arXiv:2605.17986](https://arxiv.org/abs/2605.17986) · [🌐 Project page](https://leizhao7.github.io/livepi/)

Existing prompt-injection benchmarks rely on simulated mailboxes, mock chat
rooms, and fake wallets. **LivePI tests against 100% real services**: real
Gmail, real Slack, real Telegram & WhatsApp groups, real Solana crypto wallet,
real GitHub repository, ... — nothing is mocked.

The benchmark spans **7 input surfaces × 12 attack-rendering families × 5
malicious goals = 169 executable cases per model**, and supports many agent
harnesses out-of-the-box — including **OpenClaw**, **Hermes** (Nous Research),
**Codex CLI** (OpenAI), and **Claude Code** (Anthropic) — each drivable by
any OpenRouter-routed model via `--base-model <id>`. Paper Table 4 reports
the per-model attack-success-rate matrix.

## 🛠 Getting Started

### System requirements

- Ubuntu 24.04+ (Ubuntu 22.04 also verified)
- Docker (with the daemon running)
- Python 3.10+
- SSH key for the host (only when targeting a remote VPS via `--host user@vps`)

### Run

```bash
# 1. Clone
git clone https://github.com/leizhao7/livepi.git
cd livepi

# 2. Fill in your credentials (OpenRouter / Anthropic / SMTP / Slack token / ...)
cp secrets.example.env secrets.env
$EDITOR secrets.env

# 3. One-shot setup (installs OpenClaw, builds the docker runner image,
#    bootstraps the GitHub supply-chain repo, seeds the synthetic user folder,
#    writes prompt_injection_lab/.env, ...).
#    Default target is local; pass --host user@vps to target a remote VPS.
python3 setup_openclaw_benchmark_env.py --apply

# 4. Run a single benchmark case
bash scripts/run_in_docker.sh \
  --agent openclaw \
  --base-model anthropic/claude-opus-4.6 \
  --surface-tag direct_chat_txt \
  --technique-tag checklist_handoff_injection \
  --malicious-task-tag email_summary_to_external

# 5. Run a paper-aligned sweep (fixed surface × all objectives, or vice versa)
python3 prompt_injection_lab/scripts/benchmark_matrix.py run-plan \
  --docker --agent openclaw --base-model anthropic/claude-opus-4.6 \
  --fixed-surface direct_chat_txt --selection first \
  --env-file secrets.env --execute

# 6. Aggregate results + ASR
python3 scripts/aggregate_results.py
```

## 📨 Contact

- **Lei Zhao** — [leizhao7@wharton.upenn.edu](mailto:leizhao7@wharton.upenn.edu)
- **Edgar Dobriban** — [dobriban@wharton.upenn.edu](mailto:dobriban@wharton.upenn.edu)

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
