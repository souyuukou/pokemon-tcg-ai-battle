"""T-TIME: Time bank harness tests."""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from ptcg_ai.baseline.policy_b0 import PolicyB0
from ptcg_ai.contract.runtime_profile import DEFAULT_PROFILE
from ptcg_ai.eval.arena import ArenaConfig, AuthoritativeTimeTracker, run_self_play
from ptcg_ai.host.host_adapter import HostAdapter
from ptcg_ai.host.raw_observation import RawObservation
from ptcg_ai.runtime.agent_session import AgentSession
from ptcg_ai.runtime.deadline import Deadline
from ptcg_ai.runtime.time_bank import TimeBankState, begin_decision_clock, update_time_bank


def _obs():
    return {
        "select": {
            "type": 0,
            "context": 0,
            "minCount": 1,
            "maxCount": 1,
            "option": [{"type": 14}, {"type": 13}],
        },
        "current": {
            "yourIndex": 0,
            "players": [
                {"hand": [], "prize": [None] * 6, "deckCount": 54, "active": [], "bench": [], "discard": []},
                {"hand": [], "handCount": 0, "prize": [None] * 6, "deckCount": 54, "active": [], "bench": [], "discard": []},
            ],
        },
        "logs": [],
    }


def test_t_time_1_emergency_uses_validated_fallback_only():
    deck = [65] * 60
    decision = HostAdapter().sanitize_decision(RawObservation.from_dict(_obs()), AgentSession.start_new(deck))
    policy = PolicyB0(DEFAULT_PROFILE)
    deadline = Deadline.from_budget(0.0, 0.0)
    with patch.object(policy._ranker, "select", return_value=None):
        resp, used_fb = policy.decide(decision, deadline=deadline, decision_counter=1, emergency=True)
    assert used_fb
    assert len(resp.option_indices) == 1
    assert 0 <= resp.option_indices[0] < decision.contract.option_count


def test_t_time_2_missing_host_time_accumulates_local_elapsed():
    state = TimeBankState()
    t0 = begin_decision_clock(state)
    time.sleep(0.01)
    update_time_bank(
        state,
        host_remaining=None,
        safety_margin=0.0,
        call_start_monotonic=t0,
        match_budget_seconds=600.0,
    )
    first = state.effective()
    time.sleep(0.01)
    t1 = begin_decision_clock(state)
    update_time_bank(
        state,
        host_remaining=None,
        safety_margin=0.0,
        call_start_monotonic=t1,
        match_budget_seconds=600.0,
    )
    assert state.effective() < first


def test_t_time_3_authoritative_tracker_only_decrements_on_agent_call():
    tracker = AuthoritativeTimeTracker(100.0)
    before = tracker.remaining
    time.sleep(0.01)
    assert tracker.remaining == before
    tracker.record_elapsed(0.5)
    assert tracker.remaining == 99.5


def test_t_time_4_emergency_mode_irreversible():
    state = TimeBankState()
    state.emergency_mode = True
    t0 = begin_decision_clock(state)
    update_time_bank(
        state,
        host_remaining=600.0,
        safety_margin=0.0,
        call_start_monotonic=t0,
        match_budget_seconds=600.0,
    )
    assert state.emergency_mode


def test_arena_no_fixed_600_injection_in_no_authoritative_mode():
    """Arena must not inject remainingOverageTime=600 when mode is no_authoritative."""
    seen: list[dict] = []

    def spy(obs):
        seen.append(dict(obs))
        return [0]

    deck = [65] * 60
    cfg = ArenaConfig(max_steps=5, time_bank_mode="no_authoritative")
    run_self_play(spy, deck, config=cfg)
    for obs in seen:
        if obs.get("select") is not None:
            assert "remainingOverageTime" not in obs
