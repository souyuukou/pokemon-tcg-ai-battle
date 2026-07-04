"""Production schema registry — semantic families approved via host apply fixtures."""
from __future__ import annotations

import itertools
import json
from dataclasses import dataclass
from pathlib import Path

from ..semantic.legal_contract import family_schema_key
from ..semantic.response_ir import classify_selection_mode

ROOT = Path(__file__).resolve().parents[3]
MATRIX_PATH = ROOT / "docs" / "competition_contract" / "response_schema_matrix.json"


@dataclass(frozen=True)
class SemanticResponseTemplate:
    semantic_schema_key: str
    selection_mode: str
    valid_index_patterns: tuple[tuple[int, ...], ...]
    response_strategy: str | None
    host_apply_verified: bool
    empty_response_legal: bool
    order_sensitive: bool
    duplicates_allowed: bool
    supported_in_production: bool


_BUILTIN_SINGLE = SemanticResponseTemplate(
    semantic_schema_key="__builtin_single_1_1__",
    selection_mode="single",
    valid_index_patterns=(),
    response_strategy="builtin_single",
    host_apply_verified=True,
    empty_response_legal=False,
    order_sensitive=False,
    duplicates_allowed=False,
    supported_in_production=True,
)

_REGISTRY: dict[str, SemanticResponseTemplate] = {}


def _load_matrix() -> None:
    if not MATRIX_PATH.is_file():
        _register_defaults()
        return
    rows = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        _register_defaults()
        return
    for row in rows:
        if not row.get("supported_in_production"):
            continue
        key = row["semantic_schema_key"]
        patterns = row.get("valid_index_patterns") or []
        _REGISTRY[key] = SemanticResponseTemplate(
            semantic_schema_key=key,
            selection_mode=row.get("selection_mode", "single"),
            valid_index_patterns=tuple(tuple(p) for p in patterns),
            response_strategy=row.get("response_strategy"),
            host_apply_verified=bool(row.get("host_apply_verified")),
            empty_response_legal=bool(row.get("empty_response_legal")),
            order_sensitive=bool(row.get("ordering_required")),
            duplicates_allowed=bool(row.get("duplicates_allowed")),
            supported_in_production=True,
        )


def _register_defaults() -> None:
    defaults = [
        SemanticResponseTemplate(
            semantic_schema_key="family:1:0:1:optional_single",
            selection_mode="optional_single",
            valid_index_patterns=(),
            response_strategy="optional_single_dynamic",
            host_apply_verified=True,
            empty_response_legal=True,
            order_sensitive=False,
            duplicates_allowed=False,
            supported_in_production=True,
        ),
        SemanticResponseTemplate(
            semantic_schema_key="family:1:0:2:sequence",
            selection_mode="sequence",
            valid_index_patterns=(),
            response_strategy="bounded_set_dynamic",
            host_apply_verified=True,
            empty_response_legal=True,
            order_sensitive=False,
            duplicates_allowed=False,
            supported_in_production=True,
        ),
        SemanticResponseTemplate(
            semantic_schema_key="family:1:0:3:sequence",
            selection_mode="sequence",
            valid_index_patterns=(),
            response_strategy="bounded_set_dynamic",
            host_apply_verified=True,
            empty_response_legal=True,
            order_sensitive=False,
            duplicates_allowed=False,
            supported_in_production=True,
        ),
        SemanticResponseTemplate(
            semantic_schema_key="family:0:0:0:empty",
            selection_mode="empty",
            valid_index_patterns=((),),
            response_strategy="fixed_patterns",
            host_apply_verified=True,
            empty_response_legal=True,
            order_sensitive=False,
            duplicates_allowed=False,
            supported_in_production=True,
        ),
    ]
    for template in defaults:
        _REGISTRY[template.semantic_schema_key] = template


def get_template(
    semantic_key: str,
    *,
    select_type: int | str | None,
    min_count: int,
    max_count: int,
    option_count: int,
) -> SemanticResponseTemplate | None:
    if semantic_key in _REGISTRY:
        return _REGISTRY[semantic_key]
    family = family_schema_key(select_type, min_count, max_count, option_count)
    if family in _REGISTRY:
        return _REGISTRY[family]
    mode = classify_selection_mode(min_count, max_count, option_count)
    if mode == "single" and min_count == 1 and max_count == 1:
        return _BUILTIN_SINGLE
    return None


def expand_dynamic_patterns(
    template: SemanticResponseTemplate,
    *,
    min_count: int,
    max_count: int,
    option_count: int,
) -> tuple[tuple[int, ...], ...]:
    if template.response_strategy == "builtin_single":
        return tuple((i,) for i in range(option_count))
    if template.response_strategy == "optional_single_dynamic":
        patterns: list[tuple[int, ...]] = []
        if template.empty_response_legal and min_count == 0:
            patterns.append(())
        for i in range(option_count):
            if min_count <= 1 <= max_count:
                patterns.append((i,))
        return tuple(patterns)
    if template.response_strategy == "bounded_set_dynamic":
        patterns = []
        for size in range(min_count, max_count + 1):
            if template.order_sensitive:
                for combo in itertools.permutations(range(option_count), size):
                    patterns.append(tuple(combo))
            else:
                for combo in itertools.combinations(range(option_count), size):
                    patterns.append(tuple(combo))
        return tuple(patterns)
    return template.valid_index_patterns


def register_template(template: SemanticResponseTemplate) -> None:
    _REGISTRY[template.semantic_schema_key] = template


_load_matrix()
