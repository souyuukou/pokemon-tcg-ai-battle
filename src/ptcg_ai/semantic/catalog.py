"""Card multiset helpers."""
from __future__ import annotations

from collections import Counter
from typing import Any, Mapping


CardMultiset = Mapping[int, int]


def _card_id(card: Any) -> int | None:
    if not isinstance(card, dict):
        return None
    cid = card.get("id") or card.get("cardId")
    if cid is None:
        return None
    try:
        return int(cid)
    except (TypeError, ValueError):
        return None


def card_multiset_from_cards(cards: list[Any]) -> dict[int, int]:
    counts: Counter[int] = Counter()
    for card in cards:
        cid = _card_id(card)
        if cid is not None:
            counts[cid] += 1
    return dict(counts)


def count_cards(zones: Mapping[str, list[Any]]) -> dict[int, int]:
    total: Counter[int] = Counter()
    for cards in zones.values():
        if not isinstance(cards, list):
            continue
        for cid, n in card_multiset_from_cards(cards).items():
            total[cid] += n
    return dict(total)
