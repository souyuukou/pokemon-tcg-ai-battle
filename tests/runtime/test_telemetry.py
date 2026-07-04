"""T-TEL: Decision telemetry tests."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ptcg_ai.runtime.runtime import CompetitionRuntime
from ptcg_ai.semantic.response_ir import UnsupportedSelectionSchema


def _deck() -> list[int]:
    from pathlib import Path

    return [int(x) for x in Path("submission/deck.csv").read_text().split() if x.strip()]


def _players():
    empty = {"hand": [], "prize": [None] * 6, "deckCount": 54, "active": [], "bench": [], "discard": []}
    return [empty, {**empty, "handCount": 0}]


def _obs(*, select_type: int = 0, context: int = 0, min_count: int = 1, max_count: int = 1):
    return {
        "select": {
            "type": select_type,
            "context": context,
            "minCount": min_count,
            "maxCount": max_count,
            "option": [{"type": 14}, {"type": 13}],
        },
        "current": {"yourIndex": 0, "players": _players()},
        "logs": [],
        "remainingOverageTime": 600.0,
    }


def _start(runtime: CompetitionRuntime) -> None:
    runtime.act({"select": None, "current": {}, "logs": []})


def test_t_tel_1_normal_decision_reports_no_fallback():
    runtime = CompetitionRuntime(_deck())
    _start(runtime)
    runtime.act(_obs())
    tel = runtime.consume_last_decision_telemetry()
    assert tel is not None
    assert tel.used_fallback is False
    assert tel.fallback_reason is None


def test_t_tel_2_emergency_reports_fallback():
    runtime = CompetitionRuntime(_deck())
    _start(runtime)
    runtime._session.emergency_mode = True
    runtime.act(_obs())
    tel = runtime.consume_last_decision_telemetry()
    assert tel is not None
    assert tel.used_fallback is True
    assert tel.emergency_mode is True
    assert tel.fallback_reason == "deadline_or_emergency"


def test_t_tel_3_ranker_exception_reports_fallback_reason():
    runtime = CompetitionRuntime(_deck())
    _start(runtime)
    runtime._policy._ranker.select = MagicMock(side_effect=RuntimeError("ranker failed"))
    runtime.act(_obs())
    tel = runtime.consume_last_decision_telemetry()
    assert tel is not None
    assert tel.used_fallback is True
    assert tel.fallback_reason == "ranker_exception"


def test_t_tel_4_unsupported_schema_incident_not_fallback():
    runtime = CompetitionRuntime(_deck())
    _start(runtime)
    obs = {
        "select": {
            "type": 0,
            "context": 0,
            "minCount": 2,
            "maxCount": 3,
            "option": [{"type": 14}] * 5,
        },
        "current": {"yourIndex": 0, "players": _players()},
        "logs": [],
    }
    with pytest.raises(UnsupportedSelectionSchema):
        runtime.act(obs)
    tel = runtime.consume_last_decision_telemetry()
    assert tel is not None
    assert tel.used_fallback is False
    assert tel.incident_code == "unsupported_schema"


def test_t_tel_5_telemetry_has_no_forbidden_fields():
    runtime = CompetitionRuntime(_deck())
    _start(runtime)
    runtime.act(_obs())
    tel = runtime.consume_last_decision_telemetry()
    assert tel is not None
    forbidden = ("search", "token", "hand", "prize", "deck_order", "raw")
    blob = repr(tel).lower()
    for word in forbidden:
        assert word not in blob or word in ("fallback", "semantic_schema_key")
