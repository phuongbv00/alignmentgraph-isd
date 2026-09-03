"""P0.2: structural schema validation for sections and the ADDIE aggregate."""
from __future__ import annotations

from alignmentgraph_isd.core.alignment_graph.audit import GraphAuditor
from alignmentgraph_isd.core.alignment_graph import AlignmentGraph
from alignmentgraph_isd.core.validation import validate_addie, validate_section


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


def test_validate_section_flags_empty_manuals_on_implementation_plan():
    # Rubric sub-items 20/21 grade these directly; empty manuals must surface
    # as required-field errors so the empty-field regen check can fire.
    payload = {
        "instructor_orientation": {"schedule": "Day 1"},
        "system_check": {"checklist": ["net"]},
        "prototype_execution": {"pilot_scope": "one cohort"},
        "monitoring": {"monitoring_criteria": ["completion"]},
        "instructor_guide": {},
        "operator_manual": {},
    }
    errors = validate_section("implementation_plan", payload)
    assert any("instructor_guide" in e and "required" in e for e in errors)
    assert any("operator_manual" in e and "required" in e for e in errors)


def test_validate_addie_flags_missing_manuals_in_development():
    addie = {
        "analysis": {"needs_analysis": {"x": 1}, "learner_analysis": {"x": 1},
                     "context_analysis": {"x": 1}, "task_analysis": {"x": 1}},
        "design": {"learning_objectives": [{"id": "ILO-01"}], "instructional_strategies": {"x": 1}},
        "development": {"learner_materials": [{"id": "MAT-01"}], "assessment_tools": [{"item_id": "AT-01"}]},
        "implementation": {"instructor_orientation": {"x": 1}, "system_check": {"x": 1},
                           "prototype_execution": {"x": 1}, "monitoring": {"x": 1}},
        "evaluation": {"formative": {"x": 1}, "summative": {"x": 1}, "improvement_plan": {"x": 1}},
    }
    errors = validate_addie(addie)
    assert any(e.startswith("development.instructor_guide") for e in errors)
    assert any(e.startswith("development.operator_manual") for e in errors)


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


def test_validate_section_flags_schema_placeholder_left_in_required_field():
    # Measured 2026-08-28 (Qwen3.5-2B single run): an operator_manual shipped
    # "<detailed system setup guide>" verbatim from the prompt schema. The
    # value is non-empty, so the plain emptiness check passed it, the regen
    # loop never fired, and the judge scored the field as absent.
    payload = {
        "instructor_orientation": {"schedule": "Day 1"},
        "system_check": {"checklist": ["net"]},
        "prototype_execution": {"pilot_scope": "one cohort"},
        "monitoring": {"monitoring_criteria": ["completion"]},
        "instructor_guide": {
            "overview": "Real overview",
            "session_guides": [{"session": 1, "objectives": ["<obj>"], "activities": ["Do the lab"]}],
        },
        "operator_manual": {"system_setup": "<detailed system setup guide>"},
    }
    errors = validate_section("implementation_plan", payload)
    assert any("operator_manual.system_setup" in e and "placeholder" in e for e in errors)
    assert any("instructor_guide" in e and "placeholder" in e for e in errors)


def test_placeholder_check_ignores_real_content_with_angle_brackets():
    # Markup and comparisons are not placeholders: only a leaf string that IS
    # a single bare <token> counts.
    payload = {
        "instructor_orientation": {"schedule": "Day 1"},
        "system_check": {"checklist": ["check that a < b holds", "<p>markup-ish</p> content"]},
        "prototype_execution": {"pilot_scope": "one cohort"},
        "monitoring": {"monitoring_criteria": ["completion"]},
        "instructor_guide": {"overview": "Real overview"},
        "operator_manual": {"system_setup": "Install Python 3.11, then configure the LMS."},
    }
    errors = validate_section("implementation_plan", payload)
    assert not any("placeholder" in e for e in errors)


def test_placeholder_in_required_field_triggers_empty_section_regen_check():
    from alignmentgraph_isd.core.outputs import _empty_required_fields

    payload = {
        "instructor_orientation": {"schedule": "Day 1"},
        "system_check": {"checklist": ["net"]},
        "prototype_execution": {"pilot_scope": "one cohort"},
        "monitoring": {"monitoring_criteria": ["completion"]},
        "instructor_guide": {"overview": "Real overview"},
        "operator_manual": {"system_setup": "<detailed system setup guide>"},
    }
    assert _empty_required_fields("implementation_plan", payload)


def test_validate_addie_flags_placeholder_in_development_manuals():
    addie = {
        "analysis": {"needs_analysis": {"x": 1}, "learner_analysis": {"x": 1},
                     "context_analysis": {"x": 1}, "task_analysis": {"x": 1}},
        "design": {"learning_objectives": [{"id": "ILO-01"}], "instructional_strategies": {"x": 1}},
        "development": {"learner_materials": [{"id": "MAT-01", "content": "Real content"}],
                        "assessment_tools": [{"item_id": "AT-01"}],
                        "instructor_guide": {"overview": "Real"},
                        "operator_manual": {"system_setup": "<detailed system setup guide>"}},
        "implementation": {"instructor_orientation": {"x": 1}, "system_check": {"x": 1},
                           "prototype_execution": {"x": 1}, "monitoring": {"x": 1}},
        "evaluation": {"formative": {"x": 1}, "summative": {"x": 1}, "improvement_plan": {"x": 1}},
    }
    errors = validate_addie(addie)
    assert any("operator_manual" in e and "placeholder" in e for e in errors)
