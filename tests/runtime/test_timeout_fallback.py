"""T9: Timeout / interruption uses validated fallback."""
from __future__ import annotations

from unittest.mock import patch

from ptcg_ai.baseline.policy_b0 import PolicyB0
from ptcg_ai.contract.runtime_profile import DEFAULT_PROFILE
from ptcg_ai.host.host_adapter import HostAdapter
from ptcg_ai.host.raw_observation import RawObservation
from ptcg_ai.runtime.agent_session import AgentSession
from ptcg_ai.runtime.deadline import Deadline


def test_proposer_exception_uses_fallback():
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
                {"hand": [], "prize": [None] * 6, "deckCount": 50, "active": [], "bench": [], "discard": []},
                {"hand": [], "handCount": 0, "prize": [None] * 6, "deckCount": 50, "active": [], "bench": [], "discard": []},
            ],
        },
        "logs": [],
    }
    deck = [65] * 60
    session = AgentSession.start_new(deck)
    decision = HostAdapter().sanitize_decision(RawObservation.from_dict(obs), session)
    policy = PolicyB0(DEFAULT_PROFILE)
    deadline = Deadline.from_budget(10.0, 10.0)
    with patch.object(policy._proposer, "propose", side_effect=RuntimeError("boom")):
        resp, used_fb = policy.decide(decision, deadline=deadline, decision_counter=1, emergency=False)
    assert used_fb
    assert len(resp.option_indices) == 1
