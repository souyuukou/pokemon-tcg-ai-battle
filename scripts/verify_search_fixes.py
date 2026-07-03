"""Fast full-rules smoke match for search correctness regressions."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sample_submission"))
os.chdir(ROOT / "sample_submission")
os.environ["POKEMON_PVS_CONFIG"] = json.dumps(
    {
        "hypotheses": 1,
        "threads": 1,
        "max_depth": 6,
        "max_ms": 80,
        "safety_seconds": 5.0,
        "risk": 0.12,
    },
    separators=(",", ":"),
)

from cg.game import battle_finish, battle_select, battle_start
from main import agent


def main() -> None:
    deck = [int(value) for value in Path("deck.csv").read_text().split()]
    obs, start_data = battle_start(deck, deck)
    if obs is None:
        raise RuntimeError(start_data.errorType)
    bank = [600.0, 600.0]
    steps = attacks = ends = 0
    illegal: list[dict] = []
    result = -1
    started = time.perf_counter()
    try:
        while steps < 1200:
            select = obs.get("select")
            player = int((obs.get("current") or {}).get("yourIndex", 0))
            given = dict(obs)
            if select is not None:
                given["remainingOverageTime"] = max(0.0, bank[player])
            before = time.perf_counter()
            choice = agent(given)
            elapsed = time.perf_counter() - before
            if select is not None:
                bank[player] -= elapsed
                lo = int(select.get("minCount", 0))
                hi = int(select.get("maxCount", 0))
                options = select.get("option") or []
                valid = (
                    lo <= len(choice) <= hi
                    and len(choice) == len(set(choice))
                    and all(0 <= index < len(options) for index in choice)
                )
                if not valid:
                    illegal.append({"step": steps, "choice": choice})
                if int(select.get("context", -1)) == 0:
                    types = [int(options[index].get("type", -1)) for index in choice]
                    attacks += types.count(14)
                    ends += types.count(13)
            obs = battle_select(choice)
            steps += 1
            result = int((obs.get("current") or {}).get("result", -1))
            if result >= 0:
                break
    finally:
        battle_finish()
    print(
        json.dumps(
            {
                "result": result,
                "turn": (obs.get("current") or {}).get("turn"),
                "steps": steps,
                "wall_s": round(time.perf_counter() - started, 2),
                "bank": [round(value, 2) for value in bank],
                "illegal": illegal,
                "attacks": attacks,
                "ends": ends,
            }
        )
    )


if __name__ == "__main__":
    main()
