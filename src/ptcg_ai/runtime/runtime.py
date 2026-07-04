"""Main competition runtime entry."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ..baseline.policy_b0 import PolicyB0
from ..contract.runtime_profile import RuntimeProfile, load_runtime_profile
from ..host.host_adapter import HostAdapter
from ..host.host_response import to_host_response
from ..host.raw_observation import RawObservation
from ..semantic.response_ir import UnsupportedSelectionSchema
from .agent_session import AgentSession, DeckSelectionRequest, FixedDeckProvider
from .deadline import Deadline
from .diagnostics import DiagnosticsBuffer
from .fallback import FallbackSelector
from .memory_guard import memory_snapshot
from .time_bank import budget_for_decision, update_time_bank

POLICY_VERSION = "b0_v1.11.2"
_RUNTIME: CompetitionRuntime | None = None


class CompetitionRuntime:
    def __init__(
        self,
        deck: list[int],
        profile: RuntimeProfile | None = None,
    ) -> None:
        self._profile = profile or load_runtime_profile()
        self._deck_provider = FixedDeckProvider(deck)
        self._session: AgentSession | None = None
        self._host = HostAdapter()
        self._policy = PolicyB0(self._profile)
        self._fallback = FallbackSelector()

    def _ensure_session(self) -> AgentSession:
        if self._session is None:
            deck = self._deck_provider.select_deck(DeckSelectionRequest())
            self._session = AgentSession.start_new(deck, profile_cache_max=self._profile.soft_cache_max_entries)
        return self._session

    def act(self, obs_dict: dict[str, Any]) -> list[int]:
        session = self._ensure_session()
        if obs_dict.get("select") is None:
            if self._session is not None:
                self._session.close()
            deck = self._deck_provider.select_deck(DeckSelectionRequest())
            self._session = AgentSession.start_new(deck, profile_cache_max=self._profile.soft_cache_max_entries)
            session = self._session
            session.diagnostics.record({"event": "deck_selection", "deck_hash": session.deck_hash})
            return list(deck)

        t0 = time.perf_counter()
        host_remaining = obs_dict.get("remainingOverageTime")
        if host_remaining is not None:
            try:
                host_remaining = float(host_remaining)
            except (TypeError, ValueError):
                host_remaining = None
        update_time_bank(
            session.time_bank_state,
            host_remaining=host_remaining,
            safety_margin=self._profile.safety_margin_seconds,
        )
        eff = session.time_bank_state.effective()
        if eff <= self._profile.emergency_threshold_seconds:
            session.emergency_mode = True

        raw = RawObservation.from_dict(obs_dict)
        try:
            decision = self._host.sanitize_decision(raw, session)
        except Exception as exc:
            session.diagnostics.incident_count += 1
            raise

        budget = budget_for_decision(
            session.time_bank_state,
            option_count=decision.contract.option_count,
            emergency_threshold=self._profile.emergency_threshold_seconds,
            emergency=session.emergency_mode,
        )
        deadline = Deadline.from_budget(
            soft_seconds=max(0.1, budget - self._profile.hard_reserve_seconds),
            hard_seconds=max(0.05, budget),
        )

        used_fallback = False
        try:
            response, used_fallback = self._policy.decide(
                decision,
                deadline=deadline,
                decision_counter=session.observation_ledger.decision_counter,
                emergency=session.emergency_mode,
            )
        except UnsupportedSelectionSchema as exc:
            session.diagnostics.incident_count += 1
            session.diagnostics.record(
                {
                    "event": "contract_violation",
                    "schema": decision.contract.response_schema_key,
                    "reason": str(exc),
                }
            )
            response = self._fallback.choose(decision, reason="unsupported_schema")
            used_fallback = True

        if used_fallback:
            session.diagnostics.record_fallback(response.category)

        host_response = to_host_response(decision.contract, response)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        session.diagnostics.record(
            {
                "event": "decision",
                "policy_version": POLICY_VERSION,
                "decision_counter": session.observation_ledger.decision_counter,
                "category": response.category,
                "schema_key": decision.contract.response_schema_key,
                "candidate_count": decision.contract.option_count,
                "elapsed_ms": round(elapsed_ms, 2),
                "fallback": used_fallback,
                **memory_snapshot(),
            }
        )
        current = obs_dict.get("current") or {}
        if int(current.get("result", -1)) >= 0:
            session.close()
        return host_response


def _load_deck_from_csv(path: Path) -> list[int]:
    text = path.read_text(encoding="utf-8")
    return [int(x) for x in text.split() if x.strip()]


def get_runtime(deck_path: Path | None = None) -> CompetitionRuntime:
    global _RUNTIME
    if _RUNTIME is None:
        if deck_path is None:
            artifact_root = Path(__file__).resolve().parents[2]
            candidates = [
                artifact_root / "deck.csv",
                Path("deck.csv"),
                Path(__file__).resolve().parents[2] / "submission" / "deck.csv",
            ]
            for c in candidates:
                if c.is_file():
                    deck_path = c
                    break
            if deck_path is None:
                raise FileNotFoundError("deck.csv not found")
        deck = _load_deck_from_csv(deck_path)
        profile_candidates = [
            Path(__file__).resolve().parents[2] / "docs" / "runtime_profiles" / "runtime_profile_local.json",
            Path("runtime_profile_local.json"),
        ]
        profile = load_runtime_profile(None)
        for pc in profile_candidates:
            if pc.is_file():
                profile = load_runtime_profile(pc)
                break
        _RUNTIME = CompetitionRuntime(deck, profile)
    return _RUNTIME
