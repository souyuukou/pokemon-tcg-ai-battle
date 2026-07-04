"""Host adapter — whitelist projection, sole raw observation reader."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..runtime.exceptions import CardConservationMismatch
from ..semantic.conservation import ConservationQuality, classify_conservation
from ..semantic.actor_view import (
    ActorView,
    DecisionContext,
    OpponentPublicSummary,
    PublicBoard,
    PublicEvent,
    PublicPokemon,
    canonical_hash,
)
from ..semantic.legal_contract import (
    LegalActionContract,
    option_fingerprint,
    request_fingerprint,
    semantic_schema_key_from,
)
from ..semantic.option_ir import SanitizedDecision, build_option_ir
from ..semantic.self_card_ledger import build_visible_zones, compute_unknown_zone, verify_conservation

from .observation_projector import ProjectedCard, project_observation

if TYPE_CHECKING:
    from ..runtime.agent_session import AgentSession


def _to_public_pokemon(card: ProjectedCard, *, zone: str, slot: int) -> PublicPokemon:
    return PublicPokemon(
        card_id=card.card_id,
        zone=zone,
        slot=slot,
        damage=card.damage,
        maximum_hp=card.maximum_hp,
        remaining_hp=card.remaining_hp,
        attached_energy=card.attached_energy,
        attached_tool_ids=card.attached_tool_ids,
        status=card.status,
        retreat_cost=card.retreat_cost,
        stage=card.stage,
        can_attack=card.can_attack,
    )


def _build_public_board(projected, your_index: int) -> tuple[PublicBoard, PublicBoard]:
    self_p = projected.players[your_index]
    opp_p = projected.players[1 - your_index]
    self_active = (
        _to_public_pokemon(self_p.active[0], zone="active", slot=0) if self_p.active else None
    )
    self_bench = tuple(
        _to_public_pokemon(c, zone="bench", slot=i) for i, c in enumerate(self_p.bench)
    )
    opp_active = (
        _to_public_pokemon(opp_p.active[0], zone="active", slot=0) if opp_p.active else None
    )
    opp_bench = tuple(
        _to_public_pokemon(c, zone="bench", slot=i) for i, c in enumerate(opp_p.bench)
    )
    board = PublicBoard(
        self_active=self_active,
        self_bench=self_bench,
        opponent_active=opp_active,
        opponent_bench=opp_bench,
        stadium=None,
        self_prize_count=self_p.prize_face_down_count + self_p.prize_known_count,
        opponent_prize_count=opp_p.prize_face_down_count,
    )
    opp_board = PublicBoard(
        self_active=opp_active,
        self_bench=opp_bench,
        opponent_active=self_active,
        opponent_bench=self_bench,
        stadium=None,
        self_prize_count=opp_p.prize_face_down_count,
        opponent_prize_count=self_p.prize_face_down_count + self_p.prize_known_count,
    )
    return board, opp_board


def _build_actor_view(
    projected,
    contract: LegalActionContract,
    session: AgentSession,
) -> ActorView:
    your_index = projected.your_index
    self_player = projected.players[your_index]
    opp_player = projected.players[1 - your_index]

    visible = build_visible_zones(self_player)
    unknown = compute_unknown_zone(
        session.deck_manifest,
        visible,
        deck_count=self_player.deck_count,
        prize_face_down=self_player.prize_face_down_count,
        known_order_valid=session.observation_ledger.known_order_valid,
    )
    if unknown.conservation_verified:
        if not verify_conservation(
            session.deck_manifest,
            visible,
            unknown,
            self_player.deck_count,
            self_player.prize_face_down_count,
        ):
            raise CardConservationMismatch(
                f"deck conservation failed: visible+unknown != manifest "
                f"(deck={self_player.deck_count} prizes_down={self_player.prize_face_down_count})"
            )
        session.diagnostics.record({"event": "conservation_quality", "quality": ConservationQuality.VERIFIED.value})
    else:
        session.diagnostics.record(
            {
                "event": "conservation_quality",
                "quality": classify_conservation(conservation_verified=False).value,
                "deck_count": self_player.deck_count,
                "prize_face_down": self_player.prize_face_down_count,
            }
        )

    public_board, opp_board = _build_public_board(projected, your_index)
    opp_seen: dict[int, int] = {}
    for c in opp_player.discard + opp_player.active + opp_player.bench:
        opp_seen[c.card_id] = opp_seen.get(c.card_id, 0) + 1

    history = tuple(
        PublicEvent(
            event_type=str(e.get("type", "")),
            player_index=e.get("playerIndex"),
            card_id=e.get("cardId"),
            summary="",
        )
        for e in projected.public_events
    )

    obs_hash_payload = {
        "turn": projected.turn,
        "your_index": your_index,
        "self_active": public_board.self_active.card_id if public_board.self_active else None,
        "self_active_hp": public_board.self_active.remaining_hp if public_board.self_active else None,
        "self_active_damage": public_board.self_active.damage if public_board.self_active else None,
        "self_bench": [p.card_id for p in public_board.self_bench],
        "opp_active": public_board.opponent_active.card_id if public_board.opponent_active else None,
        "opp_bench": [p.card_id for p in public_board.opponent_bench],
        "self_prizes": public_board.self_prize_count,
        "opp_prizes": public_board.opponent_prize_count,
        "contract": contract.option_fingerprint,
    }
    obs_hash = canonical_hash(obs_hash_payload)

    select = projected.select
    return ActorView(
        public_board=public_board,
        public_history=history,
        self_hand=visible.hand,
        self_visible_zones=visible,
        self_unknown_zone=unknown,
        opponent_public=OpponentPublicSummary(
            public_cards_seen=opp_seen,
            hand_count=opp_player.hand_count,
            prize_count=opp_player.prize_face_down_count,
            public_board=opp_board,
        ),
        decision_context=DecisionContext(
            turn=projected.turn,
            your_index=your_index,
            select_type=select.select_type if select else None,
            context=select.context if select else None,
            first_player=projected.first_player,
        ),
        legal_contract=contract,
        observation_hash=obs_hash,
    )


def _build_contract(projected, observation_hash: str, decision_id: str) -> LegalActionContract:
    select = projected.select
    if select is None:
        raise ValueError("deck selection is not an in-game decision")
    options = list(select.options)
    min_count = select.min_count
    max_count = select.max_count
    opt_fp = option_fingerprint([dict(o) for o in options])
    sem_key = semantic_schema_key_from(
        select.select_type,
        select.context,
        min_count,
        max_count,
        len(options),
        [dict(o) for o in options],
    )
    contract_fields = {
        "select_type": select.select_type,
        "context": select.context,
        "min_count": min_count,
        "max_count": max_count,
        "option_fp": opt_fp,
    }
    return LegalActionContract(
        decision_id=decision_id,
        request_fingerprint=request_fingerprint(observation_hash, contract_fields),
        semantic_schema_key=sem_key,
        select_type=select.select_type,
        context=select.context,
        min_count=min_count,
        max_count=max_count,
        option_count=len(options),
        option_fingerprint=opt_fp,
        response_schema_key=sem_key,
    )


class HostAdapter:
    def sanitize_decision(self, raw: RawObservation, session: AgentSession) -> SanitizedDecision:
        projected = project_observation(raw.data)
        session.observation_ledger.ingest_public_events(projected.public_events, turn=projected.turn)

        decision_id = f"g{session.observation_ledger.game_sequence}d{session.observation_ledger.next_decision()}"
        pre_contract = _build_contract(projected, "", decision_id)
        actor_view = _build_actor_view(projected, pre_contract, session)
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
            semantic_schema_key=pre_contract.semantic_schema_key,
            select_type=pre_contract.select_type,
            context=pre_contract.context,
            min_count=pre_contract.min_count,
            max_count=pre_contract.max_count,
            option_count=pre_contract.option_count,
            option_fingerprint=pre_contract.option_fingerprint,
            response_schema_key=pre_contract.semantic_schema_key,
        )
        actor_view = _build_actor_view(projected, contract, session)
        select = projected.select
        assert select is not None
        options = tuple(
            build_option_ir(i, dict(opt), select.context) for i, opt in enumerate(select.options)
        )
        return SanitizedDecision(actor_view=actor_view, contract=contract, options=options)


def sanitize_decision(raw_observation: RawObservation, session: AgentSession) -> SanitizedDecision:
    return HostAdapter().sanitize_decision(raw_observation, session)
