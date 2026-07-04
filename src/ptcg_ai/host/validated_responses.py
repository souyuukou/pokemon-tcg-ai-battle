"""Fixture-validated response sets — matrix registry is sole production authority."""
from __future__ import annotations

from ..semantic.action_categories import OptionCategory
from ..semantic.option_ir import (
    ResponseIR,
    SanitizedDecision,
    response_fingerprint,
)
from ..semantic.response_ir import UnsupportedSelectionSchema, classify_selection_mode
from .schema_registry import REGISTRY, expand_patterns


def compile_responses_for_decision(decision: SanitizedDecision) -> tuple[ResponseIR, ...]:
    contract = decision.contract
    sem_key = contract.semantic_schema_key
    mode = classify_selection_mode(contract.min_count, contract.max_count, contract.option_count)
    template = REGISTRY.lookup_for_contract(
        canonical_semantic_key=sem_key,
        select_type=contract.select_type,
        context=contract.context,
        min_count=contract.min_count,
        max_count=contract.max_count,
        option_count=contract.option_count,
    )

    if template is None:
        raise UnsupportedSelectionSchema(sem_key)

    family = REGISTRY.family_key_for_contract(
        select_type=contract.select_type,
        min_count=contract.min_count,
        max_count=contract.max_count,
        option_count=contract.option_count,
    )
    _ = family
    registry_key = template.semantic_schema_key

    patterns = expand_patterns(
        template,
        min_count=contract.min_count,
        max_count=contract.max_count,
        option_count=contract.option_count,
    )
    if not patterns and template.valid_index_patterns:
        patterns = template.valid_index_patterns

    responses: list[ResponseIR] = []
    for pattern in patterns:
        indices = tuple(pattern)
        responses.append(
            ResponseIR(
                request_fingerprint=contract.request_fingerprint,
                semantic_schema_key=registry_key,
                option_indices=indices,
                selection_mode=mode,
                category=_category_for_indices(decision, indices),
                fingerprint=response_fingerprint(indices, mode, registry_key),
            )
        )
    if not responses:
        raise UnsupportedSelectionSchema(sem_key)
    return tuple(responses)


def _category_for_indices(decision: SanitizedDecision, indices: tuple[int, ...]) -> str:
    if not indices:
        return OptionCategory.CONFIRM.value
    idx = indices[0]
    for opt in decision.options:
        if opt.host_index == idx:
            return opt.category
    return OptionCategory.OPAQUE.value


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
    validated = compile_responses_for_decision(decision)
    ranked = sorted(
        validated,
        key=lambda r: (_CATEGORY_PRIORITY.get(r.category, 15), -r.option_indices[0] if r.option_indices else 0),
        reverse=True,
    )
    return ranked[0]


get_validated_responses = compile_responses_for_decision
