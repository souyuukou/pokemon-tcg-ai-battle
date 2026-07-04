"""T5: Card conservation."""
from __future__ import annotations

from ptcg_ai.host.observation_projector import project_observation
from ptcg_ai.semantic.actor_view import SelfDeckManifest
from ptcg_ai.semantic.self_card_ledger import build_visible_zones, compute_unknown_zone, verify_conservation


def test_conservation_holds_for_visible_zones():
    manifest = SelfDeckManifest({65: 60})
    raw = {
        "current": {
            "yourIndex": 0,
            "players": [
                {
                    "hand": [{"id": 65}] * 5,
                    "active": [{"id": 65, "hp": 60}],
                    "bench": [],
                    "discard": [],
                    "deckCount": 48,
                    "prize": [None] * 6,
                },
                {"handCount": 0, "prize": [None] * 6, "deckCount": 48, "active": [], "bench": [], "discard": []},
            ],
        },
        "select": None,
        "logs": [],
    }
    projected = project_observation(raw)
    player = projected.players[0]
    visible = build_visible_zones(player)
    unknown = compute_unknown_zone(
        manifest, visible, deck_count=48, prize_face_down=6, known_order_valid=False
    )
    assert unknown.conservation_verified
    assert verify_conservation(manifest, visible, unknown, 48, 6)
