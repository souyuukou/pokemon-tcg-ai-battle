"""Actor observation history ledger — incremental log processing."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ObservationLedger:
    game_sequence: int = 0
    decision_counter: int = 0
    public_events: list[dict[str, Any]] = field(default_factory=list)
    shuffle_invalidations: int = 0
    known_order_valid: bool = False
    last_processed_log_count: int = 0
    last_processed_log_fingerprint: str = ""
    last_processed_turn_marker: int | None = None

    def record_public_event(self, event: dict[str, Any]) -> None:
        safe = {k: v for k, v in event.items() if k in ("type", "playerIndex", "cardId")}
        self.public_events.append(safe)

    def record_shuffle(self) -> None:
        self.shuffle_invalidations += 1
        self.known_order_valid = False

    def reset_for_new_game(self) -> None:
        self.game_sequence += 1
        self.decision_counter = 0
        self.public_events.clear()
        self.shuffle_invalidations = 0
        self.known_order_valid = False
        self.last_processed_log_count = 0
        self.last_processed_log_fingerprint = ""
        self.last_processed_turn_marker = None

    def next_decision(self) -> int:
        self.decision_counter += 1
        return self.decision_counter

    @staticmethod
    def _log_fingerprint(events: list[dict[str, Any]]) -> str:
        blob = json.dumps(events, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(blob.encode()).hexdigest()

    def ingest_public_events(
        self,
        events: tuple[dict[str, Any], ...],
        *,
        turn: int | None,
    ) -> None:
        """Process only new log delta; resync if fingerprint diverges."""
        fp = self._log_fingerprint(list(events))
        if fp == self.last_processed_log_fingerprint and len(events) == self.last_processed_log_count:
            return
        if (
            self.last_processed_log_fingerprint
            and len(events) < self.last_processed_log_count
            and fp != self.last_processed_log_fingerprint
        ):
            self.public_events.clear()
            self.shuffle_invalidations = 0
            start = 0
        else:
            start = self.last_processed_log_count
        for entry in events[start:]:
            self.record_public_event(entry)
            if str(entry.get("type")) == "0":
                self.record_shuffle()
        self.last_processed_log_count = len(events)
        self.last_processed_log_fingerprint = fp
        if turn is not None:
            self.last_processed_turn_marker = turn
