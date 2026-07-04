"""M0-H: Schema fixture builder unit tests."""
from __future__ import annotations

from ptcg_ai.eval.schema_fixture_builder import (
    CaptureContract,
    enumerate_candidate_responses,
    pattern_rule_for,
    selection_shape_for,
)


def test_enumerate_optional_single_patterns():
    patterns, trials, truncated, _reason = enumerate_candidate_responses(0, 1, 2, max_trials=32)
    assert not truncated
    assert [] in patterns
    assert [0] in patterns
    assert [1] in patterns


def test_pattern_rule_single():
    assert pattern_rule_for(1, 1, order_sensitive=False) == "any_singleton"
    assert pattern_rule_for(0, 1, order_sensitive=False) == "optional_single"


def test_capture_contract_mismatch():
    contract = CaptureContract(
        semantic_schema_key="x",
        select_type=1,
        context=2,
        min_count=0,
        max_count=1,
        selection_mode="optional_single",
        option_count=1,
        option_type_pattern=(3,),
    )
    obs = {
        "select": {
            "type": 1,
            "context": 99,
            "minCount": 0,
            "maxCount": 1,
            "option": [{"type": 3}],
        }
    }
    assert not contract.matches_obs(obs)


def test_selection_shape_bounded():
    assert selection_shape_for(0, 2) == "bounded"
