# Pokémon TCG determinized PVS agent

The submission keeps `agent(obs) -> list[int]` in Python and moves belief
sampling and search into a C++20 shared library. It uses catalog-consistent
determinizations, parallel iterative-deepening PVS, and a compact quantized
sparse evaluator. If the native library or model is unavailable, a deterministic
legal fallback remains active.

Build with `scripts/build_native.ps1` on Windows or `scripts/build_native.sh` on
Linux. Train the optional evaluator with `training/train_nnue.py`. Runtime knobs
are supplied through `POKEMON_PVS_CONFIG`. Defaults: `"hypotheses":6`, `"threads":0`
(auto-detect, capped at 2), `"max_depth":20`, `"max_ms":5000`, with the total search
budget split evenly across belief rounds (`ms_per_world = budget_ms / ceil(worlds/threads)`).

Observations are passed to the native engine as a compact binary blob
(`PKOBS1`, see `sample_submission/pvs_wire.py` and `cpp/include/pvs_wire.hpp`),
not JSON. The cg.dll simulator still returns JSON at its API boundary; the
engine converts that once into an in-memory `GameState` via
`cpp/include/sim_json_scan.hpp` and never builds a JSON DOM during search.

Set `"profile":true` in `POKEMON_PVS_CONFIG` to expose per-call simulator,
import, action-policy, and value-evaluation CPU timings through
`pvs_diagnostics()`. Profiling is disabled by default because per-node clocks
reduce throughput. x86-64 release builds use AVX2 for quantized inference.
