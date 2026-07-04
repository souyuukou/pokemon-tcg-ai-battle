"""M0-H: Fixture builder replay-target assertion tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from ptcg_ai.eval.schema_fixture_builder import (
    CaptureContract,
    build_fixture_from_capture,
    replay_to_capture_target,
)


def _deck() -> list[int]:
    return [int(x) for x in Path("submission/deck.csv").read_text().split() if x.strip()]


@pytest.fixture
def sim():
    import sys

    root = Path("sample_submission").resolve()
    sys.path.insert(0, str(root))
    from cg.game import battle_finish, battle_select, battle_start

    return battle_start, battle_select, battle_finish


def test_replay_wrong_trace_fails_target_assertion(sim):
    battle_start, battle_select, battle_finish = sim
    deck = _deck()
    contract = CaptureContract(
        semantic_schema_key="deadbeef",
        select_type=99,
        context=99,
        min_count=1,
        max_count=1,
        selection_mode="single",
        option_count=1,
        option_type_pattern=(14,),
    )
    result = replay_to_capture_target(
        deck,
        [],
        contract,
        battle_start=battle_start,
        battle_select=battle_select,
        battle_finish=battle_finish,
    )
    assert not result.ok
    assert result.reason == "replay_did_not_reach_capture_target"


def test_build_fixture_from_bad_capture_returns_error(sim):
    battle_start, battle_select, battle_finish = sim
    capture = {
        "semantic_schema_key": "0000000000000000",
        "select_type": 1,
        "context": 2,
        "min_count": 0,
        "max_count": 2,
        "selection_mode": "sequence",
        "option_count": 2,
        "option_type_pattern": [3, 3],
        "replay_trace": [],
    }
    result = build_fixture_from_capture(
        capture,
        _deck(),
        output_dir=Path("artifacts/test_fixtures"),
        tested_commit="test",
        battle_start=battle_start,
        battle_select=battle_select,
        battle_finish=battle_finish,
        slug="bad_capture",
    )
    assert not result.host_apply_verified
    assert result.error in ("replay_did_not_reach_capture_target", "no_verified_patterns_after_replay_assertion")
