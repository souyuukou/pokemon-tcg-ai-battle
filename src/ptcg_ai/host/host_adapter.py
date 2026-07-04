"""Host adapter — sole reader of raw observation dicts."""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

from ..semantic.actor_view import (
    ActorView,
    DecisionContext,
    OpponentPublicSummary,
    PublicBoard,
    PublicEvent,
    SelfDeckManifest,
    SelfKnownOrder,
    SelfUnknownZoneSummary,
    VisibleZoneSummary,
    canonical_hash,
)
from ..semantic.catalog import card_multiset_from_cards
from ..semantic.legal_contract import (
    LegalActionContract,
    option_fingerprint,
    request_fingerprint,
    response_schema_key,
)
from ..semantic.observation_ledger import ObservationLedger
from ..semantic.option_ir import SanitizedDecision, build_option_ir
from ..semantic.self_card_ledger import build_visible_zones, compute_unknown_zone

from .raw_observation import RawObservation, strip_hidden_from_raw

if TYPE_CHECKING:
    from ..runtime.agent_session import AgentSession


def _public_board(players: list[dict[str, Any]], your_index: int) -> tuple[PublicBoard, PublicBoard]:
    def board_for(idx: int) -> PublicBoard:
        p = players[idx] if idx < len(players) else {}
        active = tuple(card_multiset_from_cards(list(p.get("active") or [])).keys())
        bench = tuple(card_multiset_from_cards(list(p.get("bench") or [])).keys())
        return PublicBoard(active_self=active, bench_self=bench, active_opponent=(), bench_opponent=(), stadium=None)

    self_b = board_for(your_index)
    opp_idx = 1 - your_index
    opp = players[opp_idx] if opp_idx < len(players) else {}
    opp_active = tuple(card_multiset_from_cards(list(opp.get("active") or [])).keys())
    opp_bench = tuple(card_multiset_from_cards(list(opp.get("bench") or [])).keys())
    public_self = PublicBoard(
        active_self=self_b.active_self,
        bench_self=self_b.bench_self,
        active_opponent=opp_active,
        bench_opponent=opp_bench,
        stadium=None,
    )
    return public_self, board_for(opp_idx)


def _parse_logs(logs: list[Any]) -> tuple[PublicEvent, ...]:
    events: list[PublicEvent] = []
    for entry in logs or []:
        if not isinstance(entry, dict):
            continue
        events.append(
            PublicEvent(
                event_type=str(entry.get("type", "")),
                player_index=entry.get("playerIndex"),
                card_id=entry.get("cardId"),
                summary="",
            )
        )
        if str(entry.get("type")) == "0":
            pass  # shuffle — ledger handles invalidation separately
    return tuple(events)


def _build_actor_view(
    sanitized: dict[str, Any],
    contract: LegalActionContract,
    session: AgentSession,
) -> ActorView:
    current = sanitized.get("current") or {}
    your_index = int(current.get("yourIndex") or 0)
    players = list(current.get("players") or [{}, {}])
    while len(players) < 2:
        players.append({})
    self_player = players[your_index] if your_index < len(players) else {}
    opp_idx = 1 - your_index
    opp_player = players[opp_idx] if opp_idx < len(players) else {}

    visible = build_visible_zones(self_player)
    deck_count = int(self_player.get("deckCount") or 0)
    prize_list = list(self_player.get("prize") or [])
    prize_face_down = sum(1 for p in prize_list if p is None)
    unknown = compute_unknown_zone(
        session.deck_manifest,
        visible,
        deck_count=deck_count,
        prize_face_down=prize_face_down,
        known_order_valid=session.observation_ledger.known_order_valid,
    )
    public_board, opp_board = _public_board(players, your_index)
    opp_seen: dict[int, int] = {}
    for zone in ("discard", "active", "bench"):
        for cid, n in card_multiset_from_cards(list(opp_player.get(zone) or [])).items():
            opp_seen[cid] = opp_seen.get(cid, 0) + n

    select = sanitized.get("select") or {}
    obs_hash_payload = {
        "turn": current.get("turn"),
        "your_index": your_index,
        "self_active": list(public_board.active_self),
        "self_bench": list(public_board.bench_self),
        "opp_active": list(public_board.active_opponent),
        "opp_bench": list(public_board.bench_opponent),
        "players_public": [
            {
                "hand_count": len(players[i].get("hand") or []) if i == your_index else players[i].get("handCount"),
                "prize_len": len(players[i].get("prize") or []),
                "deck_count": players[i].get("deckCount"),
            }
            for i in range(2)
        ],
        "contract": contract.option_fingerprint,
    }
    obs_hash = canonical_hash(obs_hash_payload)

    return ActorView(
        public_board=public_board,
        public_history=_parse_logs(sanitized.get("logs") or []),
        self_hand=visible.hand,
        self_visible_zones=visible,
        self_unknown_zone=unknown,
        opponent_public=OpponentPublicSummary(
            public_cards_seen=opp_seen,
            hand_count=int(opp_player.get("handCount") or len(opp_player.get("hand") or [])),
            prize_count=len(opp_player.get("prize") or []),
            public_board=opp_board,
        ),
        decision_context=DecisionContext(
            turn=current.get("turn"),
            your_index=your_index,
            select_type=select.get("type"),
            context=select.get("context"),
            first_player=current.get("firstPlayer"),
        ),
        legal_contract=contract,
        observation_hash=obs_hash,
    )


def _build_contract(sanitized: dict[str, Any], observation_hash: str, decision_id: str) -> LegalActionContract:
    select = sanitized.get("select") or {}
    options = list(select.get("option") or [])
    min_count = int(select.get("minCount", 0))
    max_count = int(select.get("maxCount", 0))
    opt_fp = option_fingerprint(options)
    schema = response_schema_key(
        select.get("type"),
        select.get("context"),
        min_count,
        max_count,
        opt_fp,
    )
    contract_fields = {
        "select_type": select.get("type"),
        "context": select.get("context"),
        "min_count": min_count,
        "max_count": max_count,
        "option_fp": opt_fp,
    }
    return LegalActionContract(
        decision_id=decision_id,
        request_fingerprint=request_fingerprint(observation_hash, contract_fields),
        select_type=select.get("type"),
        context=select.get("context"),
        min_count=min_count,
        max_count=max_count,
        option_count=len(options),
        option_fingerprint=opt_fp,
        response_schema_key=schema,
    )


class HostAdapter:
    def sanitize_decision(self, raw: RawObservation, session: AgentSession) -> SanitizedDecision:
        sanitized = strip_hidden_from_raw(raw.data)
        for entry in sanitized.get("logs") or []:
            if isinstance(entry, dict) and str(entry.get("type")) == "0":
                session.observation_ledger.record_shuffle()
        decision_id = f"g{session.observation_ledger.game_sequence}d{session.observation_ledger.next_decision()}"
        pre_contract = _build_contract(sanitized, "", decision_id)
        actor_view = _build_actor_view(sanitized, pre_contract, session)
        contract = LegalActionContract(
            decision_id=decision_id,
            request_fingerprint=request_fingerprint(
                actor_view.observation_hash,
                {
                    "select_type": pre_contract.select_type,
                    "context": pre_contract.context,
                    "min_count": pre_contract.min_count,
                    "max_count": pre_contract.max_count,
                    "option_fp": pre_contract.option_fingerprint,
                },
            ),
            select_type=pre_contract.select_type,
            context=pre_contract.context,
            min_count=pre_contract.min_count,
            max_count=pre_contract.max_count,
            option_count=pre_contract.option_count,
            option_fingerprint=pre_contract.option_fingerprint,
            response_schema_key=pre_contract.response_schema_key,
        )
        actor_view = _build_actor_view(sanitized, contract, session)
        select = sanitized.get("select") or {}
        options_raw = list(select.get("option") or [])
        context = select.get("context")
        options = tuple(
            build_option_ir(i, opt if isinstance(opt, dict) else {}, context)
            for i, opt in enumerate(options_raw)
        )
        return SanitizedDecision(actor_view=actor_view, contract=contract, options=options)


def sanitize_decision(raw_observation: RawObservation, session: AgentSession) -> SanitizedDecision:
    return HostAdapter().sanitize_decision(raw_observation, session)
