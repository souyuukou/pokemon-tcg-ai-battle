"""Response compilation — only fixture-validated or builtin-single schemas."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..semantic.response_ir import ValidationResult, validate_response_indices
from ..semantic.option_ir import ResponseIR, SanitizedDecision
from .validated_responses import get_validated_responses

if TYPE_CHECKING:
    from ..semantic.legal_contract import LegalActionContract


def compile_candidate_responses(decision: SanitizedDecision) -> tuple[ResponseIR, ...]:
    return get_validated_responses(decision)


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
]
