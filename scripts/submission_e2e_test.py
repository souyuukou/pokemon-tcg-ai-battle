"""End-to-end submission test via main.agent with repeated native calls."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUB = ROOT / "sample_submission"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(SUB))
os.chdir(SUB)

from cg.game import battle_finish, battle_select, battle_start
from diagnostics import session_diagnostics
from main import agent, _valid_action
from model_fixture import ensure_valid_model
from pvs_bridge import bridge

PROD = {
    "hypotheses": 2,
    "threads": 1,
    "max_depth": 10,
    "max_ms": 1200,
    "safety_seconds": 5.0,
    "risk": 0.12,
}


def validate(obs: dict, choice: list[int]) -> str | None:
    select = obs.get("select") or {}
    if not _valid_action(choice, select):
        return "illegal action"
    return None


def main() -> int:
    os.environ["POKEMON_PVS_CONFIG"] = json.dumps(PROD, separators=(",", ":"))
    os.environ["POKEMON_PVS_DIAGNOSTICS"] = "1"
    deck = [int(x) for x in (SUB / "deck.csv").read_text().split() if x.strip()]
    if bridge._native_path() is None:
        print("native library missing")
        return 2
    if not ensure_valid_model(SUB / "model.nnue"):
        print("invalid model.nnue")
        return 3

    obs, start = battle_start(deck, deck)
    if obs is None:
        print(f"start failed: {start.errorType}")
        return 4

    calls = 0
    illegal = 0
    timings: list[float] = []
    try:
        agent(obs)
        while calls < 120:
            if obs.get("select") is None:
                obs = battle_select(agent(obs))
                continue
            t0 = time.perf_counter()
            choice = agent({**obs, "remainingOverageTime": 600.0})
            timings.append((time.perf_counter() - t0) * 1000)
            err = validate(obs, choice)
            if err:
                illegal += 1
            obs = battle_select(choice)
            calls += 1
            if int((obs.get("current") or {}).get("result", -1)) >= 0:
                break
    finally:
        battle_finish()

    report = session_diagnostics.as_dict()
    report["calls"] = calls
    report["illegal_actions"] = illegal
    report["avg_decision_time_ms"] = round(sum(timings) / len(timings), 2) if timings else 0
    report["p95_decision_time_ms"] = round(sorted(timings)[int(len(timings) * 0.95) - 1], 2) if timings else 0
    print(json.dumps(report, indent=2))
    if illegal:
        return 5
    if report["fallback_count"] > 0:
        return 6
    if calls < 10:
        return 7
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
