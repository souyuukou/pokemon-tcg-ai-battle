"""SelectionSemanticKey vs ResponseInstanceKey — two-layer response schema identity."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .response_ir import classify_selection_mode


def _option_type_pattern(options: list[dict[str, Any]]) -> tuple[int | str | None, ...]:
    pattern: list[int | str | None] = []
    for opt in options:
        if isinstance(opt, dict):
            pattern.append(opt.get("type"))
        else:
            pattern.append(None)
    return tuple(pattern)


def _option_category_pattern(options: list[dict[str, Any]], context: int | str | None) -> tuple[str, ...]:
    from .action_categories import categorize_option_type

    return tuple(categorize_option_type(o.get("type") if isinstance(o, dict) else None, context).value for o in options)


@dataclass(frozen=True)
class SelectionSemanticKey:
    key: str
    select_type: int | str | None
    context: int | str | None
    min_count: int
    max_count: int
    selection_mode: str
    option_type_pattern: tuple[int | str | None, ...]
    option_category_pattern: tuple[str, ...]
    order_sensitive: bool
    duplicates_allowed: bool
    empty_response_legal: bool | None
    optional_response_legal: bool | None

    @classmethod
    def from_contract_fields(
        cls,
        *,
        select_type: int | str | None,
        context: int | str | None,
        min_count: int,
        max_count: int,
        option_count: int,
        options: list[dict[str, Any]],
        empty_response_legal: bool | None = None,
        optional_response_legal: bool | None = None,
        order_sensitive: bool = False,
        duplicates_allowed: bool = False,
    ) -> SelectionSemanticKey:
        mode = classify_selection_mode(min_count, max_count, option_count)
        type_pat = _option_type_pattern(options)
        cat_pat = _option_category_pattern(options, context)
        if mode in ("set", "sequence") and min_count == max_count and min_count > 1:
            order_sensitive = mode == "sequence"
        payload = {
            "select_type": select_type,
            "context": context,
            "min_count": min_count,
            "max_count": max_count,
            "selection_mode": mode,
            "option_type_pattern": type_pat,
            "option_category_pattern": cat_pat,
            "order_sensitive": order_sensitive,
            "duplicates_allowed": duplicates_allowed,
            "empty_response_legal": empty_response_legal,
            "optional_response_legal": optional_response_legal,
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        key = hashlib.sha256(blob.encode()).hexdigest()[:16]
        return cls(
            key=key,
            select_type=select_type,
            context=context,
            min_count=min_count,
            max_count=max_count,
            selection_mode=mode,
            option_type_pattern=type_pat,
            option_category_pattern=cat_pat,
            order_sensitive=order_sensitive,
            duplicates_allowed=duplicates_allowed,
            empty_response_legal=empty_response_legal,
            optional_response_legal=optional_response_legal,
        )


@dataclass(frozen=True)
class ResponseInstanceKey:
    key: str
    request_fingerprint: str
    option_fingerprint: str
    response_mode: str

    @classmethod
    def build(
        cls,
        *,
        request_fingerprint: str,
        option_fingerprint: str,
        response_mode: str,
        option_indices: tuple[int, ...],
    ) -> ResponseInstanceKey:
        payload = {
            "request_fp": request_fingerprint,
            "option_fp": option_fingerprint,
            "response_mode": response_mode,
            "indices": option_indices,
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return cls(
            key=hashlib.sha256(blob.encode()).hexdigest()[:16],
            request_fingerprint=request_fingerprint,
            option_fingerprint=option_fingerprint,
            response_mode=response_mode,
        )
