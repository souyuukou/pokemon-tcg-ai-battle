"""Read-only decision telemetry — no raw observation or private card data."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DecisionTelemetry:
    used_fallback: bool
    fallback_reason: str | None
    emergency_mode: bool
    semantic_schema_key: str | None
    response_pattern: tuple[int, ...] | None
    elapsed_ms: float | None
    conservation_quality: str | None
    incident_code: str | None
    host_call_kind: str | None = None
