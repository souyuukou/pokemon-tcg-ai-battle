"""Capture host-apply-validated schemas from cabt simulator."""
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
from ptcg_ai.semantic.legal_contract import option_fingerprint, semantic_schema_key_from


def _try_responses(obs: dict, deck: list[int]) -> list[tuple[int, ...]]:
    select = obs.get("select") or {}
    lo, hi = int(select.get("minCount", 0)), int(select.get("maxCount", 0))
    n = len(select.get("option") or [])
    candidates: list[tuple[int, ...]] = [()]
    for i in range(n):
        candidates.append((i,))
    if hi >= 2:
        for i in range(n):
            for j in range(i + 1, n):
                candidates.append((i, j))
    valid: list[tuple[int, ...]] = []
    for cand in candidates:
        if len(cand) < lo or len(cand) > hi:
            continue
        if len(cand) != len(set(cand)):
            continue
        o2, s = battle_start(deck, deck)
        if o2 is None:
            continue
        # replay to same state is hard — use fresh game heuristic: only validate on live obs
        try:
            battle_select(list(cand))
            valid.append(cand)
        except Exception:
            pass
        battle_finish()
    return valid


def capture_games(deck: list[int], games: int = 30) -> dict:
    discovered: dict[str, dict] = {}
    for g in range(games):
        obs, start = battle_start(deck, deck)
        if obs is None:
            continue
        steps = 0
        try:
            while steps < 600:
                if obs.get("select") is None:
                    obs = battle_select(deck)
                    steps += 1
                    continue
                select = obs.get("select") or {}
                opts = [dict(o) if isinstance(o, dict) else {} for o in (select.get("option") or [])]
                lo, hi = int(select.get("minCount", 0)), int(select.get("maxCount", 0))
                sem = semantic_schema_key_from(
                    select.get("type"),
                    select.get("context"),
                    lo,
                    hi,
                    len(opts),
                    opts,
                )
                if sem not in discovered:
                    discovered[sem] = {
                        "semantic_schema_key": sem,
                        "select_type": select.get("type"),
                        "context": select.get("context"),
                        "min_count": lo,
                        "max_count": hi,
                        "option_type_pattern": [o.get("type") for o in opts],
                        "observation": redact_for_fixture(copy.deepcopy(obs)),
                    }
                # greedy legal: pick index 0 for single, [] for optional try
                if lo == 0 and hi == 0:
                    choice: list[int] = []
                elif lo == 0 and hi == 1:
                    choice = [0] if opts else []
                else:
                    choice = [0] if opts else []
                try:
                    obs = battle_select(choice)
                except Exception:
                    if lo == 0 and hi == 1:
                        try:
                            obs = battle_select([])
                        except Exception:
                            break
                    else:
                        break
                steps += 1
                if int((obs.get("current") or {}).get("result", -1)) >= 0:
                    break
        finally:
            battle_finish()
    return discovered


def main() -> int:
    deck_path = ROOT / "submission" / "deck.csv"
    deck = [int(x) for x in deck_path.read_text().split() if x.strip()]
    discovered = capture_games(deck, games=40)
    out = ROOT / "docs" / "competition_contract" / "captured_schemas.json"
    out.write_text(json.dumps(list(discovered.values()), indent=2), encoding="utf-8")
    print(f"captured {len(discovered)} schemas -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
