"""Deterministic legal fallback used when the native engine is unavailable."""
from __future__ import annotations
def choose(obs: dict) -> list[int]:
    select = obs.get("select") or {}
    options = select.get("option") or []
    lo, hi = int(select.get("minCount", 0)), int(select.get("maxCount", 0))
    if not options:
        return []
    # Main action ordering: attack, ability, evolution, attach, play, retreat, end.
    weights = {13: 80, 10: 60, 9: 50, 8: 40, 7: 30, 12: 5, 14: 0,
               1: 10, 2: 5, 3: 10, 15: 10}
    ranked = sorted(range(len(options)), key=lambda i: (weights.get(options[i].get("type"), 20), -i), reverse=True)
    count = max(lo, min(hi, 1 if hi else 0))
    return sorted(ranked[:count])
