# Runtime v1 Repository Map

**Date:** 2026-07-04

## Production candidate (new B0 runtime)

| Item | Location |
|------|----------|
| Submission entry point (new) | `submission/main.py` → `ptcg_runtime.runtime.get_runtime()` |
| Submission entry point (legacy) | `sample_submission/main.py` |
| Deck CSV (legacy) | `sample_submission/deck.csv` |
| Deck CSV (new) | `submission/deck.csv` |
| Host / cabt wrapper | `sample_submission/cg/` (BattleStart, Select, search API) |
| B0 runtime source | `src/ptcg_ai/` |
| Build / smoke tools | `tools/build_submission.py`, `tools/run_smoke.py`, `tools/run_soak.py` |

## Research-only (must not import from submission/runtime)

| Item | Location |
|------|----------|
| Native PVS engine | `cpp/`, `sample_submission/pvs_bridge.py`, `libpokemon_pvs.so` |
| MCTS / search | `sample_submission/cg/api.py` (search_begin/step/end) |
| Training | `training/train_nnue.py` |
| Self-play scripts | `scripts/kaggle_selfplay_test.py`, `scripts/review_selfplay.py`, etc. |
| Belief / oracle | not in production import graph |

## Agent entry

- Host I/F: `agent(obs_dict: dict) -> list[int]`
- Deck selection: `obs["select"] is None` → return 60 card IDs
- In-game: return index list for `obs["select"]["option"]`

## Tests

- Legacy: `tests/test_agent.py`, `tests/test_hidden_info.py`, `pytest` from repo root
- New qualification: `tests/contract/`, `tests/semantic/`, `tests/runtime/`, `tests/submission/`

## Package manager

- No pyproject.toml; pure Python + optional NumPy
- Python 3.x (tested with system Python)
- Native build: CMake + MSVC/GCC for legacy PVS only

## Submission packaging (legacy)

- Tarball: `main.py` + `deck.csv` + bundled files under `sample_submission/`
- New: `tools/build_submission.py` → `dist/submission/` with manifest.json

## Local simulator

- `sample_submission/cg/game.py`: `battle_start`, `battle_select`, `battle_finish`
- Requires `cg.dll` / platform native sim library in `sample_submission/cg/`

## Current smoke test (legacy)

- `scripts/submission_smoke_test.py` — requires native library + model.nnue
