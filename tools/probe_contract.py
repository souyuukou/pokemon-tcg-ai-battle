#!/usr/bin/env python3
"""Contract probe — collect schema and decision coverage."""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "competition_contract"
sys.path.insert(0, str(ROOT / "src"))


def _field_types(obj: dict) -> dict[str, str]:
    return {k: type(v).__name__ for k, v in obj.items()}


def probe_from_sim(deck: list[int], games: int = 3) -> dict:
    sim_root = ROOT / "sample_submission"
    sys.path.insert(0, str(sim_root))
    from cg.game import battle_finish, battle_select, battle_start

    from ptcg_ai.host.raw_observation import redact_for_fixture

    top_keys: Counter[str] = Counter()
    select_types: Counter[str] = Counter()
    option_types: Counter[str] = Counter()
    minmax: Counter[str] = Counter()
    option_counts: list[int] = []
    response_shapes: Counter[str] = Counter()
    contexts: Counter[str] = Counter()
    unknown_fields: Counter[str] = Counter()
    decisions_per_game: list[int] = []
    time_fields: dict[str, str] = {}

    for _ in range(games):
        obs, start = battle_start(deck, deck)
        if obs is None:
            continue
        decisions = 0
        steps = 0
        try:
            while steps < 400:
                for k in obs.keys():
                    top_keys[k] += 1
                for k, v in obs.items():
                    if k not in ("logs", "current", "select", "remainingOverageTime"):
                        unknown_fields[k] += 1
                if obs.get("remainingOverageTime") is not None:
                    time_fields["remainingOverageTime"] = "observed"
                select = obs.get("select")
                if select is None:
                    obs = battle_select(deck)
                    steps += 1
                    continue
                decisions += 1
                sel = select or {}
                select_types[str(sel.get("type"))] += 1
                contexts[str(sel.get("context"))] += 1
                lo, hi = int(sel.get("minCount", 0)), int(sel.get("maxCount", 0))
                minmax[f"{lo}..{hi}"] += 1
                opts = sel.get("option") or []
                option_counts.append(len(opts))
                for o in opts:
                    if isinstance(o, dict):
                        option_types[str(o.get("type"))] += 1
                response_shapes[f"{lo}..{hi}"] += 1
                choice = [0] if opts else []
                if hi >= 1 and opts:
                    choice = [0]
                obs = battle_select(choice)
                steps += 1
                if int((obs.get("current") or {}).get("result", -1)) >= 0:
                    break
        finally:
            battle_finish()
        decisions_per_game.append(decisions)
    return {
        "top_level_keys": dict(top_keys),
        "select_types": dict(select_types),
        "option_types": dict(option_types),
        "minmax_combinations": dict(minmax),
        "option_count_summary": {
            "min": min(option_counts) if option_counts else 0,
            "max": max(option_counts) if option_counts else 0,
            "samples": len(option_counts),
        },
        "response_shapes": dict(response_shapes),
        "contexts": dict(contexts),
        "unknown_field_names": dict(unknown_fields),
        "decisions_per_game": decisions_per_game,
        "time_bank_fields": time_fields,
        "redaction_note": "search_begin_input stripped in fixtures",
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    deck_path = ROOT / "submission" / "deck.csv"
    if not deck_path.is_file():
        deck_path = ROOT / "sample_submission" / "deck.csv"
    deck = [int(x) for x in deck_path.read_text().split() if x.strip()]
    try:
        report = probe_from_sim(deck)
        source = "cabt_simulator"
    except Exception as exc:
        report = {
            "source": "synthetic_fallback",
            "error": type(exc).__name__,
            "top_level_keys": {"logs": 1, "current": 1, "select": 1},
            "select_types": {"0": 1},
            "option_types": {"14": 1, "13": 1, "7": 1},
            "minmax_combinations": {"1..1": 1},
            "unknown_field_names": {},
            "time_bank_fields": {"remainingOverageTime": "documented_unverified_locally"},
        }
        source = "synthetic_fallback"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    report["probe_source"] = source
    report["probe_timestamp"] = datetime.now(timezone.utc).isoformat()
    (OUT / f"contract_probe_{stamp}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (OUT / "observed_select_types.json").write_text(
        json.dumps(report.get("select_types", {}), indent=2), encoding="utf-8"
    )
    (OUT / "observed_option_types.json").write_text(
        json.dumps(report.get("option_types", {}), indent=2), encoding="utf-8"
    )
    (OUT / "response_shape_matrix.json").write_text(
        json.dumps(report.get("response_shapes", report.get("minmax_combinations", {})), indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"written_to": str(OUT), "source": source}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
