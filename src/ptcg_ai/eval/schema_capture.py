"""Schema capture for M0-H discovery harvest — redacted, no secrets."""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..contract.manifest import sha256_deck
from ..host.host_envelope import HostCallKind, preflight
from ..host.raw_observation import RawObservation, strip_hidden_from_raw
from ..host.schema_registry import REGISTRY
from ..semantic.action_categories import categorize_option_type
from ..semantic.schema_keys import SelectionSemanticKey


FORBIDDEN_CAPTURE_KEYS = frozenset(
    {
        "search_begin_input",
    }
)


@dataclass(frozen=True)
class SchemaCaptureRecord:
    capture_id: str
    tested_commit: str
    simulator_version: str
    deck_a_hash: str
    deck_b_hash: str
    agent_seat: int | None
    game_index: int
    turn: int | None
    decision_index: int
    semantic_schema_key: str
    select_type: int | str | None
    context: int | str | None
    min_count: int
    max_count: int
    selection_mode: str
    option_type_pattern: tuple[int | str | None, ...]
    option_count: int
    option_category_summary: tuple[str, ...]
    public_state_summary: dict[str, Any]
    actor_view_summary: dict[str, Any]
    replay_trace: tuple[tuple[int, ...], ...]
    decision_trace_prefix: tuple[tuple[int, ...], ...]
    desired_seat: int | None
    schema_fingerprint: str
    host_call_kind: str
    time_bank_mode: str
    captured_at: str


@dataclass
class SchemaBacklogRow:
    semantic_schema_key: str
    observation_count: int = 0
    first_seen_commit: str = ""
    last_seen_commit: str = ""
    select_type: int | str | None = None
    context: int | str | None = None
    min_count: int = 0
    max_count: int = 0
    selection_mode: str = ""
    option_type_pattern: list[int | str | None] = field(default_factory=list)
    example_capture_ids: list[str] = field(default_factory=list)
    currently_supported: bool = False
    fixture_status: str = "pending"
    evidence_status: str = "pending"


def _option_dicts(select: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(o) if isinstance(o, dict) else {} for o in (select.get("option") or [])]


def semantic_key_from_obs(obs: dict[str, Any]) -> SelectionSemanticKey | None:
    select = obs.get("select")
    if not isinstance(select, dict):
        return None
    opts = _option_dicts(select)
    lo = int(select.get("minCount", 0))
    hi = int(select.get("maxCount", 0))
    return SelectionSemanticKey.from_contract_fields(
        select_type=select.get("type"),
        context=select.get("context"),
        min_count=lo,
        max_count=hi,
        option_count=len(opts),
        options=opts,
    )


def _public_state_summary(obs: dict[str, Any]) -> dict[str, Any]:
    redacted = strip_hidden_from_raw(obs)
    current = redacted.get("current") or {}
    players = current.get("players") or []
    summary_players = []
    for p in players[:2]:
        if not isinstance(p, dict):
            summary_players.append({})
            continue
        summary_players.append(
            {
                "handCount": p.get("handCount"),
                "deckCount": p.get("deckCount"),
                "benchCount": len(p.get("bench") or []),
                "activeCount": len(p.get("active") or []),
                "discardCount": len(p.get("discard") or []),
                "prizeCount": len(p.get("prize") or []),
            }
        )
    return {
        "turn": current.get("turn"),
        "yourIndex": current.get("yourIndex"),
        "result": current.get("result"),
        "players": summary_players,
        "log_count": len(redacted.get("logs") or []),
    }


def _actor_view_summary(obs: dict[str, Any]) -> dict[str, Any]:
    select = obs.get("select") or {}
    opts = _option_dicts(select)
    context = select.get("context")
    categories = [categorize_option_type(o.get("type"), context).value for o in opts]
    return {
        "option_count": len(opts),
        "option_categories": categories,
        "select_type": select.get("type"),
        "context": context,
        "min_count": select.get("minCount"),
        "max_count": select.get("maxCount"),
    }


def _schema_fingerprint(sem: SelectionSemanticKey) -> str:
    payload = {
        "key": sem.key,
        "select_type": sem.select_type,
        "context": sem.context,
        "min_count": sem.min_count,
        "max_count": sem.max_count,
        "selection_mode": sem.selection_mode,
        "option_type_pattern": list(sem.option_type_pattern),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]


def build_capture_record(
    obs: dict[str, Any],
    *,
    tested_commit: str,
    simulator_version: str,
    deck: list[int],
    agent_seat: int | None,
    game_index: int,
    decision_index: int,
    replay_trace: list[list[int]],
    time_bank_mode: str,
    desired_seat: int | None = None,
) -> SchemaCaptureRecord | None:
    sem = semantic_key_from_obs(obs)
    if sem is None:
        return None
    redacted = strip_hidden_from_raw(obs)
    for key in FORBIDDEN_CAPTURE_KEYS:
        redacted.pop(key, None)
    current = redacted.get("current") or {}
    deck_hash = sha256_deck(deck)
    envelope = preflight(RawObservation.from_dict(obs))
    return SchemaCaptureRecord(
        capture_id=uuid.uuid4().hex,
        tested_commit=tested_commit,
        simulator_version=simulator_version,
        deck_a_hash=deck_hash,
        deck_b_hash=deck_hash,
        agent_seat=agent_seat,
        game_index=game_index,
        turn=current.get("turn") if isinstance(current, dict) else None,
        decision_index=decision_index,
        semantic_schema_key=sem.key,
        select_type=sem.select_type,
        context=sem.context,
        min_count=sem.min_count,
        max_count=sem.max_count,
        selection_mode=sem.selection_mode,
        option_type_pattern=sem.option_type_pattern,
        option_count=len(sem.option_type_pattern),
        option_category_summary=tuple(
            categorize_option_type(t, sem.context).value for t in sem.option_type_pattern
        ),
        public_state_summary=_public_state_summary(obs),
        actor_view_summary=_actor_view_summary(obs),
        replay_trace=tuple(tuple(step) for step in replay_trace),
        decision_trace_prefix=tuple(tuple(step) for step in replay_trace),
        desired_seat=desired_seat,
        schema_fingerprint=_schema_fingerprint(sem),
        host_call_kind=envelope.host_call_kind.value,
        time_bank_mode=time_bank_mode,
        captured_at=datetime.now(timezone.utc).isoformat(),
    )


def _is_supported(sem: SelectionSemanticKey) -> bool:
    template = REGISTRY.lookup_for_contract(
        canonical_semantic_key=sem.key,
        select_type=sem.select_type,
        context=sem.context,
        min_count=sem.min_count,
        max_count=sem.max_count,
        option_count=len(sem.option_type_pattern),
        option_types=sem.option_type_pattern,
    )
    return template is not None and template.host_apply_verified


class SchemaCaptureStore:
    def __init__(self, run_id: str, root: Path) -> None:
        self.run_id = run_id
        self.root = root / "artifacts" / "schema_capture" / run_id
        self.root.mkdir(parents=True, exist_ok=True)
        self._captures: dict[str, SchemaCaptureRecord] = {}
        self._backlog: dict[str, SchemaBacklogRow] = {}

    def save_capture(self, record: SchemaCaptureRecord) -> Path:
        self._captures[record.capture_id] = record
        sem_key = record.semantic_schema_key
        row = self._backlog.get(sem_key)
        if row is None:
            row = SchemaBacklogRow(
                semantic_schema_key=sem_key,
                first_seen_commit=record.tested_commit,
                select_type=record.select_type,
                context=record.context,
                min_count=record.min_count,
                max_count=record.max_count,
                selection_mode=record.selection_mode,
                option_type_pattern=list(record.option_type_pattern),
                currently_supported=_is_supported(
                    SelectionSemanticKey.from_contract_fields(
                        select_type=record.select_type,
                        context=record.context,
                        min_count=record.min_count,
                        max_count=record.max_count,
                        option_count=record.option_count,
                        options=[{"type": t} for t in record.option_type_pattern],
                    )
                ),
            )
            self._backlog[sem_key] = row
        row.observation_count += 1
        row.last_seen_commit = record.tested_commit
        if record.capture_id not in row.example_capture_ids:
            row.example_capture_ids.append(record.capture_id)
        if len(row.example_capture_ids) > 5:
            row.example_capture_ids = row.example_capture_ids[-5:]
        path = self.root / f"{record.capture_id}.json"
        payload = asdict(record)
        payload["option_type_pattern"] = list(record.option_type_pattern)
        payload["option_category_summary"] = list(record.option_category_summary)
        payload["replay_trace"] = [list(step) for step in record.replay_trace]
        payload["decision_trace_prefix"] = [list(step) for step in record.decision_trace_prefix]
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return path

    def write_run_summary(self) -> Path:
        summary = {
            "run_id": self.run_id,
            "capture_count": len(self._captures),
            "unique_schemas": len(self._backlog),
            "capture_ids": sorted(self._captures.keys()),
        }
        path = self.root / "run_summary.json"
        path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return path

    def backlog_rows(self) -> list[SchemaBacklogRow]:
        return sorted(self._backlog.values(), key=lambda r: (-r.observation_count, r.semantic_schema_key))

    def inventory_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "schema_count": len(self._backlog),
            "schemas": [
                {
                    "semantic_schema_key": row.semantic_schema_key,
                    "observation_count": row.observation_count,
                    "first_seen_commit": row.first_seen_commit,
                    "last_seen_commit": row.last_seen_commit,
                    "select_type": row.select_type,
                    "context": row.context,
                    "min_count": row.min_count,
                    "max_count": row.max_count,
                    "selection_mode": row.selection_mode,
                    "option_type_pattern": row.option_type_pattern,
                    "example_capture_ids": row.example_capture_ids,
                    "currently_supported": row.currently_supported,
                    "fixture_status": row.fixture_status,
                    "evidence_status": row.evidence_status,
                }
                for row in self.backlog_rows()
            ],
        }

    def write_inventory(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.inventory_dict(), indent=2, default=str), encoding="utf-8")
        return path
