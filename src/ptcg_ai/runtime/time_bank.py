"""Match-level time bank with local pessimistic estimation."""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class TimeBankState:
    authoritative_remaining: float | None = None
    last_authoritative_remaining: float | None = None
    last_local_monotonic: float | None = None
    local_consumed_since_last_host_update: float = 0.0
    local_remaining: float | None = None
    effective_remaining: float | None = None
    estimated_remaining_decisions: int = 200
    emergency_mode: bool = False
    exhausted: bool = False
    decisions_seen: int = 0

    def effective(self) -> float:
        return self.effective_remaining or 0.0

    def record_local_elapsed(self, seconds: float) -> None:
        self.local_consumed_since_last_host_update += max(0.0, seconds)


def begin_decision_clock(state: TimeBankState) -> float:
    return time.monotonic()


def update_time_bank(
    state: TimeBankState,
    *,
    host_remaining: float | None,
    safety_margin: float,
    call_start_monotonic: float,
    match_budget_seconds: float,
) -> None:
    now = time.monotonic()
    elapsed_since_call = now - call_start_monotonic
    state.record_local_elapsed(elapsed_since_call)

    if host_remaining is not None and host_remaining >= 0:
        state.last_authoritative_remaining = host_remaining
        state.authoritative_remaining = host_remaining
        state.local_consumed_since_last_host_update = 0.0
        state.last_local_monotonic = now

    t_auth = state.authoritative_remaining
    if t_auth is not None:
        t_local = max(0.0, t_auth - safety_margin - state.local_consumed_since_last_host_update)
    else:
        consumed = state.local_consumed_since_last_host_update
        if state.last_local_monotonic is None:
            state.last_local_monotonic = call_start_monotonic
        total_elapsed = now - (state.last_local_monotonic or call_start_monotonic)
        t_local = max(0.0, match_budget_seconds - total_elapsed - safety_margin)

    state.local_remaining = t_local
    if t_auth is not None:
        state.effective_remaining = min(t_auth - safety_margin, t_local)
    else:
        state.effective_remaining = t_local

    state.exhausted = (state.effective_remaining or 0.0) <= 0.05
    state.emergency_mode = state.emergency_mode or state.exhausted
    state.decisions_seen += 1
    if state.decisions_seen > 10:
        state.estimated_remaining_decisions = max(20, 400 - state.decisions_seen)


def budget_for_decision(
    state: TimeBankState,
    *,
    option_count: int,
    emergency_threshold: float,
    emergency: bool,
    total_budget_seconds: float,
) -> float:
    eff = state.effective()
    if emergency or eff <= emergency_threshold:
        return min(0.5, eff)
    per_decision = eff / max(1, state.estimated_remaining_decisions)
    if option_count <= 1:
        return min(0.2, per_decision, eff)
    if option_count <= 4:
        return min(2.0, per_decision * 2, eff * 0.01)
    return min(5.0, per_decision * 4, eff * 0.02)
