"""Deterministic B0 ranker."""
from __future__ import annotations

import hashlib

from ..contract.runtime_profile import RuntimeProfile
from ..semantic.actor_view import ActorView
from ..semantic.option_ir import ResponseIR, SanitizedDecision
from .features import extract_features, feature_vector


POLICY_VERSION = "b0_v1.11.2"


class Ranker:
    def __init__(self, profile: RuntimeProfile) -> None:
        self._profile = profile

    def score(self, actor_view: ActorView, response: ResponseIR, decision_counter: int) -> float:
        feats = extract_features(actor_view, response)
        score = (
            feats.get("attack_bonus", 0) * 10
            + feats.get("attach_bonus", 0) * 5
            + feats.get("evolve_bonus", 0) * 4
            + feats.get("opp_prize", 0) * -0.5
            + feats.get("self_hand", 0) * 0.1
            + feats.get("self_active_hp", 0) * 0.01
            + feats.get("end_penalty", 0) * 2
        )
        return score

    def tie_break(self, actor_view: ActorView, response: ResponseIR, decision_counter: int) -> int:
        payload = f"{actor_view.observation_hash}:{response.fingerprint}:{decision_counter}:{POLICY_VERSION}"
        return int(hashlib.sha256(payload.encode()).hexdigest()[:8], 16)

    def select(
        self,
        decision: SanitizedDecision,
        candidates: tuple[ResponseIR, ...],
        *,
        decision_counter: int,
    ) -> ResponseIR | None:
        if not candidates:
            return None
        view = decision.actor_view
        limit = self._profile.full_eval_limit
        pool = candidates if len(candidates) <= limit else self._coverage_subset(decision, candidates)
        best: ResponseIR | None = None
        best_score = float("-inf")
        best_tb = -1
        for cand in pool:
            s = self.score(view, cand, decision_counter)
            tb = self.tie_break(view, cand, decision_counter)
            if s > best_score or (s == best_score and tb > best_tb):
                best_score = s
                best_tb = tb
                best = cand
        return best

    def _coverage_subset(
        self, decision: SanitizedDecision, candidates: tuple[ResponseIR, ...]
    ) -> tuple[ResponseIR, ...]:
        seen_cat: set[str] = set()
        chosen: list[ResponseIR] = []
        for c in sorted(
            candidates,
            key=lambda r: self.score(decision.actor_view, r, 0),
            reverse=True,
        ):
            if c.category not in seen_cat:
                seen_cat.add(c.category)
                chosen.append(c)
            if len(chosen) >= self._profile.full_eval_limit:
                break
        if not chosen:
            return candidates[: self._profile.full_eval_limit]
        return tuple(chosen)
