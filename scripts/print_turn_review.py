import json
from pathlib import Path

root = Path(__file__).parent
d = json.loads((root / "turn_review_latest.json").read_text(encoding="utf-8"))
lines = []
lines.append(f"Winner P{d['winner']} final turn {d['final_turn']} prize {d['final_prize']}")
lines.append(f"Deck: {d['deck_names']}")
lines.append("---")
for t in d["turns"]:
    b = t["board_start"]
    lines.append(f"T{t['turn']} P{t['player']} prize={b['prize']} hand={b['hand']} deck={b['deck']}")
    lines.append(f"  me: {b['my_active']}")
    lines.append(f"  my_bench: {b['my_bench']}")
    lines.append(f"  opp: {b['opp_active']}")
    lines.append(f"  opp_bench: {b['opp_bench']}")
    if b.get("stadium"):
        lines.append(f"  stadium: {b['stadium']}")
    lines.append("  -> " + " | ".join(t["actions"]))
    lines.append("")
(root / "turn_review_summary.txt").write_text("\n".join(lines), encoding="utf-8")
print(f"wrote {root / 'turn_review_summary.txt'}")
