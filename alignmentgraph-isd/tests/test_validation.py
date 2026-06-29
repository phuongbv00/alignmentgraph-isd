"""P0.2: structural schema validation for sections and the ADDIE aggregate."""
from __future__ import annotations

from alignmentgraph_isd.audit import GraphAuditor
from alignmentgraph_isd.graph import AlignmentGraph
from alignmentgraph_isd.validation import validate_addie, validate_section


def test_validate_section_flags_missing_learning_objectives():
    errors = validate_section("objective", {"instructional_strategies": {"model": "x"}})
    assert any("learning_objectives" in e for e in errors)


def test_validate_section_flags_wrong_assessment_tools_type():
    errors = validate_section("assessment", {"assessment_tools": "not-a-list"})
    assert any("assessment_tools" in e and "expected list" in e for e in errors)


def test_validate_section_flags_malformed_objective_id():
    errors = validate_section(
        "objective",
        {"learning_objectives": [{"id": "9 bad id", "statement": "x"}], "instructional_strategies": {}},
    )
    assert any("malformed id" in e for e in errors)


def test_validate_addie_flags_missing_phase():
    errors = validate_addie({"analysis": {}, "design": {}, "development": {}, "implementation": {}})
    assert any(e.startswith("evaluation") for e in errors)


def test_auditor_surfaces_schema_violation_and_routes_for_regeneration():
    graph = AlignmentGraph()
    # assessment section present but with a wrong-typed required field
    graph.add_node("assessment", "assessment_0", {"assessment_tools": "oops"})
    audit = GraphAuditor(graph).audit()
    assert "assessment" in audit.schema_violations
    # the type error becomes a regeneration trigger so the planner reruns the owner
    assert audit.missing_section_keys.get("assessment")
    assert not audit.ready_to_aggregate
