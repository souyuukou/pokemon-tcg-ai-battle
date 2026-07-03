"""Sweep remainingOverageTime vs search budget."""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sample_submission"))
from cg.game import battle_finish, battle_select, battle_start
from pvs_bridge import bridge

deck = [int(x) for x in (Path(__file__).parents[1] / "sample_submission" / "deck.csv").read_text().split() if x.strip()]
bridge.initialize(deck)
obs, _ = battle_start(deck, deck)
while obs.get("select") is None:
    obs = battle_select(deck)
while obs.get("select", {}).get("context") != 0:
    obs = battle_select([0])
print("remain sweep budget_ms:")
for remain in [600, 400, 200, 100, 50, 20, 10, 5, 4]:
    trial = dict(obs)
    trial["remainingOverageTime"] = remain
    t0 = time.time()
    bridge.choose(trial)
    d = bridge.diagnostics()
    print(
        f"  remain={remain:6} budget_ms={d.get('budget_ms')} "
        f"wall_ms={round(d.get('wall_ms', 0), 1)} elapsed={round(time.time()-t0, 2)}"
    )
battle_finish()
