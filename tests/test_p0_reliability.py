"""P0 reliability tests: multi-select, hidden info, diagnostics, particles."""
from __future__ import annotations

import json
import os
import pathlib
import struct
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).parents[1]
SUB = ROOT / "sample_submission"
sys.path.insert(0, str(SUB))
sys.path.insert(0, str(ROOT))

from action_codec import decode_action, encode_action, validate_action
from diagnostics import SessionDiagnostics
from fallback import choose as fallback_choose
from observation_sanitize import sanitize_observation
from pvs_bridge import bridge
from pvs_wire import encode_observation
from training.train_nnue import action_features, examples_from_path, features


def _player(hand=None, hand_count=None, prize=None, deck_count=0):
    hand = hand or []
    return {
        "deckCount": deck_count,
        "handCount": hand_count if hand_count is not None else len(hand),
        "hand": hand,
        "prize": prize or [],
        "active": [],
        "bench": [],
        "discard": [],
    }


def _obs(select, your_index=0, opponent_hand=None, opponent_deck_order=None):
    opponent_hand = opponent_hand or []
    return {
        "current": {
            "yourIndex": your_index,
            "turn": 4,
            "firstPlayer": 0,
            "players": [
                _player(hand=[{"id": 10}, {"id": 20}], deck_count=15),
                _player(hand=opponent_hand, deck_count=20, prize=[None] * 6),
            ],
        },
        "select": select,
        "remainingOverageTime": 600.0,
        "_hidden_opponent_deck": opponent_deck_order or [],
    }


def test_multiselect_two_pick_teacher_count():
    select = {
        "context": 3,
        "minCount": 2,
        "maxCount": 2,
        "option": [{"type": 3, "index": i} for i in range(5)],
    }
    obs = _obs(select)
    rows = examples_from_path(_write_replay(obs, [1, 3]))
    assert len(rows) == 2
    assert rows[0][3] == 1
    assert rows[1][3] == 3


def test_multiselect_three_pick_teacher_count():
    select = {
        "context": 3,
        "minCount": 3,
        "maxCount": 3,
        "option": [{"type": 3, "index": i} for i in range(6)],
    }
    obs = _obs(select)
    rows = examples_from_path(_write_replay(obs, [0, 2, 5]))
    assert len(rows) == 3
    assert [row[3] for row in rows] == [0, 2, 5]


def test_multiselect_variable_count():
    select = {
        "context": 3,
        "minCount": 1,
        "maxCount": 3,
        "option": [{"type": 3, "index": i} for i in range(4)],
    }
    obs = _obs(select)
    rows_one = examples_from_path(_write_replay(obs, [2]))
    rows_two = examples_from_path(_write_replay(obs, [1, 3]))
    assert len(rows_one) == 1
    assert len(rows_two) == 2


def test_multiselect_same_head_different_tail():
    select = {
        "context": 3,
        "minCount": 2,
        "maxCount": 2,
        "option": [{"type": 3, "index": i} for i in range(6)],
    }
    obs = _obs(select)
    a = examples_from_path(_write_replay(obs, [4, 5]))
    b = examples_from_path(_write_replay(obs, [4, 3]))
    assert [row[3] for row in a] != [row[3] for row in b]
    assert a[0][3] == b[0][3] == 4
    assert a[1][3] == 5
    assert b[1][3] == 3


def test_action_codec_round_trip():
    select = {
        "context": 3,
        "minCount": 2,
        "maxCount": 2,
        "option": [{"type": 3, "index": i} for i in range(4)],
    }
    obs = _obs(select)
    encoded = encode_action(obs, [1, 3])
    assert decode_action(obs, encoded) == [1, 3]


def test_hidden_info_sanitize_equality():
    select = {"context": 0, "minCount": 1, "maxCount": 1, "option": [{"type": 14}]}
    state_a = _obs(select, opponent_hand=[{"id": 1001}, {"id": 1002}])
    state_b = _obs(select, opponent_hand=[{"id": 2001}, {"id": 2002}])
    assert sanitize_observation(state_a) == sanitize_observation(state_b)
    assert features(sanitize_observation(state_a)) == features(sanitize_observation(state_b))
    assert encode_observation(state_a) == encode_observation(state_b)


def test_fallback_increments_diagnostics():
    diag = SessionDiagnostics()
    diag.record_choose(ok=False, elapsed_ms=1.0, diag={}, error="forced", used_fallback=True)
    assert diag.fallback_count == 1


def _native_ready() -> bool:
    deck = [int(x) for x in (SUB / "deck.csv").read_text().split() if x.strip()]
    if bridge._native_path() is None:
        return False
    bridge.lib = None
    return bridge.initialize(deck)


def test_submission_smoke_rejects_fallback():
    script = ROOT / "scripts" / "submission_smoke_test.py"
    if not script.exists() or not _native_ready():
        return
    env = os.environ.copy()
    env["POKEMON_PVS_DIAGNOSTICS"] = "1"
    proc = subprocess.run(
        [sys.executable, str(script), "--allow-fallback", "0"],
        cwd=str(SUB),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if bridge._native_path() is None:
        assert proc.returncode != 0
        return
    if proc.returncode == 3:
        return
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_native_library_loads_if_present():
    if not _native_ready():
        return
    assert bridge.error == ""


def test_native_choose_once_if_present():
    if not _native_ready():
        return
    obs = {
        "current": {"yourIndex": 0, "turn": 0, "firstPlayer": 0, "players": [{}, {}]},
        "select": {"context": 0, "minCount": 0, "maxCount": 0, "option": []},
        "remainingOverageTime": 600.0,
    }
    result = bridge.choose(obs)
    assert result is not None


def _write_replay(obs: dict, action: list[int]) -> pathlib.Path:
    tmp = ROOT / "tests" / "_tmp_replay.json"
    tmp.write_text(
        json.dumps({"rewards": [1, -1], "steps": [[{"observation": obs, "action": action}, None]]}),
        encoding="utf-8",
    )
    return tmp


if __name__ == "__main__":
    names = [name for name in globals() if name.startswith("test_")]
    failed = 0
    for name in names:
        try:
            globals()[name]()
            print(f"PASS {name}")
        except Exception as exc:
            failed += 1
            print(f"FAIL {name}: {exc}")
    raise SystemExit(failed)
