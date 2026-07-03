"""Replay to a target turn and dump legal MAIN options + probe search configs."""
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

from cg.api import OptionType, all_card_data
from cg.game import battle_finish, battle_select, battle_start
from main import agent
from pvs_bridge import bridge
from pvs_wire import encode_observation

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


def card_name(cards: dict[int, str], cid) -> str:
    return cards.get(int(cid), f"#{cid}") if cid else "?"


def fmt_opt(cards: dict[int, str], opt: dict) -> str:
    t = int(opt.get("type", -1))
    s = OPTION.get(t, str(t))
    if opt.get("cardId") is not None:
        s += f"({card_name(cards, opt['cardId'])})"
    if opt.get("attackId") is not None:
        s += f"[atk={opt['attackId']}]"
    return s


def board_line(cards: dict[int, str], obs: dict) -> str:
    cur = obs.get("current") or {}
    ps = cur.get("players") or [{}, {}]
    yi = int(cur.get("yourIndex", 0))
    me, opp = ps[yi], ps[1 - yi]
    act = (me.get("active") or [None])[0]
    oact = (opp.get("active") or [None])[0]
    return (
        f"T{cur.get('turn')} P{yi} prize={[len(ps[0].get('prize') or []), len(ps[1].get('prize') or [])]} "
        f"me={card_name(cards, (act or {}).get('id'))}({(act or {}).get('hp')}HP,E{len((act or {}).get('energyCards') or [])}) "
        f"opp={card_name(cards, (oact or {}).get('id'))}({(oact or {}).get('hp')}HP)"
    )


def main_options(cards: dict[int, str], obs: dict) -> list[str]:
    sel = obs.get("select") or {}
    if int(sel.get("context", -1)) != 0:
        return []
    return [fmt_opt(cards, o) for o in (sel.get("option") or [])]


def replay_to(deck: list[int], target_turn: int, target_player: int) -> dict | None:
    cards = {c.cardId: c.name for c in all_card_data()}
    obs, start = battle_start(deck, deck)
    if obs is None:
        raise RuntimeError(start.errorType)
    try:
        while True:
            sel = obs.get("select")
            if sel is None:
                obs = battle_select(agent(obs))
                continue
            cur = obs.get("current") or {}
            turn = int(cur.get("turn") or 0)
            player = int(cur.get("yourIndex", 0))
            if turn >= target_turn and player == target_player and int(sel.get("context", -1)) == 0:
                return {
                    "obs": obs,
                    "board": board_line(cards, obs),
                    "options": main_options(cards, obs),
                    "cards": cards,
                }
            choice = agent(obs)
            obs = battle_select(choice)
            if int((obs.get("current") or {}).get("result", -1)) >= 0:
                return None
    finally:
        battle_finish()


def probe(obs: dict, deck: list[int], label: str, config: dict) -> dict:
    os.environ["POKEMON_PVS_CONFIG"] = json.dumps(config, separators=(",", ":"))
    if not bridge.initialize(deck):
        return {"label": label, "error": bridge.error}
    t0 = time.perf_counter()
    choice = bridge.choose(obs)
    elapsed = time.perf_counter() - t0
    diag = bridge.diagnostics()
    sel = obs.get("select") or {}
    opts = sel.get("option") or []
    picked = [fmt_opt({c.cardId: c.name for c in all_card_data()}, opts[i]) for i in (choice or []) if i < len(opts)]
    if bridge.lib is not None:
        bridge.lib.pvs_reset()
    gc.collect()
    return {
        "label": label,
        "picked": picked,
        "elapsed_s": round(elapsed, 2),
        "depth": diag.get("depth"),
        "nodes": diag.get("call_nodes"),
        "budget_ms": diag.get("budget_ms"),
        "worlds": diag.get("worlds"),
        "root": diag.get("root"),
    }


def run() -> None:
    deck = load_deck()
    targets = [(5, 0), (29, 0)]
    results = {"positions": [], "probes": []}
    for turn, player in targets:
        snap = replay_to(deck, turn, player)
        if not snap:
            results["positions"].append({"turn": turn, "player": player, "error": "game ended early"})
            continue
        pos = {"turn": turn, "player": player, "board": snap["board"], "options": snap["options"]}
        results["positions"].append(pos)
        obs = dict(snap["obs"])
        obs["remainingOverageTime"] = 600.0
        configs = [
            ("prod", PROD),
            ("depth5", {**PROD, "max_depth": 5, "max_ms": 5000}),
            ("depth40", {**PROD, "max_depth": 40, "max_ms": 30000}),
            ("time60s", {**PROD, "max_depth": 20, "max_ms": 60000}),
            ("no_model", {**PROD, "model_scale": 0.0}),
            ("no_risk", {**PROD, "risk": 0.0}),
            ("hyp1", {**PROD, "hypotheses": 1}),
            ("order_only", {**PROD, "max_depth": 1, "max_ms": 50}),
        ]
        for label, cfg in configs:
            results["probes"].append({**probe(obs, deck, f"T{turn}P{player}/{label}", cfg), "position": f"T{turn}P{player}"})
        # Save obs bytes for first stall position
        if turn == 29 and player == 0:
            (ROOT / "scripts" / "stall_t29p0.obs.b64").write_text(
                __import__("base64").b64encode(encode_observation(obs)).decode()
            )

    out = ROOT / "scripts" / "stall_probe_results.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    run()
