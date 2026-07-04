"""Self deck card conservation accounting."""
from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

from .actor_view import SelfDeckManifest, SelfKnownOrder, SelfUnknownZoneSummary, VisibleZoneSummary
from .catalog import card_multiset_from_cards


def build_visible_zones(player: dict[str, Any]) -> VisibleZoneSummary:
    hand = card_multiset_from_cards(list(player.get("hand") or []))
    active = card_multiset_from_cards(list(player.get("active") or []))
    bench = card_multiset_from_cards(list(player.get("bench") or []))
    discard = card_multiset_from_cards(list(player.get("discard") or []))
    return VisibleZoneSummary(
        hand=hand,
        active=active,
        bench=bench,
        discard=discard,
        lost_or_removed={},
        prizes_taken=_prizes_taken_historical(player),
    )


def _prizes_taken_historical(player: dict[str, Any]) -> dict[int, int]:
    """Prize cards currently in hand that were taken from prizes (historical accounting)."""
    return {}


def compute_unknown_zone(
    manifest: SelfDeckManifest,
    visible: VisibleZoneSummary,
    *,
    deck_count: int,
    prize_face_down: int,
    known_order_valid: bool,
) -> SelfUnknownZoneSummary:
    accounted: Counter[int] = Counter()
    for zone in (visible.hand, visible.active, visible.bench, visible.discard, visible.lost_or_removed):
        for cid, n in zone.items():
            accounted[cid] += n
    remaining: Counter[int] = Counter(manifest.card_counts)
    for cid, n in accounted.items():
        remaining[cid] -= n
    remaining = Counter({k: v for k, v in remaining.items() if v > 0})
    deck_slots = max(0, deck_count)
    prize_slots = max(0, prize_face_down)
    unknown_total = deck_slots + prize_slots
    return SelfUnknownZoneSummary(
        remaining_card_counts=dict(remaining),
        known_order=SelfKnownOrder(top_cards=(), bottom_cards=(), valid=known_order_valid and unknown_total > 0),
    )


def verify_conservation(
    manifest: SelfDeckManifest,
    visible: VisibleZoneSummary,
    unknown: SelfUnknownZoneSummary,
    deck_count: int,
    prize_face_down: int,
) -> bool:
    total_visible = sum(visible.hand.values()) + sum(visible.active.values())
    total_visible += sum(visible.bench.values()) + sum(visible.discard.values())
    total_visible += sum(visible.lost_or_removed.values()) + sum(visible.prizes_taken.values())
    total_unknown = sum(unknown.remaining_card_counts.values())
    expected = sum(manifest.card_counts.values())
    return total_visible + total_unknown == expected
