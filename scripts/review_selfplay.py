"""Run self-play games and print a gameplay quality review."""
from __future__ import annotations

import gc
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sample_submission"))

from cg.api import OptionType, SelectContext, all_card_data
from cg.game import battle_finish, battle_select, battle_start
from main import agent
from pvs_bridge import bridge

OPTION = {e.value: e.name for e in OptionType}
CONTEXT = {e.value: e.name for e in SelectContext}


def load_deck() -> list[int]:
    deck_path = ROOT / "sample_submission" / "deck.csv"
    return [int(x) for x in deck_path.read_text().split() if x.strip()]


def card_name(cards: dict[int, str], cid: int) -> str:
    return cards.get(cid, f"#{cid}")


def fmt_option(cards: dict[int, str], opt: dict) -> str:
    opt_type = opt.get("type", -1)
    parts = [OPTION.get(opt_type, str(opt_type))]
    for key in ("cardId", "attackId", "index", "area", "inPlayIndex", "playerIndex"):
        if key in opt and opt[key] is not None:
            value = opt[key]
            if key == "cardId":
                parts.append(f"{key}={card_name(cards, value)}")
            else:
                parts.append(f"{key}={value}")
    return "/".join(parts)


def validate(obs: dict, choice: list[int]) -> str | None:
    select = obs.get("select") or {}
    options = select.get("option") or []
    lo, hi = int(select.get("minCount", 0)), int(select.get("maxCount", 0))
    if not (lo <= len(choice) <= hi):
        return f"count {len(choice)} not in [{lo},{hi}]"
    for index in choice:
        if not (0 <= index < len(options)):
            return f"index {index} out of range"
    if len(choice) != len(set(choice)):
        return "duplicate indices"
    return None


def run_game(
    deck: list[int],
    cards: dict[int, str],
    max_steps: int = 8000,
) -> dict:
    obs, start = battle_start(deck, deck)
    if obs is None:
        return {"error": f"start failed: {start.errorType}"}

    steps = 0
    main_log: list[dict] = []
    ctx_counts: dict[int, int] = {}
    type_counts: dict[int, int] = {}
    errors: list[dict] = []
    end_turns_without_attack = 0
    attacks_before_end = 0
    saw_attack_this_turn = False

    try:
        while steps < max_steps:
            select = obs.get("select")
            if select is None:
                choice = agent(obs)
                obs = battle_select(choice)
                steps += 1
                continue

            context = select.get("context", -1)
            ctx_counts[context] = ctx_counts.get(context, 0) + 1
            choice = agent(obs)
            err = validate(obs, choice)
            if err:
                errors.append({"step": steps, "ctx": context, "err": err, "choice": choice})

            options = select.get("option") or []
            for index in choice:
                opt_type = options[index].get("type") if index < len(options) else -1
                type_counts[opt_type] = type_counts.get(opt_type, 0) + 1

            if context == 0:
                picked = [fmt_option(cards, options[i]) for i in choice if i < len(options)]
                current = obs.get("current", {})
                players = current.get("players", [{}, {}])
                prize = [
                    len(players[0].get("prize") or []),
                    len(players[1].get("prize") or []),
                ]
                for label in picked:
                    if label.startswith("ATTACK"):
                        saw_attack_this_turn = True
                    if label.startswith("END"):
                        if not saw_attack_this_turn:
                            end_turns_without_attack += 1
                        else:
                            attacks_before_end += 1
                        saw_attack_this_turn = False
                main_log.append(
                    {
                        "turn": current.get("turn", "?"),
                        "player": current.get("yourIndex", "?"),
                        "prize": prize,
                        "pick": picked,
                    }
                )

            obs = battle_select(choice)
            result = obs.get("current", {}).get("result", -1)
            if result >= 0:
                current = obs.get("current", {})
                players = current.get("players", [{}, {}])
                return {
                    "winner": result,
                    "steps": steps,
                    "turn": current.get("turn", "?"),
                    "final_prize": [
                        len(players[0].get("prize") or []),
                        len(players[1].get("prize") or []),
                    ],
                    "main_decisions": len(main_log),
                    "ctx_counts": {CONTEXT.get(k, str(k)): v for k, v in ctx_counts.items()},
                    "type_counts": {OPTION.get(k, str(k)): v for k, v in type_counts.items()},
                    "end_without_attack": end_turns_without_attack,
                    "attack_then_end": attacks_before_end,
                    "errors": errors,
                    "main_log": main_log,
                }
            steps += 1
    finally:
        battle_finish()

    return {"error": "max_steps", "steps": steps, "main_decisions": len(main_log)}


def main() -> None:
    games = 3
    threads = 1
    hypotheses = 4
    for arg in sys.argv[1:]:
        if arg.isdigit():
            games = int(arg)
        elif arg.startswith("--threads="):
            threads = int(arg.split("=", 1)[1])
        elif arg.startswith("--hypotheses="):
            hypotheses = int(arg.split("=", 1)[1])

    os.chdir(ROOT / "sample_submission")
    config = {
        "hypotheses": hypotheses,
        "threads": threads,
        "max_depth": 7,
        "max_ms": 1500,
        "profile": False,
    }
    os.environ["POKEMON_PVS_CONFIG"] = json.dumps(config, separators=(",", ":"))

    deck = load_deck()
    if not bridge.initialize(deck):
        raise SystemExit(f"bridge init failed: {bridge.error}")

    cards = {card.cardId: card.name for card in all_card_data()}
    results: list[dict] = []
    for game_index in range(games):
        print(f"Running game {game_index + 1}/{games}...", flush=True)
        results.append(run_game(deck, cards))
        if bridge.lib is not None:
            bridge.lib.pvs_reset()
        gc.collect()

    print(
        f"=== Self-play review ({games} games, "
        f"threads={threads}, hypotheses={hypotheses}) ==="
    )
    wins = {0: 0, 1: 0, 2: 0}
    unfinished = 0
    total_errors = 0
    agg_types: dict[str, int] = {}

    for index, result in enumerate(results):
        if "winner" in result:
            wins[result["winner"]] = wins.get(result["winner"], 0) + 1
            total_errors += len(result["errors"])
            print(
                f"Game {index}: winner=P{result['winner']} "
                f"turn={result['turn']} steps={result['steps']} "
                f"prize={result['final_prize']} main={result['main_decisions']} "
                f"errors={len(result['errors'])} "
                f"end_no_atk={result['end_without_attack']} atk_end={result['attack_then_end']}"
            )
            top = sorted(result["type_counts"].items(), key=lambda item: -item[1])[:6]
            print("  actions:", ", ".join(f"{name}:{count}" for name, count in top))
            for name, count in result["type_counts"].items():
                agg_types[name] = agg_types.get(name, 0) + count
        else:
            unfinished += 1
            print(f"Game {index}: {result.get('error')} steps={result.get('steps', 0)}")

    finished = games - unfinished
    print("\nSummary:")
    print(f"  finished: {finished}/{games}")
    print(f"  wins P0={wins.get(0,0)} P1={wins.get(1,0)} draw={wins.get(2,0)}")
    print(f"  illegal choices: {total_errors}")
    print("  aggregate actions:", dict(sorted(agg_types.items(), key=lambda item: -item[1])))

    sample = next((r for r in results if r.get("main_decisions", 0) > 8), None)
    if sample:
        print(f"\nSample game {results.index(sample)} main turns (first 12 / last 6):")
        for entry in sample["main_log"][:12]:
            print(
                f"  T{entry['turn']} P{entry['player']} prize={entry['prize']}: "
                f"{entry['pick']}"
            )
        print("  ...")
        for entry in sample["main_log"][-6:]:
            print(
                f"  T{entry['turn']} P{entry['player']} prize={entry['prize']}: "
                f"{entry['pick']}"
            )


if __name__ == "__main__":
    main()
