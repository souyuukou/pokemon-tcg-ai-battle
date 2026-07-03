"""Thin, fail-safe ctypes bridge to the C++ PVS engine."""
from __future__ import annotations

import ctypes
import json
import os
import platform
from pathlib import Path

from paths import submission_root
from pvs_wire import encode_observation


class PVSBridge:
    def __init__(self) -> None:
        self.root = submission_root()
        self.lib = None
        self.error = "not initialized"
        self.deck: list[int] = []

    def _native_path(self) -> Path | None:
        ext = ".dll" if os.name == "nt" else ".dylib" if platform.system() == "Darwin" else ".so"
        names = [self.root / f"pokemon_pvs{ext}", self.root / f"libpokemon_pvs{ext}"]
        return next((path for path in names if path.exists()), None)

    def _catalog_path(self) -> Path:
        bundled = self.root / "deck_catalog.json"
        return bundled if bundled.exists() else self.root.parent / "data" / "deck_catalog.json"

    def initialize(self, deck: list[int]) -> bool:
        self.deck = list(deck)
        self.lib = None
        native = self._native_path()
        if native is None:
            self.error = "native library not built"
            return False
        try:
            lib = ctypes.CDLL(str(native))
            lib.pvs_init.argtypes = [ctypes.c_char_p] * 4
            lib.pvs_init.restype = ctypes.c_int
            lib.pvs_choose.argtypes = [
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.POINTER(ctypes.c_int),
                ctypes.c_int,
                ctypes.POINTER(ctypes.c_int),
                ctypes.c_int,
            ]
            lib.pvs_choose.restype = ctypes.c_int
            lib.pvs_reset.argtypes = []
            lib.pvs_reset.restype = None
            lib.pvs_diagnostics.argtypes = []
            lib.pvs_diagnostics.restype = ctypes.c_char_p
            cg_name = "cg.dll" if os.name == "nt" else "libcg.dylib" if platform.system() == "Darwin" else (
                "libcg-arm64.so" if platform.machine().lower() in {"arm64", "aarch64"} else "libcg.so")
            catalog = self._catalog_path()
            config = os.environ.get(
                "POKEMON_PVS_CONFIG",
                '{"hypotheses":6,"threads":0,"max_depth":20,"max_ms":5100,"hard_ms":5100}',
            )
            rc = lib.pvs_init(str(self.root / "cg" / cg_name).encode(), str(catalog).encode(),
                              str(self.root / "model.nnue").encode(), config.encode())
            if rc:
                self.error = f"pvs_init failed: {rc}"
                return False
            self.lib = lib
            self.error = ""
            return True
        except Exception as exc:
            self.error = repr(exc)
            self.lib = None
            return False

    def choose(self, obs: dict) -> list[int] | None:
        if self.lib is None:
            return None
        deck = (ctypes.c_int * len(self.deck))(*self.deck)
        capacity = max(64, len((obs.get("select") or {}).get("option") or []))
        output = (ctypes.c_int * capacity)()
        payload = encode_observation(obs)
        buf = (ctypes.c_uint8 * len(payload)).from_buffer_copy(payload)
        count = self.lib.pvs_choose(
            ctypes.cast(buf, ctypes.c_void_p),
            len(payload),
            deck,
            len(deck),
            output,
            capacity,
        )
        if count < 0:
            self.error = f"pvs_choose failed: {count}"
            return None
        return list(output[:count])

    def diagnostics(self) -> dict:
        if self.lib is None:
            return {}
        raw = self.lib.pvs_diagnostics()
        if not raw:
            return {}
        return json.loads(raw.decode())


bridge = PVSBridge()
