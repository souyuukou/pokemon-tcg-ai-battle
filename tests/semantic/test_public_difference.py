"""T2: Public difference changes actor view."""
from __future__ import annotations

from ptcg_ai.host.host_adapter import HostAdapter
from ptcg_ai.host.raw_observation import RawObservation
from ptcg_ai.runtime.agent_session import AgentSession


def _obs(active_id: int) -> dict:
    return {
        "select": {
            "type": 0,
            "context": 0,
            "minCount": 1,
            "maxCount": 1,
            "option": [{"type": 14}],
        },
        "current": {
            "yourIndex": 0,
            "turn": 3,
            "players": [
                {"hand": [], "prize": [None] * 6, "deckCount": 50, "active": [{"id": active_id}], "bench": [], "discard": []},
                {"hand": [], "handCount": 0, "prize": [None] * 6, "deckCount": 50, "active": [], "bench": [], "discard": []},
            ],
        },
        "logs": [],
    }


def test_public_board_change_alters_observation_hash():
    deck = [65] * 60
    adapter = HostAdapter()
    s1 = AgentSession.start_new(deck)
    s2 = AgentSession.start_new(deck)
    d1 = adapter.sanitize_decision(RawObservation.from_dict(_obs(100)), s1)
    d2 = adapter.sanitize_decision(RawObservation.from_dict(_obs(200)), s2)
    assert d1.actor_view.observation_hash != d2.actor_view.observation_hash
