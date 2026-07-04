"""Actor observation history ledger."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ObservationLedger:
    game_sequence: int = 0
    decision_counter: int = 0
    public_events: list[dict[str, Any]] = field(default_factory=list)
    own_hand_snapshots: list[dict[int, int]] = field(default_factory=list)
    shuffle_invalidations: int = 0
    known_order_valid: bool = False

    def record_public_event(self, event: dict[str, Any]) -> None:
        safe = {
            "type": event.get("type"),
            "playerIndex": event.get("playerIndex"),
        }
        self.public_events.append(safe)

    def record_shuffle(self) -> None:
        self.shuffle_invalidations += 1
        self.known_order_valid = False

    def reset_for_new_game(self) -> None:
        self.game_sequence += 1
        self.decision_counter = 0
        self.public_events.clear()
        self.own_hand_snapshots.clear()
        self.shuffle_invalidations = 0
        self.known_order_valid = False

    def next_decision(self) -> int:
        self.decision_counter += 1
        return self.decision_counter
