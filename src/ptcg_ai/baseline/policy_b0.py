"""B0 policy orchestration."""
from __future__ import annotations

from ..contract.runtime_profile import RuntimeProfile
from ..runtime.deadline import Deadline
from ..runtime.exceptions import OperationalFailure
from ..runtime.fallback import ValidatedFallbackSelector
from ..semantic.option_ir import ResponseIR, SanitizedDecision
from ..semantic.response_ir import UnsupportedSelectionSchema
from .proposer import Proposer
from .ranker import Ranker, POLICY_VERSION


class PolicyB0:
    def __init__(self, profile: RuntimeProfile) -> None:
        self._profile = profile
        self._proposer = Proposer()
        self._ranker = Ranker(profile)
        self._fallback = ValidatedFallbackSelector()

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
        if deadline.should_stop() or emergency:
            return self._fallback.choose(decision, reason="deadline_or_emergency"), True
        try:
            candidates = self._proposer.propose(decision)
        except UnsupportedSelectionSchema:
            raise
        try:
            selected = self._ranker.select(decision, candidates, decision_counter=decision_counter)
        except Exception:
            return self._fallback.choose(decision, reason="ranker_exception"), True
        if selected is not None:
            return selected, False
        try:
            return self._fallback.choose(decision, reason="ranker_empty"), True
        except OperationalFailure:
            raise
        except Exception as exc:
            try:
                return self._fallback.choose(decision, reason="exception"), True
            except OperationalFailure:
                raise OperationalFailure("ranker failed without validated fallback") from exc
