"""Agent session lifecycle."""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from typing import Protocol

from ..contract.manifest import sha256_deck
from ..semantic.actor_view import SelfDeckManifest
from ..semantic.observation_ledger import ObservationLedger
from .diagnostics import DiagnosticsBuffer
from .time_bank import TimeBankState


class DeckProvider(Protocol):
    def select_deck(self, request: DeckSelectionRequest) -> list[int]: ...


@dataclass(frozen=True)
class DeckSelectionRequest:
    pass


@dataclass
class ActorViewCache:
    max_entries: int = 64
    _store: dict[str, object] = field(default_factory=dict, repr=False)

    def get(self, key: str) -> object | None:
        return self._store.get(key)

    def put(self, key: str, value: object) -> None:
        if len(self._store) >= self.max_entries:
            oldest = next(iter(self._store))
            del self._store[oldest]
        self._store[key] = value

    def clear(self) -> None:
        self._store.clear()


@dataclass
class AgentSession:
    session_id: str
    actor_index: int | None
    deck_manifest: SelfDeckManifest
    deck_hash: str
    observation_ledger: ObservationLedger
    time_bank_state: TimeBankState
    decision_counter: int
    actor_view_cache: ActorViewCache
    diagnostics: DiagnosticsBuffer
    emergency_mode: bool = False

    @classmethod
    def start_new(cls, deck: list[int], *, profile_cache_max: int = 64) -> AgentSession:
        counts: dict[int, int] = {}
        for cid in deck:
            counts[cid] = counts.get(cid, 0) + 1
        manifest = SelfDeckManifest(card_counts=counts)
        return cls(
            session_id=uuid.uuid4().hex,
            actor_index=None,
            deck_manifest=manifest,
            deck_hash=sha256_deck(deck),
            observation_ledger=ObservationLedger(),
            time_bank_state=TimeBankState(),
            decision_counter=0,
            actor_view_cache=ActorViewCache(max_entries=profile_cache_max),
            diagnostics=DiagnosticsBuffer(),
            emergency_mode=False,
        )

    def close(self) -> None:
        self.actor_view_cache.clear()
        self.observation_ledger.reset_for_new_game()


class FixedDeckProvider:
    def __init__(self, deck: list[int]) -> None:
        if len(deck) != 60:
            raise ValueError(f"deck must have 60 cards, got {len(deck)}")
        self._deck = list(deck)

    def select_deck(self, request: DeckSelectionRequest) -> list[int]:
        return list(self._deck)
