import json
from pathlib import Path

d = json.loads(Path("scripts/stall_probe_results.json").read_text(encoding="utf-8"))
opts = d["positions"][1]["options"]
for p in d["probes"]:
    if p["position"] != "T29P0" or p["label"] != "T29P0/prod":
        continue
    print("options count", len(opts))
    for r in p["root"]:
        idx = r["pick"][0]
        print(f"  idx={idx:2} agg={r['agg']:8.1f} order={r['order']:7.2f} opt={opts[idx] if idx < len(opts) else '?'}")
    # find attack/end
    for idx, o in enumerate(opts):
        if "ATTACK" in o or o == "END":
            print(f"  [all] idx={idx} opt={o}")
