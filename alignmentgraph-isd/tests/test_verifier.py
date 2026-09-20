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

from conftest import add_assessment, RepairActor

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
    assert violations
    # Keyed on the STRUCTURED fact, not on the wording. The message is prompt
    # surface — it goes verbatim into the agent's repair turn — and is pinned
    # byte-for-byte by `checks.messages.bloom` in golden_prompts.json. A
    # behavioural test that also asserts on its prose pins the same string
    # twice and turns a deliberate rewording into two failures in two places.
    found = violations[0]
    assert found.metadata["rule"] == "verb_level_mismatch"
    assert found.metadata["verb_level"] == "remember"
    # It must still name both levels, or the reader cannot act on it.
    assert "apply" in found.message and "remember" in found.message


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


def test_evaluation_quality_reads_formative_intent_off_lo_coverage_targets():
    """The gate used to be ``plan["formative"]`` — one of the three optional
    buckets P3 also hung on, asked for by no rule and no longer declared by the
    schema. So this check could not fire on a real plan either: MEASURED (run
    7ef3ed16) the plan promised a formative item for eight of nine objectives,
    shipped a ``pilot_data_plan`` with no ``collection_points``, and produced
    zero ``evaluation_quality`` findings."""
    graph = AlignmentGraph()
    graph.add_node(NodeType.ASSESSMENT_PLAN, "assessment_plan_0", {
        "lo_coverage_targets": {"ILO-01": ["formative"]},
        "formative_methods": [],
    })
    assert "evaluation_quality" in _types(checks.evaluation_quality(graph))


def test_evaluation_quality_silent_when_no_formative_intent():
    graph = AlignmentGraph()
    graph.add_node(NodeType.ASSESSMENT_PLAN, "assessment_plan_0", {
        "lo_coverage_targets": {"ILO-01": ["summative"]}, "formative_methods": []})
    assert checks.evaluation_quality(graph) == []


def test_evaluation_quality_silent_when_no_formative_intent_archived_plan():
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


# ── modules: a material, an activity and an objective each name theirs ──────

def test_a_material_with_no_module_is_a_p5_gap_and_is_repaired_from_its_work_set():
    """Materials are developed one module at a time and every material carries
    the `plan_set` of the work set that wrote it, so the module a material
    with a dangling `linked_module` belongs to is known exactly. A material
    whose set names no module that exists is left a finding: picking one for
    it would be authoring the claim the edge records."""
    graph = AlignmentGraph()
    for module in ("MOD-01", "MOD-02"):
        graph.add_element_node(NodeType.MODULE, module, {"id": module})
    graph.add_element_node(NodeType.MATERIAL, "MAT-0201", {
        "id": "MAT-0201", "linked_module": "Inheritance", "plan_set": "MU-MOD-02"})
    graph.add_element_node(NodeType.MATERIAL, "MAT-0901", {"id": "MAT-0901", "plan_set": "S0"})
    trajectory = TrajectoryLogger()

    before = [v for v in checks.relation_coverage(graph) if v.violation_type == "P5"]
    assert {v.node_id for v in before} == {"material:MAT-0201", "material:MAT-0901"}
    assert all("linked_module" in v.repair_hint for v in before)

    repairs.repair(
        "content_designer", before,
        RepairActor("ContentDesignerAgent", HarnessRunConfig(), graph=graph,
                    trajectory=trajectory).ctx())

    assert graph.get_node("material:MAT-0201")["data"]["linked_module"] == "MOD-02"
    assert [(e["source"], e["target"]) for e in graph.get_edges(relation_id="P5")] == [
        ("module:MOD-02", "material:MAT-0201")]
    left = [v.node_id for v in checks.relation_coverage(graph) if v.violation_type == "P5"]
    assert left == ["material:MAT-0901"], "no module was picked for it"


def test_a_module_nothing_is_taught_or_assessed_in_is_reported_and_never_filled():
    """P13 and P14 are report-only for the harness: the only deterministic way
    to close "this module has no activity" is an activity whose one property is
    existing."""
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.MODULE, "MOD-01", {"id": "MOD-01"})
    trajectory = TrajectoryLogger()
    found = [v for v in checks.relation_coverage(graph) if v.violation_type in ("P13", "P14")]
    assert {v.violation_type for v in found} == {"P13", "P14"}
    assert all(v.severity == "warning" for v in found), "a module's relations are secondary"
    assert "module_id" in next(v for v in found if v.violation_type == "P13").repair_hint
    assert "task_id" in next(v for v in found if v.violation_type == "P14").repair_hint

    for family in ("activity_designer", "assessment_designer"):
        owned = [v for v in found if v.violation_type in repairs.OWNED_BY_FAMILY[family]]
        assert owned
        assert repairs.repair(family, owned, RepairActor(
            family, HarnessRunConfig(), graph=graph, trajectory=trajectory).ctx()) == owned
    assert len(graph.to_dict()["nodes"]) == 1 and not trajectory.repair_events


def test_the_outcomes_commit_links_modules_whatever_order_the_artifacts_arrive_in():
    """The three outcomes artifacts are separate submits. A module that lands
    BEFORE the objectives it names must still get its P12 edges when they
    arrive, and a namespaced reference ("objective:ILO-01" is the node's own
    id and unambiguous) must resolve exactly as a bare one does."""
    from alignmentgraph_isd.core.agentic import specialists

    graph = AlignmentGraph()
    graph.add_element_node(NodeType.TOPIC, "TOP-01", {"id": "TOP-01"})
    trajectory = TrajectoryLogger()
    specialists.commit_outcomes(graph, trajectory, {"course_modules": [
        {"id": "MOD-01", "title": "M", "objectives": ["objective:ILO-01", "ILO-02"],
         "covers_topics": ["TOP-01"], "minutes": 60}]})
    assert graph.get_edges(relation_id="P12") == []
    assert [e["source"] for e in graph.get_edges(relation_id="P7")] == ["topic:TOP-01"]

    specialists.commit_outcomes(graph, trajectory, {"learning_objectives": [
        {"id": "ILO-01", "level": "apply", "bloom_verb": "apply", "statement": "Apply a."},
        {"id": "ILO-02", "level": "apply", "bloom_verb": "apply", "statement": "Apply b."},
        {"id": "ILO-03", "level": "apply", "bloom_verb": "apply", "statement": "Apply c."}]})
    assert {(e["source"], e["target"]) for e in graph.get_edges(relation_id="P12")} == {
        ("module:MOD-01", "objective:ILO-01"), ("module:MOD-01", "objective:ILO-02")}
    assert alignment.relation_coverage(graph, "P12")[1] == ["objective:ILO-03"]


# ── Rubric Designer's own checks: rubric_consistency, evidence_alignment ────

def test_rubric_consistency_fires_for_vague_description():
    """A criterion is a FIELD of the item it marks (2026-09-02), so the check
    reads it off the item — the same way the prose arm always has, which is
    what lets both substrates run the identical implementation."""
    graph = AlignmentGraph()
    add_assessment(graph, {
        "item_id": "AT-01", "type": "short_answer",
        "rubric": [{"id": "RC-01", "description": "good"}]})
    violations = [v for v in checks.rubric_consistency(graph)
                  if v.violation_type == "rubric_consistency"]
    assert violations and violations[0].metadata["rc_id"] == "RC-01"


def test_rubric_consistency_silent_for_observable_description():
    graph = AlignmentGraph()
    add_assessment(graph, {
        "item_id": "AT-01", "type": "short_answer",
        "rubric": [{"id": "RC-01", "description":
                    "Scored 0-3: cites at least two pieces of observable evidence "
                    "and states the trade-off each one implies."}]})
    assert not [v for v in checks.rubric_consistency(graph)
                if v.violation_type == "rubric_consistency"]


def test_a_vague_word_is_matched_as_a_word_and_not_as_a_substring():
    """MEASURED (run 2b9e911a): "clear" matched "clearly", so three rubric
    descriptions that name exactly what the learner must produce were reported
    as lacking an observable one. "clearly articulates X" is the check's own
    ideal, not its target — the adverb intensifies the observation."""
    graph = AlignmentGraph()
    for index, description in enumerate((
            "Student clearly articulates that embedded systems are designed for "
            "real-time control and industrial applications, not consumer use.",
            "The learner provides a specific development toolchain and a clearly "
            "defined IoT prototype addressing a real-world problem."), start=1):
        add_assessment(graph, {
            "item_id": f"AT-{index:02d}", "type": "short_answer",
            "rubric": [{"id": f"RC-{index:02d}", "description": description}]})

    assert not [v for v in checks.rubric_consistency(graph)
                if v.violation_type == "rubric_consistency"]


def test_an_activity_marker_is_a_word_too_and_a_stem_stays_a_stem():
    """The active-format list REDEEMS, so a false match there lets a passive
    design through: "lab" matched "collaborate" and "syllabus". Narrowing it
    makes the check fire more, which is the correct direction — but the entries
    that are deliberate stems ("cod" for code/coding) must keep matching their
    inflections, so the policy is a leading boundary, not a whole word."""
    assert not checks._ACTIVE_ACTIVITY_RE.search("learners collaborate on a syllabus")
    assert checks._ACTIVE_ACTIVITY_RE.search("a coding lab on sensor drift")
    assert checks._ACTIVE_ACTIVITY_RE.search("two labs and a guided exercise")


def test_a_taxonomy_verb_is_matched_as_a_word_too():
    """The other redemption list: "rate" matched "generate" and "use" matched
    "because", so a statement carrying no taxonomy verb excused itself."""
    assert not checks._BLOOM_VERB_RE.search("the delay happened because of the queue")
    assert checks._BLOOM_VERB_RE.search("generates a report")
    assert checks._BLOOM_VERB_RE.search("demonstrates the process")


def test_evidence_alignment_fires_when_item_cannot_produce_required_evidence():
    """The item is the criterion's PARENT now, not the far end of a C6 edge, so
    the lookup is direct and the "no linked item" case cannot occur."""
    graph = AlignmentGraph()
    add_assessment(graph, {
        "item_id": "AT-01", "type": "multiple_choice",
        "rubric": [{"id": "RC-01", "evidence_type": "performance_task"}]})
    violations = [v for v in checks.evidence_alignment(graph)
                  if v.violation_type == "evidence_alignment"]
    assert violations and violations[0].metadata["rc_id"] == "RC-01"


def test_evidence_alignment_silent_when_item_can_produce_evidence():
    graph = AlignmentGraph()
    add_assessment(graph, {
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


# ── relation_coverage(): re-runs rerunnable establishers + full 18-relation check ──

def test_relation_coverage_flags_uncovered_core_relation():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {"id": "ILO-01"})
    assert "C2" in _types(checks.relation_coverage(graph))


def test_relation_coverage_silent_once_established():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {"id": "ILO-01"})
    add_assessment(graph, {"item_id": "AT-01", "aligned_objective": "ILO-01"})
    assert "C2" not in _types(checks.relation_coverage(graph))


def test_relation_coverage_reports_dangling_reference_from_rerunnable_establisher():
    graph = AlignmentGraph()
    add_assessment(graph, {"item_id": "AT-01", "aligned_objective": "ILO-99"})
    assert "C2" in _types(checks.relation_coverage(graph))


# ── bloom_mismatches(): the two Bloom cross-checks, tagged per artifact type ──

def test_bloom_mismatches_tags_assessment_and_activity_separately():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {"id": "ILO-01", "level": "analyze"})
    add_assessment(graph, {"item_id": "AT-01", "type": "multiple_choice"})
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
    add_assessment(graph, {
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
    kept = graph.get_node("assessment:AT-01")["data"]["items"][0]["rubric"][0]
    assert kept["description"] == "good", "the criterion is left exactly as written"
    assert not trajectory.repair_events, "nothing changed, so nothing is logged as a repair"


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
        add_assessment(graph, {
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


