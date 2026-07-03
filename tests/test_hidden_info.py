"""Hidden-information boundary tests for sanitize, wire, and training features."""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "sample_submission"))

from common.observation_sanitize import sanitize_observation
from pvs_wire import encode_observation
from training.train_nnue import features


def _player(*, hand=None, prize=None, deck_count=15, active=None):
    return {
        "deckCount": deck_count,
        "handCount": len(hand or []),
        "hand": hand or [],
        "prize": prize or [None] * 6,
        "active": active or [],
        "bench": [],
        "discard": [],
    }


def _state(*, opponent_prize=None, opponent_hand=None, own_prize=None, opponent_active=None):
    if opponent_prize is None:
        opponent_prize = [None] * 6
    return {
        "current": {
            "yourIndex": 0,
            "turn": 4,
            "firstPlayer": 0,
            "players": [
                _player(hand=[{"id": 10}], prize=own_prize or [{"id": 501}, None, None, None, None, None]),
                _player(hand=opponent_hand or [{"id": 999}], prize=opponent_prize, active=opponent_active or []),
            ],
        },
        "select": {"context": 0, "minCount": 1, "maxCount": 1, "option": [{"type": 14}]},
        "remainingOverageTime": 600.0,
    }


def test_opponent_prize_ids_masked_in_sanitize_and_wire():
    state_a = _state(opponent_prize=[{"id": 101}, {"id": 102}, None, None, None, None])
    state_b = _state(opponent_prize=[{"id": 201}, {"id": 202}, None, None, None, None])
    assert sanitize_observation(state_a) == sanitize_observation(state_b)
    assert encode_observation(state_a) == encode_observation(state_b)


def test_own_prize_preserved_when_sanitized():
    own = [{"id": 501}, None, None, None, None, None]
    state = _state(opponent_prize=[{"id": 101}] * 6, own_prize=own)
    sanitized = sanitize_observation(state)
    assert sanitized["current"]["players"][0]["prize"][0]["id"] == 501


def test_training_features_ignore_opponent_hidden_hand_and_prize():
    state_a = _state(
        opponent_hand=[{"id": 101}, {"id": 102}],
        opponent_prize=[{"id": 201}, {"id": 202}, None, None, None, None],
    )
    state_b = _state(
        opponent_hand=[{"id": 301}, {"id": 302}],
        opponent_prize=[{"id": 401}, {"id": 402}, None, None, None, None],
    )
    assert features(sanitize_observation(state_a)) == features(sanitize_observation(state_b))


def test_training_features_use_public_opponent_information():
    state_a = _state(opponent_active=[{"id": 1001, "hp": 120}])
    state_b = _state(opponent_active=[{"id": 2002, "hp": 120}])
    assert features(sanitize_observation(state_a)) != features(sanitize_observation(state_b))
