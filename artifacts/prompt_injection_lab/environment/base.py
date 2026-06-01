from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class EnvironmentConfig:
    environment_id: str
    description: str
    required_skills: list[str]
    setup_steps: list[str] = field(default_factory=list)
    teardown_steps: list[str] = field(default_factory=list)
    fixtures: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

