"""Code complexity analysis using Python's AST module.

Computes cyclomatic complexity, lines of code, and a basic
maintainability index for each function/method in a module.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any


def _cyclomatic_complexity(node: ast.AST) -> int:
    """Count decision points in an AST node to estimate cyclomatic complexity."""
    complexity = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            complexity += len(child.values) - 1
        elif isinstance(child, ast.Assert):
            complexity += 1
    return complexity


def _count_lines(source: str) -> int:
    """Count non-blank, non-comment lines."""
    count = 0
    for line in source.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            count += 1
    return count


def _maintainability_index(complexity: int, loc: int) -> float:
    """Simplified maintainability index (0-100 scale)."""
    import math

    if loc == 0:
        return 100.0
    volume = loc * math.log2(max(1, loc))
    mi = max(0.0, (171 - 5.2 * math.log(volume) - 0.23 * complexity - 16.2 * math.log(max(1, loc))) * 100 / 171)
    return round(mi, 1)


def analyze_function(node: ast.FunctionDef | ast.AsyncFunctionDef, source: str) -> dict[str, Any]:
    """Analyze a single function/method."""
    start = node.lineno
    end = node.end_lineno or start
    func_source = "\n".join(source.splitlines()[start - 1 : end])
    loc = _count_lines(func_source)
    cc = _cyclomatic_complexity(node)
    mi = _maintainability_index(cc, loc)
    return {
        "function": node.name,
        "line": start,
        "complexity": cc,
        "loc": loc,
        "maintainability": mi,
    }


def analyze_module(filepath: Path, threshold: int = 10) -> list[dict[str, Any]]:
    """Analyze all functions in a Python module."""
    source = filepath.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return [{"file": str(filepath), "function": "<parse-error>", "complexity": -1, "loc": 0, "maintainability": 0}]

    results = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            info = analyze_function(node, source)
            info["file"] = str(filepath)
            if info["complexity"] >= threshold:
                info["warning"] = True
            results.append(info)
    return results


def analyze_path(path: Path, threshold: int = 10) -> list[dict[str, Any]]:
    """Analyze all Python files under a path."""
    results: list[dict[str, Any]] = []
    if path.is_file() and path.suffix == ".py":
        results.extend(analyze_module(path, threshold))
    elif path.is_dir():
        for root, _dirs, files in os.walk(path):
            for f in sorted(files):
                if f.endswith(".py"):
                    results.extend(analyze_module(Path(root) / f, threshold))
    return results
