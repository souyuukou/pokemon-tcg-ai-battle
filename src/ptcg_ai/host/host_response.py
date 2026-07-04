"""Response compilation and host index list generation."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..semantic.action_categories import OptionCategory
from ..semantic.option_ir import (
    ResponseIR,
    SanitizedDecision,
    SelectionMode,
    response_fingerprint,
)
from ..semantic.response_ir import (
    UnsupportedSelectionSchema,
    ValidationResult,
    classify_selection_mode,
    validate_response_indices,
)

if TYPE_CHECKING:
    from ..semantic.legal_contract import LegalActionContract


# Fixture-validated independent-set schemas (empty until probe adds more).
VALIDATED_SET_SCHEMAS: frozenset[str] = frozenset()
VALIDATED_SEQUENCE_SCHEMAS: frozenset[str] = frozenset()


def compile_candidate_responses(decision: SanitizedDecision) -> tuple[ResponseIR, ...]:
    contract = decision.contract
    mode = classify_selection_mode(contract.min_count, contract.max_count, contract.option_count)
    responses: list[ResponseIR] = []

    if mode == SelectionMode.SINGLE.value or mode == SelectionMode.CONFIRM.value:
        for opt in decision.options:
            indices = (opt.host_index,)
            responses.append(
                ResponseIR(
                    request_fingerprint=contract.request_fingerprint,
                    option_indices=indices,
                    selection_mode=mode,
                    category=opt.category,
                    fingerprint=response_fingerprint(indices, mode, opt.category),
                )
            )
        return tuple(responses)

    if mode == SelectionMode.SET.value:
        if contract.response_schema_key not in VALIDATED_SET_SCHEMAS:
            raise UnsupportedSelectionSchema(contract.response_schema_key)
        return _compile_independent_set(decision)

    raise UnsupportedSelectionSchema(contract.response_schema_key)


def _compile_independent_set(decision: SanitizedDecision) -> tuple[ResponseIR, ...]:
    contract = decision.contract
    lo, hi = contract.min_count, contract.max_count
    indices_list: list[tuple[int, ...]] = []

    def backtrack(start: int, chosen: list[int]) -> None:
        if len(chosen) >= lo:
            indices_list.append(tuple(chosen))
        if len(chosen) == hi:
            return
        for i in range(start, len(decision.options)):
            chosen.append(decision.options[i].host_index)
            backtrack(i + 1, chosen)
            chosen.pop()

    backtrack(0, [])
    mode = SelectionMode.SET.value
    return tuple(
        ResponseIR(
            request_fingerprint=contract.request_fingerprint,
            option_indices=idxs,
            selection_mode=mode,
            category=OptionCategory.TARGET_SELECT.value,
            fingerprint=response_fingerprint(idxs, mode, OptionCategory.TARGET_SELECT.value),
        )
        for idxs in indices_list
    )


def validate_response(contract: LegalActionContract, response: ResponseIR) -> ValidationResult:
    if response.request_fingerprint != contract.request_fingerprint:
        return ValidationResult(False, "fingerprint_mismatch")
    return validate_response_indices(
        contract.min_count,
        contract.max_count,
        contract.option_count,
        response.option_indices,
    )


def to_host_response(contract: LegalActionContract, response: ResponseIR) -> list[int]:
    result = validate_response(contract, response)
    if not result.ok:
        raise ValueError(result.reason)
    return list(response.option_indices)


__all__ = [
    "compile_candidate_responses",
    "to_host_response",
    "validate_response",
    "VALIDATED_SET_SCHEMAS",
    "VALIDATED_SEQUENCE_SCHEMAS",
]
