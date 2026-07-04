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
    ) -> tuple[ResponseIR, bool, str | None]:
        if deadline.should_stop() or emergency:
            return self._fallback.choose(decision, reason="deadline_or_emergency"), True, "deadline_or_emergency"
        try:
            candidates = self._proposer.propose(decision)
        except UnsupportedSelectionSchema:
            raise
        try:
            selected = self._ranker.select(decision, candidates, decision_counter=decision_counter)
        except Exception:
            return self._fallback.choose(decision, reason="ranker_exception"), True, "ranker_exception"
        if selected is not None:
            return selected, False, None
        try:
            return self._fallback.choose(decision, reason="ranker_empty"), True, "ranker_empty"
        except OperationalFailure:
            raise
        except Exception as exc:
            try:
                return self._fallback.choose(decision, reason="exception"), True, "exception"
            except OperationalFailure:
                raise OperationalFailure("ranker failed without validated fallback") from exc
