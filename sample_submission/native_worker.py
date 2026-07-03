"""Out-of-process owner for the native search library.

The parent may kill this process safely if cg/SearchStep stops returning.
Protocol messages are one compact JSON object per line on stdin/stdout.
"""
from __future__ import annotations

import json
import os
import sys
import time

from pvs_bridge import PVSBridge


def send(value: dict) -> None:
    sys.stdout.write(json.dumps(value, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def main() -> None:
    bridge = PVSBridge()
    for line in sys.stdin:
        try:
            message = json.loads(line)
            command = message.get("cmd")
            if command == "init":
                ok = bridge.initialize([int(value) for value in message["deck"]])
                send({"ok": ok, "error": bridge.error})
            elif command == "choose":
                delay = float(os.environ.get("POKEMON_PVS_WORKER_TEST_DELAY", "0"))
                if delay > 0:
                    time.sleep(delay)
                result = bridge.choose(message["observation"])
                send({
                    "ok": result is not None,
                    "result": result,
                    "error": bridge.error,
                    "diagnostics": bridge.diagnostics(),
                })
            elif command == "reset":
                if bridge.lib is not None:
                    bridge.lib.pvs_reset()
                send({"ok": True})
            else:
                send({"ok": False, "error": "unknown command"})
        except BaseException as exc:
            send({"ok": False, "error": repr(exc)})


if __name__ == "__main__":
    main()
