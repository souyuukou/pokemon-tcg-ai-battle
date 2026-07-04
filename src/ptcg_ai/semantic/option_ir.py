"""Intermediate representations for options and responses."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .action_categories import OptionCategory, categorize_option_type
from .actor_view import ActorView
from .legal_contract import LegalActionContract


class SelectionMode(str, Enum):
    SINGLE = "single"
    SET = "set"
    SEQUENCE = "sequence"
    CONFIRM = "confirm"
    OPAQUE = "opaque"


@dataclass(frozen=True)
class OptionIR:
    host_index: int
    raw_type: int | str | None
    category: str
    card_id: int | None
    attack_id: int | None
    target_area: int | None
    target_index: int | None
    fingerprint: str
    opaque: bool


@dataclass(frozen=True)
class SanitizedDecision:
    actor_view: ActorView
    contract: LegalActionContract
    options: tuple[OptionIR, ...]


@dataclass(frozen=True)
class ResponseIR:
    request_fingerprint: str
    option_indices: tuple[int, ...]
    selection_mode: str
    category: str
    fingerprint: str


def _option_fp(opt: dict[str, Any], index: int) -> str:
    payload = {"i": index, "type": opt.get("type"), "cardId": opt.get("cardId")}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]


def build_option_ir(host_index: int, opt: dict[str, Any], context: int | str | None) -> OptionIR:
    raw_type = opt.get("type")
    cat = categorize_option_type(raw_type, context)
    opaque = cat == OptionCategory.OPAQUE
    card_id = opt.get("cardId") or opt.get("id")
    if card_id is not None:
        try:
            card_id = int(card_id)
        except (TypeError, ValueError):
            card_id = None
    attack_id = opt.get("attackId")
    if attack_id is not None:
        try:
            attack_id = int(attack_id)
        except (TypeError, ValueError):
            attack_id = None
    target_area = opt.get("area")
    if target_area is not None:
        try:
            target_area = int(target_area)
        except (TypeError, ValueError):
            target_area = None
    target_index = opt.get("index")
    if target_index is not None:
        try:
            target_index = int(target_index)
        except (TypeError, ValueError):
            target_index = None
    return OptionIR(
        host_index=host_index,
        raw_type=raw_type,
        category=cat.value,
        card_id=card_id,
        attack_id=attack_id,
        target_area=target_area,
        target_index=target_index,
        fingerprint=_option_fp(opt, host_index),
        opaque=opaque,
    )


def response_fingerprint(indices: tuple[int, ...], mode: str, category: str) -> str:
    payload = {"indices": indices, "mode": mode, "category": category}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
