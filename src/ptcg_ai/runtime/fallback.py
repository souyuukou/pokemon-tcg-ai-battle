"""Validated legal fallback — only from fixture-verified response sets."""
from __future__ import annotations

from ..host.validated_responses import operational_fallback
from ..runtime.exceptions import OperationalFailure
from ..semantic.option_ir import ResponseIR, SanitizedDecision


class ValidatedFallbackSelector:
    """Choose only from SchemaRegistry-validated response sets."""

    def choose(self, decision: SanitizedDecision, *, reason: str = "operational") -> ResponseIR:
        try:
            return operational_fallback(decision, reason=reason)
        except Exception as exc:
            raise OperationalFailure(f"no validated fallback: {reason}") from exc


FallbackSelector = ValidatedFallbackSelector
