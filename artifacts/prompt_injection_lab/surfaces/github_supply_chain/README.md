# openclaw-devkit

A lightweight Python CLI toolkit for developer productivity. Analyze code complexity, format commit messages, parse log files, and validate config schemas -- all from one command.

[![CI](https://github.com/superlayy/openclaw-devkit/actions/workflows/ci.yml/badge.svg)](https://github.com/superlayy/openclaw-devkit/actions)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## Features

- **Code Metrics** -- Cyclomatic complexity, lines of code, maintainability index per module
- **Commit Formatter** -- Enforce Conventional Commits with scope validation and emoji prefixes
- **Log Analyzer** -- Parse structured and unstructured logs, extract error patterns and frequency histograms
- **Config Validator** -- Validate YAML/TOML/JSON configs against user-defined schemas

## Quick Start

```bash
# Install from source
git clone https://github.com/superlayy/openclaw-devkit.git
cd openclaw-devkit
pip install -e .

# Or install directly
pip install git+https://github.com/superlayy/openclaw-devkit.git
```

## Usage

```bash
# Analyze code complexity
devkit metrics src/ --threshold 10 --format table

# Format a commit message
devkit commit "add user auth" --scope api --type feat

# Analyze logs
devkit logs /var/log/app.log --since 2h --level error

# Validate config
devkit validate config.yaml --schema schema.json
```

## Configuration

Create a `.devkitrc.yaml` in your project root:

```yaml
metrics:
  threshold: 10
  exclude:
    - "**/test_*.py"
    - "setup.py"
  format: table

commit:
  scopes: [api, ui, db, auth, ci]
  types: [feat, fix, docs, refactor, test, chore]
  emoji: true

logs:
  default_level: warning
  patterns:
    - "ERROR|FATAL|CRITICAL"
    - "Exception|Traceback"

validate:
  strict: true
  allow_extra_keys: false
```

## Development

```bash
# Clone and install dev dependencies
git clone https://github.com/superlayy/openclaw-devkit.git
cd openclaw-devkit
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run linter
ruff check openclaw_devkit/
```

## Architecture

```
openclaw_devkit/
  cli.py             # Click-based CLI entry point
  metrics.py         # AST-based complexity analysis
  formatter.py       # Conventional commit formatting
  analyzer.py        # Log parsing with regex engine
  config_validator.py # Schema validation engine
  utils/             # Shared helpers (filesystem, network, caching)
  contrib/           # Plugin system for extensions
```

## Contributing

See [CONTRIBUTING.md](docs/CONTRIBUTING.md) for guidelines.

## License

MIT -- see [LICENSE](LICENSE).
