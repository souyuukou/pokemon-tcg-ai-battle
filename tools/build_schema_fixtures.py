#!/usr/bin/env python3
"""Capture host-apply observation fixtures for schema matrix rows."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "sample_submission"))

from cg.game import battle_finish, battle_select, battle_start
from ptcg_ai.host.raw_observation import redact_for_fixture


def _greedy_play(deck: list[int], *, target: str) -> dict | None:
    obs, _ = battle_start(deck, deck)
    trace: list[list[int]] = []
    try:
        while True:
            if obs.get("select") is None:
                obs = battle_select(deck)
                trace.append(list(deck))
                continue
            s = obs["select"]
            lo, hi = int(s["minCount"]), int(s["maxCount"])
            n = len(s.get("option") or [])
            mode_key = f"{lo}:{hi}:{s.get('context')}:{n}"
            if mode_key == target:
                return redact_for_fixture(copy.deepcopy(obs))
            if lo == 0 and hi == 0:
                c: list[int] = []
            elif lo == 0 and hi == 1:
                c = [0] if n else []
            else:
                c = [0] if n else []
            trace.append(c)
            obs = battle_select(c)
            if int((obs.get("current") or {}).get("result", -1)) >= 0:
                return None
    finally:
        battle_finish()


def main() -> int:
    deck_path = ROOT / "submission" / "deck.csv"
    deck = [int(x) for x in deck_path.read_text().split() if x.strip()]
    out_dir = ROOT / "docs" / "competition_contract" / "fixtures"
    out_dir.mkdir(parents=True, exist_ok=True)

    targets = {
        "optional_single_ctx2.json": "0:1:2:1",
        "bounded_0_2_ctx5.json": "0:2:5:3",
    }
    for name, key in targets.items():
        fixture = _greedy_play(deck, target=key)
        if fixture:
            (out_dir / name).write_text(json.dumps(fixture, indent=2), encoding="utf-8")
            print(f"wrote {name}")
        else:
            print(f"skip {name} (not found)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
