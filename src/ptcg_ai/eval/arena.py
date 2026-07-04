"""Local evaluation arena (optional cabt simulator)."""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Callable

from .scorecard import Scorecard


def run_self_play(
    agent_fn: Callable[[dict[str, Any]], list[int]],
    deck: list[int],
    *,
    max_steps: int = 500,
    sim_root: Path | None = None,
) -> Scorecard:
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

    try:
        obs, start = battle_start(deck, deck)
        if obs is None:
            card.protocol_error_count += 1
            return card
        steps = 0
        while steps < max_steps:
            if obs.get("select") is None:
                choice = agent_fn(obs)
                obs = battle_select(choice)
                steps += 1
                continue
            t0 = time.perf_counter()
            choice = agent_fn({**obs, "remainingOverageTime": 600.0})
            elapsed = (time.perf_counter() - t0) * 1000
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
