"""Binary observation encoder for the native PVS engine."""
from __future__ import annotations

import struct
from typing import Any

from observation_sanitize import sanitize_observation

MAGIC = b"PKOBS1\x00\x00"
VERSION = 2
FLAG_HAS_SELECT = 1
FLAG_HAS_SEARCH_BEGIN = 2
MISSING_I32 = -(2 ** 31)
MISSING_I16 = -(2 ** 15)


def _opt_i32(value: Any) -> int:
    return int(value) if value is not None else MISSING_I32


def _opt_i16(value: Any) -> int:
    return int(value) if value is not None else MISSING_I16


def _pack_pokemon(slot: dict[str, Any] | None) -> bytes:
    if slot is None:
        return b"".join([
            struct.pack("<B", 2),
            struct.pack("<i", 0),
            struct.pack("<h", 0),
            struct.pack("<BB", 0, 0),
            struct.pack("<B", 0),
        ])
    attached: list[int] = []
    for key in ("energyCards", "tools"):
        for card in slot.get(key) or []:
            if card and card.get("id"):
                attached.append(int(card["id"]))
    energies = slot.get("energies") or []
    pre_evo = slot.get("preEvolution") or []
    chunks = [
        struct.pack("<B", 1),
        struct.pack("<i", int(slot.get("id") or 0)),
        struct.pack("<h", int(slot.get("hp") or 0)),
        struct.pack("<B", len(energies)),
        struct.pack("<B", len(pre_evo)),
        struct.pack("<B", len(attached)),
    ]
    chunks.extend(struct.pack("<i", card_id) for card_id in attached)
    return b"".join(chunks)


def _pack_card(card: dict[str, Any]) -> bytes:
    return struct.pack("<i", int(card.get("id") or 0))


def _pack_player(player: dict[str, Any]) -> bytes:
    prize = player.get("prize") or []
    hand = player.get("hand") or []
    active = player.get("active") or []
    bench = player.get("bench") or []
    discard = player.get("discard") or []
    chunks = [
        struct.pack("<hh", int(player.get("deckCount") or 0), int(player.get("handCount") or 0)),
        struct.pack("<B", len(prize)),
    ]
    chunks.extend(
        struct.pack("<i", 0 if card is None else int(card.get("id") or 0))
        for card in prize
    )
    chunks.append(struct.pack("<B", len(hand)))
    chunks.extend(_pack_card(card) for card in hand)
    chunks.append(struct.pack("<B", len(active)))
    chunks.extend(_pack_pokemon(slot) for slot in active)
    chunks.append(struct.pack("<B", len(bench)))
    chunks.extend(_pack_pokemon(slot) for slot in bench)
    chunks.append(struct.pack("<B", len(discard)))
    chunks.extend(_pack_card(card) for card in discard)
    return b"".join(chunks)


def _pack_option(option: dict[str, Any]) -> bytes:
    base = struct.pack(
        "<hiihhhhhhhh",
        int(option.get("type", -1)),
        _opt_i32(option.get("cardId")),
        _opt_i32(option.get("attackId")),
        _opt_i16(option.get("area")),
        _opt_i16(option.get("index")),
        _opt_i16(option.get("playerIndex")),
        _opt_i16(option.get("inPlayArea")),
        _opt_i16(option.get("inPlayIndex")),
        _opt_i16(option.get("number")),
        _opt_i16(option.get("count")),
        _opt_i16(option.get("specialConditionType")),
    )
    return base + struct.pack(
        "<hhi",
        _opt_i16(option.get("toolIndex")),
        _opt_i16(option.get("energyIndex")),
        _opt_i32(option.get("serial")),
    )


def _zone_cards(current: dict[str, Any], key: str) -> list[tuple[int, int]]:
    cards: list[tuple[int, int]] = []
    zone = current.get(key)
    if not zone:
        return cards
    for card in zone:
        if card is None:
            cards.append((0, -1))
            continue
        cards.append((int(card.get("id") or 0), int(card.get("playerIndex", -1))))
    return cards


def encode_observation(obs: dict[str, Any]) -> bytes:
    obs = sanitize_observation(obs)
    flags = 0
    select = obs.get("select")
    if select is not None:
        flags |= FLAG_HAS_SELECT
    search_begin = obs.get("search_begin_input") or ""
    if search_begin:
        flags |= FLAG_HAS_SEARCH_BEGIN
    remain_raw = obs.get("remainingOverageTime")
    remain = 600.0 if remain_raw is None else float(remain_raw)
    current = obs.get("current") or {}
    players = current.get("players") or [{}, {}]
    if len(players) < 2:
        players = list(players) + [{}] * (2 - len(players))
    stadium_cards = _zone_cards(current, "stadium")
    looking_cards = _zone_cards(current, "looking")
    chunks = [
        MAGIC,
        struct.pack("<II", VERSION, flags),
        struct.pack("<d", remain),
    ]
    if flags & FLAG_HAS_SEARCH_BEGIN:
        encoded = search_begin.encode("ascii")
        chunks.extend([struct.pack("<I", len(encoded)), encoded])
    chunks.extend([
        struct.pack(
            "<bbbhh",
            int(current.get("result", -1)),
            int(current.get("yourIndex") or 0),
            int(current.get("firstPlayer", -1)),
            int(current.get("turn") or 0),
            int(current.get("turnActionCount") or 0),
        ),
        struct.pack("<H", len(stadium_cards)),
    ])
    chunks.extend(
        struct.pack("<ib", card_id, player_index)
        for card_id, player_index in stadium_cards
    )
    chunks.append(struct.pack("<H", len(looking_cards)))
    chunks.extend(
        struct.pack("<ib", card_id, player_index)
        for card_id, player_index in looking_cards
    )
    chunks.extend([_pack_player(players[0]), _pack_player(players[1])])
    if flags & FLAG_HAS_SELECT:
        options = select.get("option") or []
        chunks.extend([
            struct.pack(
                "<hbbH",
                int(select.get("context", -1)),
                int(select.get("minCount") or 0),
                int(select.get("maxCount") or 0),
                len(options),
            ),
        ])
        chunks.extend(_pack_option(option) for option in options)
    return b"".join(chunks)
