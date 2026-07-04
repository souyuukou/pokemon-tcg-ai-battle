"""Bounded redacted diagnostics."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DiagnosticsBuffer:
    max_entries: int = 128
    entries: list[dict[str, Any]] = field(default_factory=list)
    fallback_count: int = 0
    incident_count: int = 0

    def record(self, entry: dict[str, Any]) -> None:
        safe = {k: v for k, v in entry.items() if k not in ("raw_observation", "search_begin_input")}
        if len(self.entries) >= self.max_entries:
            self.entries.pop(0)
        self.entries.append(safe)

    def record_fallback(self, reason: str) -> None:
        self.fallback_count += 1
        self.record({"event": "fallback", "reason": reason})

    def as_summary(self) -> dict[str, Any]:
        return {
            "fallback_count": self.fallback_count,
            "incident_count": self.incident_count,
            "entry_count": len(self.entries),
        }
