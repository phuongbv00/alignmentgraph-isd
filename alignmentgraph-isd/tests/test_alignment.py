"""alignment.py: the relation registry's establishers, coverage, and the
Bloom cross-checks. All deterministic — no LLM calls anywhere here."""
from __future__ import annotations

from alignmentgraph_isd.core.alignment_graph import alignment
from alignmentgraph_isd.core.alignment_graph import AlignmentGraph, NodeType


# ── id-list match, standard direction (C4) ────────────────────────────────

def test_match_list_activity_prepares_for_multiple_assessments():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.ASSESSMENT, "AT-01", {"item_id": "AT-01"})
    graph.add_element_node(NodeType.ASSESSMENT, "AT-02", {"item_id": "AT-02"})
    graph.add_element_node(NodeType.ACTIVITY, "TLA-01", {"id": "TLA-01", "prepares_for_assessment": ["AT-01", "AT-02"]})
    violations = alignment.match_list(graph, "C4", field="prepares_for_assessment")
    assert violations == []
    edges = graph.get_edges(relation_id="C4")
    assert {e["target"] for e in edges} == {"assessment:AT-01", "assessment:AT-02"}
    assert {e["source"] for e in edges} == {"activity:TLA-01"}


def test_match_list_reports_activity_with_no_resolvable_assessment():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.ACTIVITY, "TLA-01", {"id": "TLA-01", "prepares_for_assessment": ["AT-99"]})
    violations = alignment.match_list(graph, "C4", field="prepares_for_assessment")
    assert len(violations) == 1 and violations[0]["relation_id"] == "C4"


# ── id-list match, REVERSED direction (C3) ────────────────────────────────

def test_match_list_reverse_stores_edge_source_as_resolved_objective():
    """C3 (practiced_by): Activity declares aligned_objectives, but the
    edge is stored source=LO, target=Activity."""
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {"id": "ILO-01"})
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-02", {"id": "ILO-02"})
    graph.add_element_node(NodeType.ACTIVITY, "TLA-01", {"id": "TLA-01", "aligned_objectives": ["ILO-01", "ILO-02"]})
    violations = alignment.match_list_reverse(graph, "C3", field="aligned_objectives")
    assert violations == []
    edges = graph.get_edges(relation_id="C3")
    assert {e["source"] for e in edges} == {"objective:ILO-01", "objective:ILO-02"}
    assert {e["target"] for e in edges} == {"activity:TLA-01"}


def test_match_list_reverse_reports_activity_with_no_resolvable_objective():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.ACTIVITY, "TLA-01", {"id": "TLA-01", "aligned_objectives": ["ILO-99"]})
    violations = alignment.match_list_reverse(graph, "C3", field="aligned_objectives")
    assert len(violations) == 1 and violations[0]["relation_id"] == "C3"


# ── type-match (P3, P6) ────────────────────────────────────────────────────

def test_p3_reads_the_field_the_plan_is_actually_required_to_write():
    """P3 used to hang on three OPTIONAL plan keys — `diagnostic`,
    `formative`, `summative` — that no rule asked for and the schema no longer
    declares, so the relation could not fire on any run.

    MEASURED (run 7ef3ed16, multi+graph): the model wrote the REQUIRED
    `lo_coverage_targets` and all 13 items carried a valid `plan_category`;
    P3 scored 0.0 and `assessment_plan_0` was the only isolated node in a
    139-node graph. The plan's promise and the item's claim are now read off
    the same field `checks.plan_coverage` reads.
    """
    graph = AlignmentGraph()
    graph.add_node(NodeType.ASSESSMENT_PLAN, "assessment_plan_0", {
        "lo_coverage_targets": {"ILO-01": ["formative"], "ILO-02": ["formative"]}})
    graph.add_element_node(NodeType.ASSESSMENT, "AT-01",
                           {"item_id": "AT-01", "plan_category": "formative"})
    # Unfailable is the C6/C7 trap: a category the plan never promised, and an
    # item that declares none at all, still have no edge.
    graph.add_element_node(NodeType.ASSESSMENT, "AT-02",
                           {"item_id": "AT-02", "plan_category": "summative"})
    graph.add_element_node(NodeType.ASSESSMENT, "AT-03", {"item_id": "AT-03"})

    violations = alignment.match_p3_realizes(graph)

    assert {v["node_id"] for v in violations} == {"assessment:AT-02", "assessment:AT-03"}
    assert {e["target"] for e in graph.get_edges(relation_id="P3")} == {"assessment:AT-01"}


def test_match_p3_realizes_still_reads_an_archived_plan_s_buckets():
    """The three bucket keys survive as a fallback and for nothing else, so a
    graph dumped before 2026-09-16 still scores the same P3 it scored then."""
    graph = AlignmentGraph()
    graph.add_node(NodeType.ASSESSMENT_PLAN, "assessment_plan_0", {"summative": ["final exam"], "diagnostic": [], "formative": []})
    graph.add_element_node(NodeType.ASSESSMENT, "AT-01", {"item_id": "AT-01", "plan_category": "summative"})
    graph.add_element_node(NodeType.ASSESSMENT, "AT-02", {"item_id": "AT-02", "plan_category": "diagnostic"})  # plan.diagnostic is empty
    violations = alignment.match_p3_realizes(graph)
    violated_ids = {v["node_id"] for v in violations}
    assert violated_ids == {"assessment:AT-02"}
    assert {e["source"] for e in graph.get_edges(relation_id="P3")} == {"assessment_plan_0"}


def test_match_p6_realizes_normalizes_aliases():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.MEDIA_SELECTION, "MED-01", {"media_type": "video walkthrough"})
    graph.add_element_node(NodeType.MATERIAL, "MAT-01", {"type": "screencast", "format": "mp4"})
    graph.add_element_node(NodeType.MATERIAL, "MAT-02", {"type": "worksheet", "format": "docx"})
    violations = alignment.match_p6_realizes(graph)
    assert {v["node_id"] for v in violations} == {"material:MAT-02"}
    assert graph.get_edges(relation_id="P6")[0]["source"] == "media_selection:MED-01"


# ── provenance (C1, C5, P1, P2, P4, P5, P7, P8, P9, P10, P11) ───────────────────

def test_record_provenance_establishes_edge_from_every_source():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {"id": "ILO-01"})
    graph.add_element_node(NodeType.GAP, "GAP-01", {"description": "g1"})
    graph.add_element_node(NodeType.TOPIC, "TOP-01", {"topic": "t1"})
    alignment.record_provenance(graph, "P1", ["gap:GAP-01", "topic:TOP-01"], "objective:ILO-01")
    edges = graph.get_edges(relation_id="P1")
    assert {e["source"] for e in edges} == {"gap:GAP-01", "topic:TOP-01"}
    assert all(e["established_by"] == "provenance" for e in edges)


def test_record_provenance_is_a_noop_for_missing_target():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.GAP, "GAP-01", {})
    alignment.record_provenance(graph, "P1", ["gap:GAP-01"], "objective:ILO-01")  # target doesn't exist
    assert graph.get_edges(relation_id="P1") == []


# ── coverage aggregation ──────────────────────────────────────────────────

def test_relation_coverage_target_side_reports_fraction_and_uncovered_ids():
    """C5 (supports) checks the TARGET side: does every activity have >=1
    supporting content module."""
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.ACTIVITY, "TLA-01", {"id": "TLA-01"})
    graph.add_element_node(NodeType.ACTIVITY, "TLA-02", {"id": "TLA-02"})
    graph.add_element_node(NodeType.CONTENT, "MOD-01", {"id": "MOD-01"})
    alignment.record_provenance(graph, "C5", ["content:MOD-01"], "activity:TLA-01")
    coverage, uncovered = alignment.relation_coverage(graph, "C5")
    assert coverage == 0.5
    assert uncovered == ["activity:TLA-02"]


def test_relation_coverage_source_side_reports_fraction_and_uncovered_ids():
    """C2 (assessed_by) checks the SOURCE side (LO) — the id-reverse
    relations flip which side "coverage" means."""
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {"id": "ILO-01"})
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-02", {"id": "ILO-02"})
    graph.add_element_node(NodeType.ASSESSMENT, "AT-01", {"item_id": "AT-01", "aligned_objective": "ILO-01"})
    alignment.match_id_reverse(graph, "C2", field="aligned_objective")
    coverage, uncovered = alignment.relation_coverage(graph, "C2")
    assert coverage == 0.5
    assert uncovered == ["objective:ILO-02"]


def test_relation_coverage_full_when_no_required_targets_exist():
    graph = AlignmentGraph()
    coverage, uncovered = alignment.relation_coverage(graph, "C5")
    assert coverage == 1.0 and uncovered == []


def test_structural_relations_stay_out_of_the_alignment_matrix():
    """S1/S2 are registered so one table names every edge kind, but a
    navigation edge must never acquire a coverage figure: "37% of activities
    have no incoming `precedes`" is not a finding, and reported beside C2 it
    reads as one. Everything that measures the construct iterates MATRIX, and
    this is what says so — `REGISTRY` is one careless `.items()` away."""
    assert set(alignment.STRUCTURAL) == {"S1", "S2"}
    assert not set(alignment.MATRIX) & set(alignment.STRUCTURAL)
    assert set(alignment.MATRIX) | set(alignment.STRUCTURAL) == set(alignment.REGISTRY)

    graph = AlignmentGraph()
    graph.add_node(NodeType.GAP, graph.section_id(NodeType.GAP), {"priority_matrix": "..."})
    graph.add_element_node(NodeType.GAP, "GAP-01", {"description": "g1"})
    graph.add_element_node(NodeType.ACTIVITY, "TLA-01", {"id": "TLA-01"})
    alignment.link_section_narrative(graph, NodeType.GAP)
    assert graph.get_edges(relation_id="S2")  # the edges really are there

    assert set(alignment.all_relations_coverage(graph)) == set(alignment.MATRIX)

    # And the coverage sweep raises no violation naming one — TLA-01 has no
    # incoming `precedes`, which is the non-finding this test exists for.
    from alignmentgraph_isd.core import checks
    types = {v.violation_type for v in checks.relation_coverage(graph)}
    assert not types & set(alignment.STRUCTURAL)


def test_all_relations_coverage_covers_the_whole_registry():
    graph = AlignmentGraph()
    result = alignment.all_relations_coverage(graph)
    assert set(result.keys()) == set(alignment.MATRIX.keys())
    assert len(result) == len(alignment.MATRIX)
    # FIVE core relations since 2026-09-02, not seven. C6/C7 went with the
    # rubric node type: a criterion is written by the same call as the item it
    # marks and the rules require it to name that item's objective, so neither
    # relation could fail — measured coverage 1.0 on both, in all 28 recorded
    # runs. A relation that cannot fail is not construct-validity evidence, so
    # the backbone is five that genuinely break rather than seven of which two
    # are guaranteed.
    assert sum(1 for r in alignment.REGISTRY.values() if r.tier == "core") == 5
    assert sum(1 for r in alignment.REGISTRY.values() if r.tier == "secondary") == 11
    # The structural pair is registered but deliberately outside the matrix.
    assert sum(1 for r in alignment.REGISTRY.values() if r.tier == "structural") == 2
    assert set(alignment.STRUCTURAL) & set(result) == set()
    # Every core relation still carries the theory it claims.
    assert all(r.theory for r in alignment.REGISTRY.values() if r.tier == "core")


# ── Bloom cross-checks (attribute-based, not an edge) ─────────────────────

def test_bloom_assessment_violation_grouped_by_objective_not_per_edge():
    """One capable item redeems several recognition-only ones for the SAME
    objective — this must be checked per-objective, not per-edge."""
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {"id": "ILO-01", "level": "analyze"})
    graph.add_element_node(NodeType.ASSESSMENT, "AT-01", {"item_id": "AT-01", "type": "multiple_choice"})
    graph.add_element_node(NodeType.ASSESSMENT, "AT-02", {"item_id": "AT-02", "type": "performance_task"})
    graph.add_edge("assessed_by", "objective:ILO-01", "assessment:AT-01", relation_id="C2", established_by="id")
    graph.add_edge("assessed_by", "objective:ILO-01", "assessment:AT-02", relation_id="C2", established_by="id")
    assert alignment.bloom_assessment_violations(graph) == []


def test_bloom_assessment_violation_fires_when_every_item_is_recognition_only():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {"id": "ILO-01", "level": "analyze"})
    graph.add_element_node(NodeType.ASSESSMENT, "AT-01", {"item_id": "AT-01", "type": "multiple_choice"})
    graph.add_edge("assessed_by", "objective:ILO-01", "assessment:AT-01", relation_id="C2", established_by="id")
    violations = alignment.bloom_assessment_violations(graph)
    assert len(violations) == 1
    assert violations[0]["metadata"]["lo_id"] == "ILO-01"


def test_bloom_assessment_violation_honors_declared_required_cognitive_process():
    """The item's own declared ``required_cognitive_process`` takes
    precedence over the format-derived fallback capability."""
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {"id": "ILO-01", "level": "analyze"})
    graph.add_element_node(NodeType.ASSESSMENT, "AT-01", {"item_id": "AT-01", "type": "multiple_choice", "required_cognitive_process": "analyze"})
    graph.add_edge("assessed_by", "objective:ILO-01", "assessment:AT-01", relation_id="C2", established_by="id")
    assert alignment.bloom_assessment_violations(graph) == []


def test_bloom_activity_violation_fires_when_no_activity_matches_level():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {"id": "ILO-01", "level": "apply"})
    graph.add_element_node(NodeType.ACTIVITY, "TLA-01", {"id": "TLA-01", "learner_cognitive_process": "remember"})
    graph.add_edge("practiced_by", "objective:ILO-01", "activity:TLA-01", relation_id="C3", established_by="id")
    violations = alignment.bloom_activity_violations(graph)
    assert len(violations) == 1
    assert violations[0]["metadata"]["lo_id"] == "ILO-01"


def test_bloom_activity_violation_clean_when_activity_matches_level():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {"id": "ILO-01", "level": "apply"})
    graph.add_element_node(NodeType.ACTIVITY, "TLA-01", {"id": "TLA-01", "learner_cognitive_process": "apply"})
    graph.add_edge("practiced_by", "objective:ILO-01", "activity:TLA-01", relation_id="C3", established_by="id")
    assert alignment.bloom_activity_violations(graph) == []


def test_format_valid_for_capability_low_bloom_levels_always_pass():
    assert alignment.format_valid_for_capability(1, 1) is True  # Remember: any format is fine
    assert alignment.format_valid_for_capability(1, 3) is False  # Apply: recognition-only fails
    assert alignment.format_valid_for_capability(6, 3) is True


# ── Bloom cross-check is a LEVEL comparison, not a recognition gate ──────────

def test_bloom_assessment_violation_fires_on_a_level_shortfall_not_only_recognition():
    """The check used to be a binary recognition/non-recognition gate, so an
    Apply-level item measuring a Create-level objective passed: both sides are
    merely "not recognition". Measured cost of that blind spot: 26% of items in
    a run sat below the objective they were aligned to while the check reported
    nothing, and that is exactly what the RQ2 cognitive-demand family scores."""
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {"id": "ILO-01", "level": "create"})
    graph.add_element_node(NodeType.ASSESSMENT, "AT-01", {
        "item_id": "AT-01", "type": "performance_task", "required_cognitive_process": "apply",
    })
    graph.add_edge("assessed_by", "objective:ILO-01", "assessment:AT-01",
                   relation_id="C2", established_by="id")
    violations = alignment.bloom_assessment_violations(graph)
    assert len(violations) == 1
    assert violations[0]["metadata"]["lo_id"] == "ILO-01"


def test_bloom_assessment_violation_silent_when_item_meets_the_level():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {"id": "ILO-01", "level": "create"})
    graph.add_element_node(NodeType.ASSESSMENT, "AT-01", {
        "item_id": "AT-01", "type": "performance_task", "required_cognitive_process": "create",
    })
    graph.add_edge("assessed_by", "objective:ILO-01", "assessment:AT-01",
                   relation_id="C2", established_by="id")
    assert alignment.bloom_assessment_violations(graph) == []


def test_format_valid_for_capability_compares_levels():
    assert alignment.format_valid_for_capability(6, 6) is True
    assert alignment.format_valid_for_capability(4, 6) is False   # Apply item, Create objective
    assert alignment.format_valid_for_capability(2, 2) is True    # recognition item, Understand objective
    assert alignment.format_valid_for_capability(1, 2) is False
    assert alignment.format_valid_for_capability(1, None) is True  # unknown level: cannot judge
