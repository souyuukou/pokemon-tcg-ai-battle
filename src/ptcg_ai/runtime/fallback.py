"""Validated legal fallback layer."""
from __future__ import annotations

from ..semantic.action_categories import OptionCategory
from ..semantic.option_ir import ResponseIR, SanitizedDecision, SelectionMode, response_fingerprint
from ..semantic.response_ir import classify_selection_mode, validate_response_indices


_CATEGORY_PRIORITY: dict[str, int] = {
    OptionCategory.ATTACK.value: 80,
    OptionCategory.TARGET_SELECT.value: 50,
    OptionCategory.EVOLVE.value: 45,
    OptionCategory.ATTACH.value: 40,
    OptionCategory.PLAY.value: 30,
    OptionCategory.RETREAT.value: 10,
    OptionCategory.END.value: 0,
    OptionCategory.CONFIRM.value: 20,
    OptionCategory.OPAQUE.value: 5,
}


class FallbackSelector:
    def choose(self, decision: SanitizedDecision, *, reason: str = "operational") -> ResponseIR:
        contract = decision.contract
        mode = classify_selection_mode(contract.min_count, contract.max_count, contract.option_count)
        if not decision.options:
            return ResponseIR(
                request_fingerprint=contract.request_fingerprint,
                option_indices=(),
                selection_mode=mode,
                category=OptionCategory.OPAQUE.value,
                fingerprint=response_fingerprint((), mode, OptionCategory.OPAQUE.value),
            )
        ranked = sorted(
            decision.options,
            key=lambda o: (_CATEGORY_PRIORITY.get(o.category, 15), -o.host_index),
            reverse=True,
        )
        lo, hi = contract.min_count, contract.max_count
        count = max(lo, min(hi, 1 if hi else 0))
        indices = tuple(sorted(ranked[i].host_index for i in range(min(count, len(ranked)))))
        vr = validate_response_indices(contract.min_count, contract.max_count, contract.option_count, indices)
        if not vr.ok:
            indices = (ranked[0].host_index,) if ranked else ()
        cat = ranked[0].category if ranked else OptionCategory.OPAQUE.value
        return ResponseIR(
            request_fingerprint=contract.request_fingerprint,
            option_indices=indices,
            selection_mode=mode,
            category=cat,
            fingerprint=response_fingerprint(indices, mode, cat),
        )
