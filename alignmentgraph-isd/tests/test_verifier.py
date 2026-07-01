"""P0.3: the pedagogical verifier covers the checks claimed in the docs."""
from __future__ import annotations

from alignmentgraph_isd import DesignBrief, HarnessRunConfig
from alignmentgraph_isd.agents.pedagogical_verifier import PedagogicalVerifierAgent
from alignmentgraph_isd.graph import AlignmentGraph
from alignmentgraph_isd.trajectory import TrajectoryLogger


def _verifier(graph: AlignmentGraph) -> PedagogicalVerifierAgent:
    config = HarnessRunConfig.from_ablation("full")
    return PedagogicalVerifierAgent(config, graph, TrajectoryLogger())


def _objective_node(graph: AlignmentGraph) -> None:
    graph.add_node("objective", "objective_0", {
        "learning_objectives": [
            {"id": "LO-01", "level": "Apply", "statement": "Apply X", "bloom_verb": "apply"},
        ],
        "instructional_strategies": {"model": "Gagné"},
    })


def test_verifier_flags_missing_assessment_coverage():
    graph = AlignmentGraph()
    _objective_node(graph)
    violations = _verifier(graph).verify()
    assert any(v.violation_type == "coverage" for v in violations)


def test_verifier_reports_at_least_five_check_types():
    """A deliberately broken graph should surface a broad spread of violation types."""
    graph = AlignmentGraph()
    graph.add_node("objective", "objective_0", {
        "learning_objectives": [{"id": "LO-01", "level": "Apply", "statement": "do x", "bloom_verb": "frobnicate"}],
        "instructional_strategies": {},
        "content_structure": {"modules": ["m"] * 12},
    })
    graph.add_node("assessment", "assessment_0", {
        "assessment_tools": [
            {"item_id": "AT-01", "type": "performance_task", "scoring_criteria": "good"},  # vague + no aligned_objective
        ],
    })
    graph.add_node("activity", "activity_0", {"learner_materials": []})
    graph.add_node("implementation_plan", "implementation_plan_0", {
        "instructor_orientation": {}, "system_check": {}, "prototype_execution": {}, "monitoring": {},
    })
    brief = DesignBrief.model_validate({"duration": "2 hours", "context": {"duration": "2 hours"}})

    types = {v.violation_type for v in _verifier(graph).verify(brief)}
    expected = {"coverage", "bloom", "activity_support", "rubric_consistency", "feasibility"}
    assert expected.issubset(types), f"missing: {expected - types}"


def test_verifier_clean_graph_has_no_coverage_or_rubric_errors():
    graph = AlignmentGraph()
    _objective_node(graph)
    graph.add_node("assessment", "assessment_0", {
        "assessment_tools": [
            {"item_id": "AT-01", "type": "performance_task", "aligned_objective": "LO-01",
             "scoring_criteria": "Rubric scores accuracy and completeness on a 0-4 scale."},
        ],
    })
    graph.add_edge("measures", "assessment_0", "objective_0", evidence="LO-01")
    graph.add_edge("evaluates", "evaluation_0", "objective_0", evidence="LO-01")
    errors = [v for v in _verifier(graph).verify() if v.severity == "error"]
    assert not errors, [e.message for e in errors]
