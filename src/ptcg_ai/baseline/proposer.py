"""B0 candidate proposer."""
from __future__ import annotations

from ..host.host_response import compile_candidate_responses
from ..semantic.option_ir import ResponseIR, SanitizedDecision
from ..semantic.response_ir import UnsupportedSelectionSchema


class Proposer:
    def propose(self, decision: SanitizedDecision) -> tuple[ResponseIR, ...]:
        try:
            return compile_candidate_responses(decision)
        except UnsupportedSelectionSchema:
            return ()
