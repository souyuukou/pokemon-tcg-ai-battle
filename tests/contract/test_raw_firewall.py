"""T-RAW: Raw observation boundary tests."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "ptcg_ai"
RAW_FIELD_PATTERNS = (
    'obs_dict.get("select")',
    'obs_dict.get("remainingOverageTime")',
    'obs_dict.get("current")',
)
FORBIDDEN_PACKAGES = ("runtime", "baseline", "semantic")


def test_runtime_baseline_semantic_do_not_read_raw_select():
    for pkg in FORBIDDEN_PACKAGES:
        base = SRC / pkg
        for py in base.rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            for pat in RAW_FIELD_PATTERNS:
                assert pat not in text, f"{py} contains raw obs access pattern {pat!r}"


def test_only_host_package_imports_raw_observation_module():
    importers: list[str] = []
    for py in SRC.rglob("*.py"):
        if "host" in py.parts:
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and "raw_observation" in node.module:
                importers.append(str(py.relative_to(ROOT)))
    allowed = {
        "src/ptcg_ai/runtime/runtime.py",
    }
    normalized = {str(Path(p)) for p in importers}
    assert normalized <= {str(Path(a)) for a in allowed}, f"unexpected imports: {importers}"
