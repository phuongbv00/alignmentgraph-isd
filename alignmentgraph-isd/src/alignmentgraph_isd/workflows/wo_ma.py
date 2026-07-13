"""Ablation arm: NO multi-agent decomposition (single agent), with QC.

One agent generates the whole ADDIE design, then repairs itself holistically —
routing to specialist repair agents would smuggle decomposition back into the
QC loop, so the single agent owns its own quality control. Isolates the
contribution of multi-agent decomposition.
"""
from __future__ import annotations

from ..core.agents.single_agent import SingleAgent
from ..core.nodes import ISDState, NodeFactory


def build_graph(config, graph, trajectory, context_pack, design_brief):
    from langgraph.graph import StateGraph, START, END

    nf = NodeFactory(config, graph, trajectory, context_pack, design_brief)
    wf = StateGraph(ISDState)
    wf.add_node("single_agent", nf.single_agent_node())
    wf.add_node("single_agent_qc", nf.qc_node(SingleAgent, "single_agent_qc"))
    wf.add_node("aggregate", nf.aggregate_node())

    wf.add_edge(START, "single_agent")
    wf.add_edge("single_agent", "single_agent_qc")
    wf.add_edge("single_agent_qc", "aggregate")
    wf.add_edge("aggregate", END)
    return wf.compile()
