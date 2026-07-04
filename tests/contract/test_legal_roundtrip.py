"""T3: Legal round-trip on fixtures."""
from __future__ import annotations

from pathlib import Path

from ptcg_ai.eval.fixture_loader import FixtureLoader
from ptcg_ai.host.host_adapter import HostAdapter
from ptcg_ai.host.host_response import compile_candidate_responses, to_host_response
from ptcg_ai.host.raw_observation import RawObservation
from ptcg_ai.runtime.agent_session import AgentSession


def test_response_validated_fixtures_compile():
    loader = FixtureLoader(Path(__file__).resolve().parents[1] / "fixtures")
    deck = [65] * 60
    adapter = HostAdapter()
    for fx in loader.iter_fixtures(min_maturity="response-validated"):
        session = AgentSession.start_new(deck)
        decision = adapter.sanitize_decision(RawObservation.from_dict(fx.raw_observation), session)
        candidates = compile_candidate_responses(decision)
        assert candidates
        host_resp = to_host_response(decision.contract, candidates[0])
        lo, hi = decision.contract.min_count, decision.contract.max_count
        assert lo <= len(host_resp) <= hi
