"""T5: Card conservation."""
from __future__ import annotations

from ptcg_ai.semantic.actor_view import SelfDeckManifest
from ptcg_ai.semantic.self_card_ledger import build_visible_zones, compute_unknown_zone, verify_conservation


def test_conservation_holds_for_visible_zones():
    manifest = SelfDeckManifest({65: 60})
    player = {
        "hand": [{"id": 65}] * 5,
        "active": [{"id": 65}],
        "bench": [],
        "discard": [],
        "deckCount": 54,
        "prize": [None] * 6,
    }
    visible = build_visible_zones(player)
    unknown = compute_unknown_zone(manifest, visible, deck_count=54, prize_face_down=6, known_order_valid=False)
    assert verify_conservation(manifest, visible, unknown, 54, 6)
