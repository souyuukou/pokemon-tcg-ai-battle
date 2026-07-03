"""Deep analysis of make_replay loss games + optional native probe."""
from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPLAYS = ROOT / "make_replay"
TYPE = {
    3: "CARD",
    7: "PLAY",
    8: "ATTACH",
    9: "EVOLVE",
    10: "ABILITY",
    12: "RETREAT",
    13: "ATTACK",
    14: "END",
}


def pokemon(slot: dict | None) -> str:
    if not slot:
        return "-"
    return (
        f"{slot.get('name', slot.get('id'))} "
        f"{slot.get('hp')}HP E{len(slot.get('energyCards') or [])}"
    )


def analyze_replay(episode: str, seat: int) -> dict:
    replay = json.loads((REPLAYS / f"{episode}.json").read_text(encoding="utf-8"))
    timing_text = (REPLAYS / f"{episode}-{seat}.json").read_text(encoding="utf-8")
    durations = [float(x) for x in re.findall(r'"duration"\s*:\s*([0-9.]+)', timing_text)]

    main_by_turn: dict[int, list[str]] = defaultdict(list)
    end_with_attack_turns: list[dict] = []
    end_only_streak = 0
    max_end_streak = 0
    prize_stall_turns = 0
    last_prize = None
    type_counts = Counter()
    context_counts = Counter()
    slow_calls = []

    for step_no, pair in enumerate(replay["steps"][:-1]):
        entry = pair[seat]
        obs = entry.get("observation") or {}
        select = obs.get("select")
        if not select or entry.get("status") != "ACTIVE":
            continue
        action = replay["steps"][step_no + 1][seat].get("action") or []
        if not action:
            continue
        context = int(select.get("context", -1))
        context_counts[context] += 1
        options = select.get("option") or []
        picked_types = [
            int(options[i].get("type", -1)) for i in action if 0 <= i < len(options)
        ]
        type_counts.update(picked_types)
        if context != 0:
            continue

        current = obs.get("current") or {}
        turn = int(current.get("turn") or 0)
        players = current.get("players") or [{}, {}]
        me, opp = players[seat], players[1 - seat]
        prize_pair = (len(me.get("prize") or []), len(opp.get("prize") or []))
        if last_prize == prize_pair:
            prize_stall_turns += 1
        last_prize = prize_pair

        labels = [TYPE.get(t, str(t)) for t in picked_types]
        main_by_turn[turn].extend(labels)

        option_types = [int(o.get("type", -1)) for o in options]
        if 14 in picked_types:
            if 13 in option_types:
                end_with_attack_turns.append(
                    {
                        "turn": turn,
                        "prize": prize_pair,
                        "me": pokemon((me.get("active") or [None])[0]),
                        "opp": pokemon((opp.get("active") or [None])[0]),
                        "attacks": [
                            o.get("attackId")
                            for o in options
                            if int(o.get("type", -1)) == 13
                        ],
                        "also": [TYPE.get(t) for t in option_types if t not in {13, 14}],
                    }
                )
            end_only_streak += 1
            max_end_streak = max(max_end_streak, end_only_streak)
        else:
            end_only_streak = 0

        if step_no < len(durations):
            dur = durations[step_no]
            if dur >= 2.5:
                slow_calls.append(
                    {
                        "step": step_no,
                        "turn": turn,
                        "duration": round(dur, 3),
                        "picked": labels,
                    }
                )

    turns_sorted = sorted(main_by_turn)
    late_end_heavy = sum(
        1
        for t in turns_sorted
        if t >= max(turns_sorted[-1] - 4, 0)
        and main_by_turn[t]
        and all(x == "END" for x in main_by_turn[t])
    )

    return {
        "episode": int(episode),
        "seat": seat,
        "turns": turns_sorted,
        "main_by_turn": {str(k): v for k, v in main_by_turn.items()},
        "end_with_attack_turns": end_with_attack_turns,
        "max_end_streak": max_end_streak,
        "prize_stall_turns": prize_stall_turns,
        "late_end_heavy_turns": late_end_heavy,
        "slow_calls": slow_calls[:8],
        "calls": len(durations),
        "time_s": round(sum(durations), 2),
        "max_call_s": round(max(durations, default=0), 3),
        "types": dict(type_counts),
        "contexts": dict(context_counts),
    }


def probe_positions(episode: str, seat: int, labels: list[str]) -> list[dict]:
    sys.path.insert(0, str(ROOT / "sample_submission"))
    from pvs_bridge import bridge  # noqa: WPS433

    deck = [
        int(x)
        for x in (ROOT / "sample_submission" / "deck.csv").read_text().split()
        if x.strip()
    ]
    if not bridge.initialize(deck):
        return [{"error": bridge.error}]

    replay = json.loads((REPLAYS / f"{episode}.json").read_text(encoding="utf-8"))
    probes = []
    for step_no, pair in enumerate(replay["steps"][:-1]):
        entry = pair[seat]
        obs = entry.get("observation") or {}
        select = obs.get("select") or {}
        if int(select.get("context", -1)) != 0:
            continue
        action = replay["steps"][step_no + 1][seat].get("action") or []
        options = select.get("option") or []
        picked = []
        for i in action:
            if 0 <= i < len(options):
                picked.append(TYPE.get(int(options[i].get("type", -1)), "?"))
        label = " | ".join(picked)
        if label not in labels:
            continue
        t0 = time.perf_counter()
        choice = bridge.choose(obs)
        elapsed = round(time.perf_counter() - t0, 3)
        diag = bridge.diagnostics()
        probes.append(
            {
                "label": label,
                "turn": int((obs.get("current") or {}).get("turn") or 0),
                "replay_action": action,
                "engine_action": choice,
                "elapsed_s": elapsed,
                "depth": diag.get("depth"),
                "completed_width": diag.get("completed_width"),
                "root_coverage": diag.get("root_coverage"),
                "common_worlds": diag.get("common_worlds"),
                "worlds": diag.get("worlds"),
                "nodes": diag.get("call_nodes"),
                "budget_ms": diag.get("budget_ms"),
                "coverage_fallback": diag.get("coverage_fallback"),
                "belief_failed": diag.get("belief_failed"),
            }
        )
    return probes


def main() -> None:
    analyses = []
    for timing_path in sorted(REPLAYS.glob("*-?.json")):
        episode, seat_s = timing_path.stem.rsplit("-", 1)
        analyses.append(analyze_replay(episode, int(seat_s)))

    # Probe a few representative bad positions from the worst stall game.
    probes = probe_positions("83464516", 0, ["END", "PLAY(1097) | END"])
    out = {"analyses": analyses, "probes": probes}
    path = ROOT / "scripts" / "make_replay_analysis.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
