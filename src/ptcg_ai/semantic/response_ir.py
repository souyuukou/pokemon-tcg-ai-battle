"""Response IR helpers and schema classification."""
from __future__ import annotations

from dataclasses import dataclass

from .option_ir import ResponseIR, SelectionMode


class UnsupportedSelectionSchema(Exception):
    """Raised when multi-select semantics are not fixture-validated."""


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    reason: str = ""


def classify_selection_mode(min_count: int, max_count: int, option_count: int) -> str:
    if min_count == 0 and max_count == 0:
        return SelectionMode.EMPTY.value
    if min_count == 1 and max_count == 1:
        return SelectionMode.SINGLE.value
    if min_count == 0 and max_count == 1:
        return SelectionMode.OPTIONAL_SINGLE.value
    if min_count > 1 or max_count > 1:
        if min_count == max_count:
            return SelectionMode.SET.value
        return SelectionMode.SEQUENCE.value
    return SelectionMode.OPAQUE.value


def validate_response_indices(
    min_count: int,
    max_count: int,
    option_count: int,
    indices: tuple[int, ...],
) -> ValidationResult:
    if len(indices) < min_count or len(indices) > max_count:
        return ValidationResult(False, "count_out_of_range")
    if len(indices) != len(set(indices)):
        return ValidationResult(False, "duplicate_index")
    for i in indices:
        if i < 0 or i >= option_count:
            return ValidationResult(False, "index_out_of_range")
    return ValidationResult(True)


__all__ = [
    "ResponseIR",
    "SelectionMode",
    "UnsupportedSelectionSchema",
    "ValidationResult",
    "classify_selection_mode",
    "validate_response_indices",
]
