"""T-REG-INT: SchemaRegistry wired through CompetitionRuntime.act()."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ptcg_ai.host.schema_registry import REGISTRY
from ptcg_ai.runtime.runtime import CompetitionRuntime
from ptcg_ai.semantic.response_ir import UnsupportedSelectionSchema

ROOT_DECK = None


def _deck() -> list[int]:
    global ROOT_DECK
    if ROOT_DECK is None:
        from pathlib import Path

        ROOT_DECK = [int(x) for x in Path("submission/deck.csv").read_text().split() if x.strip()]
    return ROOT_DECK


def _players():
    empty = {"hand": [], "prize": [None] * 6, "deckCount": 54, "active": [], "bench": [], "discard": []}
    return [empty, {**empty, "handCount": 0}]


def _start(runtime: CompetitionRuntime) -> None:
    runtime.act({"select": None, "current": {}, "logs": []})


def _obs(*, select_type: int, context: int, min_count: int, max_count: int, options: list[dict]):
    return {
        "select": {
            "type": select_type,
            "context": context,
            "minCount": min_count,
            "maxCount": max_count,
            "option": options,
        },
        "current": {"yourIndex": 0, "players": _players()},
        "logs": [],
        "remainingOverageTime": 600.0,
    }


def test_reg_int_1_single_schema_uses_registry():
    runtime = CompetitionRuntime(_deck())
    _start(runtime)
    obs = _obs(select_type=0, context=0, min_count=1, max_count=1, options=[{"type": 14}, {"type": 13}])
    with patch.object(REGISTRY, "lookup_for_contract", wraps=REGISTRY.lookup_for_contract) as spy:
        choice = runtime.act(obs)
    spy.assert_called()
    assert len(choice) == 1


def test_reg_int_2_optional_single_schema_uses_registry():
    runtime = CompetitionRuntime(_deck())
    _start(runtime)
    obs = _obs(select_type=1, context=2, min_count=0, max_count=1, options=[{"type": 14}])
    with patch.object(REGISTRY, "lookup_for_contract", wraps=REGISTRY.lookup_for_contract) as spy:
        choice = runtime.act(obs)
    spy.assert_called()
    assert len(choice) in (0, 1)


def test_reg_int_3_bounded_sequence_schema_uses_registry():
    runtime = CompetitionRuntime(_deck())
    _start(runtime)
    obs = _obs(
        select_type=1,
        context=5,
        min_count=0,
        max_count=2,
        options=[{"type": 3}, {"type": 3}, {"type": 3}],
    )
    with patch.object(REGISTRY, "lookup_for_contract", wraps=REGISTRY.lookup_for_contract) as spy:
        choice = runtime.act(obs)
    spy.assert_called()
    assert len(choice) <= 2


def test_reg_int_4_emergency_mode_still_uses_registry():
    runtime = CompetitionRuntime(_deck())
    _start(runtime)
    obs = _obs(select_type=0, context=0, min_count=1, max_count=1, options=[{"type": 14}, {"type": 13}])
    runtime._session.emergency_mode = True
    with patch.object(REGISTRY, "lookup_for_contract", wraps=REGISTRY.lookup_for_contract) as spy:
        runtime.act(obs)
    assert spy.call_count >= 1


def test_reg_int_5_ranker_exception_uses_registry_fallback_only():
    runtime = CompetitionRuntime(_deck())
    _start(runtime)
    obs = _obs(select_type=0, context=0, min_count=1, max_count=1, options=[{"type": 14}, {"type": 13}])
    runtime._policy._ranker.select = MagicMock(side_effect=RuntimeError("ranker failed"))
    with patch.object(REGISTRY, "lookup_for_contract", wraps=REGISTRY.lookup_for_contract) as spy:
        choice = runtime.act(obs)
    assert spy.call_count >= 1
    assert len(choice) == 1


def test_reg_int_6_unknown_schema_raises_without_fallback():
    runtime = CompetitionRuntime(_deck())
    _start(runtime)
    obs = _obs(select_type=0, context=0, min_count=2, max_count=3, options=[{"type": 14}] * 5)
    with pytest.raises(UnsupportedSelectionSchema):
        runtime.act(obs)
