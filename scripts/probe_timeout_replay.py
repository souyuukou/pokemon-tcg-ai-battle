"""Replay one timed-out Kaggle observation through the local native engine."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sample_submission"))
os.chdir(ROOT / "sample_submission")

episode, seat = int(sys.argv[1]), int(sys.argv[2])
data = json.loads((ROOT / "make_replay" / f"{episode}.json").read_text(encoding="utf-8"))
last = dict(data["steps"][-1][seat]["observation"])
previous_remaining = data["steps"][-2][seat]["observation"]["remainingOverageTime"]
last["remainingOverageTime"] = previous_remaining

from main import agent
from pvs_bridge import bridge

deck = [int(value) for value in Path("deck.csv").read_text().split()]
if not bridge.initialize(deck):
    raise SystemExit(bridge.error)
started = time.perf_counter()
choice = bridge.choose(last)
print(json.dumps({"choice": choice, "elapsed": time.perf_counter() - started,
                  "diagnostics": bridge.diagnostics()}))
