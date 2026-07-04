"""Decode host option objects to safe fields."""
from __future__ import annotations

from typing import Any


def safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def decode_option(opt: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": safe_int(opt.get("type")),
        "area": safe_int(opt.get("area")),
        "index": safe_int(opt.get("index")),
        "attackId": safe_int(opt.get("attackId")),
        "cardId": safe_int(opt.get("cardId") or opt.get("id")),
        "playerIndex": safe_int(opt.get("playerIndex")),
    }
