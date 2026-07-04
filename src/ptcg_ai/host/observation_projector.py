"""Whitelist projection from raw host observation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..semantic.event_visibility import project_public_event


@dataclass(frozen=True)
class ProjectedCard:
    card_id: int
    damage: int | None = None
    maximum_hp: int | None = None
    remaining_hp: int | None = None
    attached_energy: tuple[tuple[int, int], ...] = ()
    attached_tool_ids: tuple[int, ...] = ()
    status: tuple[str, ...] = ()
    retreat_cost: int | None = None
    stage: int | None = None
    can_attack: bool | None = None


@dataclass(frozen=True)
class ProjectedPlayer:
    hand: tuple[ProjectedCard, ...]
    hand_count: int | None
    active: tuple[ProjectedCard, ...]
    bench: tuple[ProjectedCard, ...]
    discard: tuple[ProjectedCard, ...]
    deck_count: int
    prize_face_down_count: int
    prize_known_count: int


@dataclass(frozen=True)
class ProjectedSelect:
    select_type: int | str | None
    context: int | str | None
    min_count: int
    max_count: int
    options: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class ProjectedObservation:
    your_index: int
    turn: int | None
    first_player: int | None
    result: int
    players: tuple[ProjectedPlayer, ProjectedPlayer]
    select: ProjectedSelect | None
    public_events: tuple[dict[str, Any], ...]
    remaining_overage_time: float | None


_OPTION_FIELDS = frozenset(
    {"type", "area", "index", "attackId", "cardId", "id", "playerIndex", "energyIndex", "toolIndex", "count"}
)


def _safe_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _project_card(raw: dict[str, Any]) -> ProjectedCard | None:
    cid = _safe_int(raw.get("id") or raw.get("cardId"))
    if cid is None:
        return None
    energy_summary: list[tuple[int, int]] = []
    for e in raw.get("energy") or []:
        if isinstance(e, dict):
            et = _safe_int(e.get("type") or e.get("energyType"))
            if et is not None:
                energy_summary.append((et, 1))
    tools: list[int] = []
    for t in raw.get("tool") or raw.get("tools") or []:
        if isinstance(t, dict):
            tid = _safe_int(t.get("id") or t.get("cardId"))
            if tid is not None:
                tools.append(tid)
    hp = _safe_int(raw.get("hp") or raw.get("maximumHp"))
    damage = _safe_int(raw.get("damage"))
    remaining = hp - damage if hp is not None and damage is not None else hp
    status: list[str] = []
    for sc in raw.get("specialCondition") or raw.get("specialConditions") or []:
        status.append(str(sc))
    return ProjectedCard(
        card_id=cid,
        damage=damage,
        maximum_hp=hp,
        remaining_hp=remaining,
        attached_energy=tuple(energy_summary),
        attached_tool_ids=tuple(tools),
        status=tuple(status),
        retreat_cost=_safe_int(raw.get("retreatCost")),
        stage=_safe_int(raw.get("stage")),
        can_attack=raw.get("canAttack") if isinstance(raw.get("canAttack"), bool) else None,
    )


def _project_cards(raw_list: list[Any]) -> tuple[ProjectedCard, ...]:
    out: list[ProjectedCard] = []
    for item in raw_list or []:
        if isinstance(item, dict):
            c = _project_card(item)
            if c is not None:
                out.append(c)
    return tuple(out)


def _project_player(raw: dict[str, Any], *, own: bool) -> ProjectedPlayer:
    hand_cards = _project_cards(list(raw.get("hand") or [])) if own else ()
    hand_count = len(hand_cards) if own else _safe_int(raw.get("handCount")) or 0
    prize_list = list(raw.get("prize") or [])
    face_down = sum(1 for p in prize_list if p is None or not isinstance(p, dict))
    known = sum(1 for p in prize_list if isinstance(p, dict) and p.get("id") is not None)
    return ProjectedPlayer(
        hand=hand_cards,
        hand_count=hand_count,
        active=_project_cards(list(raw.get("active") or [])),
        bench=_project_cards(list(raw.get("bench") or [])),
        discard=_project_cards(list(raw.get("discard") or [])),
        deck_count=_safe_int(raw.get("deckCount")) or 0,
        prize_face_down_count=face_down,
        prize_known_count=known if own else 0,
    )


def _project_option(raw: dict[str, Any]) -> dict[str, Any]:
    return {k: raw[k] for k in _OPTION_FIELDS if k in raw}


def project_observation(raw: dict[str, Any]) -> ProjectedObservation:
    current = raw.get("current") if isinstance(raw.get("current"), dict) else {}
    your_index = _safe_int(current.get("yourIndex")) or 0
    players_raw = list(current.get("players") or [{}, {}])
    while len(players_raw) < 2:
        players_raw.append({})
    players = tuple(
        _project_player(players_raw[i] if isinstance(players_raw[i], dict) else {}, own=(i == your_index))
        for i in range(2)
    )
    select_raw = raw.get("select")
    select: ProjectedSelect | None = None
    if isinstance(select_raw, dict):
        opts = tuple(
            _project_option(o) for o in (select_raw.get("option") or []) if isinstance(o, dict)
        )
        select = ProjectedSelect(
            select_type=select_raw.get("type"),
            context=select_raw.get("context"),
            min_count=_safe_int(select_raw.get("minCount")) or 0,
            max_count=_safe_int(select_raw.get("maxCount")) or 0,
            options=opts,
        )
    events: list[dict[str, Any]] = []
    for entry in raw.get("logs") or []:
        if isinstance(entry, dict):
            projected = project_public_event(entry, your_index=your_index)
            if projected is not None:
                events.append(projected)
    rot: float | None = None
    if raw.get("remainingOverageTime") is not None:
        try:
            rot = float(raw["remainingOverageTime"])
        except (TypeError, ValueError):
            rot = None
    return ProjectedObservation(
        your_index=your_index,
        turn=_safe_int(current.get("turn")),
        first_player=_safe_int(current.get("firstPlayer")),
        result=_safe_int(current.get("result")) if current.get("result") is not None else -1,
        players=players,
        select=select,
        public_events=tuple(events),
        remaining_overage_time=rot,
    )
