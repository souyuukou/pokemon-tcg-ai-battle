"""Local evaluation arena (optional cabt simulator)."""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Literal

from ..runtime.memory_guard import memory_snapshot
from .scorecard import Scorecard, merge_scorecards

TimeBankMode = Literal["authoritative", "no_authoritative"]


@dataclass
class ArenaConfig:
    max_steps: int = 800
    time_bank_mode: TimeBankMode = "authoritative"
    initial_time_seconds: float = 600.0
    desired_seat: int | None = None


class AuthoritativeTimeTracker:
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


def _first_seat(obs: dict[str, Any]) -> int | None:
    if obs.get("select") is None:
        return None
    current = obs.get("current")
    if not isinstance(current, dict):
        return None
    try:
        return int(current.get("yourIndex", 0))
    except (TypeError, ValueError):
        return None


def _play_one_game(
    agent_fn: Callable[[dict[str, Any]], list[int]],
    deck: list[int],
    *,
    cfg: ArenaConfig,
    battle_start,
    battle_select,
    battle_finish,
) -> Scorecard:
    card = Scorecard(total_games=1)
    tracker: AuthoritativeTimeTracker | None = None
    if cfg.time_bank_mode == "authoritative":
        tracker = AuthoritativeTimeTracker(cfg.initial_time_seconds)

    for _attempt in range(8):
        finished = False
        try:
            obs, _ = battle_start(deck, deck)
            if obs is None:
                card.protocol_error_count += 1
                return card
            seat_recorded = False
            steps = 0
            while steps < cfg.max_steps:
                if obs.get("select") is None:
                    choice = agent_fn(_prepare_observation(obs, tracker))
                    obs = battle_select(choice)
                    steps += 1
                    continue
                seat = _first_seat(obs)
                if seat is not None and not seat_recorded:
                    if cfg.desired_seat is not None and seat != cfg.desired_seat:
                        finished = True
                        break
                    card.record_seat(seat)
                    seat_recorded = True
                t0 = time.perf_counter()
                choice = agent_fn(_prepare_observation(obs, tracker))
                elapsed = (time.perf_counter() - t0) * 1000
                if tracker is not None:
                    tracker.record_elapsed(elapsed / 1000.0)
                card.record_decision_time(elapsed)
                card.record_rss(memory_snapshot().get("rss_bytes"))
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
                    finished = True
                    break
            if finished and (seat_recorded or cfg.desired_seat is None):
                return card
        except Exception as exc:
            from ..semantic.response_ir import UnsupportedSelectionSchema

            if isinstance(exc, UnsupportedSelectionSchema):
                card.unsupported_schema_count += 1
            else:
                card.crash_count += 1
            return card
        finally:
            try:
                battle_finish()
            except Exception:
                pass
        if seat_recorded:
            return card
    if cfg.desired_seat is not None and not seat_recorded:
        card.protocol_error_count += 1
    return card


def run_self_play(
    agent_fn: Callable[[dict[str, Any]], list[int]],
    deck: list[int],
    *,
    max_steps: int = 500,
    sim_root: Path | None = None,
    config: ArenaConfig | None = None,
) -> Scorecard:
    cfg = config or ArenaConfig(max_steps=max_steps)
    root = sim_root or Path(__file__).resolve().parents[3] / "sample_submission"
    if not (root / "cg").is_dir():
        card = Scorecard(total_games=1)
        card.protocol_error_count += 1
        return card
    sys.path.insert(0, str(root))
    try:
        from cg.game import battle_finish, battle_select, battle_start
    except ImportError:
        card = Scorecard(total_games=1)
        card.protocol_error_count += 1
        return card
    return _play_one_game(
        agent_fn,
        deck,
        cfg=replace(cfg, max_steps=max_steps),
        battle_start=battle_start,
        battle_select=battle_select,
        battle_finish=battle_finish,
    )


def run_soak_batch(
    agent_fn: Callable[[dict[str, Any]], list[int]],
    deck: list[int],
    *,
    games: int = 50,
    sim_root: Path | None = None,
    config: ArenaConfig | None = None,
) -> Scorecard:
    merged = Scorecard()
    for _i in range(games):
        base = config or ArenaConfig()
        cfg = replace(base, desired_seat=None)
        card = run_self_play(agent_fn, deck, sim_root=sim_root, config=cfg)
        merged = merge_scorecards(merged, card)
    merged.total_games = games
    return merged
