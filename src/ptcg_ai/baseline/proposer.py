"""B0 candidate proposer — does not swallow contract exceptions."""
from __future__ import annotations

from ..host.validated_responses import compile_responses_for_decision
from ..semantic.option_ir import ResponseIR, SanitizedDecision


class Proposer:
    def propose(self, decision: SanitizedDecision) -> tuple[ResponseIR, ...]:
        return compile_responses_for_decision(decision)
