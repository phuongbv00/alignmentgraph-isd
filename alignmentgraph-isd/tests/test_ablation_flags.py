"""Ablation flags: enable_verifier / enable_graph_context (defaults preserve
the full pipeline; each flag cleanly disables exactly its mechanism)."""
from __future__ import annotations

from alignmentgraph_isd import HarnessRunConfig, run_design_brief
from alignmentgraph_isd.core.graph import AlignmentGraph, NodeType
from alignmentgraph_isd.core.nodes import build_graph
from alignmentgraph_isd.core.agents.assessment_design import AssessmentDesignAgent
from alignmentgraph_isd.core.trajectory import TrajectoryLogger

from conftest import load_brief

QC_NODES = {
    "objective_design_qc",
    "assessment_design_qc",
    "activity_material_qc",
    "implementation_plan_qc",
    "evaluation_revision_qc",
}


def _compiled_node_names(config, brief):
    compiled = build_graph(config, AlignmentGraph(), TrajectoryLogger(), brief)
    return set(compiled.get_graph().nodes)


def test_flags_default_on():
    config = HarnessRunConfig()
    assert config.enable_verifier is True
    assert config.enable_graph_context is True


def test_default_config_wires_all_qc_nodes(fake_config):
    brief = load_brief("minimal_brief.json")
    names = _compiled_node_names(fake_config, brief)
    assert QC_NODES <= names
    # needs_context owns no violation types -> never gets a QC node
    assert "needs_context_qc" not in names


def test_verifier_off_wires_no_qc_nodes(fake_llm_factory):
    config = HarnessRunConfig(llm_factory=fake_llm_factory, enable_verifier=False)
    brief = load_brief("minimal_brief.json")
    names = _compiled_node_names(config, brief)
    assert not (QC_NODES & names)
    # the generation chain + aggregation stay intact
    assert {"needs_context", "objective_design", "aggregate"} <= names


def test_graph_context_off_returns_empty(fake_llm_factory):
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "LO-01", {"statement": "Explain X."})

    off = HarnessRunConfig(llm_factory=fake_llm_factory, enable_graph_context=False)
    agent_off = AssessmentDesignAgent(off, graph, TrajectoryLogger())
    nodes = graph.element_nodes(NodeType.OBJECTIVE)
    assert agent_off._element_context(nodes) == ""

    on = HarnessRunConfig(llm_factory=fake_llm_factory)
    agent_on = AssessmentDesignAgent(on, graph, TrajectoryLogger())
    assert agent_on._element_context(nodes) != ""


def test_skeleton_run_end_to_end(fake_llm_factory):
    config = HarnessRunConfig(
        llm_factory=fake_llm_factory,
        enable_verifier=False,
        enable_graph_context=False,
    )
    brief = load_brief("minimal_brief.json")
    result = run_design_brief(brief, config)

    assert set(result) >= {"addie_output", "trajectory", "metadata", "graph"}
    addie = result["addie_output"]
    assert set(addie) == {"analysis", "design", "development", "implementation", "evaluation"}
    assert addie["design"]["learning_objectives"], "expected learning objectives"
    # the graph is still WRITTEN even when its read side is ablated
    assert result["graph"]["nodes"] if isinstance(result["graph"], dict) else result["graph"]


def test_metadata_records_run_config(fake_config, fake_llm_factory):
    brief = load_brief("minimal_brief.json")

    result = run_design_brief(brief, fake_config)
    rc = result["metadata"]["run_config"]
    assert rc["enable_verifier"] is True
    assert rc["enable_graph_context"] is True

    skeleton = HarnessRunConfig(
        llm_factory=fake_llm_factory,
        enable_verifier=False,
        enable_graph_context=False,
    )
    result = run_design_brief(brief, skeleton)
    rc = result["metadata"]["run_config"]
    assert rc["enable_verifier"] is False
    assert rc["enable_graph_context"] is False
