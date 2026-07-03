"""Run one production-like game and dump turn-by-turn review JSON."""
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

from cg.api import OptionType, SelectContext, all_card_data
from cg.game import battle_finish, battle_select, battle_start
from main import agent
from pvs_bridge import bridge

OPTION = {e.value: e.name for e in OptionType}
CONTEXT = {e.value: e.name for e in SelectContext}
PROD_CONFIG = {
    "hypotheses": 6,
    "threads": 1,
    "max_depth": 20,
    "max_ms": 5000,
    "safety_seconds": 5.0,
    "risk": 0.12,
}
START_BANK = 600.0


def load_deck() -> list[int]:
    return [int(x) for x in (ROOT / "sample_submission" / "deck.csv").read_text().split() if x.strip()]


def card_name(cards: dict[int, str], cid: int | None) -> str:
    if not cid:
        return "?"
    return cards.get(int(cid), f"#{cid}")


def fmt_pokemon(cards: dict[int, str], slot: dict | None) -> str:
    if not slot:
        return "-"
    name = card_name(cards, slot.get("id"))
    hp = slot.get("hp", "?")
    energies = len(slot.get("energyCards") or [])
    tools = len(slot.get("tools") or [])
    extra = []
    if energies:
        extra.append(f"E{energies}")
    if tools:
        extra.append(f"T{tools}")
    suffix = f" ({', '.join(extra)})" if extra else ""
    return f"{name} {hp}HP{suffix}"


def board_snapshot(cards: dict[int, str], obs: dict) -> dict:
    current = obs.get("current") or {}
    players = current.get("players") or [{}, {}]
    yi = int(current.get("yourIndex", 0))
    me, opp = players[yi], players[1 - yi]
    return {
        "prize": [len(players[0].get("prize") or []), len(players[1].get("prize") or [])],
        "deck": [int(me.get("deckCount") or 0), int(opp.get("deckCount") or 0)],
        "hand": [int(me.get("handCount") or 0), int(opp.get("handCount") or 0)],
        "my_active": fmt_pokemon(cards, (me.get("active") or [None])[0]),
        "my_bench": [fmt_pokemon(cards, s) for s in (me.get("bench") or [])],
        "opp_active": fmt_pokemon(cards, (opp.get("active") or [None])[0]),
        "opp_bench": [fmt_pokemon(cards, s) for s in (opp.get("bench") or [])],
        "stadium": card_name(cards, ((current.get("stadium") or [None])[0] or {}).get("id"))
        if current.get("stadium")
        else None,
    }


def fmt_option(cards: dict[int, str], opt: dict) -> str:
    t = int(opt.get("type", -1))
    label = OPTION.get(t, str(t))
    if opt.get("cardId") is not None:
        label += f" {card_name(cards, opt['cardId'])}"
    if opt.get("attackId") is not None:
        label += f" atk={opt['attackId']}"
    if opt.get("inPlayIndex") is not None:
        label += f" slot={opt['inPlayIndex']}"
    return label


class TimeBank:
    def __init__(self) -> None:
        self.bank = [START_BANK, START_BANK]

    def inject(self, obs: dict) -> dict:
        if obs.get("select") is None:
            return obs
        player = int((obs.get("current") or {}).get("yourIndex", 0))
        out = dict(obs)
        out["remainingOverageTime"] = max(0.0, self.bank[player])
        return out

    def spend(self, player: int, seconds: float) -> None:
        self.bank[player] = max(0.0, self.bank[player] - seconds)


def run() -> dict:
    deck = load_deck()
    cards = {c.cardId: c.name for c in all_card_data()}
    bank = TimeBank()
    obs, start = battle_start(deck, deck)
    if obs is None:
        return {"error": f"start failed: {start.errorType}"}

    turns: list[dict] = []
    sub_choices: list[dict] = []
    steps = 0
    current_key: tuple | None = None
    turn_actions: list[str] = []
    turn_board_start: dict | None = None
    prev_player = 0

    try:
        while steps < 8000:
            select = obs.get("select")
            if select is None:
                choice = agent(obs)
                obs = battle_select(choice)
                steps += 1
                continue

            player = int((obs.get("current") or {}).get("yourIndex", 0))
            turn = (obs.get("current") or {}).get("turn")
            ctx = int(select.get("context", -1))
            obs_in = bank.inject(obs)
            t0 = time.perf_counter()
            choice = agent(obs_in)
            elapsed = time.perf_counter() - t0
            bank.spend(player, elapsed)

            options = select.get("option") or []
            picks = [fmt_option(cards, options[i]) for i in choice if i < len(options)]

            if ctx == 0:
                key = (turn, player)
                if current_key is not None and key != current_key and turn_actions:
                    turns.append(
                        {
                            "turn": current_key[0],
                            "player": current_key[1],
                            "board_start": turn_board_start,
                            "actions": turn_actions,
                        }
                    )
                    turn_actions = []
                if not turn_actions:
                    turn_board_start = board_snapshot(cards, obs)
                current_key = key
                prev_player = player
                turn_actions.extend(picks)
            elif picks:
                sub_choices.append(
                    {
                        "step": steps,
                        "turn": turn,
                        "player": player,
                        "ctx": CONTEXT.get(ctx, str(ctx)),
                        "pick": picks,
                    }
                )
                if current_key is not None:
                    turn_actions.extend([f"[{CONTEXT.get(ctx, ctx)}] {p}" for p in picks])

            obs = battle_select(choice)
            steps += 1
            result = (obs.get("current") or {}).get("result", -1)
            if result is not None and result >= 0:
                if current_key is not None and turn_actions:
                    turns.append(
                        {
                            "turn": current_key[0],
                            "player": current_key[1],
                            "board_start": turn_board_start,
                            "actions": turn_actions,
                        }
                    )
                players = (obs.get("current") or {}).get("players") or [{}, {}]
                return {
                    "winner": result,
                    "final_turn": (obs.get("current") or {}).get("turn"),
                    "final_prize": [len(players[0].get("prize") or []), len(players[1].get("prize") or [])],
                    "final_bank": list(bank.bank),
                    "steps": steps,
                    "turns": turns,
                    "sub_choices": sub_choices,
                    "deck_names": {
                        str(cid): card_name(cards, cid)
                        for cid in sorted(set(deck))
                    },
                }
    finally:
        battle_finish()
    return {"error": "max_steps"}


def main() -> None:
    os.environ["POKEMON_PVS_CONFIG"] = json.dumps(PROD_CONFIG, separators=(",", ":"))
    deck = load_deck()
    if not bridge.initialize(deck):
        raise SystemExit(bridge.error)
    result = run()
    if bridge.lib is not None:
        bridge.lib.pvs_reset()
    gc.collect()
    out = ROOT / "scripts" / "turn_review_latest.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out}")
    print(f"winner=P{result.get('winner')} turns={len(result.get('turns', []))}")


if __name__ == "__main__":
    main()
