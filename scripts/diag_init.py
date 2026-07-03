"""Diagnose pvs_init / AllCard behavior."""
from __future__ import annotations

import ctypes
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "sample_submission"
sys.path.insert(0, str(ROOT))

import os

os.chdir(ROOT)

cg = ROOT / "cg" / ("cg.dll" if os.name == "nt" else "libcg.so")
lib = ctypes.CDLL(str(cg))
lib.AllCard.restype = ctypes.c_char_p
raw = lib.AllCard()
cards = json.loads(raw.decode() if raw else "[]")
print("AllCard count", len(cards))
if cards[:1]:
    print("sample keys", list(cards[0].keys())[:8])

from pvs_bridge import bridge

deck = [int(x) for x in (ROOT / "deck.csv").read_text().split() if x.strip()]
ok = bridge.initialize(deck)
print("initialize", ok, "error", bridge.error)
