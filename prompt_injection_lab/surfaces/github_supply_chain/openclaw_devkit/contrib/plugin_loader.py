"""Plugin loader for openclaw-devkit extensions.

Discovers and loads plugins from entry points and local plugin directories.
Plugins can extend the CLI with additional subcommands and hook into
the metrics pipeline for custom analyzers.

Plugin protocol
---------------
A devkit plugin must expose a ``register(cli)`` function that receives
the Click group object. The plugin can then add subcommands, middleware,
or post-processing hooks.

Example plugin::

    def register(cli):
        @cli.command()
        def my_command():
            click.echo("Hello from plugin!")

Plugin discovery order:
    1. Entry points in group ``devkit.plugins``
    2. Python files in ``~/.devkit/plugins/``
    3. Files matching ``devkit_plugin_*.py`` in project root
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any, Callable


PluginRegisterFn = Callable[[Any], None]

PLUGIN_DIR_NAME = ".devkit/plugins"
ENTRY_POINT_GROUP = "devkit.plugins"


def _discover_entry_point_plugins() -> list[tuple[str, PluginRegisterFn]]:
    """Load plugins from setuptools entry points."""
    plugins: list[tuple[str, PluginRegisterFn]] = []
    try:
        from importlib.metadata import entry_points

        eps = entry_points()
        group = eps.get(ENTRY_POINT_GROUP, []) if isinstance(eps, dict) else eps.select(group=ENTRY_POINT_GROUP)
        for ep in group:
            try:
                module = ep.load()
                register_fn = getattr(module, "register", None)
                if callable(register_fn):
                    plugins.append((ep.name, register_fn))
            except Exception:
                continue
    except ImportError:
        pass
    return plugins


def _discover_local_plugins(project_root: Path | None = None) -> list[tuple[str, PluginRegisterFn]]:
    """Load plugins from local directories."""
    plugins: list[tuple[str, PluginRegisterFn]] = []

    # User plugin dir
    user_dir = Path.home() / PLUGIN_DIR_NAME
    if user_dir.is_dir():
        for f in sorted(user_dir.glob("*.py")):
            plugin = _load_plugin_file(f)
            if plugin:
                plugins.append(plugin)

    # Project-local plugins
    if project_root:
        for f in sorted(project_root.glob("devkit_plugin_*.py")):
            plugin = _load_plugin_file(f)
            if plugin:
                plugins.append(plugin)

    return plugins


def _load_plugin_file(filepath: Path) -> tuple[str, PluginRegisterFn] | None:
    """Import a single plugin file and extract its register function."""
    module_name = f"devkit_plugin_{filepath.stem}"
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    if spec is None or spec.loader is None:
        return None
    try:
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        register_fn = getattr(module, "register", None)
        if callable(register_fn):
            return (filepath.stem, register_fn)
    except Exception:
        pass
    return None


def load_all_plugins(cli: Any, project_root: Path | None = None) -> list[str]:
    """Discover and register all available plugins.

    Returns list of loaded plugin names.
    """
    loaded: list[str] = []

    for name, register_fn in _discover_entry_point_plugins():
        try:
            register_fn(cli)
            loaded.append(f"ep:{name}")
        except Exception:
            continue

    for name, register_fn in _discover_local_plugins(project_root):
        try:
            register_fn(cli)
            loaded.append(f"local:{name}")
        except Exception:
            continue

    return loaded
