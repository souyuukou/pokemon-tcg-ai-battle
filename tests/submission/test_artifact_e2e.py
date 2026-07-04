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
    import json

    text = (result.stdout or "").strip()
    start = text.find("{")
    assert start >= 0, result.stdout
    payload = json.loads(text[start:].splitlines()[0] if "\n" in text[start:] else text[start:])
    assert payload.get("passed") is True
    assert payload.get("illegal") == 0
    main_file = Path(payload["main.__file__"]).resolve()
    assert main_file.name == "main.py"
    assert main_file != (ROOT / "submission" / "main.py").resolve()
    assert payload.get("runtime.__file__")
    assert payload.get("manifest_hash")
    assert payload.get("schema_registry_matrix_path")
