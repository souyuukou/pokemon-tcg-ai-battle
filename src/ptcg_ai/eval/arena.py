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
ArenaMode = Literal["strict", "discovery"]


@dataclass
class ArenaConfig:
    max_steps: int = 800
    time_bank_mode: TimeBankMode = "authoritative"
    initial_time_seconds: float = 600.0
    desired_seat: int | None = None
    mode: ArenaMode = "strict"


@dataclass(frozen=True)
class UnsupportedSchemaEvent:
    obs: dict[str, Any]
    agent_seat: int | None
    game_index: int
    decision_index: int
    decision_trace_prefix: tuple[tuple[int, ...], ...]
    time_bank_mode: str
    exception_key: str


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


def _minimal_legal_choice(obs: dict[str, Any]) -> list[int]:
    s = obs.get("select") or {}
    lo = int(s.get("minCount", 0))
    opts = s.get("option") or []
    if lo == 0:
        return []
    if not opts:
        return []
    if lo == 1:
        return [0]
    return list(range(min(lo, len(opts))))


def _handle_unsupported_schema(
    exc: Exception,
    *,
    cfg: ArenaConfig,
    card: Scorecard,
    obs: dict[str, Any],
    agent_seat: int | None,
    game_index: int,
    decision_index: int,
    decision_trace: list[list[int]],
    on_unsupported_schema: Callable[[UnsupportedSchemaEvent], Any] | None,
) -> bool:
    from ..semantic.response_ir import UnsupportedSelectionSchema

    if not isinstance(exc, UnsupportedSelectionSchema):
        raise exc
    if cfg.mode == "discovery":
        card.schema_incomplete_games += 1
        card.captured_schema_events += 1
        if on_unsupported_schema is not None:
            on_unsupported_schema(
                UnsupportedSchemaEvent(
                    obs=_prepare_observation(obs, None),
                    agent_seat=agent_seat,
                    game_index=game_index,
                    decision_index=decision_index,
                    decision_trace_prefix=tuple(tuple(step) for step in decision_trace),
                    time_bank_mode=cfg.time_bank_mode,
                    exception_key=str(exc),
                )
            )
        return True
    card.unsupported_schema_count += 1
    return True


def _play_one_game(
    agent_fn: Callable[[dict[str, Any]], list[int]],
    deck: list[int],
    *,
    cfg: ArenaConfig,
    battle_start,
    battle_select,
    battle_finish,
    game_index: int = 0,
    on_unsupported_schema: Callable[[UnsupportedSchemaEvent], Any] | None = None,
) -> Scorecard:
    card = Scorecard(total_games=1)
    tracker: AuthoritativeTimeTracker | None = None
    if cfg.time_bank_mode == "authoritative":
        tracker = AuthoritativeTimeTracker(cfg.initial_time_seconds)

    seat_recorded = False
    decision_trace: list[list[int]] = []
    agent_decision_index = 0
    try:
        obs, _ = battle_start(deck, deck)
        if obs is None:
            card.protocol_error_count += 1
            return card
        steps = 0
        while steps < cfg.max_steps:
            if obs.get("select") is None:
                try:
                    choice = agent_fn(_prepare_observation(obs, tracker))
                except Exception as exc:
                    if _handle_unsupported_schema(
                        exc,
                        cfg=cfg,
                        card=card,
                        obs=obs,
                        agent_seat=None,
                        game_index=game_index,
                        decision_index=agent_decision_index,
                        decision_trace=decision_trace,
                        on_unsupported_schema=on_unsupported_schema,
                    ):
                        return card
                    raise
                obs = battle_select(choice)
                steps += 1
                continue

            seat = _first_seat(obs)
            agent_turn = cfg.desired_seat is None or seat == cfg.desired_seat
            if agent_turn and seat is not None and not seat_recorded:
                card.record_seat(seat)
                seat_recorded = True

            if agent_turn:
                t0 = time.perf_counter()
                if tracker is not None and tracker.remaining <= 0:
                    card.time_bank_exhaustion_count += 1
                    card.protocol_error_count += 1
                    break
                try:
                    choice = agent_fn(_prepare_observation(obs, tracker))
                except Exception as exc:
                    if _handle_unsupported_schema(
                        exc,
                        cfg=cfg,
                        card=card,
                        obs=obs,
                        agent_seat=seat,
                        game_index=game_index,
                        decision_index=agent_decision_index,
                        decision_trace=decision_trace,
                        on_unsupported_schema=on_unsupported_schema,
                    ):
                        return card
                    raise
                elapsed = (time.perf_counter() - t0) * 1000
                if tracker is not None:
                    tracker.record_elapsed(elapsed / 1000.0)
                    if tracker.remaining <= 0:
                        card.time_bank_exhaustion_count += 1
                        card.protocol_error_count += 1
                        break
                card.record_decision_time(elapsed)
                card.record_rss(memory_snapshot().get("rss_bytes"))
                decision_trace.append(list(choice))
                agent_decision_index += 1
            else:
                choice = _minimal_legal_choice(obs)
                decision_trace.append(list(choice))

            lo = int((obs.get("select") or {}).get("minCount", 0))
            hi = int((obs.get("select") or {}).get("maxCount", 0))
            opts = (obs.get("select") or {}).get("option") or []
            if agent_turn:
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
        card.crash_count += 1
        return card
    finally:
        try:
            battle_finish()
        except Exception:
            pass

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
    game_index: int = 0,
    on_unsupported_schema: Callable[[UnsupportedSchemaEvent], Any] | None = None,
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
        game_index=game_index,
        on_unsupported_schema=on_unsupported_schema,
    )


def run_soak_batch(
    agent_fn: Callable[[dict[str, Any]], list[int]],
    deck: list[int],
    *,
    games: int = 50,
    sim_root: Path | None = None,
    config: ArenaConfig | None = None,
    on_unsupported_schema: Callable[[UnsupportedSchemaEvent], Any] | None = None,
) -> Scorecard:
    merged = Scorecard()
    for game_index in range(games):
        base = config or ArenaConfig()
        cfg = replace(base, desired_seat=game_index % 2)
        card = run_self_play(
            agent_fn,
            deck,
            sim_root=sim_root,
            config=cfg,
            game_index=game_index,
            on_unsupported_schema=on_unsupported_schema,
        )
        merged = merge_scorecards(merged, card)
    merged.total_games = games
    return merged
