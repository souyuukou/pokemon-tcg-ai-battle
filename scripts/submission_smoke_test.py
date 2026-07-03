"""Submission smoke test: native must work, fallback must be zero."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUB = ROOT / "sample_submission"
sys.path.insert(0, str(SUB))
os.chdir(SUB)

from cg.game import battle_finish, battle_select, battle_start
from diagnostics import session_diagnostics
from main import agent
from pvs_bridge import bridge

PROD = {
    "hypotheses": 2,
    "threads": 1,
    "max_depth": 12,
    "max_ms": 1500,
    "safety_seconds": 5.0,
    "risk": 0.12,
}


def load_deck() -> list[int]:
    return [int(x) for x in (SUB / "deck.csv").read_text().split() if x.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-fallback", type=int, default=0)
    parser.add_argument("--steps", type=int, default=40)
    args = parser.parse_args()

    os.environ["POKEMON_PVS_CONFIG"] = json.dumps(PROD, separators=(",", ":"))
    deck = load_deck()
    if bridge._native_path() is None:
        print("native library missing")
        return 2
    if not bridge.initialize(deck):
        print(f"native init failed: {bridge.error}")
        return 3

    obs, start = battle_start(deck, deck)
    if obs is None:
        print(f"battle_start failed: {start.errorType}")
        return 4

    steps = 0
    try:
        while steps < args.steps:
            if obs.get("select") is None:
                obs = battle_select(agent(obs))
                steps += 1
                continue
            choice = agent({**obs, "remainingOverageTime": 600.0})
            obs = battle_select(choice)
            steps += 1
            if int((obs.get("current") or {}).get("result", -1)) >= 0:
                break
    finally:
        battle_finish()

    session_diagnostics.detect_backend(bridge.diagnostics())
    report = session_diagnostics.as_dict()
    print(json.dumps(report, indent=2))
    if not report["native_initialized"]:
        return 5
    if args.allow_fallback == 0 and report["fallback_count"] > 0:
        print("fallback_count > 0")
        return 6
    if report["native_choose_count"] <= 0:
        print("native_choose_count == 0")
        return 7
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
