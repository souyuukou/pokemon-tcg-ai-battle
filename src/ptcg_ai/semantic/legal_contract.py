"""Legal action contract from host select."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LegalActionContract:
    decision_id: str
    request_fingerprint: str
    semantic_schema_key: str
    select_type: int | str | None
    context: int | str | None
    min_count: int
    max_count: int
    option_count: int
    option_fingerprint: str
    response_schema_key: str  # legacy alias = semantic_schema_key


def family_schema_key(
    select_type: int | str | None,
    min_count: int,
    max_count: int,
    option_count: int,
) -> str:
    from .response_ir import classify_selection_mode

    mode = classify_selection_mode(min_count, max_count, option_count)
    return f"family:{select_type}:{min_count}:{max_count}:{mode}"


def semantic_schema_key_from(
    select_type: int | str | None,
    context: int | str | None,
    min_count: int,
    max_count: int,
    option_count: int,
    options: list[dict[str, Any]],
    *,
    empty_response_legal: bool | None = None,
    optional_response_legal: bool | None = None,
) -> str:
    from .schema_keys import SelectionSemanticKey

    return SelectionSemanticKey.from_contract_fields(
        select_type=select_type,
        context=context,
        min_count=min_count,
        max_count=max_count,
        option_count=option_count,
        options=options,
        empty_response_legal=empty_response_legal,
        optional_response_legal=optional_response_legal,
    ).key


def response_schema_key(
    select_type: int | str | None,
    context: int | str | None,
    min_count: int,
    max_count: int,
    option_fingerprint: str,
    *,
    option_count: int = 0,
    options: list[dict[str, Any]] | None = None,
) -> str:
    """Legacy name — returns SelectionSemanticKey (no option fingerprint)."""
    return semantic_schema_key_from(
        select_type,
        context,
        min_count,
        max_count,
        option_count or len(options or []),
        options or [],
    )


def option_fingerprint(options: list[dict[str, Any]]) -> str:
    safe = []
    for opt in options:
        if not isinstance(opt, dict):
            safe.append({"type": None})
            continue
        safe.append(
            {
                "type": opt.get("type"),
                "area": opt.get("area"),
                "index": opt.get("index"),
                "attackId": opt.get("attackId"),
                "cardId": opt.get("cardId"),
            }
        )
    blob = json.dumps(safe, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def request_fingerprint(
    observation_hash: str,
    contract_fields: dict[str, Any],
) -> str:
    payload = {"obs": observation_hash, **contract_fields}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode()).hexdigest()
