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
    emergency_decision_count: int = 0
    backend_failure_count: int = 0
    unsupported_schema_count: int = 0
    schema_incomplete_games: int = 0
    captured_schema_events: int = 0
    conservation_unverified_count: int = 0
    conservation_verified_count: int = 0
    conservation_mismatch_count: int = 0
    conservation_unavailable_count: int = 0
    in_game_decision_count: int = 0
    seat_first_count: int = 0
    seat_second_count: int = 0
    max_rss_bytes: int | None = None
    decision_times_ms: list[float] = field(default_factory=list)
    time_bank_exhaustion_count: int = 0

    def record_decision_time(self, ms: float) -> None:
        self.decision_times_ms.append(ms)

    def record_rss(self, rss_bytes: int | None) -> None:
        if rss_bytes is None:
            return
        self.max_rss_bytes = max(self.max_rss_bytes or 0, rss_bytes)

    def record_seat(self, your_index: int) -> None:
        if your_index == 0:
            self.seat_first_count += 1
        else:
            self.seat_second_count += 1

    def conservation_decision_total(self) -> int:
        return (
            self.conservation_verified_count
            + self.conservation_unverified_count
            + self.conservation_mismatch_count
            + self.conservation_unavailable_count
        )

    def conservation_telemetry_coverage_ok(self) -> bool:
        if self.in_game_decision_count == 0:
            return False
        return self.conservation_decision_total() == self.in_game_decision_count

    def percentile(self, p: float) -> float | None:
        if not self.decision_times_ms:
            return None
        sorted_t = sorted(self.decision_times_ms)
        idx = max(0, min(len(sorted_t) - 1, int(len(sorted_t) * p) - 1))
        return sorted_t[idx]

    def seat_distribution(self) -> dict[str, int]:
        return {"first": self.seat_first_count, "second": self.seat_second_count}

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["median_decision_ms"] = self.percentile(0.5)
        d["p95_decision_ms"] = self.percentile(0.95)
        d["p99_decision_ms"] = self.percentile(0.99)
        d["seat_distribution"] = self.seat_distribution()
        d["conservation_telemetry_coverage"] = (
            self.conservation_decision_total() / self.in_game_decision_count
            if self.in_game_decision_count
            else 0.0
        )
        d["conservation_telemetry_coverage_ok"] = self.conservation_telemetry_coverage_ok()
        return d


def merge_scorecards(a: Scorecard, b: Scorecard) -> Scorecard:
    return Scorecard(
        total_games=a.total_games + b.total_games,
        completed_games=a.completed_games + b.completed_games,
        crash_count=a.crash_count + b.crash_count,
        illegal_action_count=a.illegal_action_count + b.illegal_action_count,
        protocol_error_count=a.protocol_error_count + b.protocol_error_count,
        fallback_count=a.fallback_count + b.fallback_count,
        emergency_decision_count=a.emergency_decision_count + b.emergency_decision_count,
        backend_failure_count=a.backend_failure_count + b.backend_failure_count,
        unsupported_schema_count=a.unsupported_schema_count + b.unsupported_schema_count,
        schema_incomplete_games=a.schema_incomplete_games + b.schema_incomplete_games,
        captured_schema_events=a.captured_schema_events + b.captured_schema_events,
        conservation_unverified_count=a.conservation_unverified_count + b.conservation_unverified_count,
        conservation_verified_count=a.conservation_verified_count + b.conservation_verified_count,
        conservation_mismatch_count=a.conservation_mismatch_count + b.conservation_mismatch_count,
        conservation_unavailable_count=a.conservation_unavailable_count + b.conservation_unavailable_count,
        in_game_decision_count=a.in_game_decision_count + b.in_game_decision_count,
        seat_first_count=a.seat_first_count + b.seat_first_count,
        seat_second_count=a.seat_second_count + b.seat_second_count,
        max_rss_bytes=max(filter(None, [a.max_rss_bytes, b.max_rss_bytes]), default=None),
        decision_times_ms=a.decision_times_ms + b.decision_times_ms,
        time_bank_exhaustion_count=a.time_bank_exhaustion_count + b.time_bank_exhaustion_count,
    )
