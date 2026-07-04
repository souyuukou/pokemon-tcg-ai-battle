#!/usr/bin/env python3
"""Soak test — consecutive games via local simulator when available."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=1)
    args = parser.parse_args()

    from ptcg_ai.eval.arena import ArenaConfig, run_self_play, run_soak_batch
    from ptcg_ai.runtime.runtime import CompetitionRuntime

    deck_path = ROOT / "submission" / "deck.csv"
    deck = [int(x) for x in deck_path.read_text().split() if x.strip()]
    runtime = CompetitionRuntime(deck)
    cfg = ArenaConfig(max_steps=800, time_bank_mode="authoritative", initial_time_seconds=600.0)
    if args.games <= 1:
        card = run_self_play(runtime.act, deck, sim_root=ROOT / "sample_submission", config=cfg)
    else:
        card = run_soak_batch(runtime.act, deck, games=args.games, sim_root=ROOT / "sample_submission", config=cfg)
    out = ROOT / "artifacts" / "qualification" / "local" / "soak_latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(card.to_dict(), indent=2), encoding="utf-8")
    print(json.dumps(card.to_dict(), indent=2))
    if card.crash_count > 0:
        return 1
    if card.illegal_action_count > 0:
        return 2
    if card.unsupported_schema_count > 0:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
