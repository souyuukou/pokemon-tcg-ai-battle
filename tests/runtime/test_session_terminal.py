"""T-SESSION-TERMINAL: terminal vs deck-selection state machine."""
from __future__ import annotations

from unittest.mock import MagicMock

from ptcg_ai.runtime.runtime import CompetitionRuntime


def _deck() -> list[int]:
    from pathlib import Path

    return [int(x) for x in Path("submission/deck.csv").read_text().split() if x.strip()]


def test_session_terminal_1_deck_provider_not_called_on_terminal():
    runtime = CompetitionRuntime(_deck())
    runtime.act({"select": None, "current": {}, "logs": []})
    spy = MagicMock(side_effect=runtime._deck_provider.select_deck)
    runtime._deck_provider.select_deck = spy

    terminal_obs = {
        "select": None,
        "current": {"result": 1, "yourIndex": 0, "players": []},
        "logs": [],
    }
    result = runtime.act(terminal_obs)

    spy.assert_not_called()
    assert result == []


def test_session_terminal_2_new_session_only_on_deck_selection():
    runtime = CompetitionRuntime(_deck())
    runtime.act({"select": None, "current": {}, "logs": []})
    first_session = runtime._session
    assert first_session is not None

    runtime.act(
        {
            "select": None,
            "current": {"result": 0, "yourIndex": 0, "players": []},
            "logs": [],
        }
    )
    assert runtime._session is None

    runtime.act({"select": None, "current": {}, "logs": []})
    assert runtime._session is not None
    assert runtime._session is not first_session


def test_session_terminal_3_terminal_does_not_carry_ledger_counter():
    deck = _deck()
    runtime = CompetitionRuntime(deck)
    runtime.act({"select": None, "current": {}, "logs": []})
    runtime._session.observation_ledger.decision_counter = 7

    runtime.act(
        {
            "select": None,
            "current": {"result": 1, "yourIndex": 0, "players": []},
            "logs": [],
        }
    )

    runtime.act({"select": None, "current": {}, "logs": []})
    assert runtime._session.observation_ledger.decision_counter == 0


def test_session_terminal_4_hidden_fields_do_not_invoke_policy():
    runtime = CompetitionRuntime(_deck())
    runtime.act({"select": None, "current": {}, "logs": []})
    policy_spy = MagicMock(side_effect=runtime._policy.decide)
    runtime._policy.decide = policy_spy
    deck_spy = MagicMock(side_effect=runtime._deck_provider.select_deck)
    runtime._deck_provider.select_deck = deck_spy

    terminal_obs = {
        "select": None,
        "current": {"result": 1, "yourIndex": 0, "players": []},
        "logs": [],
        "search_begin_input": {"token": "secret"},
        "unknown_host_field": [1, 2, 3],
    }
    result = runtime.act(terminal_obs)

    deck_spy.assert_not_called()
    policy_spy.assert_not_called()
    assert result == []
