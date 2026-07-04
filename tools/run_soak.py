#!/usr/bin/env python3
"""Soak test — consecutive games via local simulator when available."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))


def main() -> int:
    from ptcg_ai.eval.arena import run_self_play
    from ptcg_ai.runtime.runtime import CompetitionRuntime, get_runtime

    deck_path = ROOT / "submission" / "deck.csv"
    deck = [int(x) for x in deck_path.read_text().split() if x.strip()]
    runtime = CompetitionRuntime(deck)
    card = run_self_play(runtime.act, deck, max_steps=800, sim_root=ROOT / "sample_submission")
    out = ROOT / "docs" / "qualification_reports" / "soak_latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(card.to_dict(), indent=2), encoding="utf-8")
    print(json.dumps(card.to_dict(), indent=2))
    if card.crash_count > 0:
        return 1
    if card.illegal_action_count > 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
