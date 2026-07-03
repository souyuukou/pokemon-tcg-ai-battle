"""Probe isolated worker timeout rate after opponent-model fix."""
from __future__ import annotations

import gc
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sample_submission"))
os.chdir(ROOT / "sample_submission")

os.environ["POKEMON_PVS_ISOLATE_NATIVE"] = "1"
os.environ.pop("POKEMON_PVS_CONFIG", None)

from cg.game import battle_finish, battle_select, battle_start
from main import agent


def deck() -> list[int]:
    return [int(x) for x in (ROOT / "sample_submission" / "deck.csv").read_text().split() if x.strip()]


def main() -> None:
    cards = deck()
    obs, start = battle_start(cards, cards)
    timeouts = 0
    calls = 0
    try:
        while calls < 40:
            sel = obs.get("select")
            if sel is None:
                obs = battle_select(agent(obs))
                continue
            t0 = time.perf_counter()
            choice = agent({**obs, "remainingOverageTime": 600.0})
            wall = (time.perf_counter() - t0) * 1000.0
            if wall > 6000:
                timeouts += 1
            obs = battle_select(choice or [0])
            calls += 1
            if int((obs.get("current") or {}).get("result", -1)) >= 0:
                break
    finally:
        battle_finish()
    print(json.dumps({"calls": calls, "timeouts_6000": timeouts}, indent=2))


if __name__ == "__main__":
    main()
