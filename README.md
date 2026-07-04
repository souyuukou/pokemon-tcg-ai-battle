# Pokémon TCG AI Battle

This repository contains **two separate submission runtimes**. Do not mix their import graphs.

## Competition runtime v1 (B0 safe path)

**Branch:** `feat/competition-runtime-v1`  
**Status:** Phase -1〜1 implemented; **not yet qualified for production submission**

Host-contract-safe pure-Python baseline for the Kaggle PTCGABC competition.

| Item | Location |
|------|----------|
| Entry point | `submission/main.py` |
| Source | `src/ptcg_ai/` |
| Build | `python tools/build_submission.py` |
| Smoke | `python tools/run_smoke.py` |
| Qualification tests | `pytest tests/contract tests/semantic tests/runtime tests/submission` |
| Reports | `docs/qualification_reports/` |

Properties:

- Whitelist observation projection (no raw `obs_dict` below `host_adapter`)
- Validated-response-only fallback (unsupported multi-select fails fast)
- No research / torch / search API in production import graph

## Current stable legacy runtime (PVS / C++)

**Location:** `sample_submission/`  
**Status:** Existing production-oriented agent with native search

The legacy submission keeps `agent(obs) -> list[int]` in Python and moves belief
sampling and search into a C++20 shared library. It uses catalog-consistent
determinizations, parallel iterative-deepening PVS, and a compact quantized
sparse evaluator.

Build with `scripts/build_native.ps1` on Windows or `scripts/build_native.sh` on
Linux. Train the optional evaluator with `training/train_nnue.py`. Runtime knobs
are supplied through `POKEMON_PVS_CONFIG`.

Observations are passed to the native engine as a compact binary blob
(`PKOBS1`, see `sample_submission/pvs_wire.py` and `cpp/include/pvs_wire.hpp`),
not JSON.

**Do not submit the legacy and v1 runtimes from the same artifact without explicit merge qualification.**
