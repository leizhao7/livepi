"""Verifier modules for prompt-injection tasks."""

from .base import VerificationResult
from .email_gmail_verifier import verify as verify_email_gmail
from .shared_docs_verifier import verify as verify_shared_docs
from .system_hardening_verifier import verify_state_drift
from .telegram_group_verifier import verify as verify_telegram_group
from .wallet_file_deletion_verifier import verify_wallet_file_deletion
from .web_link_verifier import verify as verify_web_link
from .x_post_verifier import verify as verify_x_post

__all__ = [
    "VerificationResult",
    "verify_email_gmail",
    "verify_shared_docs",
    "verify_state_drift",
    "verify_telegram_group",
    "verify_wallet_file_deletion",
    "verify_web_link",
    "verify_x_post",
]
