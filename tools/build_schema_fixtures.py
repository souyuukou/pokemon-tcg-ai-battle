#!/usr/bin/env python3
"""Capture fixtures with replay traces and host-apply evidence for schema matrix."""
from __future__ import annotations

import copy
import itertools
import json
import random
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "sample_submission"))

from cg.game import battle_finish, battle_select, battle_start
from ptcg_ai.host.raw_observation import redact_for_fixture


def _replay_apply(deck: list[int], trace: list[list[int]], choice: list[int]) -> bool:
    obs, _ = battle_start(deck, deck)
    if obs is None:
        return False
    try:
        for step in trace:
            obs = battle_select(step)
        battle_select(choice)
        return True
    except Exception:
        return False
    finally:
        battle_finish()


def _candidate_patterns(lo: int, hi: int, n: int, *, order_sensitive: bool) -> list[list[int]]:
    patterns: list[list[int]] = []
    for size in range(lo, hi + 1):
        if order_sensitive:
            for combo in itertools.permutations(range(n), size):
                patterns.append(list(combo))
        else:
            for combo in itertools.combinations(range(n), size):
                patterns.append(list(combo))
    return patterns


def _verify_patterns(deck: list[int], trace: list[list[int]], lo: int, hi: int, n: int, *, order_sensitive: bool) -> list[list[int]]:
    verified: list[list[int]] = []
    for cand in _candidate_patterns(lo, hi, n, order_sensitive=order_sensitive):
        if _replay_apply(deck, trace, cand):
            verified.append(cand)
    return verified


def _capture_until(deck: list[int], predicate, *, random_attempts: int = 0) -> tuple[dict, list[list[int]]] | None:
    for attempt in range(1 + random_attempts):
        obs, _ = battle_start(deck, deck)
        trace: list[list[int]] = []
        rng = random.Random(attempt + 17)
        try:
            while True:
                if obs.get("select") is None:
                    step = list(deck)
                    trace.append(step)
                    obs = battle_select(step)
                    continue
                s = obs["select"]
                lo, hi = int(s["minCount"]), int(s["maxCount"])
                n = len(s.get("option") or [])
                if predicate(s, lo, hi, n):
                    payload = {
                        "observation": redact_for_fixture(copy.deepcopy(obs)),
                        "replay_trace": trace,
                        "metadata": {
                            "select_type": s.get("type"),
                            "context": s.get("context"),
                            "min_count": lo,
                            "max_count": hi,
                            "option_count": n,
                        },
                    }
                    return payload, trace
                if attempt == 0:
                    if lo == 0 and hi == 0:
                        choice: list[int] = []
                    elif lo == 0 and hi == 1:
                        choice = [0] if n else []
                    elif lo == 0 and hi <= 3:
                        choice = [0] if n else []
                    else:
                        choice = [0] if n else []
                else:
                    if lo == 0 and hi == 0:
                        choice = []
                    elif n == 0:
                        choice = []
                    else:
                        maxk = min(hi, n)
                        k = rng.randint(lo, maxk)
                        choice = rng.sample(range(n), k) if k else []
                trace.append(choice)
                obs = battle_select(choice)
                if int((obs.get("current") or {}).get("result", -1)) >= 0:
                    break
        finally:
            battle_finish()
    return None


def _pattern_rule(lo: int, hi: int, *, order_sensitive: bool) -> str:
    if lo == 1 and hi == 1:
        return "any_singleton"
    if lo == 0 and hi == 1:
        return "optional_single"
    if lo == 0 and hi == 0:
        return "fixed"
    if order_sensitive:
        return "fixed"
    return "bounded_set"


def capture_and_verify(deck: list[int], *, name: str, predicate, random_attempts: int = 150) -> bool:
    out_dir = ROOT / "docs" / "competition_contract" / "fixtures"
    out_dir.mkdir(parents=True, exist_ok=True)
    captured = _capture_until(deck, predicate, random_attempts=0)
    if captured is None:
        captured = _capture_until(deck, predicate, random_attempts=random_attempts)
    if captured is None:
        print(f"skip {name}: not found")
        return False
    payload, trace = captured
    meta = payload["metadata"]
    lo, hi, n = meta["min_count"], meta["max_count"], meta["option_count"]
    order_sensitive = lo == hi and lo > 1
    verified = _verify_patterns(deck, trace, lo, hi, n, order_sensitive=order_sensitive)
    if not verified:
        print(f"skip {name}: no host-verified patterns")
        return False
    rule = _pattern_rule(lo, hi, order_sensitive=order_sensitive)
    if rule == "optional_single" and [] not in verified:
        rule = "fixed"
    fixture_path = out_dir / f"{name}.json"
    evidence_path = out_dir / f"{name}.evidence.json"
    fixture_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    evidence = {
        "semantic_schema_key": f"family:{meta['select_type']}:{lo}:{hi}:{_mode_name(lo, hi, n)}",
        "verified_patterns": verified,
        "pattern_rule": rule,
        "reference_option_count": n,
        "empty_response_legal": [] in verified,
        "order_sensitive": order_sensitive,
        "duplicates_allowed": False,
        "host_apply_verified": len(verified) > 0,
    }
    evidence_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(f"wrote {name}: {len(verified)} verified patterns")
    return True


def _mode_name(lo: int, hi: int, n: int) -> str:
    if lo == 0 and hi == 0:
        return "empty"
    if lo == 1 and hi == 1:
        return "single"
    if lo == 0 and hi == 1:
        return "optional_single"
    return "sequence"


def main() -> int:
    deck_path = ROOT / "submission" / "deck.csv"
    deck = [int(x) for x in deck_path.read_text().split() if x.strip()]

    targets: list[tuple[str, Any]] = [
        ("single_main", lambda s, lo, hi, n: lo == 1 and hi == 1 and s.get("type") == 0 and n >= 2),
        ("single_type1", lambda s, lo, hi, n: lo == 1 and hi == 1 and s.get("type") == 1 and n >= 2),
        ("optional_single_ctx2", lambda s, lo, hi, n: lo == 0 and hi == 1 and s.get("context") == 2 and n == 1),
        ("bounded_0_2_ctx5", lambda s, lo, hi, n: lo == 0 and hi == 2 and s.get("context") == 5 and n == 3),
        ("bounded_0_3_ctx2", lambda s, lo, hi, n: lo == 0 and hi == 3 and s.get("context") == 2 and n == 3),
    ]
    ok = 0
    for name, pred in targets:
        for _ in range(300):
            if capture_and_verify(deck, name=name, predicate=pred):
                ok += 1
                break
        else:
            print(f"failed {name} after retries")
    print(f"captured {ok}/{len(targets)}")
    return 0 if ok >= 4 else 1


if __name__ == "__main__":
    raise SystemExit(main())
