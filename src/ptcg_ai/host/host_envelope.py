"""Host call envelope — only preflight surface exposed to runtime."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .raw_observation import RawObservation


class HostCallKind(str, Enum):
    DECK_SELECTION = "deck_selection"
    IN_GAME = "in_game"
    TERMINAL = "terminal"


@dataclass(frozen=True)
class HostCallEnvelope:
    is_deck_selection: bool
    is_terminal: bool
    authoritative_remaining_time: float | None
    legal_option_count: int
    host_call_kind: HostCallKind


def preflight(raw: RawObservation) -> HostCallEnvelope:
    data = raw.data
    select = data.get("select")
    current = data.get("current") if isinstance(data.get("current"), dict) else {}
    result = current.get("result")
    is_terminal = result is not None and int(result) >= 0

    # Priority: TERMINAL > DECK_SELECTION > IN_GAME
    if is_terminal:
        return HostCallEnvelope(
            is_deck_selection=False,
            is_terminal=True,
            authoritative_remaining_time=_parse_time(data.get("remainingOverageTime")),
            legal_option_count=0 if select is None else len((select or {}).get("option") or []),
            host_call_kind=HostCallKind.TERMINAL,
        )

    if select is None:
        return HostCallEnvelope(
            is_deck_selection=True,
            is_terminal=False,
            authoritative_remaining_time=_parse_time(data.get("remainingOverageTime")),
            legal_option_count=0,
            host_call_kind=HostCallKind.DECK_SELECTION,
        )

    sel = select if isinstance(select, dict) else {}
    opts = sel.get("option") or []
    return HostCallEnvelope(
        is_deck_selection=False,
        is_terminal=False,
        authoritative_remaining_time=_parse_time(data.get("remainingOverageTime")),
        legal_option_count=len(opts),
        host_call_kind=HostCallKind.IN_GAME,
    )


def _parse_time(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
