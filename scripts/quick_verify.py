"""Lightweight verification: depth + no illegal empty chooses + short self-play."""
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

from cg.api import OptionType
from cg.game import battle_finish, battle_select, battle_start
from main import agent
from pvs_bridge import bridge

OPTION = {e.value: e.name for e in OptionType}
PROD = {
    "hypotheses": 2,
    "threads": 1,
    "max_depth": 12,
    "max_ms": 1500,
    "safety_seconds": 5.0,
    "risk": 0.12,
}


def deck() -> list[int]:
    return [int(x) for x in (ROOT / "sample_submission" / "deck.csv").read_text().split() if x.strip()]


def main() -> None:
    os.environ["POKEMON_PVS_CONFIG"] = json.dumps(PROD, separators=(",", ":"))
    cards = deck()
    if not bridge.initialize(cards):
        raise SystemExit(bridge.error)

    obs, start = battle_start(cards, cards)
    if obs is None:
        raise SystemExit(start.errorType)

    illegal = 0
    depths: list[int] = []
    attacks = 0
    end_only = 0
    steps = 0
    t0 = time.perf_counter()
    try:
        while steps < 80:
            sel = obs.get("select")
            if sel is None:
                obs = battle_select(agent(obs))
                steps += 1
                continue
            choice = agent({**obs, "remainingOverageTime": 600.0})
            if not choice:
                illegal += 1
            ctx = int(sel.get("context", -1))
            opts = sel.get("option") or []
            labels = [OPTION.get(int(opts[i].get("type", -1)), "?") for i in (choice or []) if i < len(opts)]
            if ctx == 0:
                if labels == ["END"]:
                    end_only += 1
                if "ATTACK" in labels:
                    attacks += 1
            diag = bridge.diagnostics()
            if diag.get("depth") is not None:
                depths.append(int(diag["depth"]))
            obs = battle_select(choice or [0])
            steps += 1
            if steps % 20 == 0 and bridge.lib is not None:
                bridge.lib.pvs_reset()
                gc.collect()
            if int((obs.get("current") or {}).get("result", -1)) >= 0:
                break
    finally:
        battle_finish()

    result = {
        "steps": steps,
        "illegal_empty": illegal,
        "attacks": attacks,
        "end_only_main": end_only,
        "avg_depth": round(sum(depths) / len(depths), 2) if depths else 0,
        "max_depth": max(depths) if depths else 0,
        "depth_ge3": sum(1 for d in depths if d >= 3),
        "wall_s": round(time.perf_counter() - t0, 1),
    }
    out = ROOT / "scripts" / "quick_verify.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
