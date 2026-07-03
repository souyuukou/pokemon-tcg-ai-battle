"""Production-like self-play: main.agent, Kaggle time bank, full rules via cg."""
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
    path = ROOT / "sample_submission" / "deck.csv"
    return [int(x) for x in path.read_text().split() if x.strip()]


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


def run_game(deck: list[int], max_steps: int = 8000) -> dict:
    bank = TimeBank()
    obs, start = battle_start(deck, deck)
    if obs is None:
        return {"error": f"start failed: {start.errorType}"}

    steps = 0
    errors: list[dict] = []
    ctx_counts: Counter[int] = Counter()
    type_counts: Counter[int] = Counter()
    timings: list[dict] = []
    fallback_calls = 0
    init_ok = True
    main_log: list[dict] = []

    try:
        while steps < max_steps:
            select = obs.get("select")
            player = int((obs.get("current") or {}).get("yourIndex", 0)) if select else 0
            obs_in = bank.inject(obs)
            t0 = time.perf_counter()
            choice = agent(obs_in)
            elapsed = time.perf_counter() - t0
            if select is not None:
                bank.spend(player, elapsed)
            diag = bridge.diagnostics()
            if select is not None:
                ctx = int(select.get("context", -1))
                ctx_counts[ctx] += 1
                err = validate(obs, choice)
                if err:
                    errors.append({"step": steps, "ctx": ctx, "err": err, "choice": choice})
                for index in choice:
                    opts = select.get("option") or []
                    if index < len(opts):
                        type_counts[int(opts[index].get("type", -1))] += 1
                if bridge.error or diag.get("budget_ms", 0) == 0 and elapsed < 0.05:
                    fallback_calls += 1
                timings.append(
                    {
                        "step": steps,
                        "ctx": ctx,
                        "turn": (obs.get("current") or {}).get("turn"),
                        "remain": round(bank.bank[player], 2),
                        "elapsed_ms": round(elapsed * 1000, 1),
                        "budget_ms": diag.get("budget_ms"),
                        "search_wall_ms": diag.get("search_wall_ms"),
                        "worlds": diag.get("worlds"),
                        "choices_left": diag.get("choices_left"),
                    }
                )
                if ctx == 0:
                    opts = select.get("option") or []
                    labels = [OPTION.get(int(opts[i].get("type", -1)), "?") for i in choice if i < len(opts)]
                    main_log.append(
                        {
                            "turn": (obs.get("current") or {}).get("turn"),
                            "player": player,
                            "pick": labels,
                            "elapsed_ms": round(elapsed * 1000, 1),
                            "budget_ms": diag.get("budget_ms"),
                        }
                    )

            obs = battle_select(choice)
            steps += 1
            result = (obs.get("current") or {}).get("result", -1)
            if result is not None and result >= 0:
                players = (obs.get("current") or {}).get("players") or [{}, {}]
                return {
                    "winner": result,
                    "steps": steps,
                    "turn": (obs.get("current") or {}).get("turn"),
                    "final_prize": [len(players[0].get("prize") or []), len(players[1].get("prize") or [])],
                    "errors": errors,
                    "fallback_calls": fallback_calls,
                    "init_ok": init_ok,
                    "ctx_counts": dict(ctx_counts),
                    "type_counts": {OPTION.get(k, str(k)): v for k, v in type_counts.items()},
                    "timings": timings,
                    "main_log": main_log,
                    "final_bank": list(bank.bank),
                }
    finally:
        battle_finish()

    return {"error": "max_steps", "steps": steps, "timings": timings}


def summarize_timings(timings: list[dict]) -> dict:
    if not timings:
        return {}
    n = len(timings)
    third = max(1, n // 3)

    def bucket(name: str, items: list[dict]) -> dict:
        if not items:
            return {"name": name, "n": 0}
        budgets = [t.get("budget_ms") or 0 for t in items]
        elapsed = [t.get("elapsed_ms") or 0 for t in items]
        search = [t.get("search_wall_ms") or 0 for t in items]
        return {
            "name": name,
            "n": len(items),
            "avg_budget_ms": round(sum(budgets) / len(budgets), 1),
            "avg_elapsed_ms": round(sum(elapsed) / len(elapsed), 1),
            "avg_search_ms": round(sum(search) / len(search), 1),
            "min_budget_ms": min(budgets),
            "max_budget_ms": max(budgets),
        }

    return {
        "early": bucket("early", timings[:third]),
        "mid": bucket("mid", timings[third : 2 * third]),
        "late": bucket("late", timings[2 * third :]),
    }


def main() -> None:
    games = 1
    for arg in sys.argv[1:]:
        if arg.isdigit():
            games = int(arg)

    os.environ["POKEMON_PVS_CONFIG"] = json.dumps(PROD_CONFIG, separators=(",", ":"))
    deck = load_deck()
    print("=== Kaggle production self-play test ===")
    print("config:", PROD_CONFIG)
    print("deck cards:", len(deck))

    if not bridge.initialize(deck):
        raise SystemExit(f"bridge init failed: {bridge.error}")
    print("bridge init: OK")

    cards = {c.cardId: c.name for c in all_card_data()}
    del cards  # unused but confirms cg catalog loaded

    for gi in range(games):
        print(f"\n--- Game {gi + 1}/{games} ---", flush=True)
        t_game = time.perf_counter()
        result = run_game(deck)
        if bridge.lib is not None:
            bridge.lib.pvs_reset()
        gc.collect()
        game_sec = round(time.perf_counter() - t_game, 1)

        if "winner" not in result:
            print("FAILED:", result)
            continue

        print(f"winner: P{result['winner']} turn={result['turn']} steps={result['steps']} time={game_sec}s")
        print(f"final prize: {result['final_prize']} final bank: {result['final_bank']}")
        print(f"illegal actions: {len(result['errors'])} fallback-ish fast calls: {result['fallback_calls']}")
        print("context counts:", {CONTEXT.get(int(k), k): v for k, v in result["ctx_counts"].items()})
        top = sorted(result["type_counts"].items(), key=lambda x: -x[1])[:8]
        print("top actions:", ", ".join(f"{k}:{v}" for k, v in top))

        timing_summary = summarize_timings(result["timings"])
        print("\nTiming by game phase:")
        for phase in ("early", "mid", "late"):
            b = timing_summary.get(phase, {})
            if b.get("n"):
                print(
                    f"  {b['name']:5} n={b['n']:3} "
                    f"budget_avg={b['avg_budget_ms']}ms elapsed_avg={b['avg_elapsed_ms']}ms "
                    f"search_avg={b['avg_search_ms']}ms budget_range=[{b['min_budget_ms']},{b['max_budget_ms']}]"
                )

        mains = result["main_log"]
        print("\nMain turns (first 8):")
        for e in mains[:8]:
            print(f"  T{e['turn']} P{e['player']} {e['pick']} budget={e['budget_ms']}ms took={e['elapsed_ms']}ms")
        print("Main turns (last 6):")
        for e in mains[-6:]:
            print(f"  T{e['turn']} P{e['player']} {e['pick']} budget={e['budget_ms']}ms took={e['elapsed_ms']}ms")

        ok_time = timing_summary.get("late", {}).get("avg_budget_ms", 0) > 100
        ok_legal = len(result["errors"]) == 0
        ok_finish = True
        print("\n=== Verdict ===")
        print(f"  game completes: {'PASS' if ok_finish else 'FAIL'}")
        print(f"  all actions legal: {'PASS' if ok_legal else 'FAIL'} ({len(result['errors'])} errors)")
        print(f"  late-game budget >100ms: {'PASS' if ok_time else 'FAIL'}")
        if result["errors"]:
            for e in result["errors"][:5]:
                print("  error:", e)


if __name__ == "__main__":
    main()
