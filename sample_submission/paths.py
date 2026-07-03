"""Resolve submission root on Kaggle (no __file__) and locally."""
from __future__ import annotations

from pathlib import Path


def submission_root() -> Path:
    kaggle = Path("/kaggle_simulations/agent")
    if kaggle.is_dir():
        return kaggle
    file_ref = globals().get("__file__")
    if file_ref:
        return Path(file_ref).resolve().parent
    return Path.cwd()
