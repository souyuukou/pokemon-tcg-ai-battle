"""Hard-deadline client for native_worker.py."""
from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

from paths import submission_root


class NativeWorkerClient:
    def __init__(self) -> None:
        self.process: subprocess.Popen[str] | None = None
        self.responses: queue.Queue[dict | None] = queue.Queue()
        self.deck: list[int] = []
        self.error = "not initialized"
        self.last_diagnostics: dict = {}

    def _stop(self) -> None:
        process, self.process = self.process, None
        if process is None:
            return
        try:
            process.kill()
            process.wait(timeout=0.5)
        except Exception:
            pass
        for stream in (process.stdin, process.stdout):
            try:
                if stream:
                    stream.close()
            except Exception:
                pass

    def close(self) -> None:
        self._stop()

    def _reader(self, process: subprocess.Popen[str], responses: queue.Queue) -> None:
        try:
            assert process.stdout is not None
            for line in process.stdout:
                responses.put(json.loads(line))
        except Exception:
            pass
        finally:
            responses.put(None)

    def _send(self, message: dict) -> bool:
        try:
            if self.process is None or self.process.stdin is None:
                return False
            self.process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
            self.process.stdin.flush()
            return True
        except Exception as exc:
            self.error = f"worker send failed: {exc!r}"
            return False

    def _receive(self, timeout: float) -> dict | None:
        try:
            response = self.responses.get(timeout=max(0.01, timeout))
        except queue.Empty:
            self.error = "native search hard timeout"
            self._stop()
            return None
        if response is None:
            self.error = "native worker exited"
            self._stop()
            return None
        return response

    def start(self, deck: list[int], timeout: float = 5.0) -> bool:
        self._stop()
        self.deck = list(deck)
        self.responses = queue.Queue()
        root = submission_root()
        try:
            self.process = subprocess.Popen(
                [sys.executable, str(root / "native_worker.py")],
                cwd=str(root),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
            threading.Thread(
                target=self._reader,
                args=(self.process, self.responses),
                daemon=True,
            ).start()
            if not self._send({"cmd": "init", "deck": self.deck}):
                self._stop()
                return False
            response = self._receive(timeout)
            if not response or not response.get("ok"):
                self.error = (response or {}).get("error", self.error)
                self._stop()
                return False
            self.error = ""
            return True
        except Exception as exc:
            self.error = f"worker start failed: {exc!r}"
            self._stop()
            return False

    def choose(self, observation: dict, timeout: float) -> list[int] | None:
        deadline = time.monotonic() + max(0.01, timeout)
        if self.process is None or self.process.poll() is not None:
            if not self.start(self.deck, min(2.0, max(0.01, deadline - time.monotonic()))):
                return None
        if not self._send({"cmd": "choose", "observation": observation}):
            self._stop()
            return None
        response = self._receive(deadline - time.monotonic())
        if not response or not response.get("ok"):
            self.error = (response or {}).get("error", self.error)
            return None
        self.error = ""
        self.last_diagnostics = response.get("diagnostics") or {}
        return response.get("result")
