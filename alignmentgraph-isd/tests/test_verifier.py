"""The pedagogical verifier's two tiers: completeness (single-artifact content
quality) and alignment (relation coverage + the Bloom/format validity rule).
Graphs here always populate ELEMENT nodes alongside section nodes — the
alignment tier reads element nodes/edges, not the raw section blob, mirroring
how the real specialists build the graph."""
from __future__ import annotations

from alignmentgraph_isd import DesignBrief, HarnessRunConfig
from alignmentgraph_isd.core import alignment
from alignmentgraph_isd.core.agents.pedagogical_verifier import PedagogicalVerifierAgent
from alignmentgraph_isd.core.graph import AlignmentGraph, NodeType
from alignmentgraph_isd.core.trajectory import TrajectoryLogger


def _verifier(graph: AlignmentGraph) -> PedagogicalVerifierAgent:
    return PedagogicalVerifierAgent(HarnessRunConfig(), graph, TrajectoryLogger())


def _types(graph: AlignmentGraph) -> set[str]:
    return {v.violation_type for v in _verifier(graph).verify()}


def _objective(graph: AlignmentGraph, lo: dict) -> None:
    graph.add_node(NodeType.OBJECTIVE, "objective_0", {"learning_objectives": [lo]})
    graph.add_element_node(NodeType.OBJECTIVE, lo["id"], dict(lo))


def _assessment(graph: AlignmentGraph, items: list[dict]) -> None:
    graph.add_node(NodeType.ASSESSMENT, "assessment_0", {"assessment_tools": items})
    for item in items:
        graph.add_element_node("assessment", item["item_id"], dict(item))


# ── alignment tier: relation coverage (R3..R13) ──────────────────────────────

def test_r3_fires_for_uncovered_objective():
    graph = AlignmentGraph()
    _objective(graph, {"id": "LO-01", "level": "Apply", "statement": "Apply X", "bloom_verb": "apply"})
    assert "R3" in _types(graph)


def test_r3_silent_once_established():
    graph = AlignmentGraph()
    _objective(graph, {"id": "LO-01", "level": "Apply", "statement": "Apply X", "bloom_verb": "apply"})
    _assessment(graph, [{
        "item_id": "AT-01", "type": "performance_task", "aligned_objective": "LO-01",
        "scoring_criteria": "Rubric scores accuracy and completeness on a 0-4 scale.",
    }])
    assert "R3" not in _types(graph)


def test_verifier_reports_a_broad_spread_of_completeness_and_alignment_types():
    """A deliberately broken graph should surface a broad spread of violation types."""
    graph = AlignmentGraph()
    _objective(graph, {"id": "LO-01", "level": "Apply", "statement": "do x", "bloom_verb": "frobnicate"})
    graph.add_node("content_structure", "content_structure_0", {"modules": ["m"] * 12})
    _assessment(graph, [
        {"item_id": "AT-01", "type": "performance_task", "scoring_criteria": "good"},  # vague + no aligned_objective
    ])
    graph.add_node(NodeType.ACTIVITY, "activity_0", {"learner_materials": []})
    graph.add_node(NodeType.IMPLEMENTATION_PLAN, "implementation_plan_0", {
        "instructor_orientation": {}, "system_check": {}, "prototype_execution": {}, "monitoring": {},
    })
    brief = DesignBrief.model_validate({"duration": "2 hours", "context": {"duration": "2 hours"}})

    types = {v.violation_type for v in _verifier(graph).verify(brief)}
    expected = {"R3", "R4", "bloom", "rubric_consistency", "feasibility"}
    assert expected.issubset(types), f"missing: {expected - types}"


def test_r4_supports_established_via_declared_aligned_objectives():
    graph = AlignmentGraph()
    _objective(graph, {"id": "LO-01", "level": "Apply", "statement": "Apply X", "bloom_verb": "apply"})
    graph.add_node(NodeType.ACTIVITY, "activity_0", {"learning_activities": [
        {"id": "ACT-01", "activity_name": "Lab", "aligned_objectives": ["LO-01"]},
    ]})
    graph.add_element_node("activity", "ACT-01", {"id": "ACT-01", "aligned_objectives": ["LO-01"]})
    assert "R4" not in _types(graph)
    cov, uncovered = alignment.relation_coverage(graph, "R4")
    assert cov == 1.0 and not uncovered


# ── completeness tier: single-artifact content quality (always on) ──────────

def test_measurability_fires_only_on_vague_verb_without_criterion():
    graph = AlignmentGraph()
    _objective(graph, {"id": "LO-01", "level": "Understand", "statement": "Understand dependency injection.", "bloom_verb": "understand"})
    assert "measurability" in _types(graph)


def test_measurability_silent_for_observable_verb():
    # A well-formed objective with an observable Bloom verb is measurable enough
    # even without a numeric degree — must NOT over-fire.
    graph = AlignmentGraph()
    _objective(graph, {"id": "LO-01", "level": "Apply", "statement": "Apply dependency injection.", "bloom_verb": "apply"})
    assert "measurability" not in _types(graph)


def test_measurability_passes_vague_verb_with_degree():
    graph = AlignmentGraph()
    _objective(graph, {
        "id": "LO-01", "level": "Understand",
        "statement": "Understand dependency injection with at least 80% of unit tests passing.",
        "bloom_verb": "understand",
    })
    assert "measurability" not in _types(graph)


def test_bloom_verb_level_consistency():
    graph = AlignmentGraph()
    _objective(graph, {"id": "LO-01", "level": "Apply", "statement": "Given a spec, list three items.", "bloom_verb": "list"})
    violations = [v for v in _verifier(graph).verify() if v.violation_type == "bloom"]
    assert violations and "different Bloom level" in violations[0].message


def test_rubric_consistency_flags_missing_criteria():
    graph = AlignmentGraph()
    _objective(graph, {"id": "LO-01", "level": "Apply", "statement": "Apply X", "bloom_verb": "apply"})
    _assessment(graph, [
        {"item_id": "AT-01", "type": "short_answer", "question": "Explain LO-01.", "aligned_objective": "LO-01"},
    ])
    violations = [v for v in _verifier(graph).verify() if v.violation_type == "rubric_consistency"]
    assert violations and "no scoring criteria" in violations[0].message


def test_evaluation_quality_fires_for_empty_formative_methods():
    graph = AlignmentGraph()
    graph.add_node(NodeType.EVALUATION, "evaluation_0", {
        "formative": {"data_collection": {"methods": []}},
        "summative": {},
    })
    assert "evaluation_quality" in _types(graph)


# ── alignment tier: the Bloom/format validity rule (bloom_mismatch) ─────────

def test_bloom_mismatch_fires_for_recognition_only_coverage():
    graph = AlignmentGraph()
    _objective(graph, {
        "id": "LO-01", "level": "Analyze",
        "statement": "Given a codebase, analyze coupling with at least three findings.",
        "bloom_verb": "analyze",
    })
    _assessment(graph, [
        {"item_id": "AT-01", "type": "multiple_choice", "question": "Pick the coupled pair.",
         "aligned_objective": "LO-01", "scoring_criteria": "Answer key: option B."},
    ])
    assert "bloom_mismatch" in _types(graph)


def test_bloom_mismatch_silent_with_performance_item():
    graph = AlignmentGraph()
    _objective(graph, {
        "id": "LO-01", "level": "Analyze",
        "statement": "Given a codebase, analyze coupling with at least three findings.",
        "bloom_verb": "analyze",
    })
    _assessment(graph, [
        {"item_id": "AT-01", "type": "multiple_choice", "question": "Pick the coupled pair.",
         "aligned_objective": "LO-01", "scoring_criteria": "Answer key: option B."},
        {"item_id": "AT-02", "type": "performance_task", "question": "Refactor the module.",
         "aligned_objective": "LO-01",
         "scoring_criteria": "Rubric scores coupling reduction and test pass rate on a 0-4 scale."},
    ])
    assert "bloom_mismatch" not in _types(graph)


# ── activity_engagement (completeness tier, owned by ActivityMaterialAgent) ──

def test_activity_engagement_fires_for_passive_only_practice():
    graph = AlignmentGraph()
    _objective(graph, {
        "id": "LO-01", "level": "Apply",
        "statement": "Given a task, apply X with at least 80% accuracy.", "bloom_verb": "apply",
    })
    graph.add_node(NodeType.ACTIVITY, "activity_0", {"learning_activities": [
        {"id": "ACT-01", "activity_name": "X lecture", "duration": "60m",
         "description": "Instructor presentation on X concepts.",
         "materials": [], "aligned_objectives": ["LO-01"]},
    ]})
    assert "activity_engagement" in _types(graph)


def test_activity_engagement_silent_with_active_practice():
    graph = AlignmentGraph()
    _objective(graph, {
        "id": "LO-01", "level": "Apply",
        "statement": "Given a task, apply X with at least 80% accuracy.", "bloom_verb": "apply",
    })
    graph.add_node(NodeType.ACTIVITY, "activity_0", {"learning_activities": [
        {"id": "ACT-01", "activity_name": "X practice lab", "duration": "60m",
         "description": "Learners solve a realistic task hands-on.",
         "materials": [], "aligned_objectives": ["LO-01"]},
    ]})
    assert "activity_engagement" not in _types(graph)


# ── Verify → repair convergence without an LLM (deterministic fallbacks) ─────

def test_content_violations_repair_to_convergence_without_llm():
    from alignmentgraph_isd.core.agents.assessment_design import AssessmentDesignAgent
    from alignmentgraph_isd.core.agents.activity_material import ActivityMaterialAgent
    from alignmentgraph_isd.core.agents.objective_design import ObjectiveDesignAgent

    graph = AlignmentGraph()
    graph.add_node(NodeType.OBJECTIVE, "objective_0", {"learning_objectives": [
        {"id": "LO-01", "level": "Apply", "statement": "Apply dependency injection.", "bloom_verb": "apply"},
        {"id": "LO-02", "level": "Analyze", "statement": "Analyze coupling.", "bloom_verb": "analyze"},
    ]})
    graph.add_element_node(NodeType.OBJECTIVE, "LO-01", {"id": "LO-01", "level": "Apply", "bloom_verb": "apply"})
    graph.add_element_node(NodeType.OBJECTIVE, "LO-02", {"id": "LO-02", "level": "Analyze", "bloom_verb": "analyze"})
    graph.add_node(NodeType.ACTIVITY, "activity_0", {"learning_activities": [
        {"id": "ACT-01", "activity_name": "DI lecture", "duration": "60m",
         "description": "Instructor presentation on DI concepts.",
         "materials": [], "aligned_objectives": ["LO-01"]},
    ]})
    _assessment(graph, [
        # LO-01: vague criteria on a performance item -> rubric_consistency.
        {"item_id": "AT-01", "type": "performance_task", "question": "Refactor to DI.",
         "aligned_objective": "LO-01", "scoring_criteria": "good"},
        # LO-02: recognition-only coverage -> bloom_mismatch.
        {"item_id": "AT-02", "type": "multiple_choice", "question": "Pick the coupled pair.",
         "aligned_objective": "LO-02", "scoring_criteria": "Answer key: option B."},
    ])

    config = HarnessRunConfig()  # no llm_factory → deterministic fallback
    trajectory = TrajectoryLogger()
    before = PedagogicalVerifierAgent(config, graph, trajectory).verify()
    before_types = {v.violation_type for v in before}
    # measurability is audit-only (not repaired); the repairable content findings:
    content_types = {"activity_engagement", "rubric_consistency", "bloom_mismatch"}
    assert content_types <= before_types, f"expected all content findings, got {before_types}"

    ObjectiveDesignAgent(config, graph, trajectory).repair(
        [v for v in before if v.violation_type == "bloom"]
    )
    ActivityMaterialAgent(config, graph, trajectory).repair(
        [v for v in before if v.violation_type == "activity_engagement"]
    )
    AssessmentDesignAgent(config, graph, trajectory).repair(
        [v for v in before if v.violation_type in ("rubric_consistency", "bloom_mismatch")]
    )

    after_types = {v.violation_type for v in PedagogicalVerifierAgent(config, graph, trajectory).verify()}
    assert not (content_types & after_types), f"unresolved content findings: {content_types & after_types}"


def test_evaluation_quality_repairs_to_convergence_without_llm():
    from alignmentgraph_isd.core.agents.evaluation_revision import EvaluationRevisionAgent

    graph = AlignmentGraph()
    graph.add_node(NodeType.EVALUATION, "evaluation_0", {
        "formative": {"data_collection": {"methods": []}},
        "summative": {},
    })
    config = HarnessRunConfig()
    trajectory = TrajectoryLogger()
    before = [
        v for v in PedagogicalVerifierAgent(config, graph, trajectory).verify()
        if v.violation_type == "evaluation_quality"
    ]
    assert before
    EvaluationRevisionAgent(config, graph, trajectory).repair(before)
    after = {v.violation_type for v in PedagogicalVerifierAgent(config, graph, trajectory).verify()}
    assert "evaluation_quality" not in after
