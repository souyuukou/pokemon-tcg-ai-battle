from .agent_session import AgentSession, ActorViewCache, DeckProvider, FixedDeckProvider
from .deadline import Deadline
from .diagnostics import DiagnosticsBuffer
from .exceptions import CardConservationMismatch, ContractMismatch, OperationalFailure
from .fallback import FallbackSelector
from .time_bank import TimeBankState, update_time_bank


def __getattr__(name: str):
    if name == "CompetitionRuntime":
        from .runtime import CompetitionRuntime

        return CompetitionRuntime
    if name == "get_runtime":
        from .runtime import get_runtime

        return get_runtime
    raise AttributeError(name)


__all__ = [
    "AgentSession",
    "ActorViewCache",
    "CompetitionRuntime",
    "Deadline",
    "CardConservationMismatch",
    "ContractMismatch",
    "DeckProvider",
    "DiagnosticsBuffer",
    "FallbackSelector",
    "FixedDeckProvider",
    "get_runtime",
    "OperationalFailure",
    "TimeBankState",
    "update_time_bank",
]
