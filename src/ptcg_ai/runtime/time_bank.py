"""Match-level time bank."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TimeBankState:
    authoritative_remaining: float | None = None
    local_remaining: float | None = None
    effective_remaining: float | None = None
    exhausted: bool = False

    def effective(self) -> float:
        return self.effective_remaining or 0.0


def update_time_bank(
    state: TimeBankState,
    *,
    host_remaining: float | None,
    safety_margin: float,
) -> None:
    if host_remaining is not None and host_remaining >= 0:
        state.authoritative_remaining = host_remaining
    if state.authoritative_remaining is not None:
        local_est = max(0.0, state.authoritative_remaining - safety_margin)
        state.local_remaining = local_est
        state.effective_remaining = local_est
    state.exhausted = (state.effective_remaining or 0.0) <= 0.05


def budget_for_decision(
    state: TimeBankState,
    *,
    option_count: int,
    emergency_threshold: float,
    emergency: bool,
) -> float:
    eff = state.effective()
    if emergency or eff <= emergency_threshold:
        return min(0.5, eff)
    if option_count <= 1:
        return min(0.2, eff)
    if option_count <= 4:
        return min(2.0, eff * 0.01)
    return min(5.0, eff * 0.02)
