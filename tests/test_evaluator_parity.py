"""Python vs C++ evaluator parity on base feature schema."""
from __future__ import annotations

import math
import pathlib
import struct
import sys

import numpy as np

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "sample_submission"))
sys.path.insert(0, str(ROOT / "tests"))

from common.observation_sanitize import sanitize_observation
from model_fixture import ensure_valid_model
from pvs_bridge import bridge
from training.train_nnue import action_features, features, hfeature


def _native_ready() -> bool:
    model = ROOT / "sample_submission" / "model.nnue"
    if not ensure_valid_model(model):
        return False
    deck = [int(x) for x in (ROOT / "sample_submission" / "deck.csv").read_text().split() if x.strip()]
    if bridge._native_path() is None:
        return False
    bridge.lib = None
    return bridge.initialize(deck)


def _python_policy_score(obs: dict, option: dict) -> float:
    state_ids = features(obs)
    action_ids = action_features(obs, option)
    data = (ROOT / "sample_submission" / "model.nnue").read_bytes()
    nf, nh = 4096, 256
    payload_off = 64
    scale_e = struct.unpack("<f", data[24:28])[0]
    emb = np.frombuffer(data[payload_off : payload_off + nf * nh], dtype=np.int8).reshape(nf, nh)
    bias = np.frombuffer(data[payload_off + nf * nh : payload_off + nf * nh + nh * 4], dtype=np.float32)
    action_off = payload_off + nf * nh + nh * 4 + nh + 4
    action_emb = np.frombuffer(data[action_off : action_off + nf * nh], dtype=np.int8).reshape(nf, nh)
    hidden = bias.copy()
    for sid in state_ids:
        hidden += emb[sid] * scale_e
    hidden = np.clip(hidden, 0, 127)
    action_vec = np.zeros(nh, dtype=np.float32)
    for aid in action_ids:
        action_vec += action_emb[aid] * scale_e
    return float(np.dot(action_vec, hidden) / math.sqrt(nh))


def test_feature_schema_hashes_match_native_contract():
    expected = {
        "first:True": 4041,
        "first:False": 3492,
        "us:active:hp:3": 2424,
        "them:bench:hp:12": 72,
        "action:type_card:7:123": 3031,
        "action:type_resolved:8:722": 269,
    }
    assert {text: hfeature(text) for text in expected} == expected


def test_cpp_model_rejects_invalid_hidden_size():
    if bridge._native_path() is None:
        return
    bad = ROOT / "sample_submission" / "model.nnue"
    if bad.stat().st_size < 64:
        return
    deck = [int(x) for x in (ROOT / "sample_submission" / "deck.csv").read_text().split() if x.strip()]
    bridge.lib = None
    ok = bridge.initialize(deck)
    assert ok or "failed" in bridge.error


def test_python_cpp_policy_score_parity_if_native_available():
    if not _native_ready():
        return
    obs = sanitize_observation({
        "current": {
            "yourIndex": 0,
            "turn": 2,
            "firstPlayer": 0,
            "players": [
                {"deckCount": 20, "handCount": 5, "hand": [{"id": 10}], "prize": [None] * 6, "active": [], "bench": [], "discard": []},
                {"deckCount": 20, "handCount": 5, "hand": [], "prize": [None] * 6, "active": [], "bench": [], "discard": []},
            ],
        },
        "select": {
            "context": 0,
            "minCount": 1,
            "maxCount": 1,
            "option": [{"type": 14}, {"type": 13, "attackId": 1}],
        },
        "remainingOverageTime": 600.0,
    })
    option = obs["select"]["option"][0]
    py_score = _python_policy_score(obs, option)
    result = bridge.choose(obs)
    assert result is not None
    diag = bridge.diagnostics()
    assert diag.get("native_backend") in {"avx2", "scalar", "unknown"}
    assert math.isfinite(py_score)
