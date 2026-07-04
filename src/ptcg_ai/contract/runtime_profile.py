"""Versioned runtime resource and budget profile."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimeProfile:
    profile_id: str
    time_bank_seconds: float
    safety_margin_seconds: float
    hard_reserve_seconds: float
    full_eval_limit: int
    soft_cache_max_entries: int
    emergency_threshold_seconds: float
    notes: tuple[str, ...]


DEFAULT_PROFILE = RuntimeProfile(
    profile_id="local_b0_v1",
    time_bank_seconds=600.0,
    safety_margin_seconds=60.0,
    hard_reserve_seconds=2.0,
    full_eval_limit=32,
    soft_cache_max_entries=64,
    emergency_threshold_seconds=30.0,
    notes=("conservative local defaults",),
)


def load_runtime_profile(path: Path | None = None) -> RuntimeProfile:
    if path is None or not path.is_file():
        return DEFAULT_PROFILE
    data = json.loads(path.read_text(encoding="utf-8"))
    return RuntimeProfile(
        profile_id=str(data.get("profile_id", "unknown")),
        time_bank_seconds=float(data.get("time_bank_seconds", 600.0)),
        safety_margin_seconds=float(data.get("safety_margin_seconds", 60.0)),
        hard_reserve_seconds=float(data.get("hard_reserve_seconds", 2.0)),
        full_eval_limit=int(data.get("full_eval_limit", 32)),
        soft_cache_max_entries=int(data.get("soft_cache_max_entries", 64)),
        emergency_threshold_seconds=float(data.get("emergency_threshold_seconds", 30.0)),
        notes=tuple(data.get("notes", ())),
    )
