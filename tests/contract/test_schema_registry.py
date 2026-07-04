"""T3: Schema registry loads matrix with fixture evidence."""
from __future__ import annotations

from ptcg_ai.host.schema_registry import REGISTRY, all_supported_templates, get_template, load_errors
from ptcg_ai.host.validated_responses import compile_responses_for_decision
from ptcg_ai.host.host_adapter import HostAdapter
from ptcg_ai.runtime.agent_session import AgentSession
from ptcg_ai.host.raw_observation import RawObservation


def test_registry_loads_matrix_without_errors():
    assert not load_errors(), load_errors()


def test_fixture_evidence_coverage_complete():
    assert REGISTRY.fixture_evidence_coverage() == 1.0


def test_registry_supports_single_family():
    tpl = get_template(
        "ignored",
        select_type=0,
        context=0,
        min_count=1,
        max_count=1,
        option_count=3,
        option_types=(14, 13, 12),
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
        option_types=(3,),
    )
    assert tpl is not None
    assert tpl.semantic_schema_key == "family:1:0:1:optional_single"


def test_registry_requires_exact_context():
    tpl = get_template(
        "ignored",
        select_type=1,
        context=99,
        min_count=0,
        max_count=1,
        option_count=1,
        option_types=(3,),
    )
    assert tpl is None


def test_all_supported_have_fixtures():
    for tpl in all_supported_templates():
        assert tpl.fixture_path
        assert tpl.evidence is not None
        assert tpl.evidence.host_apply_verified


def test_compile_optional_single_via_registry():
    obs = {
        "select": {
            "type": 1,
            "context": 2,
            "minCount": 0,
            "maxCount": 1,
            "option": [{"type": 3}],
        },
        "current": {"yourIndex": 0, "players": []},
        "logs": [],
    }
    decision = HostAdapter().sanitize_decision(RawObservation.from_dict(obs), AgentSession.start_new([65] * 60))
    responses = compile_responses_for_decision(decision)
    assert () in {r.option_indices for r in responses}
    assert (0,) in {r.option_indices for r in responses}
