import json
import os
import platform
import sys
import time
from pathlib import Path

from debug_log import debug_log
from fallback import choose as fallback_choose
from paths import submission_root
from pvs_bridge import bridge
from native_worker_client import NativeWorkerClient

_deck = None
_init_failed = False
_isolate_native = os.environ.get(
    "POKEMON_PVS_ISOLATE_NATIVE", "1" if platform.system() == "Linux" else "0"
) == "1"
_worker = NativeWorkerClient() if _isolate_native else None


def _effective_config() -> str:
    hard_limit = float(os.environ.get("POKEMON_PVS_HARD_TIMEOUT", "6.0"))
    hard_ms = max(50, int(hard_limit * 1000) - 900)
    raw = os.environ.get("POKEMON_PVS_CONFIG", "{}")
    try:
        cfg = json.loads(raw)
    except json.JSONDecodeError:
        cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}
    cfg.setdefault("hypotheses", 6)
    cfg.setdefault("threads", 0)
    cfg.setdefault("max_depth", 20)
    cfg.setdefault("safety_seconds", 5.0)
    cfg.setdefault("risk", 0.12)
    cfg["hard_ms"] = hard_ms
    cfg["max_ms"] = min(int(cfg.get("max_ms", 5000)), hard_ms)
    return json.dumps(cfg, separators=(",", ":"))


def _initialize(deck: list[int]) -> bool:
    os.environ["POKEMON_PVS_CONFIG"] = _effective_config()
    if _worker is not None:
        return _worker.start(deck)
    return bridge.initialize(deck)


def _error() -> str:
    return _worker.error if _worker is not None else bridge.error


def _choose(obs: dict) -> list[int] | None:
    if _worker is None:
        return bridge.choose(obs)
    remaining = float(obs.get("remainingOverageTime", 600.0))
    safety = 5.0
    available = remaining - safety
    if available <= 0.05:
        _worker.error = "time safety reserve reached"
        return None
    # Recover before the worker hard limit so a legal move can still be returned.
    hard_limit = float(os.environ.get("POKEMON_PVS_HARD_TIMEOUT", "6.0"))
    return _worker.choose(obs, min(hard_limit, available))


def _diagnostics() -> dict:
    return _worker.last_diagnostics if _worker is not None else bridge.diagnostics()


def read_deck_csv() -> list[int]:
    """Read deck.csv.

    Returns:
        list[int]: A list of card IDs in the deck.
    """
    base = submission_root()
    candidates = [
        Path("/kaggle_simulations/agent/deck.csv"),
        base / "deck.csv",
        Path("deck.csv"),
    ]
    file_path = next((path for path in candidates if path.exists()), base / "deck.csv")
    cards = [int(line.strip()) for line in file_path.read_text().splitlines() if line.strip()]
    if len(cards) != 60:
        raise ValueError(f"deck must contain 60 cards, got {len(cards)} from {file_path}")
    return cards


def _valid_action(result: list[int], select: dict) -> bool:
    lo = int(select.get("minCount", 0))
    hi = int(select.get("maxCount", 0))
    options = select.get("option") or []
    n = len(options)
    if not (lo <= len(result) <= hi):
        return False
    if len(result) != len(set(result)):
        return False
    return all(0 <= index < n for index in result)


def agent(obs_dict: dict) -> list[int]:
    """Implement Your Pokémon Trading Card Game Agent.

    Each element in the returned list must be >= 0 and < len(obs.select.option).
    The list length must be between obs.select.minCount and obs.select.maxCount (inclusive), with no duplicate elements.

    Returns:
        list[int]: A list of option index.
    """
    global _deck, _init_failed
    if obs_dict.get("select") is None:
        _deck = read_deck_csv()
        _init_failed = not _initialize(_deck)
        if _init_failed:
            print(f"pvs init failed: {_error()}", file=sys.stderr, flush=True)
        return _deck
    if _deck is None:
        _deck = read_deck_csv()
        _init_failed = not _initialize(_deck)
        if _init_failed:
            print(f"pvs init failed: {_error()}", file=sys.stderr, flush=True)
    select = obs_dict.get("select") or {}
    current = obs_dict.get("current") or {}
    remain_raw = obs_dict.get("remainingOverageTime")
    call_idx = getattr(agent, "_debug_call_idx", 0)
    agent._debug_call_idx = call_idx + 1
    # #region agent log
    debug_log(
        "main.py:agent:pre_choose",
        "choose call",
        {
            "call_idx": call_idx,
            "remain_raw": remain_raw,
            "context": select.get("context"),
            "turn": current.get("turn"),
            "init_failed": _init_failed,
        },
        "A",
    )
    # #endregion
    t0 = time.perf_counter()
    result = _choose(obs_dict)
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
    diag = _diagnostics()
    # #region agent log
    debug_log(
        "main.py:agent:post_choose",
        "choose result",
        {
            "call_idx": call_idx,
            "elapsed_ms": elapsed_ms,
            "bridge_error": _error(),
            "used_fallback": result is None,
            "budget_ms": diag.get("budget_ms"),
            "wall_ms": diag.get("wall_ms"),
            "search_wall_ms": diag.get("search_wall_ms"),
            "worlds": diag.get("worlds"),
            "nodes": diag.get("nodes"),
        },
        "B",
    )
    # #endregion
    if result is None:
        # #region agent log
        debug_log(
            "main.py:agent:fallback",
            "fallback path",
            {"call_idx": call_idx, "reason": "choose_none", "elapsed_ms": elapsed_ms},
            "D",
        )
        # #endregion
        print(f"pvs choose failed: {_error()}", file=sys.stderr, flush=True)
        return fallback_choose(obs_dict)
    if not _valid_action(result, select):
        # #region agent log
        debug_log(
            "main.py:agent:fallback",
            "fallback path",
            {"call_idx": call_idx, "reason": "illegal_action", "elapsed_ms": elapsed_ms},
            "D",
        )
        # #endregion
        print(
            f"pvs choose illegal: len={len(result)} min={select.get('minCount')} max={select.get('maxCount')}",
            file=sys.stderr,
            flush=True,
        )
        return fallback_choose(obs_dict)
    return result
