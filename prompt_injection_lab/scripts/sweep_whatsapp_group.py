#!/usr/bin/env python3
"""Sweep the paper WhatsApp group surface.

Runs only direct_group_message_instruction across the 5 benchmark objectives.
"""

from __future__ import annotations

from sweep_group_chat_common import main


if __name__ == "__main__":
    raise SystemExit(main("whatsapp_group"))
