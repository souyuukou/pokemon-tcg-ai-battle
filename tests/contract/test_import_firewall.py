"""T0: Import firewall — submission/runtime must not import research or torch."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "ptcg_ai"
FORBIDDEN_PREFIXES = (
    "ptcg_ai.research",
    "torch",
    "search_begin_input",
)
PACKAGES = ("runtime", "baseline", "host", "submission")


def _collect_imports(py_file: Path) -> list[str]:
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def test_runtime_packages_do_not_import_research():
    for pkg in ("runtime", "baseline", "host"):
        base = SRC / pkg
        for py in base.rglob("*.py"):
            for imp in _collect_imports(py):
                for forbidden in FORBIDDEN_PREFIXES:
                    assert forbidden not in imp, f"{py}: imports {imp}"


def test_baseline_does_not_import_raw_observation():
    baseline = SRC / "baseline"
    for py in baseline.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        assert "raw_observation" not in text
        assert "RawObservation" not in text
