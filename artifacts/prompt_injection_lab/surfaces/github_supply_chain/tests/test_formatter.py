"""Tests for the commit formatter module."""

from openclaw_devkit.formatter import format_commit, validate_commit_message


def test_basic_format():
    result = format_commit("add login", commit_type="feat")
    assert "feat" in result
    assert "add login" in result


def test_format_with_scope():
    result = format_commit("fix timeout", scope="api", commit_type="fix")
    assert "fix(api)" in result
    assert "fix timeout" in result


def test_emoji_prefix():
    result = format_commit("update docs", commit_type="docs", emoji=True)
    assert result.startswith("\U0001f4dd") or "\U0001f4dd" in result


def test_no_emoji():
    result = format_commit("cleanup", commit_type="chore", emoji=False)
    assert result.startswith("chore")


def test_truncation():
    long_msg = "a" * 100
    result = format_commit(long_msg, commit_type="feat")
    assert len(result) <= 72


def test_validate_good_message():
    errors = validate_commit_message("feat(api): add user endpoint")
    assert errors == []


def test_validate_missing_colon():
    errors = validate_commit_message("feat add something")
    assert any("colon" in e.lower() for e in errors)


def test_validate_unknown_type():
    errors = validate_commit_message("yolo: do something")
    assert any("unknown" in e.lower() for e in errors)
