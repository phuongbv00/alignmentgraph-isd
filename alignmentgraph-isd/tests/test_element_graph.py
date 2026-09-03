"""P1.1: artifact elements are first-class graph nodes; coverage uses them."""
from __future__ import annotations

from alignmentgraph_isd import run_design_brief
from alignmentgraph_isd.core.alignment_graph import AlignmentGraph

from conftest import events_of, load_brief


def test_element_nodes_created_during_run(fake_config):
    """The relation-driven refactor makes every alignment-bearing artifact
    type element-level (not just objective) — the graph itself is the
    retrieval/traversal structure the 16-relation matrix is established over.
    See alignment.py / the specialists' _decompose_elements calls."""
    result = run_design_brief(load_brief("minimal_brief.json"), fake_config)
    node_edits = events_of(result["trajectory"], "node_edit")
    element_ids = [edit["context"]["node_id"] for edit in node_edits
                   if ":" in edit["context"]["node_id"]]
    for prefix in ("objective:", "assessment:", "activity:", "material:", "gap:", "topic:"):
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


def test_add_node_coerces_non_dict_data_to_empty():
    """A malformed LLM response can hand a section field back as a bare
    string/list instead of an object. Every consumer of node["data"] (viz,
    checks, alignment, the aggregator) assumes a dict, so a non-dict value
    must be treated as an empty section rather than stored verbatim —
    reproduces a real crash seen in production (viz.to_dot -> data.get on a
    str) for the learner_analysis field."""
    graph = AlignmentGraph()
    graph.add_node("learner_profile", "learner_profile_0", "not a dict")
    graph.add_element_node("assessment", "AT-01", ["also", "not", "a", "dict"])
    assert graph.get_node("learner_profile_0")["data"] == {}
    assert graph.get_node("assessment:AT-01")["data"] == {}


def test_update_node_coerces_non_dict_data_to_noop():
    graph = AlignmentGraph()
    graph.add_node("objective", "objective_0", {"a": 1})
    graph.update_node("objective_0", "not a dict")
    assert graph.get_node("objective_0")["data"] == {"a": 1}
