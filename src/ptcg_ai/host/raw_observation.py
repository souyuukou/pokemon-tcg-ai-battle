"""Raw host observation wrapper — only host package may use this."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any


REDACT_KEYS = frozenset(
    {
        "search_begin_input",
    }
)


@dataclass(frozen=True)
class RawObservation:
    data: dict[str, Any]

    @classmethod
    def from_dict(cls, obs_dict: dict[str, Any]) -> RawObservation:
        return cls(data=obs_dict)


def redact_for_fixture(obs_dict: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(obs_dict)
    for key in REDACT_KEYS:
        out.pop(key, None)
    return out


def strip_hidden_from_raw(obs_dict: dict[str, Any]) -> dict[str, Any]:
    """Remove fields that must not flow to policy (host_adapter internal use)."""
    out = copy.deepcopy(obs_dict)
    out.pop("search_begin_input", None)
    current = out.get("current")
    if not isinstance(current, dict):
        return out
    your_index = int(current.get("yourIndex") or 0)
    players = list(current.get("players") or [{}, {}])
    while len(players) < 2:
        players.append({})
    sanitized_players = []
    for idx, player in enumerate(players[:2]):
        p = dict(player) if isinstance(player, dict) else {}
        if idx != your_index:
            hand_count = int(p.get("handCount") or len(p.get("hand") or []))
            p["handCount"] = hand_count
            p["hand"] = []
            p["prize"] = [None for _ in (p.get("prize") or [])]
            p.pop("deck", None)
        sanitized_players.append(p)
    current["players"] = sanitized_players
    out["current"] = current
    return out
