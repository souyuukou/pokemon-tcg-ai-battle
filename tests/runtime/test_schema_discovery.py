"""M0-H: Schema discovery mode tests."""
from __future__ import annotations

from pathlib import Path

from ptcg_ai.eval.arena import ArenaConfig, run_soak_batch
from ptcg_ai.eval.runtime_harness import wrap_runtime_act
from ptcg_ai.eval.schema_capture import SchemaCaptureStore, build_capture_record
from ptcg_ai.runtime.runtime import CompetitionRuntime


def _deck() -> list[int]:
    return [int(x) for x in Path("submission/deck.csv").read_text().split() if x.strip()]


def test_discovery_mode_captures_without_crash():
    deck = _deck()
    runtime = CompetitionRuntime(deck)
    card = __import__("ptcg_ai.eval.scorecard", fromlist=["Scorecard"]).Scorecard()
    captures: list[str] = []

    def on_unsupported(event):
        record = build_capture_record(
            event.obs,
            tested_commit="test",
            simulator_version="test",
            deck=deck,
            agent_seat=event.agent_seat,
            game_index=event.game_index,
            decision_index=event.decision_index,
            decision_trace_prefix=[list(s) for s in event.decision_trace_prefix],
            time_bank_mode=event.time_bank_mode,
        )
        if record is not None:
            captures.append(record.semantic_schema_key)

    cfg = ArenaConfig(max_steps=400, mode="discovery", time_bank_mode="no_authoritative")
    result = run_soak_batch(
        wrap_runtime_act(runtime, card),
        deck,
        games=4,
        sim_root=Path("sample_submission"),
        config=cfg,
        on_unsupported_schema=on_unsupported,
    )
    assert result.crash_count == 0
    assert result.total_games == 4
    assert result.schema_incomplete_games >= 0 or result.completed_games >= 0


def test_strict_mode_counts_unsupported_schema():
    deck = _deck()
    runtime = CompetitionRuntime(deck)
    card = __import__("ptcg_ai.eval.scorecard", fromlist=["Scorecard"]).Scorecard()
    cfg = ArenaConfig(max_steps=400, mode="strict", time_bank_mode="no_authoritative")
    result = run_soak_batch(
        wrap_runtime_act(runtime, card),
        deck,
        games=4,
        sim_root=Path("sample_submission"),
        config=cfg,
    )
    assert result.crash_count == 0
    assert result.total_games == 4
    if result.unsupported_schema_count > 0:
        assert result.schema_incomplete_games == 0
