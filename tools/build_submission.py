#!/usr/bin/env python3
"""Build submission artifact into dist/submission without modifying source tree."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_PKG = ROOT / "src" / "ptcg_ai"
SUB_TEMPLATE = ROOT / "submission"
DIST = ROOT / "dist" / "submission"

EXCLUDE_DIRS = {
    "__pycache__",
    ".pytest_cache",
    "research",
    ".git",
}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}


def _should_include(path: Path, artifact_root: Path) -> bool:
    rel = path.relative_to(artifact_root)
    parts = rel.parts
    if any(p in EXCLUDE_DIRS for p in parts):
        return False
    if path.suffix in EXCLUDE_SUFFIXES:
        return False
    return True


def build_submission(*, output: Path = DIST, repo_root: Path = ROOT) -> Path:
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    runtime_dest = output / "ptcg_runtime"
    shutil.copytree(
        SRC_PKG,
        runtime_dest,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "research"),
    )
    # Remove research if copied
    research = runtime_dest / "research"
    if research.exists():
        shutil.rmtree(research)

    main_src = SUB_TEMPLATE / "main.py"
    if main_src.is_file():
        shutil.copy2(main_src, output / "main.py")
    else:
        (output / "main.py").write_text(
            'from ptcg_runtime.runtime import get_runtime\n\n'
            "RUNTIME = get_runtime()\n\n"
            "def agent(obs_dict: dict) -> list[int]:\n"
            "    return RUNTIME.act(obs_dict)\n",
            encoding="utf-8",
        )

    deck_src = SUB_TEMPLATE / "deck.csv"
    if not deck_src.is_file():
        deck_src = ROOT / "sample_submission" / "deck.csv"
    shutil.copy2(deck_src, output / "deck.csv")

    contract_src = repo_root / "docs" / "competition_contract"
    if contract_src.is_dir():
        contract_dest = output / "docs" / "competition_contract"
        shutil.copytree(contract_src, contract_dest)

    deck = [int(x) for x in (output / "deck.csv").read_text().split() if x.strip()]

    sys.path.insert(0, str(ROOT / "src"))
    from ptcg_ai.contract.manifest import build_manifest, manifest_to_dict

    manifest = build_manifest(output, repo_root=repo_root, deck=deck)
    (output / "manifest.json").write_text(
        json.dumps(manifest_to_dict(manifest), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DIST)
    args = parser.parse_args()
    out = build_submission(output=args.output)
    print(f"built artifact at {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
