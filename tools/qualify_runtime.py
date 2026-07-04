#!/usr/bin/env python3
"""M0.2 qualification — writes evidence to artifacts/qualification/<commit>/ only."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))


def _git(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(["git", *cmd], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def _tree_clean() -> bool:
    return not bool(_git(["status", "--porcelain"]))


def _digest_dir_json(dir_path: Path) -> tuple[int, str]:
    paths = sorted(dir_path.rglob("*.json")) if dir_path.is_dir() else []
    h = hashlib.sha256()
    for p in paths:
        h.update(p.relative_to(dir_path).as_posix().encode())
        h.update(p.read_bytes())
    return len(paths), h.hexdigest()[:16] if paths else "none"


def _digest_file(path: Path) -> str:
    if not path.is_file():
        return "missing"
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _run_pytest() -> tuple[str, bool, str]:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/contract",
        "tests/semantic",
        "tests/runtime",
        "tests/submission",
        "-q",
    ]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    output = (proc.stdout or "") + (proc.stderr or "")
    return " ".join(cmd), proc.returncode == 0, output


def _run_artifact_e2e(decisions: int = 25) -> tuple[str, bool, str, dict]:
    cmd = [sys.executable, str(ROOT / "tools" / "run_artifact_e2e.py"), "--decisions", str(decisions)]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    output = (proc.stdout or "") + (proc.stderr or "")
    parsed: dict = {}
    text = (proc.stdout or "").strip()
    start = text.find("{")
    if start >= 0:
        try:
            parsed = json.loads(text[start:])
        except json.JSONDecodeError:
            parsed = {}
    ok = proc.returncode == 0 and parsed.get("passed", False)
    return " ".join(cmd), ok, output, parsed


def _run_soak(games: int, *, mode: str) -> tuple[str, dict]:
    from ptcg_ai.eval.arena import ArenaConfig, run_soak_batch
    from ptcg_ai.eval.runtime_harness import wrap_runtime_act
    from ptcg_ai.eval.scorecard import Scorecard
    from ptcg_ai.runtime.runtime import CompetitionRuntime

    deck_path = ROOT / "submission" / "deck.csv"
    deck = [int(x) for x in deck_path.read_text().split() if x.strip()]
    runtime = CompetitionRuntime(deck)
    telemetry_card = Scorecard()
    cmd = f"python tools/qualify_runtime.py --soak-games {games} --time-bank-mode {mode}"
    cfg = ArenaConfig(
        max_steps=800,
        time_bank_mode="authoritative" if mode == "authoritative" else "no_authoritative",
        initial_time_seconds=600.0,
    )
    card = run_soak_batch(wrap_runtime_act(runtime, telemetry_card), deck, games=games, sim_root=ROOT / "sample_submission", config=cfg)
    card.fallback_count = telemetry_card.fallback_count
    card.emergency_decision_count = telemetry_card.emergency_decision_count
    card.conservation_verified_count += telemetry_card.conservation_verified_count
    card.conservation_unverified_count += telemetry_card.conservation_unverified_count
    card.conservation_mismatch_count += telemetry_card.conservation_mismatch_count
    return cmd, card.to_dict()


def _seat_distribution_ok(soak: dict, games: int) -> bool:
    dist = soak.get("seat_distribution", {})
    return dist.get("first", -1) == games // 2 and dist.get("second", -1) == games - games // 2


def _qualification_level(status: dict) -> str:
    gates = [
        status.get("tested_tree_clean"),
        status.get("pytest_passed"),
        status.get("schema_registry_load_errors_count", 1) == 0,
        status.get("fixture_evidence_coverage", 0) >= 1.0,
        status.get("artifact_e2e_passed"),
        status.get("soak_authoritative_passed"),
        status.get("soak_no_authoritative_passed"),
        status.get("seat_distribution_authoritative_ok"),
        status.get("seat_distribution_no_authoritative_ok"),
        status.get("completed_games", 0) >= 50,
        status.get("unsupported_schema_count", 1) == 0,
        status.get("fallback_count", 1) == 0,
        status.get("illegal_action_count", 1) == 0,
        status.get("protocol_error_count", 1) == 0,
        status.get("crash_count", 1) == 0,
        status.get("time_bank_exhaustion_count", 1) == 0,
        status.get("max_rss_bytes") is not None and (status.get("max_rss_bytes") or 0) > 0,
    ]
    if all(gates):
        return "qualified"
    if status.get("completed_games", 0) >= 1 and status.get("crash_count", 1) == 0:
        return "provisional"
    return "not_qualified"


def _soak_passed(soak: dict, *, games: int) -> bool:
    return (
        soak.get("completed_games", 0) >= games
        and soak.get("unsupported_schema_count", 0) == 0
        and soak.get("fallback_count", 0) == 0
        and soak.get("illegal_action_count", 0) == 0
        and soak.get("protocol_error_count", 0) == 0
        and soak.get("crash_count", 0) == 0
        and soak.get("time_bank_exhaustion_count", 0) == 0
        and _seat_distribution_ok(soak, games)
    )


def build_status(*, soak_games: int = 50, allow_dirty: bool = False) -> dict:
    tested_commit = _git(["rev-parse", "HEAD"])
    if not allow_dirty and not _tree_clean():
        raise SystemExit("working tree is dirty — commit/stash changes or pass --allow-dirty")

    from ptcg_ai.host.schema_registry import REGISTRY, all_supported_templates, load_errors, matrix_digest

    registry_snapshot = {
        "matrix_digest": matrix_digest(),
        "load_errors": list(load_errors()),
        "supported_templates": [
            {
                "semantic_schema_key": t.semantic_schema_key,
                "select_type": t.select_type,
                "context": t.context,
                "min_count": t.min_count,
                "max_count": t.max_count,
                "selection_mode": t.selection_mode,
                "fixture_path": t.fixture_path,
            }
            for t in all_supported_templates()
        ],
    }

    fixture_dir = ROOT / "docs" / "competition_contract" / "fixtures"
    fixture_count, fixture_digest = _digest_dir_json(fixture_dir)
    matrix_path = ROOT / "docs" / "competition_contract" / "response_schema_matrix.json"
    matrix_d = _digest_file(matrix_path)
    registry_errors = list(load_errors())
    templates = all_supported_templates()
    fixture_evidence_coverage = REGISTRY.fixture_evidence_coverage()
    matrix_all_fixtures = len(registry_errors) == 0 and len(templates) > 0 and fixture_evidence_coverage >= 1.0

    test_cmd, test_ok, test_output = _run_pytest()
    tested_tree_clean = _tree_clean()

    e2e_cmd, e2e_ok, e2e_output, e2e_parsed = _run_artifact_e2e()
    tested_tree_clean = _tree_clean()

    auth_cmd, soak_auth = _run_soak(soak_games, mode="authoritative")
    tested_tree_clean = _tree_clean()

    noauth_cmd, soak_noauth = _run_soak(soak_games, mode="no_authoritative")
    tested_tree_clean = _tree_clean()

    merged_soak = {
        "completed_games": min(soak_auth.get("completed_games", 0), soak_noauth.get("completed_games", 0)),
        "unsupported_schema_count": soak_auth.get("unsupported_schema_count", 0)
        + soak_noauth.get("unsupported_schema_count", 0),
        "fallback_count": soak_auth.get("fallback_count", 0) + soak_noauth.get("fallback_count", 0),
        "illegal_action_count": soak_auth.get("illegal_action_count", 0)
        + soak_noauth.get("illegal_action_count", 0),
        "protocol_error_count": soak_auth.get("protocol_error_count", 0)
        + soak_noauth.get("protocol_error_count", 0),
        "crash_count": soak_auth.get("crash_count", 0) + soak_noauth.get("crash_count", 0),
        "time_bank_exhaustion_count": soak_auth.get("time_bank_exhaustion_count", 0)
        + soak_noauth.get("time_bank_exhaustion_count", 0),
        "max_rss_bytes": max(
            filter(None, [soak_auth.get("max_rss_bytes"), soak_noauth.get("max_rss_bytes")]),
            default=None,
        ),
        "median_decision_ms": soak_auth.get("median_decision_ms"),
        "p95_decision_ms": soak_auth.get("p95_decision_ms"),
        "p99_decision_ms": soak_auth.get("p99_decision_ms"),
        "conservation_verified_count": soak_auth.get("conservation_verified_count", 0)
        + soak_noauth.get("conservation_verified_count", 0),
        "conservation_unverified_count": soak_auth.get("conservation_unverified_count", 0)
        + soak_noauth.get("conservation_unverified_count", 0),
        "conservation_mismatch_count": soak_auth.get("conservation_mismatch_count", 0)
        + soak_noauth.get("conservation_mismatch_count", 0),
        "seat_distribution": {
            "first": soak_auth.get("seat_distribution", {}).get("first", 0),
            "second": soak_auth.get("seat_distribution", {}).get("second", 0),
        },
    }

    seat_auth_ok = _seat_distribution_ok(soak_auth, soak_games)
    seat_noauth_ok = _seat_distribution_ok(soak_noauth, soak_games)

    status = {
        "tested_commit": tested_commit,
        "tested_tree_clean": tested_tree_clean,
        "branch": _git(["rev-parse", "--abbrev-ref", "HEAD"]),
        "python_version": platform.python_version(),
        "os": platform.platform(),
        "simulator_path": str(ROOT / "sample_submission" / "cg" / "game.py"),
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "fixture_count": fixture_count,
        "fixture_digest": fixture_digest,
        "response_schema_matrix_digest": matrix_d,
        "registry_load_errors": registry_errors,
        "schema_registry_load_errors_count": len(registry_errors),
        "matrix_all_fixtures_present": matrix_all_fixtures,
        "fixture_evidence_coverage": fixture_evidence_coverage,
        "matrix_digest_runtime": matrix_digest(),
        "artifact_manifest_hash": e2e_parsed.get("manifest_hash"),
        "test_command": test_cmd,
        "pytest_passed": test_ok,
        "artifact_e2e_command": e2e_cmd,
        "artifact_e2e_passed": e2e_ok,
        "soak_authoritative_command": auth_cmd,
        "soak_authoritative_passed": _soak_passed(soak_auth, games=soak_games),
        "soak_no_authoritative_command": noauth_cmd,
        "soak_no_authoritative_passed": _soak_passed(soak_noauth, games=soak_games),
        "soak_deck_matchup": "self_play_same_deck",
        "seat_distribution_ok": seat_auth_ok and seat_noauth_ok,
        "seat_distribution_authoritative_ok": seat_auth_ok,
        "seat_distribution_no_authoritative_ok": seat_noauth_ok,
        "seat_distribution": soak_auth.get("seat_distribution", {}),
        "emergency_decision_count": soak_auth.get("emergency_decision_count", 0)
        + soak_noauth.get("emergency_decision_count", 0),
        "completed_games": merged_soak["completed_games"],
        "unsupported_schema_count": merged_soak["unsupported_schema_count"],
        "fallback_count": merged_soak["fallback_count"],
        "illegal_action_count": merged_soak["illegal_action_count"],
        "protocol_error_count": merged_soak["protocol_error_count"],
        "crash_count": merged_soak["crash_count"],
        "time_bank_exhaustion_count": merged_soak["time_bank_exhaustion_count"],
        "max_rss_bytes": merged_soak["max_rss_bytes"],
        "median_decision_ms": merged_soak["median_decision_ms"],
        "p95_decision_ms": merged_soak["p95_decision_ms"],
        "p99_decision_ms": merged_soak["p99_decision_ms"],
        "conservation_verified_count": merged_soak["conservation_verified_count"],
        "conservation_unverified_count": merged_soak["conservation_unverified_count"],
        "conservation_mismatch_count": merged_soak["conservation_mismatch_count"],
    }
    status["qualification_level"] = _qualification_level(status)
    return status, {
        "pytest_output": test_output,
        "artifact_e2e_output": e2e_output,
        "artifact_e2e_result": e2e_parsed,
        "soak_authoritative": soak_auth,
        "soak_no_authoritative": soak_noauth,
        "schema_registry_snapshot": registry_snapshot,
    }


def write_artifacts(status: dict, outputs: dict) -> Path:
    out_dir = ROOT / "artifacts" / "qualification" / status["tested_commit"]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "qualification_status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    (out_dir / "pytest_output.txt").write_text(outputs.get("pytest_output", ""), encoding="utf-8")
    (out_dir / "artifact_e2e_result.json").write_text(
        json.dumps(outputs.get("artifact_e2e_result") or {"passed": status["artifact_e2e_passed"]}, indent=2),
        encoding="utf-8",
    )
    (out_dir / "authoritative_soak.json").write_text(
        json.dumps(outputs.get("soak_authoritative", {}), indent=2),
        encoding="utf-8",
    )
    (out_dir / "no_authoritative_soak.json").write_text(
        json.dumps(outputs.get("soak_no_authoritative", {}), indent=2),
        encoding="utf-8",
    )
    (out_dir / "schema_registry_snapshot.json").write_text(
        json.dumps(outputs.get("schema_registry_snapshot", {}), indent=2),
        encoding="utf-8",
    )
    report = _render_report(status)
    (out_dir / "runtime_v1_qualification_report.md").write_text(report, encoding="utf-8")
    return out_dir


def _render_report(status: dict) -> str:
    return "\n".join(
        [
            "# Runtime v1 Qualification Report",
            "",
            f"- tested_commit: `{status['tested_commit']}`",
            f"- tested_tree_clean: `{status['tested_tree_clean']}`",
            f"- qualification_level: `{status['qualification_level']}`",
            f"- branch: `{status['branch']}`",
            f"- executed_at: {status['executed_at']}",
            "",
            "## Digests",
            f"- fixture_digest: `{status['fixture_digest']}`",
            f"- response_schema_matrix_digest: `{status['response_schema_matrix_digest']}`",
            "",
            "## Gates",
            f"- pytest_passed: {status['pytest_passed']}",
            f"- artifact_e2e_passed: {status['artifact_e2e_passed']}",
            f"- soak_authoritative_passed: {status['soak_authoritative_passed']}",
            f"- soak_no_authoritative_passed: {status['soak_no_authoritative_passed']}",
            f"- completed_games: {status['completed_games']}",
            f"- fixture_evidence_coverage: {status.get('fixture_evidence_coverage')}",
            f"- max_rss_bytes: {status['max_rss_bytes']}",
            f"- seat_distribution_ok: {status.get('seat_distribution_ok')}",
            f"- schema_registry_load_errors_count: {status.get('schema_registry_load_errors_count')}",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--soak-games", type=int, default=50)
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--time-bank-mode", choices=["authoritative", "no_authoritative"], default="authoritative")
    args = parser.parse_args()

    status, outputs = build_status(soak_games=args.soak_games, allow_dirty=args.allow_dirty)
    out_dir = write_artifacts(status, outputs)
    print(json.dumps(status, indent=2))
    print(f"artifacts -> {out_dir}")
    return 0 if status["qualification_level"] == "qualified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
