#!/usr/bin/env python3
"""Artifact smoke test in clean staging directory."""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()
    from tools.build_submission import build_submission

    staging = Path(tempfile.mkdtemp(prefix="ptcg_smoke_"))
    try:
        artifact = build_submission(output=staging / "artifact")
        import os

        os.chdir(artifact)
        sys.path.insert(0, str(artifact))
        from main import agent

        deck = agent({"select": None, "current": {}, "logs": []})
        assert len(deck) == 60, f"expected 60 cards, got {len(deck)}"

        obs = {
            "select": {
                "type": 0,
                "context": 0,
                "minCount": 1,
                "maxCount": 1,
                "option": [{"type": 14}, {"type": 13}, {"type": 7}],
            },
            "current": {
                "yourIndex": 0,
                "turn": 5,
                "firstPlayer": 0,
                "result": -1,
                "players": [
                    {
                        "hand": [{"id": 10}],
                        "handCount": 1,
                        "prize": [None] * 6,
                        "deckCount": 45,
                        "active": [],
                        "bench": [],
                        "discard": [],
                    },
                    {
                        "hand": [],
                        "handCount": 3,
                        "prize": [None] * 6,
                        "deckCount": 45,
                        "active": [],
                        "bench": [],
                        "discard": [],
                    },
                ],
            },
            "logs": [],
            "remainingOverageTime": 600.0,
        }
        choice = agent(obs)
        assert len(choice) == 1
        assert 0 <= choice[0] < 3
        print("smoke OK", {"deck_len": len(deck), "choice": choice})
        return 0
    finally:
        if not args.keep:
            shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
