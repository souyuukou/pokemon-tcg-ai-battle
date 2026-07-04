"""T6: Deck selection."""
from __future__ import annotations

from ptcg_ai.contract.manifest import sha256_deck
from ptcg_ai.runtime.agent_session import AgentSession, DeckSelectionRequest, FixedDeckProvider


def test_fixed_deck_provider():
    deck = [65] * 60
    provider = FixedDeckProvider(deck)
    selected = provider.select_deck(DeckSelectionRequest())
    assert len(selected) == 60
    session = AgentSession.start_new(selected)
    assert session.deck_hash == sha256_deck(deck)


def test_invalid_deck_fail_fast():
    import pytest

    with pytest.raises(ValueError):
        FixedDeckProvider([1, 2, 3])
