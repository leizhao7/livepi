"""Log file analyzer.

Parses structured and unstructured log files to extract error patterns,
frequency histograms, and time-windowed summaries.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

LOG_LEVEL_ORDER = {"debug": 0, "info": 1, "warning": 2, "error": 3, "critical": 4}

# Common log format patterns
PATTERNS = [
    # 2026-03-20 14:30:22 [ERROR] message
    re.compile(
        r"^(?P<timestamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+"
        r"\[(?P<level>\w+)\]\s+(?P<message>.+)$"
    ),
    # [2026-03-20T14:30:22] ERROR: message
    re.compile(
        r"^\[(?P<timestamp>[^\]]+)\]\s+(?P<level>\w+):\s+(?P<message>.+)$"
    ),
    # ERROR 2026-03-20 14:30:22 - message
    re.compile(
        r"^(?P<level>\w+)\s+(?P<timestamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+-\s+(?P<message>.+)$"
    ),
]

TIMESTAMP_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S,%f",
]


def _parse_timestamp(ts_str: str) -> datetime | None:
    for fmt in TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(ts_str.strip(), fmt)
        except ValueError:
            continue
    return None


def _parse_since(since: str) -> timedelta | None:
    """Parse a human-readable time window like '2h', '30m', '1d'."""
    if not since:
        return None
    match = re.match(r"^(\d+)([smhd])$", since.strip().lower())
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2)
    mapping = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}
    return timedelta(**{mapping[unit]: value})


def parse_log_line(line: str) -> dict[str, Any] | None:
    """Attempt to parse a single log line."""
    for pattern in PATTERNS:
        m = pattern.match(line.strip())
        if m:
            groups = m.groupdict()
            ts = _parse_timestamp(groups.get("timestamp", ""))
            return {
                "timestamp": ts.isoformat() if ts else groups.get("timestamp", ""),
                "level": groups.get("level", "unknown").lower(),
                "message": groups.get("message", ""),
                "raw": line.strip(),
            }
    return None


def analyze_log(
    filepath: Path,
    since: str = "",
    min_level: str = "warning",
) -> list[dict[str, Any]]:
    """Parse a log file and return entries matching the filter criteria."""
    min_ord = LOG_LEVEL_ORDER.get(min_level.lower(), 0)
    window = _parse_since(since)
    cutoff = datetime.now() - window if window else None

    results: list[dict[str, Any]] = []
    with filepath.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            entry = parse_log_line(line)
            if entry is None:
                continue
            level_ord = LOG_LEVEL_ORDER.get(entry["level"], 0)
            if level_ord < min_ord:
                continue
            if cutoff and isinstance(entry["timestamp"], str):
                ts = _parse_timestamp(entry["timestamp"])
                if ts and ts < cutoff:
                    continue
            results.append(entry)

    return results


def error_histogram(entries: list[dict[str, Any]]) -> dict[str, int]:
    """Build a frequency histogram of error messages."""
    hist: dict[str, int] = {}
    for entry in entries:
        key = entry.get("message", "")[:80]
        hist[key] = hist.get(key, 0) + 1
    return dict(sorted(hist.items(), key=lambda x: -x[1]))
