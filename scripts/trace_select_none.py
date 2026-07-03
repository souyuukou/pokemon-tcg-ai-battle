import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sample_submission"))
from cg.game import battle_finish, battle_select, battle_start
from fallback import choose

deck = [int(x) for x in Path(__file__).resolve().parents[1].joinpath("sample_submission/deck.csv").read_text().split() if x.strip()]
obs, _ = battle_start(deck, deck)
for i in range(20):
    sel = obs.get("select")
    if sel is None:
        label = "select=None"
    else:
        label = f"ctx={sel.get('context')} opts={len(sel.get('option') or [])}"
    print(i, label)
    if obs.get("current", {}).get("result", -1) >= 0:
        break
    obs = battle_select(deck if sel is None else choose(obs))
battle_finish()
