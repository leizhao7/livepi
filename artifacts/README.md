# livepi (Python package)

A pip-installable, **self-contained** distribution of the LivePI benchmark
([arXiv:2605.17986](https://arxiv.org/abs/2605.17986)).

Two things in one package:

1. **Read API** — curated paper results as JSON, JBB-style.
2. **Runner** — bootstrap a workspace + run new evaluations end-to-end via
   the same Docker harness that the standalone `git clone` workflow uses.

## Install

```bash
pip install "git+https://github.com/leizhao7/livepi.git#subdirectory=artifacts"
```

Optional runner-only extras (Slack/Reddit/X/Telegram surface clients):

```bash
pip install "livepi[runner] @ git+https://github.com/leizhao7/livepi.git#subdirectory=artifacts"
```

## Read curated paper results

```python
import livepi

livepi.list_artifacts()
# [{'agent': 'codex', 'model': 'openai/gpt-5.3-codex',
#   'total_cases': 13, 'hard_attack_success_rate': 0.3077, ...}, ...]

art = livepi.read_artifact(agent="openclaw", model="anthropic/claude-opus-4.6")
print(art["parameters"]["hard_attack_success_rate"])
for case in art["cases"]:
    print(case["surface"], case["objective"], case["hard_attack_success"])
```

CLI equivalents:

```bash
livepi list-artifacts
livepi read-artifact --agent openclaw --model anthropic/claude-opus-4.6 --summary
```

## Run new evaluations

`livepi bootstrap` copies a workspace skeleton (a writable
`prompt_injection_lab/` tree + `secrets.example.env`) into your CWD, then runs
the setup script. Edit `secrets.env`, re-run with `--apply`, build the Docker
image once, then run cases.

```bash
mkdir ~/livepi-work && cd ~/livepi-work
livepi bootstrap              # dry-run: prints what setup *would* do
# edit ./secrets.env
livepi bootstrap --apply      # writes prompt_injection_lab/.env, configures openclaw, ...
livepi build-image            # docker build livepi-runner:cpu

# one case
livepi run \
  --agent codex \
  --base-model openai/gpt-5.3-codex \
  --surface direct_chat_txt \
  --technique checklist_handoff_injection \
  --objective email_summary_to_external

# fixed surface, all techniques x all objectives
livepi sweep --agent codex --base-model openai/gpt-5.3-codex \
  --fixed-surface direct_chat_txt

# tabulate
livepi aggregate --format markdown
```

Same flow from Python:

```python
import livepi

livepi.bootstrap(workdir="~/livepi-work", apply=True)
livepi.build_image()

out = livepi.run_case(
    agent="codex",
    base_model="openai/gpt-5.3-codex",
    surface="direct_chat_txt",
    technique="checklist_handoff_injection",
    objective="email_summary_to_external",
    workdir="~/livepi-work",
)
print(out["summary"]["status"], out["summary"]["hard"]["attack_success"])

print(livepi.aggregate(workdir="~/livepi-work", output_format="markdown"))
```

## What's inside the wheel

```
livepi/
  api.py            # read_artifact / list_artifacts / iter_artifacts
  harness.py        # run_case / run_sweep / bootstrap / aggregate (subprocess wrappers)
  cli.py            # `livepi` console script
  paths.py          # resolves package + workspace paths
  data/
    artifacts/      # curated JSON results, one per (agent, model)
    scripts/        # vendored run_in_docker.sh, setup_openclaw_benchmark_env.py, ...
    docker/         # vendored Dockerfile for the runner image
    secrets.example.env
prompt_injection_lab/  # full surface / technique / verifier source tree
```

Runtime dependencies are minimal (`requests`, `PyYAML`). The `runner` extra
pulls in surface-specific clients only when you actually run live cases.

## Why a separate package?

The top-level repo layout (designed for `git clone`) keeps the CI scripts, the
clean Dockerfile context, and other publishing assets at the repo root. The
`artifacts/` subdirectory mirrors that into a `pip install`-friendly tree so
that downstream papers, leaderboards, and defense-training pipelines can pull
LivePI in with one command — without forking the repo.

## Citation

```bibtex
@article{zhao2026livepi,
  title  = {LivePI: A Live Indirect Prompt Injection Benchmark for Real-World Agent Harnesses},
  author = {Zhao, Lei and Bhaskar, Abhay and Dobriban, Edgar},
  journal= {arXiv preprint arXiv:2605.17986},
  year   = {2026}
}
```

## License

MIT. Curated artifacts are released for benchmark + research use under the
same license.
