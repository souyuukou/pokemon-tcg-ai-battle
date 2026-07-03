"""Hard-deadline client for native_worker.py."""
from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

from paths import submission_root


class _StderrRingBuffer:
    def __init__(self, max_bytes: int = 8192) -> None:
        self._max_bytes = max_bytes
        self._chunks: deque[str] = deque()
        self._size = 0

    def append(self, text: str) -> None:
        if not text:
            return
        self._chunks.append(text)
        self._size += len(text)
        while self._size > self._max_bytes and self._chunks:
            dropped = self._chunks.popleft()
            self._size -= len(dropped)

    def tail(self) -> str:
        return "".join(self._chunks)[-self._max_bytes :]


class NativeWorkerClient:
    def __init__(self) -> None:
        self.process: subprocess.Popen[str] | None = None
        self.responses: queue.Queue[dict | None] = queue.Queue()
        self.deck: list[int] = []
        self.error = "not initialized"
        self.last_diagnostics: dict = {}
        self._stderr_buffer = _StderrRingBuffer()
        self._stderr_thread: threading.Thread | None = None

    @property
    def stderr_tail(self) -> str:
        return self._stderr_buffer.tail()

    def _stop(self) -> None:
        process, self.process = self.process, None
        if process is None:
            return
        try:
            process.kill()
            process.wait(timeout=0.5)
        except Exception:
            pass
        for stream in (process.stdin, process.stdout, process.stderr):
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

    def _stderr_reader(self, process: subprocess.Popen[str]) -> None:
        try:
            assert process.stderr is not None
            for chunk in iter(process.stderr.read, ""):
                self._stderr_buffer.append(chunk)
        except Exception:
            pass

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
            if self.stderr_tail:
                self.error += f"; stderr={self.stderr_tail[-512:]}"
            self._stop()
            return None
        if response is None:
            self.error = "native worker exited"
            if self.stderr_tail:
                self.error += f"; stderr={self.stderr_tail[-512:]}"
            self._stop()
            return None
        return response

    def start(self, deck: list[int], timeout: float = 5.0) -> bool:
        self._stop()
        self.deck = list(deck)
        self.responses = queue.Queue()
        self._stderr_buffer = _StderrRingBuffer()
        root = submission_root()
        try:
            self.process = subprocess.Popen(
                [sys.executable, str(root / "native_worker.py")],
                cwd=str(root),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
            self._stderr_thread = threading.Thread(
                target=self._stderr_reader,
                args=(self.process,),
                daemon=True,
            )
            self._stderr_thread.start()
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
                if self.stderr_tail:
                    self.error += f"; stderr={self.stderr_tail[-512:]}"
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
        restarted = False
        if self.process is None or self.process.poll() is not None:
            restarted = True
            if not self.start(self.deck, min(2.0, max(0.01, deadline - time.monotonic()))):
                return None
        if restarted:
            try:
                from diagnostics import session_diagnostics
                session_diagnostics.record_worker_restart()
            except Exception:
                pass
        if not self._send({"cmd": "choose", "observation": observation}):
            self._stop()
            return None
        response = self._receive(deadline - time.monotonic())
        if not response or not response.get("ok"):
            self.error = (response or {}).get("error", self.error)
            if self.stderr_tail and "stderr=" not in self.error:
                self.error += f"; stderr={self.stderr_tail[-512:]}"
            return None
        self.error = ""
        self.last_diagnostics = response.get("diagnostics") or {}
        return response.get("result")
