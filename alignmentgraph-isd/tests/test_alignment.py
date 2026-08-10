"""alignment.py: the 13-relation matrix's establishers, coverage, and the
Bloom/format validity rule. All deterministic — no LLM calls anywhere here."""
from __future__ import annotations

from alignmentgraph_isd.core import alignment
from alignmentgraph_isd.core.graph import AlignmentGraph, NodeType


# ── id-match (R3, R5) ─────────────────────────────────────────────────────

def test_match_id_establishes_edge_on_resolvable_reference():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "LO-01", {"id": "LO-01"})
    graph.add_element_node("assessment", "AT-01", {"item_id": "AT-01", "aligned_objective": "LO-01"})
    violations = alignment.match_id(graph, "R3", target_node_type=NodeType.OBJECTIVE, field="aligned_objective")
    assert violations == []
    edges = graph.get_edges(relation_id="R3")
    assert len(edges) == 1
    assert edges[0]["source"] == "assessment:AT-01"
    assert edges[0]["target"] == "objective:LO-01"
    assert edges[0]["established_by"] == "id"


def test_match_id_reports_dangling_reference():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "LO-01", {"id": "LO-01"})
    graph.add_element_node("assessment", "AT-01", {"item_id": "AT-01", "aligned_objective": "LO-99"})
    violations = alignment.match_id(graph, "R3", target_node_type=NodeType.OBJECTIVE, field="aligned_objective")
    assert len(violations) == 1
    assert violations[0]["relation_id"] == "R3"
    assert not graph.get_edges(relation_id="R3")


def test_match_id_is_idempotent():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "LO-01", {"id": "LO-01"})
    graph.add_element_node("assessment", "AT-01", {"item_id": "AT-01", "aligned_objective": "LO-01"})
    alignment.match_id(graph, "R3", target_node_type=NodeType.OBJECTIVE, field="aligned_objective")
    alignment.match_id(graph, "R3", target_node_type=NodeType.OBJECTIVE, field="aligned_objective")
    assert len(graph.get_edges(relation_id="R3")) == 1


# ── list-aware id-match (R4) ──────────────────────────────────────────────

def test_match_r4_supports_multiple_objectives_per_activity():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "LO-01", {"id": "LO-01"})
    graph.add_element_node(NodeType.OBJECTIVE, "LO-02", {"id": "LO-02"})
    graph.add_element_node("activity", "ACT-01", {"id": "ACT-01", "aligned_objectives": ["LO-01", "LO-02"]})
    violations = alignment.match_r4_supports(graph)
    assert violations == []
    edges = graph.get_edges(relation_id="R4")
    assert {e["target"] for e in edges} == {"objective:LO-01", "objective:LO-02"}


def test_match_r4_reports_activity_with_no_resolvable_objective():
    graph = AlignmentGraph()
    graph.add_element_node("activity", "ACT-01", {"id": "ACT-01", "aligned_objectives": ["LO-99"]})
    violations = alignment.match_r4_supports(graph)
    assert len(violations) == 1 and violations[0]["relation_id"] == "R4"


# ── type-match (R6, R9, R12) ──────────────────────────────────────────────

def test_match_r6_realizes_requires_nonempty_plan_category():
    graph = AlignmentGraph()
    graph.add_node("assessment_plan", "assessment_plan_0", {"summative": ["final exam"], "diagnostic": [], "formative": []})
    graph.add_element_node("assessment", "AT-01", {"item_id": "AT-01", "plan_category": "summative"})
    graph.add_element_node("assessment", "AT-02", {"item_id": "AT-02", "plan_category": "diagnostic"})  # plan.diagnostic is empty
    violations = alignment.match_r6_realizes(graph)
    violated_ids = {v["node_id"] for v in violations}
    assert violated_ids == {"assessment:AT-02"}
    assert {e["source"] for e in graph.get_edges(relation_id="R6")} == {"assessment_plan_0"}


def test_match_r9_realizes_normalizes_aliases():
    graph = AlignmentGraph()
    graph.add_element_node("media", "MED-01", {"media_type": "video walkthrough"})
    graph.add_element_node("material", "MAT-01", {"type": "screencast", "format": "mp4"})
    graph.add_element_node("material", "MAT-02", {"type": "worksheet", "format": "docx"})
    violations = alignment.match_r9_realizes(graph)
    assert {v["node_id"] for v in violations} == {"material:MAT-02"}
    assert graph.get_edges(relation_id="R9")[0]["source"] == "media:MED-01"


def test_match_r12_realizes_is_coarse_presence_check():
    graph = AlignmentGraph()
    graph.add_node("assessment_plan", "assessment_plan_0", {"formative": ["exit ticket"]})
    graph.add_node(NodeType.EVALUATION, "evaluation_0", {"formative": {"data_collection": {"methods": ["exit tickets weekly"]}}})
    assert alignment.match_r12_realizes(graph) == []
    assert len(graph.get_edges(relation_id="R12")) == 1


# ── provenance (R1, R2, R7, R8, R10, R11, R13) ────────────────────────────

def test_record_provenance_establishes_edge_from_every_source():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "LO-01", {"id": "LO-01"})
    graph.add_node("gap", "gap:GAP-01", {"description": "g1"})
    graph.add_node("task", "task:TOPIC-01", {"topic": "t1"})
    alignment.record_provenance(graph, "R1", ["gap:GAP-01", "task:TOPIC-01"], "objective:LO-01")
    edges = graph.get_edges(relation_id="R1")
    assert {e["source"] for e in edges} == {"gap:GAP-01", "task:TOPIC-01"}
    assert all(e["established_by"] == "provenance" for e in edges)


def test_record_provenance_is_a_noop_for_missing_target():
    graph = AlignmentGraph()
    graph.add_node("gap", "gap:GAP-01", {})
    alignment.record_provenance(graph, "R1", ["gap:GAP-01"], "objective:LO-01")  # target doesn't exist
    assert graph.get_edges(relation_id="R1") == []


# ── coverage aggregation ──────────────────────────────────────────────────

def test_relation_coverage_reports_fraction_and_uncovered_ids():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "LO-01", {"id": "LO-01"})
    graph.add_element_node(NodeType.OBJECTIVE, "LO-02", {"id": "LO-02"})
    graph.add_element_node("assessment", "AT-01", {"item_id": "AT-01", "aligned_objective": "LO-01"})
    alignment.match_id(graph, "R3", target_node_type=NodeType.OBJECTIVE, field="aligned_objective")
    coverage, uncovered = alignment.relation_coverage(graph, "R3")
    assert coverage == 0.5
    assert uncovered == ["objective:LO-02"]


def test_relation_coverage_full_when_no_required_targets_exist():
    graph = AlignmentGraph()
    coverage, uncovered = alignment.relation_coverage(graph, "R3")
    assert coverage == 1.0 and uncovered == []


def test_all_relations_coverage_covers_the_whole_registry():
    graph = AlignmentGraph()
    result = alignment.all_relations_coverage(graph)
    assert set(result.keys()) == set(alignment.REGISTRY.keys())
    assert len(result) == 13


# ── Bloom/format validity rule ────────────────────────────────────────────

def test_bloom_format_violation_grouped_by_objective_not_per_edge():
    """One capable item redeems several recognition-only ones for the SAME
    objective — this must be checked per-objective, not per-edge."""
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "LO-01", {"id": "LO-01", "level": "Analyze"})
    graph.add_element_node("assessment", "AT-01", {"item_id": "AT-01", "type": "multiple_choice"})
    graph.add_element_node("assessment", "AT-02", {"item_id": "AT-02", "type": "performance_task"})
    graph.add_edge("measures", "assessment:AT-01", "objective:LO-01", relation_id="R3", established_by="id")
    graph.add_edge("measures", "assessment:AT-02", "objective:LO-01", relation_id="R3", established_by="id")
    assert alignment.bloom_format_violations(graph) == []


def test_bloom_format_violation_fires_when_every_item_is_recognition_only():
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "LO-01", {"id": "LO-01", "level": "Analyze"})
    graph.add_element_node("assessment", "AT-01", {"item_id": "AT-01", "type": "multiple_choice"})
    graph.add_edge("measures", "assessment:AT-01", "objective:LO-01", relation_id="R3", established_by="id")
    violations = alignment.bloom_format_violations(graph)
    assert len(violations) == 1
    assert violations[0]["metadata"]["lo_id"] == "LO-01"


def test_format_valid_for_capability_low_bloom_levels_always_pass():
    assert alignment.format_valid_for_capability(1, 1) is True  # Remember: any format is fine
    assert alignment.format_valid_for_capability(1, 3) is False  # Apply: recognition-only fails
    assert alignment.format_valid_for_capability(6, 3) is True
