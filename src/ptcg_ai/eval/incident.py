"""Incident schema."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class IncidentRecord:
    incident_id: str
    artifact_id: str
    policy_version: str
    session_id_hash: str
    decision_counter: int
    reason_code: str
    response_schema_key: str
    request_fingerprint: str
    fallback_used: bool
    exception_class: str | None
    stage: str
    elapsed_ms: float
    rss_bytes: int | None
    reproducer_fixture_path: str | None
    status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
