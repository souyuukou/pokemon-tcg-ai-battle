#!/usr/bin/env python3
"""Run artifact E2E in an isolated interpreter — no repository imports."""
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
    origins_ok = _verify_under(main_file, artifact) and _verify_under(runtime_file, artifact)
    if not origins_ok:
        _emit(
            {
                "passed": False,
                "error": "import origin outside artifact",
                "main.__file__": main_file,
                "runtime.__file__": runtime_file,
                "sys_path": sys.path,
                "manifest_hash": _manifest_hash(artifact),
                "tested_commit": args.tested_commit,
            }
        )
        return 3

    agent = main_mod.agent
    deck = agent({"select": None, "current": {}, "logs": []})
    if len(deck) != 60:
        _emit({"passed": False, "error": "bad deck length", "length": len(deck)})
        return 1

    obs, _ = battle_start(deck, deck)
    if obs.get("select") is None:
        obs = battle_select(agent({"select": None, "current": {}, "logs": []}))

    made = 0
    illegal = 0
    while made < args.decisions:
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

    _emit(
        {
            "passed": illegal == 0,
            "decisions": made,
            "illegal": illegal,
            "main.__file__": main_file,
            "runtime.__file__": runtime_file,
            "sys_path": sys.path,
            "manifest_hash": _manifest_hash(artifact),
            "tested_commit": args.tested_commit,
        }
    )
    return 0 if illegal == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
