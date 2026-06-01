# Live Prompt Injection benchmark (LivePI) Dataset Card

## Summary

Live Prompt Injection benchmark (LivePI) is an executable prompt-injection
benchmark for tool-using AI agents. The dataset component consists of
machine-readable benchmark tasks, surface definitions, technique definitions,
objective definitions, synthetic fixture metadata, and scripts that reproduce
the paper case matrix. The paper-aligned matrix contains 169 executable cases
per evaluated model.

## Composition

- Surfaces: WhatsApp Group, Telegram Group, Slack Channel, Email, Local Docs,
  Repo Links, and Gist.
- Techniques: one direct group-message rendering family, ten prompt-level
  injection families, and one code-carried execution family.
- Objectives: Crypto Files, Disable Firewall, Run scan.py, Email Summary, and
  Solana Transfer.
- Synthetic fixtures: a deterministic local user folder manifest and clean,
  secret-free benchmark skills.
- Live credentials: not included. Reproducers must provide their own test
  accounts, provider keys, and bounded test wallet credentials.

## Intended Uses

This dataset is intended for controlled safety evaluation of tool-using agents,
reproduction of the LivePI benchmark matrix, analysis of indirect
prompt-injection behavior across input surfaces, and evaluation of defenses that
mediate prompt input or tool execution.

It is not intended for autonomous attack deployment, unauthorized testing of
third-party systems, training agents to perform harmful actions, or evaluation
outside environments where the operator owns the accounts, credentials, and
infrastructure being tested.

## License

LivePI is licensed under Creative Commons Attribution 4.0 International
(CC BY 4.0).

## Data Sources And Generation

The benchmark is synthetic and author-generated. Prompt-level techniques were
selected from an internal pilot catalog and rendered through deterministic
templates. The synthetic user profile is generated with a fixed seed documented
in `prompt_injection_lab/fixtures/synthetic_user_profile_manifest.json`.
Live-channel artifacts such as emails, chat posts, Gists, and repository payloads
are created at evaluation time by the runner scripts.

## Personal Or Sensitive Information

The released package does not include real personal data, real private keys,
model API keys, account passwords, OAuth tokens, message histories, or benchmark
results from live accounts. It includes synthetic user-profile metadata and
placeholder task text that may refer to sensitive categories such as email,
wallet material, firewall settings, and local documents.

When running the benchmark, users must use test accounts, test balances, and
isolated infrastructure. Generated run logs may contain tool outputs from the
operator's environment and should be reviewed before sharing.

## Known Limitations And Biases

The benchmark intentionally focuses on a small set of high-risk surfaces and
five malicious objectives. It is not a complete taxonomy of agent harms, user
populations, languages, enterprise environments, or operating systems. The
technique set reflects author-selected prompt-injection families and may
overrepresent English-language, security-oriented, and tool-oriented attacks.

Results should not be interpreted as general robustness claims for all agents or
models. The benchmark measures behavior under the provided OpenClaw-style
runtime, task prompts, live-channel setup, and verifier assumptions.

## Social Impact

The positive use case is reproducible evaluation of agent safety and defense
mechanisms before deployment in live user environments. The main risk is dual
use: the same benchmark patterns could inform misuse if applied outside a
controlled test environment. The release mitigates this by excluding real
credentials, requiring user-provided test accounts, documenting safe setup
practices, and keeping operational details environment-scoped.

## Maintenance

The benchmark matrix is versioned in
`prompt_injection_lab/taxonomy/benchmark_case_matrix.json`. For dataset
submission, update `CITATION.cff`, the Dataverse DOI, and the Croissant metadata
after publishing or enabling the Dataverse private preview URL.
