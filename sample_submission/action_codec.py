"""Encode and decode multi-select actions for training and validation."""
from __future__ import annotations

from typing import Any


def validate_action(action: list[int], select: dict[str, Any]) -> bool:
    lo = int(select.get("minCount", 0))
    hi = int(select.get("maxCount", 0))
    options = select.get("option") or []
    if not options:
        return lo == hi == 0 and not action
    n = len(options)
    if not (lo <= len(action) <= hi):
        return False
    if len(action) != len(set(action)):
        return False
    return all(0 <= index < n for index in action)


def encode_action(obs: dict[str, Any], indices: list[int]) -> list[int]:
    select = obs.get("select") or {}
    action = [int(index) for index in indices]
    if not validate_action(action, select):
        raise ValueError(f"illegal action {action} for select {select}")
    return action


def decode_action(obs: dict[str, Any], encoded: list[int]) -> list[int]:
    select = obs.get("select") or {}
    action = [int(index) for index in encoded]
    if not validate_action(action, select):
        raise ValueError(f"illegal encoded action {action}")
    return list(action)


def expand_multiselect_teacher(
    obs: dict[str, Any],
    action: list[int],
    reward: float,
) -> list[tuple[list[int], list[int], float, int]]:
    """Expand a multi-select action into per-pick training rows.

    Each selected option becomes its own supervised example on the same
    observation, so [4, 11] and [4] produce different teachers.
    """
    select = obs.get("select") or {}
    options = select.get("option") or []
    if not options:
        return []
    picks = [int(index) for index in (action or [])]
    if not validate_action(picks, select):
        return []
    return [
        (picks[:step + 1], list(range(len(options))), reward, picks[step])
        for step in range(len(picks))
    ]
