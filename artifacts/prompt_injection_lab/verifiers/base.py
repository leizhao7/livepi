from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


@dataclass
class VerificationResult:
    passed: bool
    reason: str
    evidence: list[str] = field(default_factory=list)


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def flatten_text(items: Iterable[Any], keys: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for item in items:
        if isinstance(item, str):
            out.append(item)
            continue
        if isinstance(item, dict):
            for key in keys:
                if key in item:
                    out.append(_stringify(item[key]))
            continue
        out.append(_stringify(item))
    return out


def find_indicator_hits(candidates: Iterable[str], indicators: Iterable[str]) -> list[str]:
    text_blob = "\n".join(candidates).lower()
    hits: list[str] = []
    for indicator in indicators:
        if indicator.lower() in text_blob:
            hits.append(indicator)
    return hits


def find_tool_call_hits(tool_calls: Iterable[dict[str, Any]], dangerous: Iterable[str]) -> list[str]:
    dangerous_set = {name.lower() for name in dangerous}
    hits: list[str] = []
    for call in tool_calls:
        name = _stringify(call.get("name")).lower()
        if name in dangerous_set:
            hits.append(call.get("name", "unknown"))
    return hits

