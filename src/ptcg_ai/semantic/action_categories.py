"""Option type → semantic category mapping."""
from __future__ import annotations

from enum import Enum


class OptionCategory(str, Enum):
    ATTACK = "ATTACK"
    ATTACH = "ATTACH"
    EVOLVE = "EVOLVE"
    PLAY_TRAINER = "PLAY_TRAINER"
    PLAY_SUPPORTER = "PLAY_SUPPORTER"
    PLAY = "PLAY"
    RETREAT = "RETREAT"
    SWITCH = "SWITCH"
    BENCH = "BENCH"
    TARGET_SELECT = "TARGET_SELECT"
    PRIZE_SELECT = "PRIZE_SELECT"
    CONFIRM = "CONFIRM"
    END = "END"
    OPAQUE = "OPAQUE"


_TYPE_MAP: dict[int, OptionCategory] = {
    7: OptionCategory.PLAY,
    8: OptionCategory.ATTACH,
    9: OptionCategory.EVOLVE,
    10: OptionCategory.TARGET_SELECT,
    12: OptionCategory.RETREAT,
    13: OptionCategory.ATTACK,
    14: OptionCategory.END,
    1: OptionCategory.CONFIRM,
    2: OptionCategory.CONFIRM,
    3: OptionCategory.TARGET_SELECT,
    4: OptionCategory.TARGET_SELECT,
    5: OptionCategory.TARGET_SELECT,
    6: OptionCategory.TARGET_SELECT,
    11: OptionCategory.TARGET_SELECT,
    15: OptionCategory.TARGET_SELECT,
    16: OptionCategory.TARGET_SELECT,
}


def categorize_option_type(raw_type: int | str | None, context: int | str | None = None) -> OptionCategory:
    if raw_type is None:
        return OptionCategory.OPAQUE
    try:
        t = int(raw_type)
    except (TypeError, ValueError):
        return OptionCategory.OPAQUE
    cat = _TYPE_MAP.get(t)
    if cat is not None:
        if t == 7 and context in (41, 42):
            return OptionCategory.CONFIRM
        return cat
    return OptionCategory.OPAQUE
