"""Summarize Kaggle loss replays stored in make_replay/."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPLAYS = ROOT / "make_replay"
TYPE = {7: "PLAY", 8: "ATTACH", 9: "EVOLVE", 10: "ABILITY", 12: "RETREAT", 13: "ATTACK", 14: "END"}


def slot(player: dict, area: str = "active") -> dict:
    values = player.get(area) or []
    return values[0] if values else {}


def main() -> None:
    summaries = []
    suspicious = []
    for timing_path in sorted(REPLAYS.glob("*-?.json")):
        stem, seat_text = timing_path.stem.rsplit("-", 1)
        seat = int(seat_text)
        replay_path = REPLAYS / f"{stem}.json"
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
        timing_text = timing_path.read_text(encoding="utf-8")
        durations = [float(value) for value in re.findall(r'"duration"\s*:\s*([0-9.]+)', timing_text)]
        decisions = []
        main_count = attacks = ends = end_with_attack = 0
        first_attack_turn = None
        max_turn = 0
        last_obs = None
        context_counts = Counter()
        type_counts = Counter()
        for step_no, pair in enumerate(replay["steps"][:-1]):
            entry = pair[seat]
            obs = entry.get("observation") or {}
            current = obs.get("current") or {}
            select = obs.get("select")
            if current:
                last_obs = obs
                max_turn = max(max_turn, int(current.get("turn") or 0))
            if not select:
                continue
            # Kaggle records the response to observation i as action i+1.
            action = replay["steps"][step_no + 1][seat].get("action") or []
            if not action or entry.get("status") != "ACTIVE":
                continue
            context = int(select.get("context", -1))
            context_counts[context] += 1
            options = select.get("option") or []
            picked_types = [int(options[i].get("type", -1)) for i in action if 0 <= i < len(options)]
            type_counts.update(picked_types)
            if context != 0:
                continue
            main_count += 1
            turn = int(current.get("turn") or 0)
            option_types = [int(option.get("type", -1)) for option in options]
            if 13 in picked_types:
                attacks += 1
                first_attack_turn = turn if first_attack_turn is None else first_attack_turn
            if 14 in picked_types:
                ends += 1
                if 13 in option_types:
                    end_with_attack += 1
                    players = current.get("players") or [{}, {}]
                    me, opp = players[seat], players[1 - seat]
                    case = {
                        "episode": int(stem), "step": step_no, "turn": turn,
                        "my_prize": len(me.get("prize") or []),
                        "opp_prize": len(opp.get("prize") or []),
                        "my_deck": int(me.get("deckCount") or 0),
                        "opp_deck": int(opp.get("deckCount") or 0),
                        "my_active": slot(me).get("id"),
                        "my_hp": slot(me).get("hp"),
                        "my_energy": len(slot(me).get("energyCards") or []),
                        "opp_active": slot(opp).get("id"),
                        "opp_hp": slot(opp).get("hp"),
                        "attack_ids": [o.get("attackId") for o in options if int(o.get("type", -1)) == 13],
                    }
                    suspicious.append(case)
            decisions.append((turn, picked_types))

        current = (last_obs or {}).get("current") or {}
        players = current.get("players") or [{}, {}]
        me, opp = players[seat], players[1 - seat]
        summary = {
            "episode": int(stem), "seat": seat, "turn": max_turn,
            "steps": len(replay["steps"]), "reward": replay.get("rewards", [None, None])[seat],
            "status": replay.get("statuses", [None, None])[seat],
            "my_prize": len(me.get("prize") or []), "opp_prize": len(opp.get("prize") or []),
            "my_deck": int(me.get("deckCount") or 0), "opp_deck": int(opp.get("deckCount") or 0),
            "main": main_count, "attacks": attacks, "ends": ends,
            "end_with_attack": end_with_attack, "first_attack_turn": first_attack_turn,
            "calls": len(durations), "time_s": round(sum(durations), 2),
            "max_call_s": round(max(durations, default=0), 3),
            "remaining_s": round(float((last_obs or {}).get("remainingOverageTime", 0)), 2),
            "types": dict(type_counts), "contexts": dict(context_counts),
        }
        summaries.append(summary)

    output = {"summaries": summaries, "end_with_attack": suspicious}
    path = ROOT / "scripts" / "loss_replay_analysis.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
