# Runtime v1 Implementation Report

**Date:** 2026-07-04 (updated after P0 blocker fixes)  
**Branch:** `feat/competition-runtime-v1`  
**Reviewed commit:** `b87ee75` (pre-fix); pending new commit with P0 fixes

## Review metadata

| Field | Value |
|-------|-------|
| branch | `feat/competition-runtime-v1` |
| reviewed_commit (baseline) | `b87ee755e66373eb45bdbb0005e38aa78ff602ce` |
| Python | 3.13.5 |
| OS | Windows 10 |
| cabt simulator | `sample_submission/cg/` (local `battle_start`) |
| fixture count | 2 (`deck_selection/basic`, `attack/single_select`) |
| soak games | 1 self-play (same deck vs same deck, seat 0) |
| soak seat distribution | mirror self-play, single seat path |

### Commands run (2026-07-04)

```text
python -m pytest tests/contract tests/semantic tests/runtime tests/submission -q
→ 18 passed

python tools/run_smoke.py
→ smoke OK

python tools/run_soak.py
→ crash=0, illegal=0, fallback=0, unsupported_schema=1 (0..1 decision, fixture未登録)
```

## P0 blocker fixes (this revision)

### 1. Multi-select fail-fast
- `Proposer` は `UnsupportedSelectionSchema` を握りつぶさない
- `FallbackSelector` は `ValidatedResponseSet` / `operational_fallback()` 内の検証済み response のみ使用
- `classify_selection_mode`: `empty` / `optional_single` / `set` / `sequence` を分離
- 未登録 schema は `Runtime.act()` で incident 記録後に再送出（generic fallback 禁止）

### 2. Whitelist sanitizer
- `observation_projector.py`: raw obs を whitelist projection（削除方式を廃止）
- `event_visibility.py`: 許可イベントのみ ledger へ
- 相手 hidden / `search_begin_input` は下流へ渡さない
- 自分の face-down prize identity は unknown zone に混ぜない

### 3. Ledger incremental processing
- `ObservationLedger.ingest_public_events()`: delta のみ処理、fingerprint 再同期

### 4. Exception taxonomy
- `ContractMismatch`, `OperationalFailure`, `CardConservationMismatch`
- policy は `OperationalFailure` のみ validated fallback
- schema / conservation mismatch は fallback 禁止

### 5. Time bank
- `act()` 入口で deadline 開始（sanitize を budget に含める）
- `TimeBankState`: local monotonic 減算、host 欠損時の悲観推定

## P1 improvements (partial)

### 6. PublicPokemon / PublicBoard
- HP, damage, energy, status, retreat, slot 付き `PublicPokemon`
- bench は slot sequence（multiset 廃止）

### 7. Card conservation
- `sum(remaining) == deck_count + prize_face_down` を検証
- 未検証時は `conservation_unverified` を diagnostics に記録（黙って続行しない／偽装もしない）
- 検証済みかつ不一致時のみ `CardConservationMismatch`

## Phase status

| Phase | Status |
|-------|--------|
| -1 artifact build | OK |
| 0 contract probe | OK (local cabt) |
| 1 B0 runtime | OK for builtin `single` 1..1 |
| Blocker | `optional_single` (0..1), `empty` (0..0), `set`/`sequence` は fixture 登録待ち |

## Fixture coverage

| Category | Maturity | Notes |
|----------|----------|-------|
| deck_selection/basic | parsed | |
| attack/single_select | response-validated | builtin single 1..1 |
| optional_single (0..1) | **未登録** | soak で mulligan 等が停止 |
| empty (0..0) | **未登録** | |
| set / sequence | **未登録** | fail-fast |

## Rollback

```text
git checkout b87ee75  # pre-P0-fix baseline
git checkout main       # legacy PVS only
```

## git status at report time

Uncommitted P0 fixes on `feat/competition-runtime-v1` (pending commit).
