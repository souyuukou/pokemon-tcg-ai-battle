"""M0-H: Schema fixture builder unit tests."""
from __future__ import annotations

from ptcg_ai.eval.schema_fixture_builder import enumerate_candidate_responses, pattern_rule_for


def test_enumerate_optional_single_patterns():
    patterns, trials, truncated, _reason = enumerate_candidate_responses(0, 1, 2, max_trials=32)
    assert not truncated
    assert [] in patterns
    assert [0] in patterns
    assert [1] in patterns


def test_pattern_rule_single():
    assert pattern_rule_for(1, 1, order_sensitive=False) == "any_singleton"
    assert pattern_rule_for(0, 1, order_sensitive=False) == "optional_single"
