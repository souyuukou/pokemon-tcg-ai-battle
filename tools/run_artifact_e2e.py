#!/usr/bin/env python3
"""Artifact E2E — build in subprocess, run in isolated -I subprocess."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _git_head() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL)
            .strip()
        )
    except Exception:
        return "unknown"


def _build_artifact(output: Path) -> int:
    cmd = [sys.executable, str(ROOT / "tools" / "build_submission.py"), "--output", str(output)]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
    return proc.returncode


def _run_isolated(*, artifact: Path, sim_root: Path, decisions: int, tested_commit: str) -> tuple[int, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = ""
    env["PYTHONNOUSERSITE"] = "1"
    env.pop("PYTHONHOME", None)
    cmd = [
        sys.executable,
        str(ROOT / "tools" / "run_artifact_e2e_isolated.py"),
        "--artifact",
        str(artifact),
        "--sim-root",
        str(sim_root),
        "--decisions",
        str(decisions),
        "--tested-commit",
        tested_commit,
        "--forbid-path",
        str(ROOT),
    ]
    proc = subprocess.run(cmd, cwd=artifact, env=env, capture_output=True, text=True)
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, output


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
        staging = Path(tempfile.mkdtemp(prefix="ptcg_e2e_"))
        artifact = staging / "artifact"
        if _build_artifact(artifact) != 0:
            return 1

    sim_root = (ROOT / "sample_submission").resolve()
    tested_commit = _git_head()
    code, output = _run_isolated(
        artifact=artifact,
        sim_root=sim_root,
        decisions=args.decisions,
        tested_commit=tested_commit,
    )
    print(output)
    if staging is not None and not args.keep:
        shutil.rmtree(staging, ignore_errors=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
