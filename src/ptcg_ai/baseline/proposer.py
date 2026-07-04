"""B0 candidate proposer — does not swallow contract exceptions."""
from __future__ import annotations

from ..host.host_response import compile_candidate_responses
from ..semantic.option_ir import ResponseIR, SanitizedDecision


class Proposer:
    def propose(self, decision: SanitizedDecision) -> tuple[ResponseIR, ...]:
        return compile_candidate_responses(decision)
