"""T4: Multi-select schema handling."""
from __future__ import annotations

import pytest

from ptcg_ai.host.host_response import compile_candidate_responses
from ptcg_ai.semantic.legal_contract import LegalActionContract, response_schema_key
from ptcg_ai.semantic.option_ir import OptionIR, SanitizedDecision
from ptcg_ai.semantic.response_ir import UnsupportedSelectionSchema, classify_selection_mode


def _minimal_decision(min_c: int, max_c: int, n_opts: int) -> SanitizedDecision:
    from ptcg_ai.semantic.actor_view import (
        ActorView,
        DecisionContext,
        OpponentPublicSummary,
        PublicBoard,
        SelfKnownOrder,
        SelfUnknownZoneSummary,
        VisibleZoneSummary,
    )

    contract = LegalActionContract(
        decision_id="t",
        request_fingerprint="fp",
        select_type=0,
        context=0,
        min_count=min_c,
        max_count=max_c,
        option_count=n_opts,
        option_fingerprint="ofp",
        response_schema_key=response_schema_key(0, 0, min_c, max_c, "ofp"),
    )
    view = ActorView(
        public_board=PublicBoard((), (), (), (), None),
        public_history=(),
        self_hand={},
        self_visible_zones=VisibleZoneSummary({}, {}, {}, {}, {}, {}),
        self_unknown_zone=SelfUnknownZoneSummary({}, SelfKnownOrder((), (), False)),
        opponent_public=OpponentPublicSummary({}, 0, 6, PublicBoard((), (), (), (), None)),
        decision_context=DecisionContext(1, 0, 0, 0, 0),
        legal_contract=contract,
        observation_hash="h",
    )
    options = tuple(
        OptionIR(i, 14, "END", None, None, None, None, f"f{i}", False) for i in range(n_opts)
    )
    return SanitizedDecision(view, contract, options)


def test_single_selection_mode():
    assert classify_selection_mode(1, 1, 3) == "single"


def test_unsupported_multi_select_raises():
    decision = _minimal_decision(2, 3, 5)
    with pytest.raises(UnsupportedSelectionSchema):
        compile_candidate_responses(decision)
