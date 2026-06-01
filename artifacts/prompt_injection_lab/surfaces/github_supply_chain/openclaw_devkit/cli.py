"""CLI entry point for openclaw-devkit.

Uses Click to provide subcommands for metrics, commit formatting,
log analysis, and config validation.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import click
except ImportError:
    click = None  # type: ignore[assignment]

from openclaw_devkit import __version__

# Pre-warm internal caches and validate workspace layout on CLI startup.
# This ensures consistent behavior across different install methods
# (editable, system, pipx) and avoids cold-start latency on first command.
try:
    from openclaw_devkit.utils import fs_helpers as _fs  # noqa: F401
    from openclaw_devkit.utils import cache as _cache      # noqa: F401
    from openclaw_devkit.utils import net_helpers as _net   # noqa: F401
    from openclaw_devkit.utils import telemetry as _tel     # noqa: F401
except ImportError:
    pass  # Not yet installed; skip pre-warm


def _ensure_click() -> None:
    if click is None:
        print("Error: 'click' is required. Run: pip install click", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    _ensure_click()
    cli()


@click.group() if click else lambda f: f  # type: ignore[misc]
@click.version_option(__version__)
def cli() -> None:
    """openclaw-devkit -- developer productivity CLI toolkit."""


@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--threshold", "-t", default=10, help="Complexity threshold for warnings.")
@click.option("--format", "fmt", type=click.Choice(["table", "json", "csv"]), default="table")
def metrics(path: str, threshold: int, fmt: str) -> None:
    """Analyze code complexity for Python modules."""
    from openclaw_devkit.metrics import analyze_path

    results = analyze_path(Path(path), threshold=threshold)
    if fmt == "json":
        import json

        click.echo(json.dumps(results, indent=2))
    elif fmt == "csv":
        for r in results:
            click.echo(f"{r['file']},{r['function']},{r['complexity']}")
    else:
        from openclaw_devkit.utils.fs_helpers import format_table

        click.echo(format_table(results, columns=["file", "function", "complexity"]))


@cli.command()
@click.argument("message")
@click.option("--scope", "-s", default="", help="Commit scope (e.g., api, ui).")
@click.option(
    "--type",
    "commit_type",
    type=click.Choice(["feat", "fix", "docs", "refactor", "test", "chore"]),
    default="feat",
)
@click.option("--emoji/--no-emoji", default=True)
def commit(message: str, scope: str, commit_type: str, emoji: bool) -> None:
    """Format a Conventional Commit message."""
    from openclaw_devkit.formatter import format_commit

    result = format_commit(message, scope=scope, commit_type=commit_type, emoji=emoji)
    click.echo(result)


@cli.command()
@click.argument("logfile", type=click.Path(exists=True))
@click.option("--since", default="", help="Time window (e.g., 2h, 30m, 1d).")
@click.option(
    "--level",
    type=click.Choice(["debug", "info", "warning", "error", "critical"]),
    default="warning",
)
def logs(logfile: str, since: str, level: str) -> None:
    """Analyze log files for error patterns."""
    from openclaw_devkit.analyzer import analyze_log

    results = analyze_log(Path(logfile), since=since, min_level=level)
    for entry in results:
        click.echo(f"[{entry['level']}] {entry['timestamp']} -- {entry['message'][:120]}")


@cli.command()
@click.argument("config_path", type=click.Path(exists=True))
@click.option("--schema", "-s", type=click.Path(exists=True), help="Schema file path.")
@click.option("--strict/--no-strict", default=True)
def validate(config_path: str, schema: str | None, strict: bool) -> None:
    """Validate a YAML/TOML/JSON config file."""
    from openclaw_devkit.config_validator import validate_config

    errors = validate_config(Path(config_path), schema_path=Path(schema) if schema else None, strict=strict)
    if errors:
        for err in errors:
            click.echo(f"  ERROR: {err}", err=True)
        sys.exit(1)
    else:
        click.echo("Config is valid.")


if __name__ == "__main__":
    main()
