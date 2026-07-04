"""Actor-view feature extraction — no raw observation."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from ..semantic.actor_view import ActorView, PublicPokemon
from ..semantic.legal_contract import LegalActionContract
from ..semantic.option_ir import ResponseIR


def _hp_summary(pokemon: PublicPokemon | None) -> float:
    if pokemon is None or pokemon.remaining_hp is None:
        return 0.0
    return float(pokemon.remaining_hp)


def _energy_count(pokemon: PublicPokemon | None) -> float:
    if pokemon is None:
        return 0.0
    return float(sum(n for _, n in pokemon.attached_energy))


def extract_features(actor_view: ActorView, response: ResponseIR) -> dict[str, float]:
    board = actor_view.public_board
    opp_prize = float(board.opponent_prize_count)
    self_hand = float(sum(actor_view.self_hand.values()))
    self_active_hp = _hp_summary(board.self_active)
    opp_active_hp = _hp_summary(board.opponent_active)
    self_energy = _energy_count(board.self_active) + sum(_energy_count(p) for p in board.self_bench)
    return {
        "opp_prize": opp_prize,
        "self_hand": self_hand,
        "self_active_hp": self_active_hp,
        "opp_active_hp": opp_active_hp,
        "self_energy": self_energy,
        "option_count": float(actor_view.legal_contract.option_count),
        "attack_bonus": 1.0 if response.category == "ATTACK" else 0.0,
        "end_penalty": -1.0 if response.category == "END" else 0.0,
        "attach_bonus": 0.5 if response.category == "ATTACH" else 0.0,
        "evolve_bonus": 0.4 if response.category == "EVOLVE" else 0.0,
        "bench_size": float(len(board.self_bench)),
        "opp_bench": float(len(board.opponent_bench)),
        "prize_race": float(board.self_prize_count - board.opponent_prize_count),
    }


def feature_vector(actor_view: ActorView, response: ResponseIR) -> tuple[float, ...]:
    feats = extract_features(actor_view, response)
    return tuple(feats[k] for k in sorted(feats))


def cache_key(
    actor_view: ActorView,
    contract: LegalActionContract,
    policy_version: str,
) -> str:
    payload = {
        "obs_hash": actor_view.observation_hash,
        "request_fp": contract.request_fingerprint,
        "policy": policy_version,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
