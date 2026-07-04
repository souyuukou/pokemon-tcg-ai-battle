"""Host call envelope — only preflight surface exposed to runtime."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .raw_observation import RawObservation


@dataclass(frozen=True)
class HostCallEnvelope:
    is_deck_selection: bool
    is_terminal: bool
    authoritative_remaining_time: float | None
    legal_option_count: int
    host_call_kind: str  # deck_selection | in_game | terminal


def preflight(raw: RawObservation) -> HostCallEnvelope:
    data = raw.data
    select = data.get("select")
    current = data.get("current") if isinstance(data.get("current"), dict) else {}
    result = current.get("result")
    is_terminal = result is not None and int(result) >= 0
    if select is None:
        return HostCallEnvelope(
            is_deck_selection=True,
            is_terminal=is_terminal,
            authoritative_remaining_time=_parse_time(data.get("remainingOverageTime")),
            legal_option_count=0,
            host_call_kind="deck_selection" if not is_terminal else "terminal",
        )
    sel = select if isinstance(select, dict) else {}
    opts = sel.get("option") or []
    return HostCallEnvelope(
        is_deck_selection=False,
        is_terminal=is_terminal,
        authoritative_remaining_time=_parse_time(data.get("remainingOverageTime")),
        legal_option_count=len(opts),
        host_call_kind="terminal" if is_terminal else "in_game",
    )


def _parse_time(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
