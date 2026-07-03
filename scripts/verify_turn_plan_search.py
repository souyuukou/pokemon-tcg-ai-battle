"""Regression gate for turn-end-only progressive-width search."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sample_submission"))
os.chdir(ROOT / "sample_submission")
os.environ["POKEMON_PVS_CONFIG"] = json.dumps({
    "hypotheses": 6, "threads": 2, "max_depth": 20,
    "max_ms": 5000, "risk": .12, "probe_root": True,
}, separators=(",", ":"))

from pvs_bridge import PVSBridge

TARGETS = {(83386796, 3), (83401989, 8), (83403435, 10), (83417488, 7)}


def observation_at(episode: int, turn: int) -> tuple[dict, int]:
    replay = json.loads((ROOT / "make_replay" / f"{episode}.json").read_text())
    seat = next(i for i, reward in enumerate(replay["rewards"]) if reward == -1)
    for pair in replay["steps"]:
        entry = pair[seat]
        obs = entry.get("observation") or {}
        current = obs.get("current") or {}
        select = obs.get("select") or {}
        if int(current.get("turn", -1)) == turn and int(select.get("context", -1)) == 0:
            return obs, seat
    raise AssertionError(f"missing MAIN observation for {episode} T{turn}")


def main() -> None:
    deck = [int(value) for value in Path("deck.csv").read_text().split()]
    bridge = PVSBridge()
    assert bridge.initialize(deck), bridge.error
    results = []
    for episode, turn in sorted(TARGETS):
        obs, _ = observation_at(episode, turn)
        choice = bridge.choose(obs)
        diag = bridge.diagnostics()
        select = obs["select"]
        assert choice is not None
        assert int(select["minCount"]) <= len(choice) <= int(select["maxCount"])
        assert len(choice) == len(set(choice))
        assert all(0 <= index < len(select["option"]) for index in choice)
        assert diag.get("intermediate_evaluations") == 0, (episode, turn, diag)
        assert diag.get("root_coverage") == 1, (episode, turn, diag)
        assert diag.get("common_worlds") == 6, (episode, turn, diag)
        assert int(diag.get("completed_turn_depth", 0)) >= 1, (episode, turn, diag)
        assert int(diag.get("completed_width", 0)) >= 1, (episode, turn, diag)
        results.append({
            "episode": episode, "turn": turn, "choice": choice,
            "depth": diag["completed_turn_depth"],
            "width": diag["completed_width"],
            "endpoints": diag["completed_endpoints"],
        })
    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
