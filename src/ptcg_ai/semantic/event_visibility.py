"""Log event visibility — only whitelisted public events enter the ledger."""
from __future__ import annotations

from typing import Any

# LogType values confirmed public (no hidden card identity in actor view).
PUBLIC_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "2",  # TURN_START
        "3",  # TURN_END
        "0",  # SHUFFLE (no card id)
        "1",  # HAS_BASIC_POKEMON
        "5",  # DRAW_REVERSE (opponent drew, no card id to self)
        "7",  # MOVE_CARD_REVERSE
    }
)

# Events that may include card_id only when the card is already public to the actor.
PUBLIC_WITH_CARD_ID_TYPES: frozenset[str] = frozenset(
    {
        "6",  # MOVE_CARD
        "8",  # SWITCH
        "4",  # DRAW (own draw — card id is self-private but actor sees own draw)
    }
)


def is_event_allowed(entry: dict[str, Any], *, your_index: int) -> bool:
    etype = str(entry.get("type", ""))
    if etype in PUBLIC_EVENT_TYPES:
        return True
    if etype in PUBLIC_WITH_CARD_ID_TYPES:
        player = entry.get("playerIndex")
        if etype == "4" and player == your_index:
            return True  # own draw visible to actor
        if etype in ("6", "8") and player is not None:
            return True  # board movement is public
    return False


def project_public_event(entry: dict[str, Any], *, your_index: int) -> dict[str, Any] | None:
    if not is_event_allowed(entry, your_index=your_index):
        return None
    etype = str(entry.get("type", ""))
    out: dict[str, Any] = {"type": etype, "playerIndex": entry.get("playerIndex")}
    if etype == "4" and entry.get("playerIndex") == your_index:
        cid = entry.get("cardId")
        if cid is not None:
            out["cardId"] = int(cid)
    elif etype in PUBLIC_EVENT_TYPES:
        pass
    elif etype in ("6", "8"):
        cid = entry.get("cardId")
        if cid is not None:
            out["cardId"] = int(cid)
    return out
