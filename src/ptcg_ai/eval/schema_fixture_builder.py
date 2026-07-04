"""Offline fixture builder — host apply evidence for schema promotion."""
from __future__ import annotations

import copy
import itertools
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..host.raw_observation import redact_for_fixture


@dataclass(frozen=True)
class EnumerationResult:
    verified_patterns: list[list[int]]
    empty_response_legal: bool
    order_sensitive: bool
    duplicates_allowed: bool
    pattern_rule: str
    trials_attempted: int
    trials_limit: int
    truncated: bool
    truncation_reason: str | None


@dataclass
class FixtureBuildResult:
    fixture_path: str | None
    evidence_path: str | None
    host_apply_verified: bool
    enumeration: EnumerationResult | None
    error: str | None = None


def pattern_rule_for(lo: int, hi: int, *, order_sensitive: bool) -> str:
    if lo == 1 and hi == 1:
        return "any_singleton"
    if lo == 0 and hi == 1:
        return "optional_single"
    if lo == 0 and hi == 0:
        return "fixed"
    if order_sensitive:
        return "sequence"
    return "bounded_set"


def enumerate_candidate_responses(
    lo: int,
    hi: int,
    option_count: int,
    *,
    order_sensitive: bool = False,
    allow_duplicates: bool = False,
    max_trials: int = 256,
) -> tuple[list[list[int]], int, bool, str | None]:
    patterns: list[list[int]] = []
    trials = 0
    truncated = False
    reason: str | None = None
    for size in range(lo, hi + 1):
        if order_sensitive:
            iterator = itertools.permutations(range(option_count), size)
        elif allow_duplicates:
            iterator = itertools.product(range(option_count), repeat=size)
        else:
            iterator = itertools.combinations(range(option_count), size)
        for combo in iterator:
            trials += 1
            if trials > max_trials:
                truncated = True
                reason = f"enumeration_limit_{max_trials}"
                return patterns, trials, truncated, reason
            patterns.append(list(combo))
    return patterns, trials, truncated, reason


def replay_host_apply(
    deck: list[int],
    trace: list[list[int]],
    choice: list[int],
    *,
    battle_start: Callable,
    battle_select: Callable,
    battle_finish: Callable,
) -> bool:
    obs, _ = battle_start(deck, deck)
    if obs is None:
        return False
    try:
        for step in trace:
            obs = battle_select(step)
            if obs is None:
                return False
        result = battle_select(choice)
        return result is not None
    except Exception:
        return False
    finally:
        try:
            battle_finish()
        except Exception:
            pass


def verify_response_patterns(
    deck: list[int],
    trace: list[list[int]],
    lo: int,
    hi: int,
    option_count: int,
    *,
    order_sensitive: bool = False,
    allow_duplicates: bool = False,
    max_trials: int = 256,
    battle_start: Callable,
    battle_select: Callable,
    battle_finish: Callable,
) -> EnumerationResult:
    candidates, trials, truncated, reason = enumerate_candidate_responses(
        lo,
        hi,
        option_count,
        order_sensitive=order_sensitive,
        allow_duplicates=allow_duplicates,
        max_trials=max_trials,
    )
    verified: list[list[int]] = []
    for cand in candidates:
        if replay_host_apply(
            deck,
            trace,
            cand,
            battle_start=battle_start,
            battle_select=battle_select,
            battle_finish=battle_finish,
        ):
            verified.append(cand)
    empty_legal = [] in verified
    dup_allowed = any(len(p) != len(set(p)) for p in verified)
    return EnumerationResult(
        verified_patterns=verified,
        empty_response_legal=empty_legal,
        order_sensitive=order_sensitive,
        duplicates_allowed=dup_allowed,
        pattern_rule=pattern_rule_for(lo, hi, order_sensitive=order_sensitive),
        trials_attempted=trials,
        trials_limit=max_trials,
        truncated=truncated,
        truncation_reason=reason,
    )


def build_fixture_from_capture(
    capture: dict[str, Any],
    deck: list[int],
    *,
    output_dir: Path,
    tested_commit: str,
    battle_start: Callable,
    battle_select: Callable,
    battle_finish: Callable,
    slug: str,
) -> FixtureBuildResult:
    trace = [list(step) for step in capture.get("decision_trace_prefix") or []]
    meta = {
        "select_type": capture.get("select_type"),
        "context": capture.get("context"),
        "min_count": capture.get("min_count"),
        "max_count": capture.get("max_count"),
        "option_count": capture.get("option_count"),
    }
    lo = int(meta["min_count"])
    hi = int(meta["max_count"])
    n = int(meta["option_count"])
    order_sensitive = capture.get("selection_mode") == "sequence"
    enum = verify_response_patterns(
        deck,
        trace,
        lo,
        hi,
        n,
        order_sensitive=order_sensitive,
        battle_start=battle_start,
        battle_select=battle_select,
        battle_finish=battle_finish,
    )
    if not enum.verified_patterns:
        return FixtureBuildResult(
            fixture_path=None,
            evidence_path=None,
            host_apply_verified=False,
            enumeration=enum,
            error="no_verified_patterns",
        )
    obs_stub = {
        "select": {
            "type": meta["select_type"],
            "context": meta["context"],
            "minCount": lo,
            "maxCount": hi,
            "option": [{"type": t} for t in capture.get("option_type_pattern") or []],
        },
        "current": capture.get("public_state_summary") or {},
        "logs": [],
    }
    fixture = {
        "observation": redact_for_fixture(obs_stub),
        "replay_trace": trace,
        "metadata": meta,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    fixture_path = output_dir / f"{slug}.json"
    evidence_path = output_dir / f"{slug}.evidence.json"
    fixture_path.write_text(json.dumps(fixture, indent=2, default=str), encoding="utf-8")
    transition = {
        "verified_pattern_count": len(enum.verified_patterns),
        "empty_response_legal": enum.empty_response_legal,
        "order_sensitive": enum.order_sensitive,
    }
    evidence = {
        "semantic_schema_key": capture.get("semantic_schema_key"),
        "verified_patterns": enum.verified_patterns,
        "pattern_rule": enum.pattern_rule,
        "reference_option_count": n,
        "empty_response_legal": enum.empty_response_legal,
        "order_sensitive": enum.order_sensitive,
        "duplicates_allowed": enum.duplicates_allowed,
        "host_apply_verified": True,
        "select_type": meta["select_type"],
        "context": meta["context"],
        "option_type_pattern": list(capture.get("option_type_pattern") or []),
        "post_apply_transition_summary": transition,
        "tested_commit": tested_commit,
        "enumeration": asdict(enum),
    }
    evidence_path.write_text(json.dumps(evidence, indent=2, default=str), encoding="utf-8")
    return FixtureBuildResult(
        fixture_path=str(fixture_path),
        evidence_path=str(evidence_path),
        host_apply_verified=True,
        enumeration=enum,
    )
