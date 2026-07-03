"""Compare budget across remain and turn (post-fix verification)."""
from __future__ import annotations

import sys
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
print("turn x remain -> budget_ms (post-fix):")
for turn in [0, 20, 40, 60]:
    for remain in [600, 200, 100, 50]:
        trial = dict(obs)
        trial["remainingOverageTime"] = remain
        trial["current"] = dict(trial.get("current") or {})
        trial["current"]["turn"] = turn
        bridge.choose(trial)
        d = bridge.diagnostics()
        print(
            f"  turn={turn:2} remain={remain:3} budget_ms={d.get('budget_ms'):4} "
            f"choices_left={d.get('choices_left')} wall_ms={round(d.get('wall_ms', 0), 0)}"
        )
battle_finish()
