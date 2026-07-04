"""Ensure unsupported schema propagates without generic fallback."""
from __future__ import annotations

import pytest

from ptcg_ai.runtime.runtime import CompetitionRuntime
from ptcg_ai.semantic.response_ir import UnsupportedSelectionSchema


def test_unsupported_schema_raises_from_runtime():
    deck = [65] * 60
    runtime = CompetitionRuntime(deck)
    obs = {
        "select": {
            "type": 0,
            "context": 0,
            "minCount": 2,
            "maxCount": 3,
            "option": [{"type": 14}] * 5,
        },
        "current": {
            "yourIndex": 0,
            "players": [
                {"hand": [], "prize": [None] * 6, "deckCount": 54, "active": [], "bench": [], "discard": []},
                {"hand": [], "handCount": 0, "prize": [None] * 6, "deckCount": 54, "active": [], "bench": [], "discard": []},
            ],
        },
        "logs": [],
        "remainingOverageTime": 600.0,
    }
    runtime.act({"select": None, "current": {}, "logs": []})
    with pytest.raises(UnsupportedSelectionSchema):
        runtime.act(obs)
