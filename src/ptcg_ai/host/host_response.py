"""Response compilation — validated responses only."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..runtime.exceptions import ContractMismatch
from ..semantic.response_ir import ValidationResult, validate_response_indices
from ..semantic.option_ir import ResponseIR, SanitizedDecision
from ..semantic.schema_keys import ResponseInstanceKey
from .schema_registry import REGISTRY
from .validated_responses import compile_responses_for_decision

if TYPE_CHECKING:
    from ..semantic.legal_contract import LegalActionContract


def compile_candidate_responses(decision: SanitizedDecision) -> tuple[ResponseIR, ...]:
    """Deprecated alias — production code must import validated_responses directly."""
    return compile_responses_for_decision(decision)


def validate_response_instance(decision: SanitizedDecision, response: ResponseIR) -> ValidationResult:
    contract = decision.contract
    if response.request_fingerprint != contract.request_fingerprint:
        return ValidationResult(False, "fingerprint_mismatch")

    instance = ResponseInstanceKey.build(
        request_fingerprint=contract.request_fingerprint,
        option_fingerprint=contract.option_fingerprint,
        response_mode=response.selection_mode,
        option_indices=response.option_indices,
    )
    if instance.request_fingerprint != contract.request_fingerprint:
        return ValidationResult(False, "instance_request_mismatch")
    if instance.option_fingerprint != contract.option_fingerprint:
        return ValidationResult(False, "instance_option_mismatch")

    template = REGISTRY.lookup_for_contract(
        canonical_semantic_key=contract.semantic_schema_key,
        select_type=contract.select_type,
        context=contract.context,
        min_count=contract.min_count,
        max_count=contract.max_count,
        option_count=contract.option_count,
        option_types=tuple(o.raw_type for o in decision.options),
    )
    if template is None:
        return ValidationResult(False, "schema_not_in_registry")

    validated = compile_responses_for_decision(decision)
    allowed = {r.fingerprint for r in validated}
    if response.fingerprint not in allowed:
        return ValidationResult(False, "not_in_registry_validated_set")

    indices = response.option_indices
    if not indices and not template.empty_response_legal:
        return ValidationResult(False, "empty_response_not_legal")
    if len(indices) != len(set(indices)) and not template.duplicates_allowed:
        return ValidationResult(False, "duplicate_indices_not_allowed")

    return validate_response_indices(
        contract.min_count,
        contract.max_count,
        contract.option_count,
        indices,
    )


def require_validated_response(decision: SanitizedDecision, response: ResponseIR) -> None:
    result = validate_response_instance(decision, response)
    if not result.ok:
        raise ContractMismatch(result.reason or "invalid_response_instance")


def validate_response(contract: LegalActionContract, response: ResponseIR) -> ValidationResult:
    if response.request_fingerprint != contract.request_fingerprint:
        return ValidationResult(False, "fingerprint_mismatch")
    return validate_response_indices(
        contract.min_count,
        contract.max_count,
        contract.option_count,
        response.option_indices,
    )


def to_host_response(decision: SanitizedDecision, response: ResponseIR) -> list[int]:
    result = validate_response_instance(decision, response)
    if not result.ok:
        raise ContractMismatch(result.reason or "invalid_host_response")
    return list(response.option_indices)


__all__ = [
    "compile_candidate_responses",
    "require_validated_response",
    "to_host_response",
    "validate_response",
    "validate_response_instance",
]
