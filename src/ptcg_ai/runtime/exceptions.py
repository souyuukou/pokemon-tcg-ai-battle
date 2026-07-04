"""Runtime exception taxonomy — contract vs operational failures."""
from __future__ import annotations


class ContractMismatch(Exception):
    """Artifact / catalog / semantic spec mismatch — fallback forbidden."""


class OperationalFailure(Exception):
    """Transient ranker / backend failure — validated fallback allowed."""


class CardConservationMismatch(Exception):
    """Deck multiset accounting failed — incident + no silent continuation."""
