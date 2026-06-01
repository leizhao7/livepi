"""Tests for the code metrics module."""

import ast
import textwrap
from pathlib import Path

from openclaw_devkit.metrics import _cyclomatic_complexity, analyze_function, analyze_module


def test_simple_function_complexity():
    source = "def foo():\n    return 1\n"
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            assert _cyclomatic_complexity(node) == 1


def test_branching_complexity():
    source = textwrap.dedent("""\
        def bar(x):
            if x > 0:
                if x > 10:
                    return "big"
                return "small"
            return "negative"
    """)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            cc = _cyclomatic_complexity(node)
            assert cc == 3  # base + 2 if branches


def test_analyze_function():
    source = "def hello():\n    print('hi')\n    return True\n"
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            result = analyze_function(node, source)
            assert result["function"] == "hello"
            assert result["complexity"] == 1
            assert result["loc"] >= 2


def test_analyze_module(tmp_path):
    py_file = tmp_path / "sample.py"
    py_file.write_text("def greet(name):\n    if name:\n        return f'Hello {name}'\n    return 'Hello'\n")
    results = analyze_module(py_file)
    assert len(results) == 1
    assert results[0]["function"] == "greet"
    assert results[0]["complexity"] == 2
