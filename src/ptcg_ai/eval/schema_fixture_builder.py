"""Offline fixture builder — host apply evidence with replay-target assertion."""
from __future__ import annotations

import hashlib
import itertools
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Literal

from ..host.raw_observation import redact_for_fixture, strip_hidden_from_raw
from ..semantic.schema_keys import SelectionSemanticKey

DuplicatesPolicy = Literal["verified_disallowed", "verified_allowed", "unverified"]


@dataclass(frozen=True)
class CaptureContract:
    semantic_schema_key: str
    select_type: int | str | None
    context: int | str | None
    min_count: int
    max_count: int
    selection_mode: str
    option_count: int
    option_type_pattern: tuple[int | str | None, ...]

    @classmethod
    def from_capture(cls, capture: dict[str, Any]) -> CaptureContract:
        pattern = tuple(capture.get("option_type_pattern") or [])
        return cls(
            semantic_schema_key=str(capture.get("semantic_schema_key", "")),
            select_type=capture.get("select_type"),
            context=capture.get("context"),
            min_count=int(capture.get("min_count", 0)),
            max_count=int(capture.get("max_count", 0)),
            selection_mode=str(capture.get("selection_mode", "")),
            option_count=int(capture.get("option_count", len(pattern))),
            option_type_pattern=pattern,
        )

    def matches_obs(self, obs: dict[str, Any]) -> bool:
        select = obs.get("select")
        if not isinstance(select, dict):
            return False
        opts = [dict(o) if isinstance(o, dict) else {} for o in (select.get("option") or [])]
        lo = int(select.get("minCount", 0))
        hi = int(select.get("maxCount", 0))
        sem = SelectionSemanticKey.from_contract_fields(
            select_type=select.get("type"),
            context=select.get("context"),
            min_count=lo,
            max_count=hi,
            option_count=len(opts),
            options=opts,
        )
        if sem.key != self.semantic_schema_key:
            return False
        types = tuple(o.get("type") for o in opts)
        return (
            select.get("type") == self.select_type
            and select.get("context") == self.context
            and lo == self.min_count
            and hi == self.max_count
            and sem.selection_mode == self.selection_mode
            and len(opts) == self.option_count
            and types == self.option_type_pattern
        )


@dataclass(frozen=True)
class ReplayTargetResult:
    ok: bool
    obs: dict[str, Any] | None
    reason: str | None = None


@dataclass(frozen=True)
class EnumerationResult:
    verified_patterns: list[list[int]]
    empty_response_legal: bool
    order_sensitive: bool
    duplicates_policy: DuplicatesPolicy
    selection_shape: str
    pattern_rule: str
    trials_attempted: int
    trials_limit: int
    truncated: bool
    truncation_reason: str | None
    post_apply_hashes: dict[str, str]


@dataclass
class FixtureBuildResult:
    fixture_path: str | None
    evidence_path: str | None
    host_apply_verified: bool
    enumeration: EnumerationResult | None
    error: str | None = None


def public_state_hash(obs: dict[str, Any]) -> str:
    redacted = strip_hidden_from_raw(obs)
    current = redacted.get("current") or {}
    players = current.get("players") or []
    summary = {
        "turn": current.get("turn"),
        "yourIndex": current.get("yourIndex"),
        "result": current.get("result"),
        "turnActionCount": current.get("turnActionCount"),
        "players": [
            {
                "handCount": (p or {}).get("handCount"),
                "deckCount": (p or {}).get("deckCount"),
                "benchCount": len((p or {}).get("bench") or []),
                "activeCount": len((p or {}).get("active") or []),
                "discardCount": len((p or {}).get("discard") or []),
                "prizeCount": len((p or {}).get("prize") or []),
            }
            for p in players[:2]
        ],
        "log_count": len(redacted.get("logs") or []),
    }
    blob = json.dumps(summary, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


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


def selection_shape_for(lo: int, hi: int) -> str:
    if lo == hi == 1:
        return "single"
    if lo == 0 and hi == 1:
        return "optional_single"
    if lo == hi:
        return "fixed_count"
    return "bounded"


def replay_to_capture_target(
    deck: list[int],
    trace: list[list[int]],
    contract: CaptureContract,
    *,
    battle_start: Callable,
    battle_select: Callable,
    battle_finish: Callable,
) -> ReplayTargetResult:
    obs, _ = battle_start(deck, deck)
    if obs is None:
        return ReplayTargetResult(False, None, "battle_start_failed")
    try:
        for step in trace:
            obs = battle_select(step)
            if obs is None:
                return ReplayTargetResult(False, None, "trace_step_failed")
        if not contract.matches_obs(obs):
            return ReplayTargetResult(False, None, "replay_did_not_reach_capture_target")
        return ReplayTargetResult(True, obs, None)
    except Exception as exc:
        return ReplayTargetResult(False, None, f"replay_exception:{type(exc).__name__}")
    finally:
        try:
            battle_finish()
        except Exception:
            pass


def _apply_candidate(
    deck: list[int],
    trace: list[list[int]],
    choice: list[int],
    *,
    battle_start: Callable,
    battle_select: Callable,
    battle_finish: Callable,
) -> tuple[bool, str | None]:
    obs, _ = battle_start(deck, deck)
    if obs is None:
        return False, None
    try:
        for step in trace:
            obs = battle_select(step)
            if obs is None:
                return False, None
        result = battle_select(choice)
        if result is None:
            return False, None
        return True, public_state_hash(result)
    except Exception:
        return False, None
    finally:
        try:
            battle_finish()
        except Exception:
            pass


def enumerate_candidate_responses(
    lo: int,
    hi: int,
    option_count: int,
    *,
    include_duplicates: bool = False,
    max_trials: int = 256,
) -> tuple[list[list[int]], int, bool, str | None]:
    patterns: list[list[int]] = []
    trials = 0
    truncated = False
    reason: str | None = None
    seen: set[tuple[int, ...]] = set()

    def _add(pat: list[int]) -> bool:
        nonlocal trials
        key = tuple(pat)
        if key in seen:
            return True
        seen.add(key)
        trials += 1
        if trials > max_trials:
            return False
        patterns.append(pat)
        return True

    for size in range(lo, hi + 1):
        for combo in itertools.combinations(range(option_count), size):
            if not _add(list(combo)):
                truncated = True
                reason = f"enumeration_limit_{max_trials}"
                return patterns, trials, truncated, reason
        if include_duplicates and size >= 2:
            for idx in range(option_count):
                dup = [idx] * size
                if lo <= len(dup) <= hi and not _add(dup):
                    truncated = True
                    reason = f"enumeration_limit_{max_trials}"
                    return patterns, trials, truncated, reason
    return patterns, trials, truncated, reason


def _measure_order_sensitivity(
    deck: list[int],
    trace: list[list[int]],
    verified: list[list[int]],
    *,
    battle_start: Callable,
    battle_select: Callable,
    battle_finish: Callable,
) -> bool:
    for pat in verified:
        if len(pat) < 2:
            continue
        rev = list(reversed(pat))
        if rev == pat or rev not in verified:
            continue
        ok_a, hash_a = _apply_candidate(
            deck, trace, pat, battle_start=battle_start, battle_select=battle_select, battle_finish=battle_finish
        )
        ok_b, hash_b = _apply_candidate(
            deck, trace, rev, battle_start=battle_start, battle_select=battle_select, battle_finish=battle_finish
        )
        if ok_a and ok_b and hash_a and hash_b and hash_a != hash_b:
            return True
    return False


def _measure_duplicates_policy(
    deck: list[int],
    trace: list[list[int]],
    lo: int,
    hi: int,
    option_count: int,
    *,
    battle_start: Callable,
    battle_select: Callable,
    battle_finish: Callable,
) -> DuplicatesPolicy:
    if hi < 2 or option_count < 1:
        return "verified_disallowed"
    duplicate_candidate = [0, 0]
    if not (lo <= len(duplicate_candidate) <= hi):
        return "unverified"
    ok, _hash = _apply_candidate(
        deck,
        trace,
        duplicate_candidate,
        battle_start=battle_start,
        battle_select=battle_select,
        battle_finish=battle_finish,
    )
    if ok:
        return "verified_allowed"
    return "verified_disallowed"


def verify_response_patterns(
    deck: list[int],
    trace: list[list[int]],
    contract: CaptureContract,
    *,
    max_trials: int = 256,
    battle_start: Callable,
    battle_select: Callable,
    battle_finish: Callable,
) -> tuple[EnumerationResult | None, str | None]:
    target = replay_to_capture_target(
        deck,
        trace,
        contract,
        battle_start=battle_start,
        battle_select=battle_select,
        battle_finish=battle_finish,
    )
    if not target.ok:
        return None, target.reason or "replay_did_not_reach_capture_target"

    lo, hi, n = contract.min_count, contract.max_count, contract.option_count
    candidates, trials, truncated, reason = enumerate_candidate_responses(
        lo, hi, n, include_duplicates=True, max_trials=max_trials
    )
    verified: list[list[int]] = []
    post_hashes: dict[str, str] = {}
    for cand in candidates:
        ok, state_hash = _apply_candidate(
            deck,
            trace,
            cand,
            battle_start=battle_start,
            battle_select=battle_select,
            battle_finish=battle_finish,
        )
        if ok:
            verified.append(cand)
            post_hashes[json.dumps(cand)] = state_hash or ""

    if not verified:
        return None, "no_verified_patterns_after_replay_assertion"

    order_sensitive = _measure_order_sensitivity(
        deck,
        trace,
        verified,
        battle_start=battle_start,
        battle_select=battle_select,
        battle_finish=battle_finish,
    )
    duplicates_policy = _measure_duplicates_policy(
        deck,
        trace,
        lo,
        hi,
        n,
        battle_start=battle_start,
        battle_select=battle_select,
        battle_finish=battle_finish,
    )
    shape = selection_shape_for(lo, hi)
    return (
        EnumerationResult(
            verified_patterns=verified,
            empty_response_legal=[] in verified,
            order_sensitive=order_sensitive,
            duplicates_policy=duplicates_policy,
            selection_shape=shape,
            pattern_rule=pattern_rule_for(lo, hi, order_sensitive=order_sensitive),
            trials_attempted=trials,
            trials_limit=max_trials,
            truncated=truncated,
            truncation_reason=reason,
            post_apply_hashes=post_hashes,
        ),
        None,
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
    trace = [list(step) for step in capture.get("replay_trace") or capture.get("decision_trace_prefix") or []]
    contract = CaptureContract.from_capture(capture)
    enum, err = verify_response_patterns(
        deck,
        trace,
        contract,
        battle_start=battle_start,
        battle_select=battle_select,
        battle_finish=battle_finish,
    )
    if enum is None:
        return FixtureBuildResult(
            fixture_path=None,
            evidence_path=None,
            host_apply_verified=False,
            enumeration=None,
            error=err,
        )
    if enum.duplicates_policy == "unverified":
        return FixtureBuildResult(
            fixture_path=None,
            evidence_path=None,
            host_apply_verified=False,
            enumeration=enum,
            error="duplicates_policy_unverified",
        )

    obs_stub = {
        "select": {
            "type": contract.select_type,
            "context": contract.context,
            "minCount": contract.min_count,
            "maxCount": contract.max_count,
            "option": [{"type": t} for t in contract.option_type_pattern],
        },
        "current": capture.get("public_state_summary") or {},
        "logs": [],
    }
    fixture = {
        "observation": redact_for_fixture(obs_stub),
        "replay_trace": trace,
        "metadata": {
            "select_type": contract.select_type,
            "context": contract.context,
            "min_count": contract.min_count,
            "max_count": contract.max_count,
            "option_count": contract.option_count,
            "semantic_schema_key": contract.semantic_schema_key,
            "agent_seat": capture.get("agent_seat"),
            "desired_seat": capture.get("desired_seat"),
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    fixture_path = output_dir / f"{slug}.json"
    evidence_path = output_dir / f"{slug}.evidence.json"
    fixture_path.write_text(json.dumps(fixture, indent=2, default=str), encoding="utf-8")
    duplicates_allowed = enum.duplicates_policy == "verified_allowed"
    transition = {
        "verified_pattern_count": len(enum.verified_patterns),
        "empty_response_legal": enum.empty_response_legal,
        "order_sensitive": enum.order_sensitive,
        "selection_shape": enum.selection_shape,
        "sample_post_apply_hashes": dict(list(enum.post_apply_hashes.items())[:8]),
    }
    evidence = {
        "semantic_schema_key": contract.semantic_schema_key,
        "verified_patterns": enum.verified_patterns,
        "pattern_rule": enum.pattern_rule,
        "reference_option_count": contract.option_count,
        "empty_response_legal": enum.empty_response_legal,
        "order_sensitive": enum.order_sensitive,
        "duplicates_allowed": duplicates_allowed,
        "duplicates_policy": enum.duplicates_policy,
        "selection_shape": enum.selection_shape,
        "host_apply_verified": True,
        "replay_target_asserted": True,
        "select_type": contract.select_type,
        "context": contract.context,
        "option_type_pattern": list(contract.option_type_pattern),
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
