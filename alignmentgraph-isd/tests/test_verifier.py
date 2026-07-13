"""P0.3: the pedagogical verifier covers the checks claimed in the docs."""
from __future__ import annotations

from alignmentgraph_isd import DesignBrief, HarnessRunConfig
from alignmentgraph_isd.core.agents.pedagogical_verifier import PedagogicalVerifierAgent
from alignmentgraph_isd.core.graph import AlignmentGraph
from alignmentgraph_isd.core.trajectory import TrajectoryLogger


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


# ── Content-level checks ──────────────────────────────────────────────────────

def _types(graph: AlignmentGraph) -> set[str]:
    return {v.violation_type for v in _verifier(graph).verify()}


def test_measurability_fires_only_on_vague_verb_without_criterion():
    graph = AlignmentGraph()
    graph.add_node("objective", "objective_0", {
        "learning_objectives": [
            {"id": "LO-01", "level": "Understand", "statement": "Understand dependency injection.", "bloom_verb": "understand"},
        ],
    })
    assert "measurability" in _types(graph)


def test_measurability_silent_for_observable_verb():
    # A well-formed objective with an observable Bloom verb is measurable enough
    # even without a numeric degree — must NOT over-fire.
    graph = AlignmentGraph()
    graph.add_node("objective", "objective_0", {
        "learning_objectives": [
            {"id": "LO-01", "level": "Apply", "statement": "Apply dependency injection.", "bloom_verb": "apply"},
        ],
    })
    assert "measurability" not in _types(graph)


def test_measurability_passes_vague_verb_with_degree():
    graph = AlignmentGraph()
    graph.add_node("objective", "objective_0", {
        "learning_objectives": [
            {"id": "LO-01", "level": "Understand",
             "statement": "Understand dependency injection with at least 80% of unit tests passing.",
             "bloom_verb": "understand"},
        ],
    })
    assert "measurability" not in _types(graph)


def test_bloom_verb_level_consistency():
    graph = AlignmentGraph()
    graph.add_node("objective", "objective_0", {
        "learning_objectives": [
            {"id": "LO-01", "level": "Apply", "statement": "Given a spec, list three items.", "bloom_verb": "list"},
        ],
    })
    violations = [v for v in _verifier(graph).verify() if v.violation_type == "bloom"]
    assert violations and "different Bloom level" in violations[0].message


def test_bloom_mismatch_fires_for_recognition_only_coverage():
    graph = AlignmentGraph()
    graph.add_node("objective", "objective_0", {
        "learning_objectives": [
            {"id": "LO-01", "level": "Analyze",
             "statement": "Given a codebase, analyze coupling with at least three findings.",
             "bloom_verb": "analyze"},
        ],
    })
    graph.add_node("assessment", "assessment_0", {
        "assessment_tools": [
            {"item_id": "AT-01", "type": "multiple_choice", "question": "Pick the coupled pair.",
             "aligned_objective": "LO-01", "scoring_criteria": "Answer key: option B."},
        ],
    })
    assert "bloom_mismatch" in _types(graph)


def test_bloom_mismatch_silent_with_performance_item():
    graph = AlignmentGraph()
    graph.add_node("objective", "objective_0", {
        "learning_objectives": [
            {"id": "LO-01", "level": "Analyze",
             "statement": "Given a codebase, analyze coupling with at least three findings.",
             "bloom_verb": "analyze"},
        ],
    })
    graph.add_node("assessment", "assessment_0", {
        "assessment_tools": [
            {"item_id": "AT-01", "type": "multiple_choice", "question": "Pick the coupled pair.",
             "aligned_objective": "LO-01", "scoring_criteria": "Answer key: option B."},
            {"item_id": "AT-02", "type": "performance_task", "question": "Refactor the module.",
             "aligned_objective": "LO-01",
             "scoring_criteria": "Rubric scores coupling reduction and test pass rate on a 0-4 scale."},
        ],
    })
    assert "bloom_mismatch" not in _types(graph)


def test_rubric_consistency_flags_dangling_objective_reference():
    graph = AlignmentGraph()
    _objective_node(graph)
    graph.add_node("assessment", "assessment_0", {
        "assessment_tools": [
            {"item_id": "AT-01", "type": "short_answer", "question": "Explain LO-01.",
             "aligned_objective": "LO-99", "scoring_criteria": "Scored against a 3-point key."},
        ],
    })
    dangling = [
        v for v in _verifier(graph).verify()
        if v.violation_type == "rubric_consistency" and v.metadata.get("dangling")
    ]
    assert dangling and dangling[0].severity == "error"


def test_activity_engagement_fires_for_passive_only_practice():
    graph = AlignmentGraph()
    graph.add_node("objective", "objective_0", {
        "learning_objectives": [
            {"id": "LO-01", "level": "Apply",
             "statement": "Given a task, apply X with at least 80% accuracy.", "bloom_verb": "apply"},
        ],
        "learning_activities": [
            {"activity_name": "X lecture", "duration": "60m",
             "description": "Instructor presentation on X concepts.",
             "materials": [], "aligned_objectives": ["LO-01"]},
        ],
    })
    assert "activity_engagement" in _types(graph)


def test_activity_engagement_silent_with_active_practice():
    graph = AlignmentGraph()
    graph.add_node("objective", "objective_0", {
        "learning_objectives": [
            {"id": "LO-01", "level": "Apply",
             "statement": "Given a task, apply X with at least 80% accuracy.", "bloom_verb": "apply"},
        ],
        "learning_activities": [
            {"activity_name": "X practice lab", "duration": "60m",
             "description": "Learners solve a realistic task hands-on.",
             "materials": [], "aligned_objectives": ["LO-01"]},
        ],
    })
    assert "activity_engagement" not in _types(graph)


def test_evaluation_quality_fires_for_empty_formative_methods():
    graph = AlignmentGraph()
    graph.add_node("evaluation", "evaluation_0", {
        "formative": {"data_collection": {"methods": []}},
        "summative": {},
    })
    assert "evaluation_quality" in _types(graph)


# ── Verify → repair convergence without an LLM (deterministic fallbacks) ─────

def test_content_violations_repair_to_convergence_without_llm():
    from alignmentgraph_isd.core.agents.assessment_design import AssessmentDesignAgent
    from alignmentgraph_isd.core.agents.objective_design import ObjectiveDesignAgent

    graph = AlignmentGraph()
    graph.add_node("objective", "objective_0", {
        "learning_objectives": [
            {"id": "LO-01", "level": "Apply", "statement": "Apply dependency injection.", "bloom_verb": "apply"},
        ],
        "learning_activities": [
            {"activity_name": "DI lecture", "duration": "60m",
             "description": "Instructor presentation on DI concepts.",
             "materials": [], "aligned_objectives": ["LO-01"]},
        ],
    })
    graph.add_node("assessment", "assessment_0", {
        "assessment_tools": [
            {"item_id": "AT-01", "type": "multiple_choice", "question": "Which is DI?",
             "aligned_objective": "LO-01", "scoring_criteria": "Answer key: option B."},
            {"item_id": "AT-02", "type": "performance_task", "question": "Refactor to DI.",
             "aligned_objective": "LO-99", "scoring_criteria": "good"},
        ],
    })

    config = HarnessRunConfig.from_ablation("full")  # no llm_factory → deterministic fallback
    trajectory = TrajectoryLogger()
    before = PedagogicalVerifierAgent(config, graph, trajectory).verify()
    before_types = {v.violation_type for v in before}
    # measurability is audit-only (not repaired); the repairable content findings:
    content_types = {"activity_engagement", "rubric_consistency", "bloom_mismatch"}
    assert content_types <= before_types, f"expected all content findings, got {before_types}"

    ObjectiveDesignAgent(config, graph, trajectory).repair(
        [v for v in before if v.violation_type in ("bloom", "activity_engagement")]
    )
    AssessmentDesignAgent(config, graph, trajectory).repair(
        [v for v in before if v.violation_type in ("rubric_consistency", "bloom_mismatch")]
    )

    after_types = {v.violation_type for v in PedagogicalVerifierAgent(config, graph, trajectory).verify()}
    assert not (content_types & after_types), f"unresolved content findings: {content_types & after_types}"


def test_evaluation_quality_repairs_to_convergence_without_llm():
    from alignmentgraph_isd.core.agents.evaluation_revision import EvaluationRevisionAgent

    graph = AlignmentGraph()
    graph.add_node("evaluation", "evaluation_0", {
        "formative": {"data_collection": {"methods": []}},
        "summative": {},
    })
    config = HarnessRunConfig.from_ablation("full")
    trajectory = TrajectoryLogger()
    before = [
        v for v in PedagogicalVerifierAgent(config, graph, trajectory).verify()
        if v.violation_type == "evaluation_quality"
    ]
    assert before
    EvaluationRevisionAgent(config, graph, trajectory).repair(before)
    after = {v.violation_type for v in PedagogicalVerifierAgent(config, graph, trajectory).verify()}
    assert "evaluation_quality" not in after
