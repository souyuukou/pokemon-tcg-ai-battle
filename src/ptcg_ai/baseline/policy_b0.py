"""B0 policy orchestration."""
from __future__ import annotations

from ..contract.runtime_profile import RuntimeProfile
from ..runtime.deadline import Deadline
from ..runtime.fallback import FallbackSelector
from ..semantic.option_ir import ResponseIR, SanitizedDecision
from .proposer import Proposer
from .ranker import Ranker, POLICY_VERSION


class PolicyB0:
    def __init__(self, profile: RuntimeProfile) -> None:
        self._profile = profile
        self._proposer = Proposer()
        self._ranker = Ranker(profile)
        self._fallback = FallbackSelector()

    @property
    def version(self) -> str:
        return POLICY_VERSION

    def decide(
        self,
        decision: SanitizedDecision,
        *,
        deadline: Deadline,
        decision_counter: int,
        emergency: bool,
    ) -> tuple[ResponseIR, bool]:
        used_fallback = False
        try:
            if deadline.should_stop() or emergency:
                response = self._fallback.choose(decision, reason="deadline_or_emergency")
                return response, True
            candidates = self._proposer.propose(decision)
            if not candidates:
                response = self._fallback.choose(decision, reason="no_candidates")
                return response, True
            selected = self._ranker.select(decision, candidates, decision_counter=decision_counter)
            if selected is None:
                response = self._fallback.choose(decision, reason="ranker_empty")
                return response, True
            return selected, False
        except Exception:
            response = self._fallback.choose(decision, reason="exception")
            return response, True
