"""Deadline governor."""
from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Deadline:
    started_monotonic: float
    soft_deadline_monotonic: float
    hard_deadline_monotonic: float

    @classmethod
    def from_budget(cls, soft_seconds: float, hard_seconds: float) -> Deadline:
        now = time.monotonic()
        return cls(
            started_monotonic=now,
            soft_deadline_monotonic=now + soft_seconds,
            hard_deadline_monotonic=now + hard_seconds,
        )

    def should_stop(self) -> bool:
        return time.monotonic() >= self.soft_deadline_monotonic

    def hard_exceeded(self) -> bool:
        return time.monotonic() >= self.hard_deadline_monotonic

    def remaining_soft_seconds(self) -> float:
        return max(0.0, self.soft_deadline_monotonic - time.monotonic())
