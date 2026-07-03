"""Run self-play and emit debug logs for time-control analysis."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sample_submission"))

from cg.game import battle_finish, battle_select, battle_start
from main import agent

deck = [int(x) for x in (ROOT / "sample_submission" / "deck.csv").read_text().split() if x.strip()]
obs, _ = battle_start(deck, deck)
steps = 0
while steps < 200:
    result = obs.get("current", {}).get("result", -1)
    if result is not None and result >= 0:
        break
    if obs.get("select") is None:
        obs = battle_select(deck)
    else:
        choice = agent(obs)
        obs = battle_select(choice)
    steps += 1
battle_finish()
print("steps", steps)
