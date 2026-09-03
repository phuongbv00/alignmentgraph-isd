"""Self-validation checks (``core/checks.py``), extracted from the retired
``PedagogicalVerifierAgent`` into free functions each Designer calls inline.
Graphs here always populate ELEMENT nodes (one per artifact), mirroring how
the real Designers build the graph — not the old single section-node blob.

``test_alignment.py`` already covers the establishers/coverage primitives in
``core/alignment_graph/alignment.py`` (the establishers, ``relation_coverage``, the Bloom
cross-checks) in depth; this file covers the checks layered on top in
``core/checks.py`` (measurability, rubric_consistency, evaluation_quality,
activity_engagement, orphan_content, evidence_alignment, feasibility,
actionability) plus repair-to-convergence without an LLM for a
representative check per Designer."""
from __future__ import annotations

from conftest import RepairActor

from alignmentgraph_isd.core import repairs

from alignmentgraph_isd import HarnessRunConfig
from alignmentgraph_isd.core import checks
from alignmentgraph_isd.core.alignment_graph import alignment
from alignmentgraph_isd.core.alignment_graph import AlignmentGraph, NodeType
from alignmentgraph_isd.core.brief import DesignBrief
from alignmentgraph_isd.core.trajectory import TrajectoryLogger


def _types(violations) -> set[str]:
    return {v.violation_type for v in violations}


# ── Outcome Designer's own checks: bloom_verbs, measurability ────────────────

def test_bloom_verbs_fires_for_non_standard_verb():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {
        "id": "ILO-01", "statement": "Frobnicate the widget.", "bloom_verb": "frobnicate",
        "level": "apply",
    })
    assert "bloom" in _types(checks.bloom_verbs(graph))


def test_bloom_verbs_fires_for_level_mismatch():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {
        "id": "ILO-01", "statement": "Given a spec, list three items.", "bloom_verb": "list",
        "level": "apply",
    })
    violations = [v for v in checks.bloom_verbs(graph) if v.violation_type == "bloom"]
    assert violations and "different Bloom level" in violations[0].message


def test_bloom_verbs_silent_for_consistent_verb_and_level():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {
        "id": "ILO-01", "statement": "Apply dependency injection.", "bloom_verb": "apply",
        "level": "apply",
    })
    assert checks.bloom_verbs(graph) == []


def test_measurability_fires_only_on_vague_verb_without_criterion():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {
        "id": "ILO-01", "statement": "Understand dependency injection.", "bloom_verb": "understand",
    })
    assert "measurability" in _types(checks.measurability(graph))


def test_measurability_silent_for_observable_verb():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {
        "id": "ILO-01", "statement": "Apply dependency injection.", "bloom_verb": "apply",
    })
    assert checks.measurability(graph) == []


def test_measurability_passes_vague_verb_with_stated_degree():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {
        "id": "ILO-01", "bloom_verb": "understand",
        "statement": "Understand dependency injection with at least 80% of unit tests passing.",
    })
    assert checks.measurability(graph) == []


# ── Assessment Designer's own check: evaluation_quality ──────────────────────

def test_evaluation_quality_fires_for_empty_formative_methods():
    graph = AlignmentGraph()
    graph.add_node(NodeType.ASSESSMENT_PLAN, "assessment_plan_0", {
        "formative": ["Weekly critique"], "formative_methods": [],
    })
    assert "evaluation_quality" in _types(checks.evaluation_quality(graph))


def test_evaluation_quality_silent_when_methods_and_pilot_data_declared():
    # Since the pilot-data extension (2026-08-26), a quiet plan needs concrete
    # formative methods AND a pilot_data_plan with collection points and >=2
    # anticipated difficulties — the fields the aggregator builds
    # evaluation.formative from. See tests/test_pilot_data_repair.py for the
    # flagging/repair cases.
    graph = AlignmentGraph()
    graph.add_node(NodeType.ASSESSMENT_PLAN, "assessment_plan_0", {
        "formative": ["Weekly critique"], "formative_methods": ["Exit tickets"],
        "pilot_data_plan": {
            "collection_points": ["After module 1"],
            "anticipated_difficulties": [
                {"area": "ILO-01", "rationale": "Hard concept.", "detected_by": "Exit tickets",
                 "first_revision": "Add a worked example."},
                {"area": "MOD-01", "rationale": "Dense module.", "detected_by": "Exit tickets",
                 "first_revision": "Split the module."},
            ],
        },
    })
    assert checks.evaluation_quality(graph) == []


def test_evaluation_quality_silent_when_no_formative_intent():
    graph = AlignmentGraph()
    graph.add_node(NodeType.ASSESSMENT_PLAN, "assessment_plan_0", {"formative": [], "formative_methods": []})
    assert checks.evaluation_quality(graph) == []


# ── Activity Designer's own check: activity_engagement (uses C3 edges) ───────

def test_activity_engagement_fires_for_passive_only_practice():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {"id": "ILO-01", "level": "apply"})
    graph.add_element_node(NodeType.ACTIVITY, "TLA-01", {
        "id": "TLA-01", "activity_name": "X lecture", "description": "Instructor presentation on X concepts.",
    })
    graph.add_edge("practiced_by", "objective:ILO-01", "activity:TLA-01", relation_id="C3", established_by="id")
    violations = [v for v in checks.activity_engagement(graph) if v.violation_type == "activity_engagement"]
    assert violations and "ILO-01" in violations[0].message


def test_activity_engagement_silent_with_active_practice():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {"id": "ILO-01", "level": "apply"})
    graph.add_element_node(NodeType.ACTIVITY, "TLA-01", {
        "id": "TLA-01", "activity_name": "X practice lab", "description": "Learners solve a realistic task hands-on.",
    })
    graph.add_edge("practiced_by", "objective:ILO-01", "activity:TLA-01", relation_id="C3", established_by="id")
    assert checks.activity_engagement(graph) == []


def test_activity_engagement_silent_when_no_practice_linked():
    """Missing linkage entirely is C3 coverage's concern, not this check's."""
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {"id": "ILO-01", "level": "apply"})
    assert checks.activity_engagement(graph) == []


# ── Content Designer's own check: orphan_content (C5/P5 coverage) ───────────

def test_orphan_content_fires_for_module_with_no_activity():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.CONTENT, "MOD-01", {"id": "MOD-01"})
    violations = [v for v in checks.orphan_content(graph) if v.violation_type == "orphan_content"]
    assert any("content:MOD-01" in v.node_id for v in violations)


def test_orphan_content_silent_when_module_supports_an_activity():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.ACTIVITY, "TLA-01", {"id": "TLA-01"})
    graph.add_element_node(NodeType.CONTENT, "MOD-01", {"id": "MOD-01"})
    alignment.record_provenance(graph, "C5", ["content:MOD-01"], "activity:TLA-01")
    node_ids = {v.node_id for v in checks.orphan_content(graph)}
    assert "content:MOD-01" not in node_ids


def test_orphan_content_fires_for_material_with_no_module():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.MATERIAL, "MAT-01", {"id": "MAT-01"})
    violations = [v for v in checks.orphan_content(graph) if v.violation_type == "orphan_content"]
    assert any("material:MAT-01" in v.node_id for v in violations)


# ── Rubric Designer's own checks: rubric_consistency, evidence_alignment ────

def test_rubric_consistency_fires_for_vague_description():
    """A criterion is a FIELD of the item it marks (2026-09-02), so the check
    reads it off the item — the same way the prose arm always has, which is
    what lets both substrates run the identical implementation."""
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.ASSESSMENT, "AT-01", {
        "item_id": "AT-01", "type": "short_answer",
        "rubric": [{"id": "RC-01", "description": "good"}]})
    violations = [v for v in checks.rubric_consistency(graph)
                  if v.violation_type == "rubric_consistency"]
    assert violations and violations[0].metadata["rc_id"] == "RC-01"


def test_rubric_consistency_silent_for_observable_description():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.ASSESSMENT, "AT-01", {
        "item_id": "AT-01", "type": "short_answer",
        "rubric": [{"id": "RC-01", "description":
                    "Scored 0-3: cites at least two pieces of observable evidence "
                    "and states the trade-off each one implies."}]})
    assert not [v for v in checks.rubric_consistency(graph)
                if v.violation_type == "rubric_consistency"]


def test_evidence_alignment_fires_when_item_cannot_produce_required_evidence():
    """The item is the criterion's PARENT now, not the far end of a C6 edge, so
    the lookup is direct and the "no linked item" case cannot occur."""
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.ASSESSMENT, "AT-01", {
        "item_id": "AT-01", "type": "multiple_choice",
        "rubric": [{"id": "RC-01", "evidence_type": "performance_task"}]})
    violations = [v for v in checks.evidence_alignment(graph)
                  if v.violation_type == "evidence_alignment"]
    assert violations and violations[0].metadata["rc_id"] == "RC-01"


def test_evidence_alignment_silent_when_item_can_produce_evidence():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.ASSESSMENT, "AT-01", {
        "item_id": "AT-01", "type": "performance_task",
        "rubric": [{"id": "RC-01", "evidence_type": "short_answer"}]})
    assert not [v for v in checks.evidence_alignment(graph)
                if v.violation_type == "evidence_alignment"]


# ── ImplementationPlannerAgent's own checks: feasibility, actionability ─────

def test_feasibility_fires_for_overloaded_schedule():
    graph = AlignmentGraph()
    for i in range(10):
        graph.add_element_node(NodeType.ACTIVITY, f"TLA-{i:02d}", {"id": f"TLA-{i:02d}"})
    brief = DesignBrief.model_validate({"duration": "2 hours", "context": {"duration": "2 hours"}})
    assert "feasibility" in _types(checks.feasibility(graph, brief))


def test_feasibility_silent_without_a_design_brief():
    graph = AlignmentGraph()
    assert checks.feasibility(graph, None) == []


def test_actionability_fires_for_vague_instructor_orientation():
    graph = AlignmentGraph()
    graph.add_node(NodeType.IMPLEMENTATION_PLAN, "implementation_plan_0", {
        "instructor_orientation": {}, "system_check": {},
    })
    assert "actionability" in _types(checks.actionability(graph))


def test_actionability_silent_with_concrete_orientation_and_checklist():
    graph = AlignmentGraph()
    graph.add_node(NodeType.IMPLEMENTATION_PLAN, "implementation_plan_0", {
        "instructor_orientation": {"competency_checklist": ["Launch the lab"], "materials": ["Runbook"]},
        "system_check": {"checklist": ["Verify lab machines"]},
    })
    assert checks.actionability(graph) == []


# ── relation_coverage(): re-runs rerunnable establishers + full 16-relation check ──

def test_relation_coverage_flags_uncovered_core_relation():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {"id": "ILO-01"})
    assert "C2" in _types(checks.relation_coverage(graph))


def test_relation_coverage_silent_once_established():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {"id": "ILO-01"})
    graph.add_element_node(NodeType.ASSESSMENT, "AT-01", {"item_id": "AT-01", "aligned_objective": "ILO-01"})
    assert "C2" not in _types(checks.relation_coverage(graph))


def test_relation_coverage_reports_dangling_reference_from_rerunnable_establisher():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.ASSESSMENT, "AT-01", {"item_id": "AT-01", "aligned_objective": "ILO-99"})
    assert "C2" in _types(checks.relation_coverage(graph))


# ── bloom_mismatches(): the two Bloom cross-checks, tagged per artifact type ──

def test_bloom_mismatches_tags_assessment_and_activity_separately():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {"id": "ILO-01", "level": "analyze"})
    graph.add_element_node(NodeType.ASSESSMENT, "AT-01", {"item_id": "AT-01", "type": "multiple_choice"})
    graph.add_edge("assessed_by", "objective:ILO-01", "assessment:AT-01", relation_id="C2", established_by="id")
    graph.add_element_node(NodeType.ACTIVITY, "TLA-01", {"id": "TLA-01", "learner_cognitive_process": "remember"})
    graph.add_edge("practiced_by", "objective:ILO-01", "activity:TLA-01", relation_id="C3", established_by="id")
    types = _types(checks.bloom_mismatches(graph))
    assert types == {"bloom_mismatch_assessment", "bloom_mismatch_activity"}


# ── Verify -> repair convergence without an LLM (deterministic repairs) ─────

def test_a_vague_rubric_criterion_is_reported_and_left_alone():
    """`rubric_consistency` has no repair. The one that existed overwrote every
    flagged criterion with the SAME sentence, on both substrates: a description
    that says nothing about the item it scores, and a check that passes because
    the words changed."""
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.ASSESSMENT, "AT-01", {
        "item_id": "AT-01", "type": "short_answer",
        "rubric": [{"id": "RC-01", "description": "good"}]})
    trajectory = TrajectoryLogger()

    before = [v for v in checks.rubric_consistency(graph) if v.violation_type == "rubric_consistency"]
    assert before

    remaining = repairs.repair(
        "rubric_designer", before,
        RepairActor("RubricDesignerAgent", HarnessRunConfig(), graph=graph,
                    trajectory=trajectory).ctx())

    assert remaining == before, "an unrepairable violation must be handed back, not swallowed"
    assert checks.rubric_consistency(graph) == before
    kept = graph.get_node("assessment:AT-01")["data"]["rubric"][0]
    assert kept["description"] == "good", "the criterion is left exactly as written"
    assert not trajectory.repair_events, "nothing changed, so nothing is logged as a repair"


def test_orphan_content_repairs_by_linking_to_an_existing_activity_without_llm():

    graph = AlignmentGraph()
    graph.add_element_node(NodeType.CONTENT, "MOD-01", {"id": "MOD-01"})
    graph.add_element_node(NodeType.ACTIVITY, "TLA-01", {"id": "TLA-01"})
    config = HarnessRunConfig()
    trajectory = TrajectoryLogger()

    before = [v for v in checks.orphan_content(graph) if v.violation_type == "orphan_content"]
    assert before

    repairs.repair("content_designer", before, RepairActor("ContentDesignerAgent", config, graph=graph, trajectory=trajectory).ctx())

    assert checks.orphan_content(graph) == []


def test_a_passively_practiced_objective_is_reported_and_no_activity_is_invented():
    """`activity_engagement` has no repair. The one that existed added a
    "Hands-on practice for ILO-01" activity described as practice "on a
    realistic task with feedback" — an activity in shape only, which satisfied
    the check by existing."""
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {"id": "ILO-01", "level": "apply"})
    graph.add_element_node(NodeType.ACTIVITY, "TLA-01", {
        "id": "TLA-01", "activity_name": "X lecture", "description": "Instructor presentation on X concepts.",
    })
    graph.add_edge("practiced_by", "objective:ILO-01", "activity:TLA-01", relation_id="C3", established_by="id")
    trajectory = TrajectoryLogger()

    before = [v for v in checks.activity_engagement(graph) if v.violation_type == "activity_engagement"]
    assert before

    remaining = repairs.repair(
        "activity_designer", before,
        RepairActor("ActivityDesignerAgent", HarnessRunConfig(), graph=graph,
                    trajectory=trajectory).ctx())

    assert remaining == before
    assert len(graph.element_nodes(NodeType.ACTIVITY)) == 1, "no activity was manufactured"
    assert not trajectory.repair_events


# ── plan -> execute coverage (the check the 2-hop design implied but lacked) ──

def _plan_graph(targets: dict, items: list[tuple[str, str]]) -> AlignmentGraph:
    graph = AlignmentGraph()
    graph.add_node(NodeType.ASSESSMENT_PLAN, "assessment_plan_0", {"lo_coverage_targets": targets})
    for lo_id in targets:
        graph.add_element_node(NodeType.OBJECTIVE, lo_id, {
            "id": lo_id, "level": "apply", "statement": f"Perform {lo_id}.",
        })
    for i, (lo_id, category) in enumerate(items, start=1):
        graph.add_element_node(NodeType.ASSESSMENT, f"AT-{i:02d}", {
            "item_id": f"AT-{i:02d}", "aligned_objective": lo_id,
            "plan_category": category, "type": "performance_task",
        })
    return graph


def test_plan_coverage_flags_promised_but_unrealised_pairs():
    """Measured failure this guards: the plan asked for 5 summative and 1
    diagnostic item; the items hop produced 1 summative and 16 diagnostic and
    nothing objected, because P3 only checks that plan_category names a
    non-empty list. The near-empty summative pool then collapsed the summative
    half of ADDIE Evaluation, which is computed from it."""
    graph = _plan_graph(
        {"ILO-01": ["diagnostic", "summative"], "ILO-02": ["formative", "summative"]},
        [("ILO-01", "summative")],
    )
    violations = checks.plan_coverage(graph)
    assert {v.violation_type for v in violations} == {"plan_coverage"}
    promised = {(v.metadata["lo_id"], v.metadata["plan_category"]) for v in violations}
    assert promised == {("ILO-01", "diagnostic"), ("ILO-02", "formative"), ("ILO-02", "summative")}


def test_plan_coverage_silent_when_every_promised_pair_exists():
    graph = _plan_graph(
        {"ILO-01": ["summative"], "ILO-02": ["formative"]},
        [("ILO-01", "summative"), ("ILO-02", "formative")],
    )
    assert checks.plan_coverage(graph) == []


def test_an_unrealised_plan_promise_needs_the_model_and_is_not_filled_without_it():
    """Writing the missing item is a generation, so with no model there is no
    item. The deterministic stand-in that used to fill it built the question
    out of the objective's own statement, which reads to any text-similarity
    measure as perfect objective-assessment correspondence."""
    graph = _plan_graph(
        {"ILO-01": ["diagnostic", "summative"], "ILO-02": ["formative", "summative"]},
        [("ILO-01", "summative")],
    )
    before = checks.plan_coverage(graph)
    assert before
    trajectory = TrajectoryLogger()

    repairs.repair("assessment_designer", before,
                   RepairActor("AssessmentDesignerAgent", HarnessRunConfig(), graph=graph,
                               trajectory=trajectory).ctx())

    assert checks.plan_coverage(graph) == before, "the promise stays open, and stays reported"
    assert not trajectory.repair_events
    assert not alignment.bloom_assessment_violations(graph)


