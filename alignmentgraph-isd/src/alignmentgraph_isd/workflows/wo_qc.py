"""Ablation arm: multi-agent decomposition, fixed ADDIE order, NO quality control.

Same generation pipeline as ``full`` but with the per-agent verify/repair tools
removed — isolates the contribution of the quality-control mechanism.
"""
from __future__ import annotations

from ..core.nodes import ISDState, NodeFactory
from .full import ORDER


def build_graph(config, graph, trajectory, context_pack, design_brief):
    from langgraph.graph import StateGraph, START, END

    nf = NodeFactory(config, graph, trajectory, context_pack, design_brief)
    wf = StateGraph(ISDState)
    wf.add_node("aggregate", nf.aggregate_node())

    prev = START
    for name in ORDER:
        wf.add_node(name, nf.generation_node(name))
        wf.add_edge(prev, name)
        prev = name
    wf.add_edge(prev, "aggregate")
    wf.add_edge("aggregate", END)
    return wf.compile()
