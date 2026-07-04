"""Qualification scorecard."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Scorecard:
    total_games: int = 0
    completed_games: int = 0
    crash_count: int = 0
    illegal_action_count: int = 0
    protocol_error_count: int = 0
    fallback_count: int = 0
    backend_failure_count: int = 0
    unsupported_schema_count: int = 0
    conservation_unverified_count: int = 0
    conservation_verified_count: int = 0
    max_rss_bytes: int | None = None
    decision_times_ms: list[float] = field(default_factory=list)
    time_bank_exhaustion_count: int = 0

    def record_decision_time(self, ms: float) -> None:
        self.decision_times_ms.append(ms)

    def percentile(self, p: float) -> float | None:
        if not self.decision_times_ms:
            return None
        sorted_t = sorted(self.decision_times_ms)
        idx = max(0, min(len(sorted_t) - 1, int(len(sorted_t) * p) - 1))
        return sorted_t[idx]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["median_decision_ms"] = self.percentile(0.5)
        d["p95_decision_ms"] = self.percentile(0.95)
        d["p99_decision_ms"] = self.percentile(0.99)
        return d


def merge_scorecards(a: Scorecard, b: Scorecard) -> Scorecard:
    return Scorecard(
        total_games=a.total_games + b.total_games,
        completed_games=a.completed_games + b.completed_games,
        crash_count=a.crash_count + b.crash_count,
        illegal_action_count=a.illegal_action_count + b.illegal_action_count,
        protocol_error_count=a.protocol_error_count + b.protocol_error_count,
        fallback_count=a.fallback_count + b.fallback_count,
        backend_failure_count=a.backend_failure_count + b.backend_failure_count,
        unsupported_schema_count=a.unsupported_schema_count + b.unsupported_schema_count,
        conservation_unverified_count=a.conservation_unverified_count + b.conservation_unverified_count,
        conservation_verified_count=a.conservation_verified_count + b.conservation_verified_count,
        max_rss_bytes=max(filter(None, [a.max_rss_bytes, b.max_rss_bytes]), default=None),
        decision_times_ms=a.decision_times_ms + b.decision_times_ms,
        time_bank_exhaustion_count=a.time_bank_exhaustion_count + b.time_bank_exhaustion_count,
    )
