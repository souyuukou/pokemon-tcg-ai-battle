"""M0-5: Artifact E2E smoke with real cabt host battle_select."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_artifact_e2e_host_battle_select():
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "run_artifact_e2e.py"), "--decisions", "25"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "'illegal': 0" in result.stdout or '"illegal": 0' in result.stdout
