#!/usr/bin/env python3
"""M0-H Stage H1: harvest unknown schemas from real host self-play."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))


def _git_head() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL)
            .strip()
        )
    except Exception:
        return "unknown"


def _simulator_version(sim_root: Path) -> str:
    game_py = sim_root / "cg" / "game.py"
    if not game_py.is_file():
        return "unknown"
    import hashlib

    return hashlib.sha256(game_py.read_bytes()).hexdigest()[:12]


def run_harvest(*, games: int, modes: tuple[str, ...]) -> dict:
    from ptcg_ai.eval.arena import ArenaConfig, UnsupportedSchemaEvent, run_soak_batch
    from ptcg_ai.eval.runtime_harness import wrap_runtime_act
    from ptcg_ai.eval.schema_capture import SchemaCaptureStore, build_capture_record
    from ptcg_ai.runtime.runtime import CompetitionRuntime

    tested_commit = _git_head()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    store = SchemaCaptureStore(run_id, ROOT)
    sim_root = ROOT / "sample_submission"
    deck_path = ROOT / "submission" / "deck.csv"
    deck = [int(x) for x in deck_path.read_text().split() if x.strip()]
    sim_version = _simulator_version(sim_root)
    capture_paths: list[str] = []

    def make_handler(mode: str):
        def on_unsupported(event: UnsupportedSchemaEvent) -> None:
            record = build_capture_record(
                event.obs,
                tested_commit=tested_commit,
                simulator_version=sim_version,
                deck=deck,
                agent_seat=event.agent_seat,
                game_index=event.game_index,
                decision_index=event.decision_index,
                replay_trace=[list(step) for step in event.replay_trace],
                time_bank_mode=mode,
                desired_seat=event.desired_seat,
            )
            if record is None:
                return
            path = store.save_capture(record)
            capture_paths.append(str(path))

        return on_unsupported

    mode_results: dict[str, dict] = {}
    for mode in modes:
        runtime = CompetitionRuntime(deck)
        telemetry_card = __import__("ptcg_ai.eval.scorecard", fromlist=["Scorecard"]).Scorecard()
        cfg = ArenaConfig(
            max_steps=800,
            time_bank_mode="authoritative" if mode == "authoritative" else "no_authoritative",
            initial_time_seconds=600.0,
            mode="discovery",
        )
        card = run_soak_batch(
            wrap_runtime_act(runtime, telemetry_card),
            deck,
            games=games,
            sim_root=sim_root,
            config=cfg,
            on_unsupported_schema=make_handler(mode),
        )
        merged = card.to_dict()
        tel = telemetry_card.to_dict()
        for key in (
            "in_game_decision_count",
            "conservation_verified_count",
            "conservation_unverified_count",
            "conservation_unavailable_count",
            "conservation_mismatch_count",
            "conservation_telemetry_coverage_ok",
            "fallback_count",
            "emergency_decision_count",
        ):
            merged[key] = tel.get(key, merged.get(key, 0))
        mode_results[mode] = merged

    inventory_path = ROOT / "docs" / "competition_contract" / "captured_schemas_inventory.json"
    store.write_inventory(inventory_path)
    summary_path = store.write_run_summary()

    return {
        "run_id": run_id,
        "tested_commit": tested_commit,
        "games_per_mode": games,
        "modes": list(modes),
        "capture_count": len(capture_paths),
        "unique_schemas": len(store.backlog_rows()),
        "capture_dir": str(store.root),
        "inventory_path": str(inventory_path),
        "summary_path": str(summary_path),
        "mode_results": mode_results,
        "status": "schema_incomplete" if store.backlog_rows() else "completed",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="M0-H schema harvest (discovery mode)")
    parser.add_argument("--games", type=int, default=100)
    parser.add_argument("--modes", nargs="+", default=["authoritative", "no_authoritative"])
    parser.add_argument("--output", type=Path, default=None, help="Write harvest report JSON")
    args = parser.parse_args()

    try:
        result = run_harvest(games=args.games, modes=tuple(args.modes))
    except Exception as exc:
        print(json.dumps({"error": str(exc), "status": "tool_failure"}))
        return 2

    text = json.dumps(result, indent=2, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
