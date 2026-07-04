"""Arena helpers for CompetitionRuntime telemetry collection."""
from __future__ import annotations

from typing import Any, Callable

from ..runtime.runtime import CompetitionRuntime
from ..runtime.telemetry import DecisionTelemetry
from .scorecard import Scorecard


def apply_telemetry(card: Scorecard, telemetry: DecisionTelemetry | None) -> None:
    if telemetry is None:
        return
    if telemetry.used_fallback:
        card.fallback_count += 1
    if telemetry.emergency_mode:
        card.emergency_decision_count += 1
    q = telemetry.conservation_quality
    if q == "verified":
        card.conservation_verified_count += 1
    elif q == "mismatch":
        card.conservation_mismatch_count += 1
    elif q == "unverified":
        card.conservation_unverified_count += 1


def wrap_runtime_act(runtime: CompetitionRuntime, card: Scorecard) -> Callable[[dict[str, Any]], list[int]]:
    def agent(obs: dict[str, Any]) -> list[int]:
        result = runtime.act(obs)
        apply_telemetry(card, runtime.consume_last_decision_telemetry())
        return result

    return agent
