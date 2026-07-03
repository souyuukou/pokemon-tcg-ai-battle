"""Runtime diagnostics for native search and fallback usage."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


class SessionDiagnostics:
    def __init__(self) -> None:
        self.build_id = self._detect_build_id()
        self.native_initialized = False
        self.native_backend = "unknown"
        self.native_choose_count = 0
        self.native_failure_count = 0
        self.worker_restart_count = 0
        self.fallback_count = 0
        self.last_native_error = ""
        self.last_worker_stderr = ""
        self.last_native_elapsed_ms = 0.0
        self.last_search_depth = 0
        self.last_search_nodes = 0
        self.last_particle_count = 0
        self.belief_degraded_count = 0
        self._path = self._diagnostics_path()

    @staticmethod
    def _detect_build_id() -> str:
        root = Path(__file__).resolve().parent
        for name in ("pokemon_pvs.dll", "libpokemon_pvs.so", "libpokemon_pvs.dylib", "pokemon_pvs.so"):
            path = root / name
            if path.is_file():
                return f"{name}:{int(path.stat().st_mtime)}"
        return "native-missing"

    @staticmethod
    def _diagnostics_path() -> Path | None:
        raw = os.environ.get("POKEMON_PVS_DIAGNOSTICS_FILE", "").strip()
        if raw:
            return Path(raw)
        if os.environ.get("POKEMON_PVS_DIAGNOSTICS", "0") == "1":
            return Path(__file__).resolve().parent / "diagnostics.jsonl"
        return None

    def record_init(self, ok: bool, error: str = "", backend: str = "unknown") -> None:
        self.native_initialized = ok
        self.native_backend = backend or self.native_backend
        if not ok:
            self.native_failure_count += 1
            if error:
                self.last_native_error = error

    def record_worker_restart(self) -> None:
        self.worker_restart_count += 1

    def record_worker_stderr(self, text: str) -> None:
        if text:
            self.last_worker_stderr = text[-8192:]

    def record_choose(
        self,
        *,
        ok: bool,
        elapsed_ms: float,
        diag: dict,
        error: str = "",
        used_fallback: bool = False,
        worker_stderr: str = "",
    ) -> None:
        if worker_stderr:
            self.record_worker_stderr(worker_stderr)
        if used_fallback:
            self.fallback_count += 1
            self.native_failure_count += 1
            if error:
                self.last_native_error = error
            return
        self.native_choose_count += 1
        self.last_native_elapsed_ms = elapsed_ms
        self.last_search_depth = int(diag.get("depth") or diag.get("completed_turn_depth") or 0)
        self.last_search_nodes = int(diag.get("nodes") or diag.get("call_nodes") or 0)
        self.last_particle_count = int(diag.get("worlds") or 0)
        if diag.get("belief_degraded"):
            self.belief_degraded_count += 1
        if not ok:
            self.native_failure_count += 1
            if error:
                self.last_native_error = error

    def as_dict(self) -> dict:
        return {
            "build_id": self.build_id,
            "native_initialized": self.native_initialized,
            "native_backend": self.native_backend,
            "native_choose_count": self.native_choose_count,
            "native_failure_count": self.native_failure_count,
            "worker_restart_count": self.worker_restart_count,
            "fallback_count": self.fallback_count,
            "last_native_error": self.last_native_error,
            "last_worker_stderr": self.last_worker_stderr,
            "last_native_elapsed_ms": self.last_native_elapsed_ms,
            "last_search_depth": self.last_search_depth,
            "last_search_nodes": self.last_search_nodes,
            "last_particle_count": self.last_particle_count,
            "belief_degraded_count": self.belief_degraded_count,
        }

    def emit(self) -> None:
        payload = self.as_dict()
        line = json.dumps(payload, separators=(",", ":"))
        print(f"pvs_diagnostics {line}", file=sys.stderr, flush=True)
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")

    def detect_backend(self, diag: dict) -> str:
        backend = diag.get("native_backend")
        if backend:
            self.native_backend = str(backend)
        return self.native_backend


session_diagnostics = SessionDiagnostics()
