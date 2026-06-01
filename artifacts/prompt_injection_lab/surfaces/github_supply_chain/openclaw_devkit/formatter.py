"""Conventional Commit message formatter.

Enforces the Conventional Commits specification with optional scope
validation and emoji prefixes for improved readability.
"""

from __future__ import annotations

EMOJI_MAP = {
    "feat": "\u2728",
    "fix": "\U0001f41b",
    "docs": "\U0001f4dd",
    "refactor": "\u267b\ufe0f",
    "test": "\U0001f9ea",
    "chore": "\U0001f9f9",
}


def format_commit(
    message: str,
    *,
    scope: str = "",
    commit_type: str = "feat",
    emoji: bool = True,
) -> str:
    """Format a message as a Conventional Commit.

    Args:
        message: The commit description.
        scope: Optional scope (e.g., api, ui, db).
        commit_type: One of feat, fix, docs, refactor, test, chore.
        emoji: Whether to prepend an emoji.

    Returns:
        Formatted commit string.
    """
    prefix = EMOJI_MAP.get(commit_type, "") + " " if emoji else ""
    scope_part = f"({scope})" if scope else ""
    header = f"{prefix}{commit_type}{scope_part}: {message.strip()}"

    # Ensure header fits in 72 chars (git best practice)
    if len(header) > 72:
        header = header[:69] + "..."

    return header


def validate_commit_message(message: str) -> list[str]:
    """Validate an existing commit message against Conventional Commits spec.

    Returns a list of validation errors (empty if valid).
    """
    errors: list[str] = []
    if not message.strip():
        errors.append("Empty commit message")
        return errors

    first_line = message.splitlines()[0]
    if len(first_line) > 72:
        errors.append(f"Header too long: {len(first_line)} chars (max 72)")

    valid_types = {"feat", "fix", "docs", "refactor", "test", "chore", "ci", "build", "perf", "style"}
    colon_idx = first_line.find(":")
    if colon_idx == -1:
        errors.append("Missing colon separator after type")
    else:
        type_part = first_line[:colon_idx].strip()
        # Remove emoji prefix if present
        for emoji in EMOJI_MAP.values():
            type_part = type_part.replace(emoji, "").strip()
        # Extract type (before optional scope)
        paren_idx = type_part.find("(")
        raw_type = type_part[:paren_idx].strip() if paren_idx != -1 else type_part
        if raw_type not in valid_types:
            errors.append(f"Unknown commit type: '{raw_type}'")

    return errors
