"""T1/T12: Hidden twin and capability quarantine tests."""
from __future__ import annotations

import pytest

from ptcg_ai.baseline.features import cache_key, feature_vector
from ptcg_ai.baseline.ranker import Ranker
from ptcg_ai.contract.runtime_profile import DEFAULT_PROFILE
from ptcg_ai.host.host_adapter import HostAdapter
from ptcg_ai.host.raw_observation import RawObservation
from ptcg_ai.runtime.agent_session import AgentSession
from ptcg_ai.semantic.option_ir import ResponseIR


def _base_obs() -> dict:
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
            "turn": 4,
            "players": [
                {
                    "hand": [{"id": 65}],
                    "handCount": 1,
                    "prize": [None] * 6,
                    "deckCount": 53,
                    "active": [],
                    "bench": [],
                    "discard": [],
                },
                {
                    "hand": [{"id": 999}],
                    "handCount": 5,
                    "prize": [None] * 6,
                    "deckCount": 53,
                    "active": [],
                    "bench": [],
                    "discard": [],
                },
            ],
        },
        "logs": [],
        "remainingOverageTime": 600.0,
    }


def _deck() -> list[int]:
    base = [10] * 10 + [65] * 50
    return base[:60]


def test_hidden_twin_invariance():
    obs_a = _base_obs()
    obs_b = _base_obs()
    obs_b["current"]["players"][1]["hand"] = [{"id": 888}, {"id": 777}]
    obs_b["search_begin_input"] = "token_a"
    obs_a["search_begin_input"] = "token_b"

    adapter = HostAdapter()
    session_a = AgentSession.start_new(_deck())
    session_b = AgentSession.start_new(_deck())
    dec_a = adapter.sanitize_decision(RawObservation.from_dict(obs_a), session_a)
    dec_b = adapter.sanitize_decision(RawObservation.from_dict(obs_b), session_b)

    assert dec_a.actor_view.observation_hash == dec_b.actor_view.observation_hash
    assert dec_a.contract.request_fingerprint == dec_b.contract.request_fingerprint

    ranker = Ranker(DEFAULT_PROFILE)
    resp = ResponseIR(
        request_fingerprint=dec_a.contract.request_fingerprint,
        option_indices=(1,),
        selection_mode="single",
        category="ATTACK",
        fingerprint="abc",
    )
    assert feature_vector(dec_a.actor_view, resp) == feature_vector(dec_b.actor_view, resp)
    assert cache_key(dec_a.actor_view, dec_a.contract, "b0") == cache_key(
        dec_b.actor_view, dec_b.contract, "b0"
    )
    assert ranker.score(dec_a.actor_view, resp, 1) == ranker.score(dec_b.actor_view, resp, 1)
