"""Verify a wedged native worker is killed and replaced by a legal fallback."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sample_submission"))
os.chdir(ROOT / "sample_submission")
os.environ["POKEMON_PVS_ISOLATE_NATIVE"] = "1"
os.environ["POKEMON_PVS_HARD_TIMEOUT"] = "0.4"
os.environ["POKEMON_PVS_WORKER_TEST_DELAY"] = "2.0"

from cg.game import battle_finish, battle_select, battle_start
from main import agent

deck = [int(value) for value in Path("deck.csv").read_text().split()]
obs, start = battle_start(deck, deck)
if obs is None:
    raise SystemExit(start.errorType)
try:
    obs = battle_select(agent(obs))
    started = time.perf_counter()
    choice = agent(obs)
    elapsed = time.perf_counter() - started
    select = obs["select"]
    valid = (
        int(select["minCount"]) <= len(choice) <= int(select["maxCount"])
        and len(choice) == len(set(choice))
        and all(0 <= index < len(select["option"]) for index in choice)
    )
    if elapsed > 1.5 or not valid:
        raise AssertionError({"elapsed": elapsed, "choice": choice, "valid": valid})
    print({"elapsed": round(elapsed, 3), "choice": choice, "valid": valid})
finally:
    battle_finish()
