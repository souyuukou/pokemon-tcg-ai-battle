"""Conservation verification quality levels."""
from __future__ import annotations

from enum import Enum


class ConservationQuality(str, Enum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    MISMATCH = "mismatch"
    UNAVAILABLE = "unavailable"


def classify_conservation(*, conservation_verified: bool, mismatch: bool = False) -> ConservationQuality:
    if mismatch:
        return ConservationQuality.MISMATCH
    if conservation_verified:
        return ConservationQuality.VERIFIED
    return ConservationQuality.UNVERIFIED
