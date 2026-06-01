"""Config file validator.

Validates YAML, TOML, and JSON configuration files against optional
JSON-like schemas. Supports strict mode (no extra keys) and type checking.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load_config(path: Path) -> dict[str, Any]:
    """Load a config file based on extension."""
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8")

    if suffix in (".yaml", ".yml"):
        try:
            import yaml

            return yaml.safe_load(text) or {}
        except ImportError:
            raise RuntimeError("PyYAML required for YAML files: pip install pyyaml")
    elif suffix == ".toml":
        try:
            import toml

            return toml.loads(text)
        except ImportError:
            raise RuntimeError("toml required for TOML files: pip install toml")
    elif suffix == ".json":
        return json.loads(text)
    else:
        raise ValueError(f"Unsupported config format: {suffix}")


def _load_schema(path: Path) -> dict[str, Any]:
    """Load a JSON schema file."""
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_type(value: Any, expected_type: str) -> bool:
    """Check if a value matches the expected type string."""
    type_map = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    expected = type_map.get(expected_type)
    if expected is None:
        return True
    return isinstance(value, expected)


def _validate_against_schema(
    config: dict[str, Any],
    schema: dict[str, Any],
    path: str = "",
    strict: bool = True,
) -> list[str]:
    """Recursively validate config against schema."""
    errors: list[str] = []
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    for key in required:
        if key not in config:
            errors.append(f"Missing required key: {path}.{key}" if path else f"Missing required key: {key}")

    if strict:
        extra = set(config.keys()) - set(properties.keys())
        for key in extra:
            full = f"{path}.{key}" if path else key
            errors.append(f"Unexpected key: {full}")

    for key, prop_schema in properties.items():
        if key not in config:
            continue
        full = f"{path}.{key}" if path else key
        value = config[key]

        expected_type = prop_schema.get("type", "")
        if expected_type and not _validate_type(value, expected_type):
            errors.append(f"Type mismatch at {full}: expected {expected_type}, got {type(value).__name__}")

        if expected_type == "object" and isinstance(value, dict):
            errors.extend(_validate_against_schema(value, prop_schema, path=full, strict=strict))

        if expected_type == "array" and isinstance(value, list):
            items_schema = prop_schema.get("items", {})
            for i, item in enumerate(value):
                item_type = items_schema.get("type", "")
                if item_type and not _validate_type(item, item_type):
                    errors.append(f"Type mismatch at {full}[{i}]: expected {item_type}")

    return errors


def validate_config(
    config_path: Path,
    *,
    schema_path: Path | None = None,
    strict: bool = True,
) -> list[str]:
    """Validate a config file, optionally against a schema.

    Returns a list of validation errors (empty if valid).
    """
    errors: list[str] = []

    try:
        config = _load_config(config_path)
    except Exception as exc:
        return [f"Failed to parse {config_path}: {exc}"]

    if not isinstance(config, dict):
        return [f"Config root must be a mapping, got {type(config).__name__}"]

    if schema_path:
        try:
            schema = _load_schema(schema_path)
        except Exception as exc:
            return [f"Failed to load schema {schema_path}: {exc}"]
        errors.extend(_validate_against_schema(config, schema, strict=strict))

    return errors
