from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional


@dataclass
class Event:
    title: str
    day: date
    start_min: int
    end_min: int
    category: str
    color: str
    source: str
    conflict: bool = False
    note: Optional[str] = None
    meta: dict[str, Any] = field(default_factory=dict)
