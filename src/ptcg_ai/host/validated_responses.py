"""Fixture-validated response sets — fallback may only use these."""
from __future__ import annotations

from ..semantic.action_categories import OptionCategory
from ..semantic.option_ir import (
    ResponseIR,
    SanitizedDecision,
    SelectionMode,
    response_fingerprint,
)
from ..semantic.response_ir import UnsupportedSelectionSchema, classify_selection_mode

# Schema keys registered via fixture (categories A/B/C).
VALIDATED_EMPTY_SCHEMAS: frozenset[str] = frozenset()
VALIDATED_OPTIONAL_SINGLE_SCHEMAS: frozenset[str] = frozenset()
VALIDATED_SET_SCHEMAS: frozenset[str] = frozenset()
VALIDATED_SEQUENCE_SCHEMAS: frozenset[str] = frozenset()

# Pre-registered safe responses per schema key (from fixture host-apply validation).
_REGISTRY: dict[str, tuple[ResponseIR, ...]] = {}


def register_validated_responses(schema_key: str, responses: tuple[ResponseIR, ...]) -> None:
    _REGISTRY[schema_key] = responses


def is_builtin_single(contract) -> bool:
    return contract.min_count == 1 and contract.max_count == 1 and contract.option_count >= 1


def compile_single_responses(decision: SanitizedDecision) -> tuple[ResponseIR, ...]:
    contract = decision.contract
    mode = SelectionMode.SINGLE.value
    return tuple(
        ResponseIR(
            request_fingerprint=contract.request_fingerprint,
            option_indices=(opt.host_index,),
            selection_mode=mode,
            category=opt.category,
            fingerprint=response_fingerprint((opt.host_index,), mode, opt.category),
        )
        for opt in decision.options
    )


def compile_empty_response(decision: SanitizedDecision) -> tuple[ResponseIR, ...]:
    contract = decision.contract
    mode = SelectionMode.EMPTY.value
    return (
        ResponseIR(
            request_fingerprint=contract.request_fingerprint,
            option_indices=(),
            selection_mode=mode,
            category=OptionCategory.CONFIRM.value,
            fingerprint=response_fingerprint((), mode, OptionCategory.CONFIRM.value),
        ),
    )


def get_validated_responses(decision: SanitizedDecision) -> tuple[ResponseIR, ...]:
    contract = decision.contract
    key = contract.response_schema_key
    mode = classify_selection_mode(contract.min_count, contract.max_count, contract.option_count)

    if mode == SelectionMode.SINGLE.value:
        if is_builtin_single(contract):
            return compile_single_responses(decision)
        raise UnsupportedSelectionSchema(key)

    if mode == SelectionMode.EMPTY.value:
        if key not in VALIDATED_EMPTY_SCHEMAS and key not in _REGISTRY:
            raise UnsupportedSelectionSchema(key)
        if key in _REGISTRY:
            return _REGISTRY[key]
        return compile_empty_response(decision)

    if mode == SelectionMode.OPTIONAL_SINGLE.value:
        if key not in VALIDATED_OPTIONAL_SINGLE_SCHEMAS and key not in _REGISTRY:
            raise UnsupportedSelectionSchema(key)
        return _REGISTRY[key]

    if mode == SelectionMode.SET.value:
        if key not in VALIDATED_SET_SCHEMAS and key not in _REGISTRY:
            raise UnsupportedSelectionSchema(key)
        return _REGISTRY[key]

    if mode == SelectionMode.SEQUENCE.value:
        if key not in VALIDATED_SEQUENCE_SCHEMAS and key not in _REGISTRY:
            raise UnsupportedSelectionSchema(key)
        return _REGISTRY[key]

    raise UnsupportedSelectionSchema(key)


_CATEGORY_PRIORITY: dict[str, int] = {
    OptionCategory.ATTACK.value: 80,
    OptionCategory.TARGET_SELECT.value: 50,
    OptionCategory.EVOLVE.value: 45,
    OptionCategory.ATTACH.value: 40,
    OptionCategory.PLAY.value: 30,
    OptionCategory.RETREAT.value: 10,
    OptionCategory.END.value: 0,
    OptionCategory.CONFIRM.value: 20,
    OptionCategory.OPAQUE.value: 5,
}


def operational_fallback(decision: SanitizedDecision, *, reason: str) -> ResponseIR:
    """Pick from validated response set only — never fabricate indices."""
    validated = get_validated_responses(decision)
    if not validated:
        raise UnsupportedSelectionSchema(decision.contract.response_schema_key)
    ranked = sorted(
        validated,
        key=lambda r: (_CATEGORY_PRIORITY.get(r.category, 15), -r.option_indices[0] if r.option_indices else 0),
        reverse=True,
    )
    return ranked[0]
