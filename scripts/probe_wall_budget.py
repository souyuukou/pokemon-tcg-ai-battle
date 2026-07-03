"""Verify wall_ms stays within budget_ms + margin under production-like limits."""
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

from cg.game import battle_finish, battle_select, battle_start
from main import agent, _effective_config
from pvs_bridge import bridge

os.environ["POKEMON_PVS_ISOLATE_NATIVE"] = "0"
os.environ["POKEMON_PVS_CONFIG"] = _effective_config()


def deck() -> list[int]:
    return [int(x) for x in (ROOT / "sample_submission" / "deck.csv").read_text().split() if x.strip()]


def run_probe() -> dict:
    cards = deck()
    if not bridge.initialize(cards):
        raise SystemExit(bridge.error)
    obs, start = battle_start(cards, cards)
    if obs is None:
        raise SystemExit(start.errorType)
    violations = []
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
            diag = bridge.diagnostics()
            budget = float(diag.get("budget_ms") or 0)
            hard = float(diag.get("hard_ms") or 0)
            if budget > 0 and wall > budget + 250:
                violations.append(
                    {
                        "call": calls,
                        "wall_ms": round(wall, 1),
                        "budget_ms": budget,
                        "hard_ms": hard,
                        "context": sel.get("context"),
                    }
                )
            obs = battle_select(choice or [0])
            calls += 1
            if calls % 15 == 0 and bridge.lib is not None:
                bridge.lib.pvs_reset()
                gc.collect()
            if int((obs.get("current") or {}).get("result", -1)) >= 0:
                break
    finally:
        battle_finish()
    return {"calls": calls, "violations": violations, "config": json.loads(_effective_config())}


if __name__ == "__main__":
    print(json.dumps(run_probe(), indent=2))
