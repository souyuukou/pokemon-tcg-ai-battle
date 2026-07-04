"""SchemaRegistry — loads response_schema_matrix.json as sole production source."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..semantic.legal_contract import family_schema_key
from ..semantic.response_ir import classify_selection_mode

ROOT = Path(__file__).resolve().parents[3]
MATRIX_PATH = ROOT / "docs" / "competition_contract" / "response_schema_matrix.json"


def _resolve_repo_root() -> Path:
    here = Path(__file__).resolve()
    for depth in (3, 2):
        root = here.parents[depth]
        matrix = root / "docs" / "competition_contract" / "response_schema_matrix.json"
        if matrix.is_file():
            return root
    return ROOT


_REPO_ROOT = _resolve_repo_root()
MATRIX_PATH = _REPO_ROOT / "docs" / "competition_contract" / "response_schema_matrix.json"


@dataclass(frozen=True)
class FixtureEvidence:
    verified_patterns: tuple[tuple[int, ...], ...]
    empty_response_legal: bool
    order_sensitive: bool
    duplicates_allowed: bool
    pattern_rule: str
    host_apply_verified: bool
    reference_option_count: int | None = None


@dataclass(frozen=True)
class SemanticResponseTemplate:
    semantic_schema_key: str
    selection_mode: str
    select_type: int | str | None
    context: int | str | None
    min_count: int
    max_count: int
    valid_index_patterns: tuple[tuple[int, ...], ...]
    response_strategy: str | None
    fixture_path: str | None
    evidence: FixtureEvidence | None
    host_apply_verified: bool
    empty_response_legal: bool
    order_sensitive: bool
    duplicates_allowed: bool
    supported_in_production: bool


_REGISTRY: dict[str, SemanticResponseTemplate] = {}
_MATRIX_DIGEST: str = "none"
_LOAD_ERRORS: list[str] = []


def matrix_digest() -> str:
    return _MATRIX_DIGEST


def load_errors() -> tuple[str, ...]:
    return tuple(_LOAD_ERRORS)


def _digest_file(path: Path) -> str:
    if not path.is_file():
        return "missing"
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _load_evidence(row: dict[str, Any]) -> FixtureEvidence | None:
    evidence_path = row.get("fixture_evidence_path")
    if not evidence_path:
        stem = row.get("fixture_path")
        if stem:
            p = _REPO_ROOT / stem
            evidence_path = str(p.with_suffix(".evidence.json").relative_to(_REPO_ROOT)).replace("\\", "/")
        else:
            return None
    path = _REPO_ROOT / evidence_path
    if not path.is_file():
        _LOAD_ERRORS.append(f"missing evidence: {evidence_path}")
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    patterns = data.get("verified_patterns") or []
    return FixtureEvidence(
        verified_patterns=tuple(tuple(p) for p in patterns),
        empty_response_legal=bool(data.get("empty_response_legal", False)),
        order_sensitive=bool(data.get("order_sensitive", False)),
        duplicates_allowed=bool(data.get("duplicates_allowed", False)),
        pattern_rule=str(data.get("pattern_rule", "fixed")),
        host_apply_verified=bool(data.get("host_apply_verified", False)),
        reference_option_count=data.get("reference_option_count"),
    )


def _validate_row(row: dict[str, Any]) -> str | None:
    if not row.get("supported_in_production"):
        return None
    key = row.get("semantic_schema_key")
    if not key:
        return "row missing semantic_schema_key"
    if row.get("host_apply_verified") and not row.get("fixture_path"):
        return f"{key}: host_apply_verified requires fixture_path"
    if row.get("supported_in_production") and not row.get("fixture_path"):
        return f"{key}: supported_in_production requires fixture_path"
    if row.get("supported_in_production") and not row.get("response_strategy"):
        return f"{key}: supported_in_production requires response_strategy"
    return None


def _matches_family(row: dict[str, Any], *, select_type: int | str | None, min_count: int, max_count: int, mode: str) -> bool:
    row_type = row.get("select_type")
    row_ctx = row.get("context")
    if row_type not in ("*", None) and row_type != select_type:
        return False
    if int(row.get("min_count", -1)) != min_count:
        return False
    if int(row.get("max_count", -1)) != max_count:
        return False
    if row.get("selection_mode") != mode:
        return False
    return True


def _load_matrix() -> None:
    global _MATRIX_DIGEST
    _REGISTRY.clear()
    _LOAD_ERRORS.clear()
    if not MATRIX_PATH.is_file():
        _LOAD_ERRORS.append(f"missing matrix: {MATRIX_PATH}")
        return
    _MATRIX_DIGEST = _digest_file(MATRIX_PATH)
    rows = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        _LOAD_ERRORS.append("matrix root is not a list")
        return
    for row in rows:
        err = _validate_row(row)
        if err:
            _LOAD_ERRORS.append(err)
            continue
        if not row.get("supported_in_production"):
            continue
        key = row["semantic_schema_key"]
        evidence = _load_evidence(row)
        if evidence is None or not evidence.host_apply_verified:
            _LOAD_ERRORS.append(f"{key}: missing or unverified fixture evidence")
            continue
        patterns = row.get("valid_index_patterns") or []
        _REGISTRY[key] = SemanticResponseTemplate(
            semantic_schema_key=key,
            selection_mode=row.get("selection_mode", "single"),
            select_type=row.get("select_type"),
            context=row.get("context"),
            min_count=int(row.get("min_count", 0)),
            max_count=int(row.get("max_count", 0)),
            valid_index_patterns=tuple(tuple(p) for p in patterns),
            response_strategy=row.get("response_strategy"),
            fixture_path=row.get("fixture_path"),
            evidence=evidence,
            host_apply_verified=True,
            empty_response_legal=evidence.empty_response_legal,
            order_sensitive=evidence.order_sensitive,
            duplicates_allowed=evidence.duplicates_allowed,
            supported_in_production=True,
        )


def get_template(
    semantic_key: str,
    *,
    select_type: int | str | None,
    context: int | str | None,
    min_count: int,
    max_count: int,
    option_count: int,
) -> SemanticResponseTemplate | None:
    family = family_schema_key(select_type, min_count, max_count, option_count)
    mode = classify_selection_mode(min_count, max_count, option_count)
    wildcard = f"family:*:{min_count}:{max_count}:{mode}"
    for key in (family, wildcard):
        if key in _REGISTRY:
            return _REGISTRY[key]
    for template in _REGISTRY.values():
        if _matches_family(
            {
                "select_type": template.select_type,
                "context": template.context,
                "min_count": template.min_count,
                "max_count": template.max_count,
                "selection_mode": template.selection_mode,
            },
            select_type=select_type,
            min_count=min_count,
            max_count=max_count,
            mode=mode,
        ):
            return template
    return None


def expand_patterns(
    template: SemanticResponseTemplate,
    *,
    min_count: int,
    max_count: int,
    option_count: int,
) -> tuple[tuple[int, ...], ...]:
    evidence = template.evidence
    if evidence is None:
        return template.valid_index_patterns

    rule = evidence.pattern_rule
    if rule == "any_singleton":
        return tuple((i,) for i in range(option_count))
    if rule == "optional_single":
        patterns: list[tuple[int, ...]] = []
        if evidence.empty_response_legal and min_count == 0:
            patterns.append(())
        for i in range(option_count):
            if min_count <= 1 <= max_count:
                patterns.append((i,))
        return tuple(patterns)
    if rule == "bounded_set":
        import itertools

        sizes = {len(p) for p in evidence.verified_patterns}
        patterns: list[tuple[int, ...]] = []
        if evidence.empty_response_legal and min_count == 0:
            patterns.append(())
        ref_n = evidence.reference_option_count
        multi_ok = ref_n is None or ref_n == option_count
        for size in sorted(sizes):
            if size < min_count or size > max_count:
                continue
            if size == 1:
                patterns.extend((i,) for i in range(option_count))
            elif multi_ok:
                explicit = [tuple(p) for p in evidence.verified_patterns if len(p) == size]
                if evidence.order_sensitive:
                    for combo in itertools.permutations(range(option_count), size):
                        patterns.append(tuple(combo))
                else:
                    for combo in itertools.combinations(range(option_count), size):
                        patterns.append(tuple(combo))
                for pat in explicit:
                    if all(i < option_count for i in pat) and pat not in patterns:
                        patterns.append(pat)
            else:
                for pat in evidence.verified_patterns:
                    if len(pat) == size and all(i < option_count for i in pat):
                        patterns.append(tuple(pat))
        return tuple(dict.fromkeys(patterns))
    if rule == "fixed":
        out: list[tuple[int, ...]] = []
        for pat in evidence.verified_patterns:
            if len(pat) < min_count or len(pat) > max_count:
                continue
            if any(i < 0 or i >= option_count for i in pat):
                continue
            if len(pat) != len(set(pat)) and not evidence.duplicates_allowed:
                continue
            out.append(tuple(pat))
        return tuple(out)
    return evidence.verified_patterns


def all_supported_templates() -> tuple[SemanticResponseTemplate, ...]:
    return tuple(_REGISTRY.values())


_load_matrix()
