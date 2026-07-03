"""Strip opponent hidden information before AI inputs.

Only public observation and own private observation may reach models,
wire encoding, and native search features.
"""
from __future__ import annotations

import copy
from typing import Any


def _mask_hidden_prize(prize: list[Any]) -> list[Any]:
    out: list[Any] = []
    for card in prize:
        if card is None:
            out.append(None)
        elif isinstance(card, dict):
            out.append({"id": int(card.get("id") or 0)})
        else:
            out.append({"id": 0})
    return out


def _sanitize_player(player: dict[str, Any], *, own: bool) -> dict[str, Any]:
    p = dict(player)
    if own:
        return p
    hand_count = int(p.get("handCount") or len(p.get("hand") or []))
    p["handCount"] = hand_count
    p["hand"] = []
    p["prize"] = _mask_hidden_prize(list(p.get("prize") or []))
    p.pop("deck", None)
    return p


def sanitize_observation(obs: dict[str, Any]) -> dict[str, Any]:
    """Return a copy safe for AI inputs (public + own private only)."""
    if not obs:
        return {}
    out = copy.deepcopy(obs)
    current = out.get("current")
    if not isinstance(current, dict):
        return out
    your_index = int(current.get("yourIndex") or 0)
    players = list(current.get("players") or [{}, {}])
    while len(players) < 2:
        players.append({})
    current["players"] = [
        _sanitize_player(players[0], own=(your_index == 0)),
        _sanitize_player(players[1], own=(your_index == 1)),
    ]
    out.pop("search_begin_input", None)
    return out
