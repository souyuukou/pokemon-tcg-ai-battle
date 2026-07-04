#!/usr/bin/env python3
"""Run artifact E2E in an isolated interpreter — actual host observations only."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def _manifest_hash(artifact: Path) -> str:
    manifest = artifact / "manifest.json"
    if not manifest.is_file():
        return "missing"
    return hashlib.sha256(manifest.read_bytes()).hexdigest()[:16]


def _verify_under(path: str | None, root: Path) -> bool:
    if not path:
        return False
    try:
        return Path(path).resolve().is_relative_to(root.resolve())
    except (ValueError, OSError):
        return str(Path(path).resolve()).startswith(str(root.resolve()))


def _purge_forbidden(forbid: Path) -> None:
    cleaned: list[str] = []
    forbid_resolved = forbid.resolve()
    for entry in sys.path:
        if not entry:
            cleaned.append(entry)
            continue
        try:
            resolved = Path(entry).resolve()
        except OSError:
            cleaned.append(entry)
            continue
        if resolved == forbid_resolved or forbid_resolved in resolved.parents:
            continue
        cleaned.append(entry)
    sys.path = cleaned


def _unsupported_schema_detail(obs: dict, exc: Exception) -> dict:
    s = obs.get("select") or {}
    opts = s.get("option") or []
    return {
        "semantic_schema_key": str(exc).split(": ", 1)[-1],
        "select_type": s.get("type"),
        "context": s.get("context"),
        "min_count": s.get("minCount"),
        "max_count": s.get("maxCount"),
        "option_type_pattern": [o.get("type") if isinstance(o, dict) else None for o in opts],
        "option_count": len(opts),
    }

def _minimal_legal_choice(obs: dict) -> list[int]:
    s = obs.get("select") or {}
    lo = int(s.get("minCount", 0))
    opts = s.get("option") or []
    if lo == 0:
        return []
    if not opts:
        return []
    if lo == 1:
        return [0]
    return list(range(min(lo, len(opts)))


def _emit(result: dict) -> None:
    print(json.dumps(result, separators=(",", ":")))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--sim-root", type=Path, required=True)
    parser.add_argument("--decisions", type=int, default=25)
    parser.add_argument("--tested-commit", default="unknown")
    parser.add_argument("--forbid-path", type=Path, default=None)
    args = parser.parse_args()

    artifact = args.artifact.resolve()
    sim_root = args.sim_root.resolve()
    if not (artifact / "main.py").is_file():
        _emit({"passed": False, "error": "missing main.py", "artifact": str(artifact)})
        return 1

    if args.forbid_path is not None:
        _purge_forbidden(args.forbid_path.resolve())
    for path_entry in (str(sim_root), str(artifact)):
        while path_entry in sys.path:
            sys.path.remove(path_entry)
    sys.path.insert(0, str(sim_root))
    sys.path.insert(0, str(artifact))

    import main as main_mod
    import ptcg_runtime.runtime as runtime_mod
    from cg.game import battle_finish, battle_select, battle_start

    main_file = getattr(main_mod, "__file__", None)
    runtime_file = getattr(runtime_mod, "__file__", None)
    matrix_path = artifact / "docs" / "competition_contract" / "response_schema_matrix.json"
    origins_ok = (
        _verify_under(main_file, artifact)
        and _verify_under(runtime_file, artifact)
        and matrix_path.is_file()
    )
    if not origins_ok:
        _emit(
            {
                "passed": False,
                "error": "import origin outside artifact",
                "main.__file__": main_file,
                "runtime.__file__": runtime_file,
                "schema_registry_matrix_path": str(matrix_path),
                "manifest_hash": _manifest_hash(artifact),
                "tested_commit": args.tested_commit,
            }
        )
        return 3

    agent = main_mod.agent
    deck_csv = artifact / "deck.csv"
    deck = [int(x) for x in deck_csv.read_text().split() if x.strip()]
    if len(deck) != 60:
        _emit({"passed": False, "error": "bad deck.csv length", "length": len(deck)})
        return 1

    made = 0
    illegal = 0
    protocol_errors = 0
    completed_game = False
    last_error: str | None = None
    schema_failure: dict | None = None
    games_played = 0
    max_games = 10

    while made < args.decisions and games_played < max_games:
        obs, _ = battle_start(deck, deck)
        if obs is None:
            protocol_errors += 1
            last_error = "battle_start failed"
            break
        games_played += 1

        while made < args.decisions:
            if int((obs.get("current") or {}).get("result", -1)) >= 0:
                completed_game = True
                break
            try:
                if obs.get("select") is None:
                    choice = agent(obs)
                else:
                    seat = int((obs.get("current") or {}).get("yourIndex", 0))
                    if seat == 0:
                        choice = agent(obs)
                    else:
                        choice = _minimal_legal_choice(obs)
            except Exception as exc:
                protocol_errors += 1
                last_error = f"{type(exc).__name__}: {exc}"
                if type(exc).__name__ == "UnsupportedSelectionSchema":
                    schema_failure = _unsupported_schema_detail(obs, exc)
                break

            if obs.get("select") is not None:
                s = obs.get("select") or {}
                lo, hi = int(s.get("minCount", 0)), int(s.get("maxCount", 0))
                opts = s.get("option") or []
                if not (lo <= len(choice) <= hi):
                    illegal += 1
                for idx in choice:
                    if idx < 0 or idx >= len(opts):
                        illegal += 1
                made += 1

            obs = battle_select(choice)
            if obs is None:
                protocol_errors += 1
                last_error = last_error or f"battle_select_none choice={choice!r} made={made}"
                break

        battle_finish()
        if protocol_errors:
            break

    passed = illegal == 0 and protocol_errors == 0 and made >= args.decisions
    _emit(
        {
            "passed": passed,
            "decisions": made,
            "completed_game": completed_game,
            "illegal": illegal,
            "protocol_errors": protocol_errors,
            "main.__file__": main_file,
            "runtime.__file__": runtime_file,
            "schema_registry_matrix_path": str(matrix_path),
            "manifest_hash": _manifest_hash(artifact),
            "tested_commit": args.tested_commit,
            "last_error": last_error,
            "schema_failure": schema_failure,
        }
    )
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
