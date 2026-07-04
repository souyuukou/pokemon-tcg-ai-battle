"""SchemaRegistry — loads response_schema_matrix.json as sole production source."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..semantic.legal_contract import matrix_family_key
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
    option_type_pattern: tuple[str | int, ...]
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


def _validate_matrix_evidence_alignment(row: dict[str, Any], evidence: FixtureEvidence) -> str | None:
    key = row.get("semantic_schema_key", "?")
    if bool(row.get("empty_response_legal", False)) != evidence.empty_response_legal:
        return f"{key}: empty_response_legal mismatch matrix={row.get('empty_response_legal')} evidence={evidence.empty_response_legal}"
    if bool(row.get("ordering_required", False)) != evidence.order_sensitive:
        return f"{key}: ordering_required mismatch matrix={row.get('ordering_required')} evidence={evidence.order_sensitive}"
    if bool(row.get("duplicates_allowed", False)) != evidence.duplicates_allowed:
        return f"{key}: duplicates_allowed mismatch matrix={row.get('duplicates_allowed')} evidence={evidence.duplicates_allowed}"
    return None


def _normalize_option_type_pattern(raw: Any) -> tuple[str | int, ...]:
    if not raw:
        return ("VARLEN",)
    if isinstance(raw, list):
        return tuple(raw)
    return (raw,)


def _matches_option_type_pattern(
    template_pattern: tuple[str | int, ...],
    actual: tuple[int | str | None, ...] | None,
) -> bool:
    if not template_pattern or template_pattern == ("VARLEN",) or list(template_pattern) == ["VARLEN"]:
        return True
    if actual is None:
        return False
    if len(template_pattern) != len(actual):
        return False
    for expected, got in zip(template_pattern, actual):
        if expected in ("VARLEN", "*"):
            continue
        if expected != got:
            return False
    return True


def _matches_context(template_context: int | str | None, actual_context: int | str | None) -> bool:
    if template_context in ("*", None):
        return True
    return template_context == actual_context


def _matches_family(
    template: SemanticResponseTemplate,
    *,
    select_type: int | str | None,
    context: int | str | None,
    min_count: int,
    max_count: int,
    mode: str,
    option_types: tuple[int | str | None, ...] | None,
) -> bool:
    if template.select_type not in ("*", None) and template.select_type != select_type:
        return False
    if not _matches_context(template.context, context):
        return False
    if template.min_count != min_count or template.max_count != max_count:
        return False
    if template.selection_mode != mode:
        return False
    if not _matches_option_type_pattern(template.option_type_pattern, option_types):
        return False
    return True


def _specificity_score(
    template: SemanticResponseTemplate,
    *,
    select_type: int | str | None,
    context: int | str | None,
    option_types: tuple[int | str | None, ...] | None,
) -> int:
    score = 0
    if template.select_type not in ("*", None) and template.select_type == select_type:
        score += 16
    if template.context not in ("*", None) and template.context == context:
        score += 8
    pat = template.option_type_pattern
    if pat and pat != ("VARLEN",) and list(pat) != ["VARLEN"]:
        if option_types is not None and _matches_option_type_pattern(pat, option_types):
            score += 4
    return score


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
        align_err = _validate_matrix_evidence_alignment(row, evidence)
        if align_err:
            _LOAD_ERRORS.append(align_err)
            continue
        patterns = row.get("valid_index_patterns") or []
        _REGISTRY[key] = SemanticResponseTemplate(
            semantic_schema_key=key,
            selection_mode=row.get("selection_mode", "single"),
            select_type=row.get("select_type"),
            context=row.get("context"),
            min_count=int(row.get("min_count", 0)),
            max_count=int(row.get("max_count", 0)),
            option_type_pattern=_normalize_option_type_pattern(row.get("option_type_pattern")),
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
    option_types: tuple[int | str | None, ...] | None = None,
) -> SemanticResponseTemplate | None:
    _ = semantic_key
    family = matrix_family_key(select_type, min_count, max_count, option_count)
    mode = classify_selection_mode(min_count, max_count, option_count)
    wildcard = f"family:*:{min_count}:{max_count}:{mode}"

    candidates: list[SemanticResponseTemplate] = []
    for key in (family, wildcard):
        if key in _REGISTRY:
            candidates.append(_REGISTRY[key])
    for template in _REGISTRY.values():
        if template in candidates:
            continue
        if _matches_family(
            template,
            select_type=select_type,
            context=context,
            min_count=min_count,
            max_count=max_count,
            mode=mode,
            option_types=option_types,
        ):
            candidates.append(template)

    if not candidates:
        return None

    ranked = sorted(
        candidates,
        key=lambda t: _specificity_score(
            t,
            select_type=select_type,
            context=context,
            option_types=option_types,
        ),
        reverse=True,
    )
    return ranked[0]


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


class SchemaRegistry:
    """Loads response_schema_matrix.json and matches canonical SelectionSemanticKey via family rules (plan B)."""

    def __init__(self) -> None:
        self._templates = dict(_REGISTRY)
        self.matrix_digest = _MATRIX_DIGEST
        self.load_errors = tuple(_LOAD_ERRORS)

    @classmethod
    def load(cls) -> SchemaRegistry:
        _load_matrix()
        return cls()

    def lookup_for_contract(
        self,
        *,
        canonical_semantic_key: str,
        select_type: int | str | None,
        context: int | str | None,
        min_count: int,
        max_count: int,
        option_count: int,
        option_types: tuple[int | str | None, ...] | None = None,
    ) -> SemanticResponseTemplate | None:
        """Match matrix family rule — canonical hash key is diagnostic only."""
        return get_template(
            canonical_semantic_key,
            select_type=select_type,
            context=context,
            min_count=min_count,
            max_count=max_count,
            option_count=option_count,
            option_types=option_types,
        )

    def family_key_for_contract(
        self,
        *,
        select_type: int | str | None,
        min_count: int,
        max_count: int,
        option_count: int,
    ) -> str:
        return matrix_family_key(select_type, min_count, max_count, option_count)

    def supported_templates(self) -> tuple[SemanticResponseTemplate, ...]:
        return tuple(self._templates.values())

    def fixture_evidence_coverage(self) -> float:
        rows_path = MATRIX_PATH
        if not rows_path.is_file():
            return 0.0
        rows = json.loads(rows_path.read_text(encoding="utf-8"))
        supported = [r for r in rows if r.get("supported_in_production")]
        if not supported:
            return 0.0
        ok = sum(1 for r in supported if r["semantic_schema_key"] in self._templates)
        return ok / len(supported)


REGISTRY = SchemaRegistry.load()
