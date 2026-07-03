"""Debug session NDJSON logger (session 08370f)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

_LOG = Path(__file__).resolve().parents[1] / "debug-08370f.log"
_ENABLED = os.environ.get("POKEMON_PVS_DEBUG_LOG") == "1"


def debug_log(
    location: str,
    message: str,
    data: dict,
    hypothesis_id: str,
    run_id: str = "pre-fix",
) -> None:
    if not _ENABLED:
        return
    # #region agent log
    try:
        entry = {
            "sessionId": "08370f",
            "timestamp": int(time.time() * 1000),
            "location": location,
            "message": message,
            "data": data,
            "hypothesisId": hypothesis_id,
            "runId": run_id,
        }
        with _LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # #endregion
