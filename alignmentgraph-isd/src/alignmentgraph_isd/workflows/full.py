"""Full harness: multi-agent decomposition, fixed ADDIE order, per-agent QC.

Each specialist generates its artifact, then a quality-control node verifies the
checks that specialist owns and repairs them in place before the next specialist
runs. Coverage checks work because earlier artifacts are already in the shared
graph. No dynamic planner, no global verify phase.
"""
from __future__ import annotations

from ..core.nodes import GENERATION_AGENTS, ISDState, NodeFactory

ORDER = ["needs_context", "objective_design", "assessment_design",
         "activity_material", "implementation_plan", "evaluation_revision"]


def build_graph(config, graph, trajectory, context_pack, design_brief):
    from langgraph.graph import StateGraph, START, END

    nf = NodeFactory(config, graph, trajectory, context_pack, design_brief)
    wf = StateGraph(ISDState)
    wf.add_node("aggregate", nf.aggregate_node())

    prev = START
    for name in ORDER:
        wf.add_node(name, nf.generation_node(name))
        wf.add_edge(prev, name)
        agent_cls = GENERATION_AGENTS[name]
        if agent_cls.OWNED_VIOLATION_TYPES:          # only agents with checks get a QC node
            qc = f"{name}_qc"
            wf.add_node(qc, nf.qc_node(agent_cls, qc))
            wf.add_edge(name, qc)
            prev = qc
        else:
            prev = name
    wf.add_edge(prev, "aggregate")
    wf.add_edge("aggregate", END)
    return wf.compile()
