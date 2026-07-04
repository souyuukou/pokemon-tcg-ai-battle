"""Actor-visible observation types."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping

from .legal_contract import LegalActionContract


@dataclass(frozen=True)
class PublicBoard:
    active_self: tuple[int, ...]
    bench_self: tuple[int, ...]
    active_opponent: tuple[int, ...]
    bench_opponent: tuple[int, ...]
    stadium: int | None


@dataclass(frozen=True)
class PublicEvent:
    event_type: str
    player_index: int | None
    card_id: int | None
    summary: str


@dataclass(frozen=True)
class DecisionContext:
    turn: int | None
    your_index: int
    select_type: int | str | None
    context: int | str | None
    first_player: int | None


@dataclass(frozen=True)
class SelfDeckManifest:
    card_counts: Mapping[int, int]


@dataclass(frozen=True)
class VisibleZoneSummary:
    hand: Mapping[int, int]
    active: Mapping[int, int]
    bench: Mapping[int, int]
    discard: Mapping[int, int]
    lost_or_removed: Mapping[int, int]
    prizes_taken: Mapping[int, int]


@dataclass(frozen=True)
class SelfKnownOrder:
    top_cards: tuple[int, ...]
    bottom_cards: tuple[int, ...]
    valid: bool


@dataclass(frozen=True)
class SelfUnknownZoneSummary:
    remaining_card_counts: Mapping[int, int]
    known_order: SelfKnownOrder


@dataclass(frozen=True)
class OpponentPublicSummary:
    public_cards_seen: Mapping[int, int]
    hand_count: int | None
    prize_count: int | None
    public_board: PublicBoard


@dataclass(frozen=True)
class ActorView:
    public_board: PublicBoard
    public_history: tuple[PublicEvent, ...]
    self_hand: Mapping[int, int]
    self_visible_zones: VisibleZoneSummary
    self_unknown_zone: SelfUnknownZoneSummary
    opponent_public: OpponentPublicSummary
    decision_context: DecisionContext
    legal_contract: LegalActionContract
    observation_hash: str


def canonical_hash(payload: Mapping[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode()).hexdigest()
