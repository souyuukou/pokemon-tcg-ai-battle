"""Ablate search settings on replay positions that ended without attacking."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sample_submission"))
os.chdir(ROOT / "sample_submission")

from pvs_bridge import PVSBridge

TARGETS = {
    int(path.stem.rsplit("-", 1)[0])
    for path in (ROOT / "make_replay").glob("*-?.json")
}
TYPE = {7: "PLAY", 8: "ATTACH", 9: "EVOLVE", 10: "ABILITY", 12: "RETREAT", 13: "ATTACK", 14: "END"}


def describe(obs: dict, action: list[int] | None) -> list[str]:
    if action is None:
        return ["FAIL"]
    select = obs.get("select") or {}
    options = select.get("option") or []
    current = obs.get("current") or {}
    seat = int(current.get("yourIndex", 0))
    players = current.get("players") or [{}, {}]
    hand = players[seat].get("hand") or []
    result = []
    for index in action:
        if not (0 <= index < len(options)):
            result.append(f"INVALID({index})")
            continue
        option = options[index]
        option_type = int(option.get("type", -1))
        text = TYPE.get(option_type, str(option_type))
        hand_index = option.get("index")
        if option_type in {7, 8, 9} and isinstance(hand_index, int) and hand_index < len(hand):
            card = hand[hand_index]
            if card:
                text += f"({card.get('id')})"
        if option.get("attackId") is not None:
            text += f"({option['attackId']})"
        if option_type == 8:
            area = "A" if int(option.get("inPlayArea", -1)) == 4 else "B"
            text += f"->{area}{option.get('inPlayIndex')}"
        result.append(text)
    return result


def positions() -> list[dict]:
    found = []
    for timing in sorted((ROOT / "make_replay").glob("*-?.json")):
        episode, seat_text = timing.stem.rsplit("-", 1)
        episode, seat = int(episode), int(seat_text)
        if episode not in TARGETS:
            continue
        replay = json.loads((ROOT / "make_replay" / f"{episode}.json").read_text(encoding="utf-8"))
        for step, pair in enumerate(replay["steps"][:-1]):
            entry = pair[seat]
            obs = entry.get("observation") or {}
            select = obs.get("select") or {}
            actual = replay["steps"][step + 1][seat].get("action") or []
            if entry.get("status") != "ACTIVE" or int(select.get("context", -1)) != 0:
                continue
            options = select.get("option") or []
            actual_types = [int(options[i].get("type", -1)) for i in actual if i < len(options)]
            if 14 not in actual_types:
                continue
            current = obs["current"]
            players = current["players"]
            me, opp = players[seat], players[1 - seat]
            active = (me.get("active") or [{}])[0]
            found.append({
                "episode": episode, "step": step, "turn": current.get("turn"),
                "obs": obs, "actual": actual,
                "active": active.get("id"), "energy": len(active.get("energyCards") or []),
                "opp": (opp.get("active") or [{}])[0].get("id"),
                "attack_available": any(int(o.get("type", -1)) == 13 for o in options),
            })
    return found


def main() -> None:
    label = sys.argv[1]
    configs = {
        "prod": {"hypotheses": 6, "threads": 2, "max_depth": 20, "max_ms": 5000, "risk": .12, "probe_root": True},
        "threads6": {"hypotheses": 6, "threads": 6, "max_depth": 20, "max_ms": 5000, "risk": .12, "probe_root": True},
        "model0": {"hypotheses": 6, "threads": 2, "max_depth": 20, "max_ms": 5000, "risk": .12, "model_scale": 0, "probe_root": True},
        "hyp1": {"hypotheses": 1, "threads": 1, "max_depth": 20, "max_ms": 5000, "risk": .12, "probe_root": True},
        "shallow": {"hypotheses": 6, "threads": 2, "max_depth": 0, "max_ms": 5000, "risk": .12, "probe_root": True},
        "long": {"hypotheses": 1, "threads": 1, "max_depth": 20, "max_ms": 20000, "risk": .12, "probe_root": True},
        "long6": {"hypotheses": 6, "threads": 2, "max_depth": 20, "max_ms": 30000, "risk": .12, "probe_root": True},
    }
    os.environ["POKEMON_PVS_CONFIG"] = json.dumps(configs[label], separators=(",", ":"))
    bridge = PVSBridge()
    deck = [int(value) for value in Path("deck.csv").read_text().split()]
    if not bridge.initialize(deck):
        raise SystemExit(bridge.error)
    output = []
    selected_positions = positions()
    if len(sys.argv) > 2 and sys.argv[2] == "attack":
        selected_positions = [item for item in selected_positions if item["attack_available"]]
    episode_filter = next((int(arg.split("=", 1)[1]) for arg in sys.argv[2:]
                           if arg.startswith("episode=")), None)
    if episode_filter is not None:
        selected_positions = [item for item in selected_positions
                              if item["episode"] == episode_filter]
    if label in {"long", "long6"}:
        selected_positions = [item for item in selected_positions if item["attack_available"]]
    if len(sys.argv) > 2 and sys.argv[2] == "third":
        selected_positions = [item for item in selected_positions if item["step"] == 141]
    for item in selected_positions:
        obs = dict(item["obs"])
        if label in {"long", "long6"}:
            obs["remainingOverageTime"] = 4000.0
        started = time.perf_counter()
        chosen = bridge.choose(obs)
        elapsed = time.perf_counter() - started
        diag = bridge.diagnostics()
        root_scores = diag.get("root")
        if root_scores:
            root_scores = [dict(score, label=describe(obs, score.get("pick")))
                           for score in root_scores]
        output.append({
            **{key: value for key, value in item.items() if key != "obs"},
            "actual_label": describe(obs, item["actual"]),
            "chosen": chosen, "chosen_label": describe(obs, chosen),
            "elapsed": round(elapsed, 3), "depth": diag.get("depth"),
            "nodes": diag.get("call_nodes"), "actions": diag.get("actions"),
            "width": diag.get("completed_width"),
            "coverage": diag.get("root_coverage"),
            "endpoints": diag.get("completed_endpoints"),
            "intermediate_evaluations": diag.get("intermediate_evaluations"),
            "common_worlds": diag.get("common_worlds"),
            "coverage_fallback": diag.get("coverage_fallback"),
            "root": root_scores,
        })
    path = ROOT / "scripts" / f"attack_setup_{label}.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
