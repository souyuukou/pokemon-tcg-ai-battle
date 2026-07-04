"""T-TIME: Time bank harness tests."""
from __future__ import annotations

import time
from pathlib import Path
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

ROOT = Path(__file__).resolve().parents[2]


def _sim_deck() -> list[int]:
    deck_path = ROOT / "submission" / "deck.csv"
    return [int(x) for x in deck_path.read_text().split() if x.strip()]


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
        resp, used_fb, _reason = policy.decide(decision, deadline=deadline, decision_counter=1, emergency=True)
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


def test_t_time_5_emergency_does_not_bypass_unknown_schema():
    from ptcg_ai.runtime.runtime import CompetitionRuntime
    from ptcg_ai.semantic.response_ir import UnsupportedSelectionSchema

    deck = _sim_deck()
    runtime = CompetitionRuntime(deck)
    runtime.act({"select": None, "current": {}, "logs": []})
    runtime._session.emergency_mode = True
    obs = {
        "select": {
            "type": 0,
            "context": 0,
            "minCount": 2,
            "maxCount": 3,
            "option": [{"type": 14}] * 5,
        },
        "current": {"yourIndex": 0, "players": _obs()["current"]["players"]},
        "logs": [],
    }
    with pytest.raises(UnsupportedSelectionSchema):
        runtime.act(obs)


def test_arena_no_fixed_600_injection_in_no_authoritative_mode():
    """Arena must not inject remainingOverageTime=600 when mode is no_authoritative."""
    seen: list[dict] = []

    def spy(obs):
        seen.append(dict(obs))
        return [0]

    deck = _sim_deck()
    cfg = ArenaConfig(max_steps=5, time_bank_mode="no_authoritative")
    run_self_play(spy, deck, config=cfg)
    for obs in seen:
        if obs.get("select") is not None:
            assert "remainingOverageTime" not in obs


def test_arena_time_bank_exhaustion_disqualifies_game():
    import time

    deck = _sim_deck()

    def slow_agent(obs):
        if obs.get("select") is None:
            return list(deck)
        time.sleep(0.05)
        s = obs.get("select") or {}
        opts = s.get("option") or []
        return [0] if opts else []

    cfg = ArenaConfig(
        max_steps=200,
        time_bank_mode="authoritative",
        initial_time_seconds=0.01,
        desired_seat=None,
    )
    card = run_self_play(slow_agent, deck, config=cfg)
    assert card.time_bank_exhaustion_count >= 1
    assert card.completed_games == 0
    assert card.protocol_error_count >= 1


def test_soak_batch_alternates_seats():
    from ptcg_ai.eval.arena import run_soak_batch

    deck = _sim_deck()

    def seat_spy(obs):
        if obs.get("select") is None:
            return list(deck)
        s = obs.get("select") or {}
        opts = s.get("option") or []
        return [0] if opts else []

    card = run_soak_batch(seat_spy, deck, games=8, config=ArenaConfig(max_steps=400))
    dist = card.seat_distribution()
    assert dist["first"] >= 1
    assert dist["second"] >= 1
    assert dist["first"] + dist["second"] == 8
