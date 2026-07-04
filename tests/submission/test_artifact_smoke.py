"""T7: Artifact smoke (invokes tools/run_smoke)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_artifact_smoke():
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "run_smoke.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
