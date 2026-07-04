"""T3: Schema registry loads matrix with fixture evidence."""
from __future__ import annotations

from ptcg_ai.host.schema_registry import all_supported_templates, get_template, load_errors


def test_registry_loads_matrix_without_errors():
    assert not load_errors(), load_errors()


def test_registry_supports_single_family():
    tpl = get_template(
        "ignored",
        select_type=0,
        context=0,
        min_count=1,
        max_count=1,
        option_count=3,
    )
    assert tpl is not None
    assert tpl.host_apply_verified


def test_registry_supports_optional_single():
    tpl = get_template(
        "ignored",
        select_type=1,
        context=2,
        min_count=0,
        max_count=1,
        option_count=1,
    )
    assert tpl is not None
    assert tpl.semantic_schema_key == "family:1:0:1:optional_single"


def test_all_supported_have_fixtures():
    for tpl in all_supported_templates():
        assert tpl.fixture_path
        assert tpl.evidence is not None
        assert tpl.evidence.host_apply_verified
