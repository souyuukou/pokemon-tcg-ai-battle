"""M0-H: Conservation telemetry coverage tests."""
from __future__ import annotations

from pathlib import Path

from ptcg_ai.eval.arena import ArenaConfig, run_soak_batch
from ptcg_ai.eval.runtime_harness import wrap_runtime_act
from ptcg_ai.eval.scorecard import Scorecard
from ptcg_ai.runtime.runtime import CompetitionRuntime


def _deck() -> list[int]:
    return [int(x) for x in Path("submission/deck.csv").read_text().split() if x.strip()]


def test_conservation_telemetry_sums_to_in_game_decisions():
    deck = _deck()
    runtime = CompetitionRuntime(deck)
    card = Scorecard()
    cfg = ArenaConfig(max_steps=200, mode="strict", time_bank_mode="no_authoritative")
    run_soak_batch(
        wrap_runtime_act(runtime, card),
        deck,
        games=2,
        sim_root=Path("sample_submission"),
        config=cfg,
    )
    if card.in_game_decision_count == 0:
        return
    assert card.conservation_telemetry_coverage_ok()
    assert card.conservation_decision_total() == card.in_game_decision_count


def test_actor_view_carries_conservation_quality():
    from ptcg_ai.host.host_adapter import HostAdapter
    from ptcg_ai.host.raw_observation import RawObservation
    from ptcg_ai.runtime.agent_session import AgentSession

    obs = {
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
                {
                    "hand": [],
                    "prize": [None] * 6,
                    "deckCount": 54,
                    "active": [],
                    "bench": [],
                    "discard": [],
                },
                {"hand": [], "handCount": 0, "prize": [None] * 6, "deckCount": 54, "active": [], "bench": [], "discard": []},
            ],
        },
        "logs": [],
    }
    decision = HostAdapter().sanitize_decision(RawObservation.from_dict(obs), AgentSession.start_new(_deck()))
    assert decision.actor_view.conservation_quality in ("verified", "unverified", "unavailable")
