"""Competition contract gate — confirmed vs unconfirmed items."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompetitionContract:
    host_name: str
    host_api_version: str | None
    legal_action_authority: str
    agent_entrypoint: str
    deck_size: int | None
    time_bank_seconds: float | None
    submission_format: str | None
    search_api_allowed_in_production: bool | None
    native_extension_allowed: bool | None
    external_data_allowed: bool | None
    network_allowed: bool | None
    notes: tuple[str, ...]


def is_explicitly_allowed(value: bool | None) -> bool:
    return value is True


PTCGABC_CONTRACT = CompetitionContract(
    host_name="cabt",
    host_api_version=None,
    legal_action_authority="host_select_option",
    agent_entrypoint="agent(obs_dict: dict) -> list[int]",
    deck_size=60,
    time_bank_seconds=600.0,
    submission_format="submission.tar.gz",
    search_api_allowed_in_production=False,
    native_extension_allowed=None,
    external_data_allowed=None,
    network_allowed=None,
    notes=(
        "search API quarantined from production runtime",
        "time bank per match 10 minutes per player",
        "deck selection via deck.csv",
    ),
)
