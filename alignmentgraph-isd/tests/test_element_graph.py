"""P1.1: artifact elements are first-class graph nodes; coverage uses them."""
from __future__ import annotations

from alignmentgraph_isd import run_design_brief
from alignmentgraph_isd.core.graph import AlignmentGraph

from conftest import load_brief


def test_element_nodes_created_during_run(fake_config):
    """The relation-driven refactor makes every alignment-bearing artifact
    type element-level (not just objective) — the graph itself is the
    retrieval/traversal structure the 13-relation matrix is established over.
    See alignment.py / the specialists' _decompose_elements calls."""
    result = run_design_brief(load_brief("minimal_brief.json"), fake_config)
    node_edits = result["trajectory"]["node_edits"]
    element_ids = [edit["node_id"] for edit in node_edits if ":" in edit["node_id"]]
    for prefix in ("objective:", "assessment:", "activity:", "material:", "gap:", "task:"):
        assert any(nid.startswith(prefix) for nid in element_ids), (prefix, element_ids)


def test_coverage_clean_after_full_run(fake_config):
    result = run_design_brief(load_brief("minimal_brief.json"), fake_config)
    audit = result["metadata"]["audit"]
    assert audit["unmeasured_objectives"] == []
    assert audit["objective_count"] >= 1


def test_section_and_element_nodes_distinguished():
    graph = AlignmentGraph()
    graph.add_node("objective", "objective_0", {"learning_objectives": [{"id": "LO-01"}]})
    graph.add_element_node("objective", "LO-01", {"id": "LO-01", "statement": "x"})
    assert len(graph.section_nodes("objective")) == 1
    assert len(graph.element_nodes("objective")) == 1
    assert graph.is_element("objective:LO-01")
    assert not graph.is_element("objective_0")
