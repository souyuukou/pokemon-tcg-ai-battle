"""T4: Multi-select schema handling."""
from __future__ import annotations

import pytest

from ptcg_ai.host.host_response import compile_candidate_responses
from ptcg_ai.semantic.actor_view import (
    ActorView,
    DecisionContext,
    OpponentPublicSummary,
    PublicBoard,
    SelfKnownOrder,
    SelfUnknownZoneSummary,
    VisibleZoneSummary,
)
from ptcg_ai.semantic.legal_contract import LegalActionContract, response_schema_key
from ptcg_ai.semantic.option_ir import OptionIR, SanitizedDecision
from ptcg_ai.semantic.response_ir import UnsupportedSelectionSchema, classify_selection_mode


def _empty_board() -> PublicBoard:
    return PublicBoard(None, (), None, (), None, 6, 6)


def _minimal_decision(min_c: int, max_c: int, n_opts: int) -> SanitizedDecision:
    opts_payload = [{"type": 14} for _ in range(n_opts)]
    sem_key = response_schema_key(0, 0, min_c, max_c, "ofp", option_count=n_opts, options=opts_payload)
    contract = LegalActionContract(
        decision_id="t",
        request_fingerprint="fp",
        semantic_schema_key=sem_key,
        select_type=0,
        context=0,
        min_count=min_c,
        max_count=max_c,
        option_count=n_opts,
        option_fingerprint="ofp",
        response_schema_key=sem_key,
    )
    view = ActorView(
        public_board=_empty_board(),
        public_history=(),
        self_hand={},
        self_visible_zones=VisibleZoneSummary({}, {}, {}, {}, {}, {}, {}),
        self_unknown_zone=SelfUnknownZoneSummary({}, SelfKnownOrder((), (), False), True),
        opponent_public=OpponentPublicSummary({}, 0, 6, _empty_board()),
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


def test_empty_selection_mode():
    assert classify_selection_mode(0, 0, 0) == "empty"


def test_unsupported_multi_select_raises():
    decision = _minimal_decision(2, 3, 5)
    with pytest.raises(UnsupportedSelectionSchema):
        compile_candidate_responses(decision)


def test_unsupported_empty_raises_without_fixture():
    base = _minimal_decision(0, 0, 0)
    contract = LegalActionContract(
        decision_id="t2",
        request_fingerprint="fp2",
        semantic_schema_key="unknown_empty",
        select_type=99,
        context=0,
        min_count=0,
        max_count=0,
        option_count=0,
        option_fingerprint="ofp",
        response_schema_key="unknown_empty",
    )
    decision = SanitizedDecision(base.actor_view, contract, base.options)
    with pytest.raises(UnsupportedSelectionSchema):
        compile_candidate_responses(decision)
