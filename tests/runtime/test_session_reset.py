"""T11: Session reset between games."""
from __future__ import annotations

from ptcg_ai.runtime.agent_session import AgentSession


def test_session_reset_clears_state():
    deck = [65] * 60
    s = AgentSession.start_new(deck)
    s.observation_ledger.decision_counter = 5
    s.emergency_mode = True
    s.diagnostics.fallback_count = 3
    s.close()
    assert s.observation_ledger.decision_counter == 0
    assert s.emergency_mode is False
    s2 = AgentSession.start_new(deck)
    assert s2.observation_ledger.decision_counter == 0
    assert s2.emergency_mode is False
    assert s2.diagnostics.fallback_count == 0
