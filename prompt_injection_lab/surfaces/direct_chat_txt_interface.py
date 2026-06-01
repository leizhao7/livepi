from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DirectChatTxtSeedResult:
    path: str
    bytes_written: int
    sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "bytes_written": self.bytes_written,
            "sha256": self.sha256,
        }


def direct_chat_seed_txt_file(*, path: str, content: str) -> DirectChatTxtSeedResult:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    raw = target.read_bytes()
    return DirectChatTxtSeedResult(
        path=str(target),
        bytes_written=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def direct_chat_delete_txt_file(*, path: str) -> dict[str, object]:
    target = Path(path).expanduser()
    existed = target.exists()
    if target.exists() and target.is_file():
        target.unlink()
    return {
        "path": str(target),
        "existed": existed,
        "deleted": existed and not target.exists(),
    }
