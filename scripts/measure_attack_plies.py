"""Count simulator plies from MAIN ATTACK choice until next MAIN or terminal."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sample_submission"))

from cg.api import OptionType
from cg.game import battle_finish, battle_select, battle_start
from fallback import choose as fb_choose

OPTION = {e.value: e.name for e in OptionType}


def load_deck() -> list[int]:
    return [int(x) for x in (ROOT / "sample_submission" / "deck.csv").read_text().split() if x.strip()]


def main() -> None:
    deck = load_deck()
    obs, _ = battle_start(deck, deck)
    try:
        # reach first MAIN with ATTACK using fallback (fast)
        for _ in range(400):
            sel = obs.get("select")
            if sel is None:
                obs = battle_select(fb_choose(obs))
                continue
            ctx = int(sel.get("context", -1))
            opts = sel.get("option") or []
            types = [int(o.get("type", -1)) for o in opts]
            if ctx == 0 and 13 in types:
                atk_idx = types.index(13)
                plies = 0
                obs2 = obs
                choice = [atk_idx]
                trace = []
                main_hits = 0
                while plies < 120:
                    plies += 1
                    obs2 = battle_select(choice)
                    sel2 = obs2.get("select")
                    if int((obs2.get("current") or {}).get("result", -1)) >= 0:
                        trace.append("terminal")
                        break
                    if not sel2:
                        trace.append("no_select")
                        break
                    ctx2 = int(sel2.get("context", -1))
                    trace.append(ctx2)
                    if ctx2 == 0:
                        main_hits += 1
                        if main_hits >= 2:
                            break
                    choice = fb_choose(obs2)
                print(f"total plies until 2nd MAIN: {plies}")
                print(f"context trace: {trace[:20]}")
                print(f"prize after: {[len(p.get('prize') or []) for p in (obs2.get('current') or {}).get('players', [{}, {}])]}")
                return
            obs = battle_select(fb_choose(obs))
        print("no ATTACK position found")
    finally:
        battle_finish()


if __name__ == "__main__":
    main()
