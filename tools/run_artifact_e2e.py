#!/usr/bin/env python3
"""Artifact E2E — isolated build + real cabt battle_select loop."""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run_loop(artifact: Path, sim_root: Path, decisions: int) -> int:
    prev_cwd = Path.cwd()
    prev_path = list(sys.path)
    try:
        os.chdir(artifact)
        sys.path[:0] = [str(artifact), str(sim_root)]
        from cg.game import battle_finish, battle_select, battle_start
        from main import agent

        deck = agent({"select": None, "current": {}, "logs": []})
        if len(deck) != 60:
            print("bad deck length", len(deck))
            return 1
        obs, _ = battle_start(deck, deck)
        if obs.get("select") is None:
            obs = battle_select(agent({"select": None, "current": {}, "logs": []}))
        made = 0
        illegal = 0
        while made < decisions:
            if obs.get("select") is None:
                obs = battle_select(agent({"select": None, "current": {}, "logs": []}))
                continue
            choice = agent(obs)
            s = obs.get("select") or {}
            lo, hi = int(s.get("minCount", 0)), int(s.get("maxCount", 0))
            opts = s.get("option") or []
            if not (lo <= len(choice) <= hi):
                illegal += 1
            for idx in choice:
                if idx < 0 or idx >= len(opts):
                    illegal += 1
            obs = battle_select(choice)
            made += 1
            if int((obs.get("current") or {}).get("result", -1)) >= 0:
                break
        battle_finish()
        print({"decisions": made, "illegal": illegal})
        return 0 if illegal == 0 else 2
    finally:
        os.chdir(prev_cwd)
        sys.path[:] = prev_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--decisions", type=int, default=25)
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--artifact", type=Path, default=None)
    args = parser.parse_args()

    staging: Path | None = None
    if args.artifact is not None:
        artifact = args.artifact.resolve()
    else:
        sys.path.insert(0, str(ROOT))
        from tools.build_submission import build_submission

        staging = Path(tempfile.mkdtemp(prefix="ptcg_e2e_"))
        artifact = build_submission(output=staging / "artifact")

    sim_root = (ROOT / "sample_submission").resolve()
    try:
        return _run_loop(artifact, sim_root, args.decisions)
    finally:
        if staging is not None and not args.keep:
            shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
