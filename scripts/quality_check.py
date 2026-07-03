"""Compare gameplay quality metrics from one production self-play."""
from __future__ import annotations

import gc
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sample_submission"))
os.chdir(ROOT / "sample_submission")

from cg.api import OptionType
from cg.game import battle_finish, battle_select, battle_start
from main import agent
from pvs_bridge import bridge

OPTION = {e.value: e.name for e in OptionType}
PROD = {
    "hypotheses": 6,
    "threads": 1,
    "max_depth": 20,
    "max_ms": 5000,
    "safety_seconds": 5.0,
    "risk": 0.12,
    "probe_root": True,
}


def load_deck() -> list[int]:
    return [int(x) for x in (ROOT / "sample_submission" / "deck.csv").read_text().split() if x.strip()]


def run_game(deck: list[int]) -> dict:
    obs, start = battle_start(deck, deck)
    if obs is None:
        return {"error": start.errorType}
    steps = 0
    main_end_only = 0
    main_with_attack = 0
    main_total = 0
    attacks = 0
    ends = 0
    depths: list[int] = []
    try:
        while steps < 8000:
            sel = obs.get("select")
            if sel is None:
                obs = battle_select(agent(obs))
                steps += 1
                continue
            choice = agent({**obs, "remainingOverageTime": 600.0})
            ctx = int(sel.get("context", -1))
            opts = sel.get("option") or []
            labels = [OPTION.get(int(opts[i].get("type", -1)), "?") for i in choice if i < len(opts)]
            if ctx == 0:
                main_total += 1
                turn_actions = labels[:]
                if turn_actions == ["END"]:
                    main_end_only += 1
                if any(x == "ATTACK" for x in turn_actions):
                    main_with_attack += 1
                for x in turn_actions:
                    if x == "ATTACK":
                        attacks += 1
                    if x == "END":
                        ends += 1
            diag = bridge.diagnostics()
            if diag.get("depth") is not None:
                depths.append(int(diag["depth"]))
            obs = battle_select(choice)
            steps += 1
            if int((obs.get("current") or {}).get("result", -1)) >= 0:
                players = (obs.get("current") or {}).get("players") or [{}, {}]
                return {
                    "winner": (obs.get("current") or {}).get("result"),
                    "turn": (obs.get("current") or {}).get("turn"),
                    "steps": steps,
                    "prize": [len(players[0].get("prize") or []), len(players[1].get("prize") or [])],
                    "main_total": main_total,
                    "main_end_only": main_end_only,
                    "main_with_attack": main_with_attack,
                    "attacks": attacks,
                    "ends": ends,
                    "avg_depth": round(sum(depths) / len(depths), 2) if depths else 0,
                    "max_depth": max(depths) if depths else 0,
                    "depth_ge4": sum(1 for d in depths if d >= 4),
                }
    finally:
        battle_finish()
    return {"error": "max_steps"}


def main() -> None:
    os.environ["POKEMON_PVS_CONFIG"] = json.dumps(PROD, separators=(",", ":"))
    deck = load_deck()
    if not bridge.initialize(deck):
        raise SystemExit(bridge.error)
    t0 = time.perf_counter()
    result = run_game(deck)
    if bridge.lib:
        bridge.lib.pvs_reset()
    gc.collect()
    result["wall_s"] = round(time.perf_counter() - t0, 1)
    out = ROOT / "scripts" / "quality_check.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
