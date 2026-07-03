"""Render compact turn-by-turn decisions for loss replay review."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPLAYS = ROOT / "make_replay"
TYPE = {3: "CARD", 7: "PLAY", 8: "ATTACH", 9: "EVOLVE", 10: "ABILITY",
        12: "RETREAT", 13: "ATTACK", 14: "END"}


def pokemon(value: dict | None) -> str:
    if not value:
        return "-"
    return f"{value.get('name', value.get('id'))} {value.get('hp')}HP E{len(value.get('energyCards') or [])} T{len(value.get('tools') or [])}"


lines: list[str] = []
for timing_path in sorted(REPLAYS.glob("*-?.json")):
    episode, seat_text = timing_path.stem.rsplit("-", 1)
    seat = int(seat_text)
    replay = json.loads((REPLAYS / f"{episode}.json").read_text(encoding="utf-8"))
    turns: dict[int, dict] = {}
    public_opponent: set[str] = set()
    for step_no, pair in enumerate(replay["steps"][:-1]):
        entry = pair[seat]
        action = replay["steps"][step_no + 1][seat].get("action") or []
        obs = entry.get("observation") or {}
        current = obs.get("current") or {}
        players = current.get("players") or [{}, {}]
        if current:
            opp = players[1 - seat]
            for area in ("active", "bench", "discard"):
                for card in opp.get(area) or []:
                    if card:
                        public_opponent.add(str(card.get("name", card.get("id"))))
        select = obs.get("select") or {}
        if (not action or entry.get("status") != "ACTIVE" or
                int(select.get("context", -1)) != 0):
            continue
        turn = int(current.get("turn") or 0)
        options = select.get("option") or []
        labels = []
        for index in action:
            if not (0 <= index < len(options)):
                continue
            option = options[index]
            option_type = int(option.get("type", -1))
            label = TYPE.get(option_type, str(option.get("type")))
            if option_type in {7, 8, 9} and option.get("index") is not None:
                hand = players[seat].get("hand") or []
                hand_index = int(option["index"])
                if 0 <= hand_index < len(hand) and hand[hand_index]:
                    label += f"({hand[hand_index].get('name', hand[hand_index].get('id'))})"
            if option_type == 8 and option.get("inPlayIndex") is not None:
                area = "A" if int(option.get("inPlayArea", -1)) == 4 else "B"
                label += f"->{area}{option['inPlayIndex']}"
            if option.get("attackId") is not None:
                label += f"({option['attackId']})"
            labels.append(label)
        if turn not in turns:
            me, opp = players[seat], players[1 - seat]
            turns[turn] = {
                "prize": (len(me.get("prize") or []), len(opp.get("prize") or [])),
                "deck": (int(me.get("deckCount") or 0), int(opp.get("deckCount") or 0)),
                "me": pokemon((me.get("active") or [None])[0]),
                "opp": pokemon((opp.get("active") or [None])[0]),
                "actions": [],
            }
        turns[turn]["actions"].extend(labels)
    lines.append(f"=== {episode} seat={seat} status={replay['statuses'][seat]} reward={replay['rewards'][seat]} ===")
    lines.append("opponent public: " + ", ".join(sorted(public_opponent)))
    for turn, data in turns.items():
        lines.append(
            f"T{turn} prize={data['prize']} deck={data['deck']} "
            f"me=[{data['me']}] opp=[{data['opp']}] -> {' | '.join(data['actions'])}"
        )
    lines.append("")

output = ROOT / "scripts" / "loss_turn_reviews.txt"
output.write_text("\n".join(lines), encoding="utf-8")
print(output)
