"""alignment.py: the 18-relation matrix's establishers, coverage, and the
Bloom cross-checks. All deterministic — no LLM calls anywhere here."""
from __future__ import annotations

from alignmentgraph_isd.core.alignment_graph import alignment
from alignmentgraph_isd.core.alignment_graph import AlignmentGraph, NodeType


# ── id-match, standard direction (C7) ─────────────────────────────────────

def test_match_id_establishes_edge_on_resolvable_reference():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {"id": "ILO-01"})
    graph.add_element_node(NodeType.RUBRIC, "RC-01", {"id": "RC-01", "aligned_objective": "ILO-01"})
    violations = alignment.match_id(graph, "C7", field="aligned_objective")
    assert violations == []
    edges = graph.get_edges(relation_id="C7")
    assert len(edges) == 1
    assert edges[0]["source"] == "rubric:RC-01"
    assert edges[0]["target"] == "objective:ILO-01"
    assert edges[0]["established_by"] == "id"


def test_match_id_reports_dangling_reference():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {"id": "ILO-01"})
    graph.add_element_node(NodeType.RUBRIC, "RC-01", {"id": "RC-01", "aligned_objective": "ILO-99"})
    violations = alignment.match_id(graph, "C7", field="aligned_objective")
    assert len(violations) == 1
    assert violations[0]["relation_id"] == "C7"
    assert not graph.get_edges(relation_id="C7")


def test_match_id_is_idempotent():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {"id": "ILO-01"})
    graph.add_element_node(NodeType.RUBRIC, "RC-01", {"id": "RC-01", "aligned_objective": "ILO-01"})
    alignment.match_id(graph, "C7", field="aligned_objective")
    alignment.match_id(graph, "C7", field="aligned_objective")
    assert len(graph.get_edges(relation_id="C7")) == 1


# ── id-match, REVERSED direction (C2) ─────────────────────────────────────

def test_match_id_reverse_stores_edge_source_as_resolved_target():
    """C2 (assessed_by): Assessment declares the field, but the edge is
    stored source=LO, target=Assessment — the reverse of who declared it."""
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {"id": "ILO-01"})
    graph.add_element_node(NodeType.ASSESSMENT, "AT-01", {"item_id": "AT-01", "aligned_objective": "ILO-01"})
    violations = alignment.match_id_reverse(graph, "C2", field="aligned_objective")
    assert violations == []
    edges = graph.get_edges(relation_id="C2")
    assert len(edges) == 1
    assert edges[0]["source"] == "objective:ILO-01"
    assert edges[0]["target"] == "assessment:AT-01"


def test_match_id_reverse_reports_dangling_reference():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.ASSESSMENT, "AT-01", {"item_id": "AT-01", "aligned_objective": "ILO-99"})
    violations = alignment.match_id_reverse(graph, "C2", field="aligned_objective")
    assert len(violations) == 1 and violations[0]["relation_id"] == "C2"
    assert not graph.get_edges(relation_id="C2")


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

def test_match_p3_realizes_requires_nonempty_plan_category():
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


# ── provenance (C1, C5, C6, P1, P2, P4, P5, P7, P8, P9) ───────────────────

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
    """C7 (measures) checks the target side: does every LO have >=1
    evaluating criterion."""
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {"id": "ILO-01"})
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-02", {"id": "ILO-02"})
    graph.add_element_node(NodeType.RUBRIC, "RC-01", {"id": "RC-01", "aligned_objective": "ILO-01"})
    alignment.match_id(graph, "C7", field="aligned_objective")
    coverage, uncovered = alignment.relation_coverage(graph, "C7")
    assert coverage == 0.5
    assert uncovered == ["objective:ILO-02"]


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
    coverage, uncovered = alignment.relation_coverage(graph, "C7")
    assert coverage == 1.0 and uncovered == []


def test_all_relations_coverage_covers_the_whole_registry():
    graph = AlignmentGraph()
    result = alignment.all_relations_coverage(graph)
    assert set(result.keys()) == set(alignment.REGISTRY.keys())
    assert len(result) == 18
    assert sum(1 for r in alignment.REGISTRY.values() if r.tier == "core") == 7
    assert sum(1 for r in alignment.REGISTRY.values() if r.tier == "secondary") == 11


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
