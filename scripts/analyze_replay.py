"""Analyze competition replay JSON."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

OPTION = {
    13: "ATTACK",
    14: "END",
    7: "PLAY",
    8: "ATTACH",
    12: "RETREAT",
    9: "EVOLVE",
    10: "ABILITY",
    3: "CARD",
}


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "83014871.json")
    replay = json.loads(path.read_text(encoding="utf-8"))
    steps = replay.get("steps") or []
    print("rewards", replay.get("rewards"))
    print("step pairs", len(steps))

    for player, name in ((0, "P0"), (1, "P1")):
        types: Counter[str] = Counter()
        mains = 0
        empty_main = 0
        for pair in steps:
            if not pair or len(pair) <= player:
                continue
            step = pair[player]
            if not step:
                continue
            obs = step.get("observation") or {}
            sel = obs.get("select") or {}
            action = step.get("action") or []
            if sel.get("context") == 0:
                mains += 1
                if not action:
                    empty_main += 1
            for index in action:
                opts = sel.get("option") or []
                if index < len(opts):
                    t = opts[index].get("type")
                    types[OPTION.get(t, str(t))] += 1
        print(f"{name}: main={mains} empty_main={empty_main} actions={dict(types.most_common())}")

    print("\nEmpty main-context actions:")
    for player, name in ((0, "P0"), (1, "P1")):
        for idx, pair in enumerate(steps):
            if not pair or len(pair) <= player:
                continue
            step = pair[player]
            if not step:
                continue
            obs = step.get("observation") or {}
            sel = obs.get("select") or {}
            if sel.get("context") != 0:
                continue
            action = step.get("action") or []
            if action:
                continue
            opts = sel.get("option") or []
            labels = [OPTION.get(o.get("type"), o.get("type")) for o in opts[:12]]
            turn = obs.get("current", {}).get("turn")
            print(
                f"  {name} step={idx} T{turn} "
                f"min={sel.get('minCount')} max={sel.get('maxCount')} options={labels}"
            )


if __name__ == "__main__":
    main()
