# Runtime v1 Implementation Report

**Date:** 2026-07-04  
**Branch:** `feat/competition-runtime-v1`  
**Base commit:** `4d8ad04` (main)

## 1. 実装した機能

### Phase -1: 提出物凍結・再現ビルド
- `tools/build_submission.py` — `src/ptcg_ai` を `dist/submission/ptcg_runtime/` にコピーし、`main.py` / `deck.csv` / `manifest.json` を生成
- `submission/main.py` — 極小エントリポイント (`agent` → `ptcg_runtime.runtime`)
- preflight / repository map レポート

### Phase 0: Competition Contract Probe と fixture 基盤
- `tools/probe_contract.py` — cabt シミュレータから schema 採取（ローカルで `cabt_simulator` ソース確認済み）
- `src/ptcg_ai/contract/competition_contract.py` — `CompetitionContract` + `is_explicitly_allowed`
- `docs/competition_contract/` — probe 出力 JSON
- `docs/runtime_profiles/runtime_profile_local.json`
- `tests/fixtures/` — deck_selection (parsed), attack/single_select (response-validated)
- `src/ptcg_ai/eval/fixture_loader.py`

### Phase 1: B0 Production Baseline Runtime
- **host:** `RawObservation` 隔離、`HostAdapter`、`compile_candidate_responses` / `validate_response` / `to_host_response`
- **semantic:** `ActorView`, `LegalActionContract`, `OptionIR`, `ResponseIR`, `ObservationLedger`, card conservation
- **runtime:** `AgentSession`, `Deadline`, `TimeBankState`, `DiagnosticsBuffer`, `FallbackSelector`, `CompetitionRuntime`
- **baseline:** 決定論的 B0 `PolicyB0` / `Ranker` / `Proposer`（標準ライブラリのみ）
- unsupported multi-select は `UnsupportedSelectionSchema` で fail-fast（推測 response 禁止）

## 2. 変更した主要ファイル（新規）

| 領域 | パス |
|------|------|
| コア | `src/ptcg_ai/**` |
| 提出 | `submission/main.py`, `submission/deck.csv` |
| ツール | `tools/build_submission.py`, `probe_contract.py`, `run_smoke.py`, `run_soak.py` |
| テスト | `tests/contract/`, `tests/semantic/`, `tests/runtime/`, `tests/submission/`, `tests/fixtures/` |
| ドキュメント | `docs/qualification_reports/`, `docs/competition_contract/`, `docs/runtime_profiles/` |
| pytest | `conftest.py` |

既存の `sample_submission/`, `training/`, `cpp/`, `scripts/` は**未変更**（研究・legacy 提出物は温存）。

## 3. ブランチ / commit

- ブランチ `feat/competition-runtime-v1` を main から作成
- **コミットは未作成**（ユーザー指示待ち）

## 4. 実行したコマンドとテスト結果

```text
python -m pytest tests/contract tests/semantic tests/runtime tests/submission -q
→ 14 passed

python -m pytest tests/test_agent.py tests/test_hidden_info.py -q
→ 11 passed (legacy 互換)

python tools/build_submission.py
→ dist/submission 生成成功

python tools/probe_contract.py
→ source: cabt_simulator

python tools/run_smoke.py
→ smoke OK (deck 60枚, 1 decision 処理)

python tools/run_soak.py
→ completed_games=1, crash=0, illegal=0, fallback=0, p95≈1.6ms
```

## 5. 実行できなかったテストと理由

| テスト | 状態 |
|--------|------|
| T8 長時間 soak（数百局） | 未実行（1局 soak は成功。フル統計は Phase 2 以降） |
| T3 host apply 全 fixture | attack/single_select のみ response-validated。他 decision type は fixture 未整備 |
| NumPy optional fast path parity | B0 safe path のみ実装（NumPy 経路は未追加） |

## 6. CompetitionContract 確認済み / 未確定

**確認済み（設計書 §2.1 準拠）:**
- agent I/F, deck 60枚, host legal authority, 10分 time bank（`remainingOverageTime` を観測）
- search API は production 不使用

**未確定（保守的に無効 / None）:**
- `native_extension_allowed`, `external_data_allowed`, `network_allowed`
- `actTimeout` / `agentTimeout` の意味
- artifact size 上限、提出環境 CPU/メモリ実測

## 7. fixture coverage と未対応 schema

**fixture 成熟度:**
- `deck_selection/basic` — parsed
- `attack/single_select` — response-validated

**未対応 response schema:**
- independent set (`minCount>1` かつ `maxCount>1`) — `VALIDATED_SET_SCHEMAS` 空のため `UnsupportedSelectionSchema`
- ordered sequence — 未実装

## 8. smoke / soak 集計

| 指標 | 値 |
|------|-----|
| crash | 0 |
| illegal action | 0 |
| protocol error | 0 |
| fallback | 0 |
| unsupported schema | 0 |
| time bank exhaustion | 0 |
| median decision ms | ~1.3 |
| p95 decision ms | ~1.6 |
| p99 decision ms | ~2.0 |

## 9. existing self-play / training への影響

- **影響なし** — legacy `sample_submission` と `training/` はそのまま
- 新 runtime は `submission/` + `src/ptcg_ai/` に分離

## 10. Phase 2 前の blocker

1. 主要 decision type の response-validated fixture 拡充（mulligan, evolve, multi-select 等）
2. `VALIDATED_SET_SCHEMAS` への host apply 検証済み schema 登録
3. 提出環境実測による `runtime_profile` 固定
4. B0 と starter / legacy PVS の paired 勝率評価（統計未実施）

## 11. rollback 方法

```text
git checkout main
# または feat/competition-runtime-v1 を破棄して main の sample_submission を継続利用
```

legacy 提出物は `sample_submission/` に無改造で残存。
