"""T10: Cache noninterference."""
from __future__ import annotations

from ptcg_ai.baseline.features import cache_key
from ptcg_ai.host.host_adapter import HostAdapter
from ptcg_ai.host.raw_observation import RawObservation
from ptcg_ai.runtime.agent_session import AgentSession


def _obs() -> dict:
    return {
        "select": {"type": 0, "context": 0, "minCount": 1, "maxCount": 1, "option": [{"type": 14}]},
        "current": {
            "yourIndex": 0,
            "players": [
                {"hand": [], "prize": [None] * 6, "deckCount": 54, "active": [], "bench": [], "discard": []},
                {"hand": [], "handCount": 0, "prize": [None] * 6, "deckCount": 54, "active": [], "bench": [], "discard": []},
            ],
        },
        "logs": [],
    }


def test_cache_key_ignores_search_token():
    deck = [65] * 60
    adapter = HostAdapter()
    a = _obs()
    b = {**_obs(), "search_begin_input": "secret"}
    s1 = AgentSession.start_new(deck)
    s2 = AgentSession.start_new(deck)
    d1 = adapter.sanitize_decision(RawObservation.from_dict(a), s1)
    d2 = adapter.sanitize_decision(RawObservation.from_dict(b), s2)
    assert cache_key(d1.actor_view, d1.contract, "b0") == cache_key(d2.actor_view, d2.contract, "b0")
