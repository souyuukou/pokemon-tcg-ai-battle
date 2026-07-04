"""Fixture corpus loader."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


@dataclass(frozen=True)
class FixtureRecord:
    name: str
    category: str
    maturity: str
    raw_observation: dict[str, Any]
    expected_actor_view: dict[str, Any] | None
    expected_legal_contract: dict[str, Any] | None


class FixtureLoader:
    def __init__(self, root: Path) -> None:
        self._root = root

    def iter_fixtures(self, min_maturity: str | None = None) -> Iterator[FixtureRecord]:
        maturity_order = ("observed", "parsed", "response-validated", "qualification")
        min_rank = maturity_order.index(min_maturity) if min_maturity else 0
        for category_dir in sorted(self._root.iterdir()):
            if not category_dir.is_dir():
                continue
            for fixture_dir in sorted(category_dir.iterdir()):
                raw_path = fixture_dir / "raw_observation_redacted.json"
                if not raw_path.is_file():
                    continue
                meta_path = fixture_dir / "redaction_manifest.json"
                maturity = "observed"
                if meta_path.is_file():
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    maturity = meta.get("maturity", "observed")
                if maturity_order.index(maturity) < min_rank:
                    continue
                raw = json.loads(raw_path.read_text(encoding="utf-8"))
                exp_view = None
                exp_contract = None
                vp = fixture_dir / "expected_actor_view.json"
                cp = fixture_dir / "expected_legal_contract.json"
                if vp.is_file():
                    exp_view = json.loads(vp.read_text(encoding="utf-8"))
                if cp.is_file():
                    exp_contract = json.loads(cp.read_text(encoding="utf-8"))
                yield FixtureRecord(
                    name=fixture_dir.name,
                    category=category_dir.name,
                    maturity=maturity,
                    raw_observation=raw,
                    expected_actor_view=exp_view,
                    expected_legal_contract=exp_contract,
                )
