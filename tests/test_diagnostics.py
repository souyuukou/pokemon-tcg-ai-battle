"""Diagnostics counter tests."""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "sample_submission"))

from diagnostics import SessionDiagnostics


def test_fallback_increments_both_fallback_and_native_failure():
    diag = SessionDiagnostics()
    diag.record_choose(ok=False, elapsed_ms=1.0, diag={}, error="forced", used_fallback=True)
    assert diag.fallback_count == 1
    assert diag.native_failure_count == 1
    assert diag.last_native_error == "forced"


def test_native_success_does_not_increment_failure():
    diag = SessionDiagnostics()
    diag.record_choose(ok=True, elapsed_ms=5.0, diag={"depth": 2, "nodes": 10, "worlds": 4})
    assert diag.native_choose_count == 1
    assert diag.native_failure_count == 0
    assert diag.fallback_count == 0


def test_worker_stderr_tail_recorded():
    diag = SessionDiagnostics()
    diag.record_choose(
        ok=False,
        elapsed_ms=1.0,
        diag={},
        error="worker died",
        used_fallback=True,
        worker_stderr="traceback: native load failed",
    )
    assert "native load failed" in diag.last_worker_stderr
