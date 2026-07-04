"""Self deck card conservation accounting."""
from __future__ import annotations

from collections import Counter
from typing import Any

from .actor_view import (
    SelfDeckManifest,
    SelfKnownOrder,
    SelfUnknownZoneSummary,
    VisibleZoneSummary,
)
from ..host.observation_projector import ProjectedCard, ProjectedPlayer


def _count_cards(cards: tuple[ProjectedCard, ...]) -> dict[int, int]:
    counts: Counter[int] = Counter()
    for c in cards:
        counts[c.card_id] += 1
        for _et, n in c.attached_energy:
            pass  # energy card ids not always visible — skip from conservation
    return dict(counts)


def build_visible_zones(player: ProjectedPlayer) -> VisibleZoneSummary:
    hand = _count_cards(player.hand)
    active = _count_cards(player.active)
    bench = _count_cards(player.bench)
    discard = _count_cards(player.discard)
    attached_energy: Counter[int] = Counter()
    for zone in (player.active, player.bench):
        for card in zone:
            for et, _ in card.attached_energy:
                attached_energy[et] += 1
    return VisibleZoneSummary(
        hand=hand,
        active=active,
        bench=bench,
        discard=discard,
        lost_or_removed={},
        prizes_taken={},
        attached_energy=dict(attached_energy),
    )


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
    unknown_total = sum(remaining.values())
    slot_total = deck_count + prize_face_down
    conservation_verified = unknown_total == slot_total if slot_total > 0 else unknown_total == 0
    return SelfUnknownZoneSummary(
        remaining_card_counts=dict(remaining),
        known_order=SelfKnownOrder(top_cards=(), bottom_cards=(), valid=known_order_valid and slot_total > 0),
        conservation_verified=conservation_verified,
    )


def verify_conservation(
    manifest: SelfDeckManifest,
    visible: VisibleZoneSummary,
    unknown: SelfUnknownZoneSummary,
    deck_count: int,
    prize_face_down: int,
) -> bool:
    if not unknown.conservation_verified:
        return False
    total_visible = sum(visible.hand.values()) + sum(visible.active.values())
    total_visible += sum(visible.bench.values()) + sum(visible.discard.values())
    total_visible += sum(visible.lost_or_removed.values()) + sum(visible.prizes_taken.values())
    total_unknown = sum(unknown.remaining_card_counts.values())
    expected = sum(manifest.card_counts.values())
    slot_total = deck_count + prize_face_down
    return total_visible + total_unknown == expected and total_unknown == slot_total
