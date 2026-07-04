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
    select_type: int | str | None
    context: int | str | None
    min_count: int
    max_count: int
    option_count: int
    option_fingerprint: str
    response_schema_key: str


def response_schema_key(
    select_type: int | str | None,
    context: int | str | None,
    min_count: int,
    max_count: int,
    option_fingerprint: str,
) -> str:
    payload = {
        "select_type": select_type,
        "context": context,
        "min_count": min_count,
        "max_count": max_count,
        "option_fp": option_fingerprint,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


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
