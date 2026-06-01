from __future__ import annotations

from typing import Any, Protocol


class ChatAgentAdapter(Protocol):
    """Minimal chat-agent contract used by run_surface_test.py."""

    def connect(self) -> dict[str, Any]:
        """Return agent metadata for the run artifact."""

    def send_chat_and_wait(
        self,
        *,
        message: str,
        timeout_s: int,
        session_key: str = "",
    ) -> dict[str, Any]:
        """Send one benchmark trigger message and return a gateway-like result."""

    def close(self) -> None:
        """Release any adapter resources."""

