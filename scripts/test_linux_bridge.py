"""Smoke-test the native bridge (run under Linux/WSL)."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "sample_submission"
sys.path.insert(0, str(ROOT))

from cg.game import battle_finish, battle_select, battle_start
from main import agent
from pvs_bridge import bridge

deck = [int(x) for x in (ROOT / "deck.csv").read_text().split() if x.strip()]
ok = bridge.initialize(deck)
print("init", ok)
print("error", bridge.error)
print("native", bridge._native_path())
print("lib", bridge.lib)

obs, start = battle_start(deck, deck)
if obs is None:
    raise SystemExit(f"battle_start failed: {start.errorType}")

if obs.get("select") is None:
    obs = battle_select(deck)
    bridge.initialize(deck)

while obs.get("select") is not None and obs.get("select", {}).get("context") != 0:
    obs = battle_select(agent(obs))

begin = time.time()
choice = agent(obs)
elapsed = time.time() - begin
print("choice", choice)
print("elapsed_sec", round(elapsed, 3))
print("diag", bridge.diagnostics())
battle_finish()
