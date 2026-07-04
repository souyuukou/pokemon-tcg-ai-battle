"""Local evaluation arena (optional cabt simulator)."""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

from .scorecard import Scorecard, merge_scorecards


TimeBankMode = Literal["authoritative", "no_authoritative"]


@dataclass
class ArenaConfig:
    max_steps: int = 800
    time_bank_mode: TimeBankMode = "authoritative"
    initial_time_seconds: float = 600.0
    seat: int = 0


class AuthoritativeTimeTracker:
    """Decrement host-visible remaining time by measured agent elapsed."""

    def __init__(self, initial: float) -> None:
        self.remaining = initial

    def wrap_observation(self, obs: dict[str, Any]) -> dict[str, Any]:
        out = dict(obs)
        out["remainingOverageTime"] = self.remaining
        return out

    def record_elapsed(self, elapsed_seconds: float) -> None:
        self.remaining = max(0.0, self.remaining - elapsed_seconds)


def _prepare_observation(obs: dict[str, Any], tracker: AuthoritativeTimeTracker | None) -> dict[str, Any]:
    if tracker is None:
        out = dict(obs)
        out.pop("remainingOverageTime", None)
        return out
    return tracker.wrap_observation(obs)


def run_self_play(
    agent_fn: Callable[[dict[str, Any]], list[int]],
    deck: list[int],
    *,
    max_steps: int = 500,
    sim_root: Path | None = None,
    config: ArenaConfig | None = None,
) -> Scorecard:
    cfg = config or ArenaConfig(max_steps=max_steps)
    card = Scorecard(total_games=1)
    root = sim_root or Path(__file__).resolve().parents[3] / "sample_submission"
    if not (root / "cg").is_dir():
        card.protocol_error_count += 1
        return card
    sys.path.insert(0, str(root))
    try:
        from cg.game import battle_finish, battle_select, battle_start
    except ImportError:
        card.protocol_error_count += 1
        return card

    tracker: AuthoritativeTimeTracker | None = None
    if cfg.time_bank_mode == "authoritative":
        tracker = AuthoritativeTimeTracker(cfg.initial_time_seconds)

    try:
        obs, start = battle_start(deck, deck)
        if obs is None:
            card.protocol_error_count += 1
            return card
        steps = 0
        while steps < cfg.max_steps:
            if obs.get("select") is None:
                choice = agent_fn(_prepare_observation(obs, tracker))
                obs = battle_select(choice)
                steps += 1
                continue
            t0 = time.perf_counter()
            choice = agent_fn(_prepare_observation(obs, tracker))
            elapsed = (time.perf_counter() - t0) * 1000
            if tracker is not None:
                tracker.record_elapsed(elapsed / 1000.0)
            card.record_decision_time(elapsed)
            lo = int((obs.get("select") or {}).get("minCount", 0))
            hi = int((obs.get("select") or {}).get("maxCount", 0))
            opts = (obs.get("select") or {}).get("option") or []
            if not (lo <= len(choice) <= hi):
                card.illegal_action_count += 1
            if len(choice) != len(set(choice)):
                card.illegal_action_count += 1
            for i in choice:
                if i < 0 or i >= len(opts):
                    card.illegal_action_count += 1
            obs = battle_select(choice)
            steps += 1
            if int((obs.get("current") or {}).get("result", -1)) >= 0:
                card.completed_games = 1
                break
    except Exception as exc:
        from ..semantic.response_ir import UnsupportedSelectionSchema

        if isinstance(exc, UnsupportedSelectionSchema):
            card.unsupported_schema_count += 1
        else:
            card.crash_count += 1
    finally:
        try:
            battle_finish()
        except Exception:
            pass
    return card


def run_soak_batch(
    agent_fn: Callable[[dict[str, Any]], list[int]],
    deck: list[int],
    *,
    games: int = 50,
    sim_root: Path | None = None,
    config: ArenaConfig | None = None,
) -> Scorecard:
    merged = Scorecard()
    first_seat = games // 2
    for i in range(games):
        cfg = config or ArenaConfig()
        cfg.seat = 0 if i < first_seat else 1
        card = run_self_play(agent_fn, deck, sim_root=sim_root, config=cfg)
        merged = merge_scorecards(merged, card)
    merged.total_games = games
    return merged
