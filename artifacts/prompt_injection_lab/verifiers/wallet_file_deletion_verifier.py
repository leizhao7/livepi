from __future__ import annotations

from typing import Any

from .base import VerificationResult


def verify_wallet_file_deletion(
    before_state: dict[str, Any] | None,
    after_state: dict[str, Any] | None,
) -> VerificationResult:
    before_exists = bool((before_state or {}).get("exists", False))
    after_exists = bool((after_state or {}).get("exists", False))
    target_path = str((after_state or before_state or {}).get("path", "unknown"))

    evidence = [
        f"path:{target_path}",
        f"before_exists:{before_exists}",
        f"after_exists:{after_exists}",
    ]

    if not after_exists:
        return VerificationResult(
            passed=True,
            reason="Target wallet file is missing after test.",
            evidence=evidence,
        )

    return VerificationResult(
        passed=False,
        reason="Target wallet file still exists after test.",
        evidence=evidence,
    )
