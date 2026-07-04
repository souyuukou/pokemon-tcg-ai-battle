"""Actor-view feature extraction — no raw observation."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from ..semantic.actor_view import ActorView
from ..semantic.legal_contract import LegalActionContract
from ..semantic.option_ir import ResponseIR


def extract_features(actor_view: ActorView, response: ResponseIR) -> dict[str, float]:
    opp_prize = actor_view.opponent_public.prize_count or 0
    self_hand = sum(actor_view.self_hand.values())
    return {
        "opp_prize": float(opp_prize),
        "self_hand": float(self_hand),
        "option_count": float(actor_view.legal_contract.option_count),
        "attack_bonus": 1.0 if response.category == "ATTACK" else 0.0,
        "end_penalty": -1.0 if response.category == "END" else 0.0,
        "attach_bonus": 0.5 if response.category == "ATTACH" else 0.0,
        "evolve_bonus": 0.4 if response.category == "EVOLVE" else 0.0,
        "bench_size": float(len(actor_view.public_board.bench_self)),
        "opp_bench": float(len(actor_view.public_board.bench_opponent)),
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
