"""Dynamic-planner workflow (kept for multi-session refinement).

A planner reads the graph state each round and drives adaptive generation AND a
global verify -> repair -> cascade loop through one task-planning loop. This is
the workflow used for the refinement entrypoint; it is not the single-pass
default. Behaviour is preserved from the original orchestrator dynamic branch.
"""
from __future__ import annotations

from ..core.agents.objective_design import ObjectiveDesignAgent
from ..core.agents.assessment_design import AssessmentDesignAgent
from ..core.agents.activity_material import ActivityMaterialAgent
from ..core.agents.implementation_plan import ImplementationPlanAgent
from ..core.agents.evaluation_revision import EvaluationRevisionAgent
from ..core.nodes import GENERATION_AGENTS, ISDState, NodeFactory

_REPAIR_AGENTS = {
    "objective_repair": ObjectiveDesignAgent,
    "assessment_repair": AssessmentDesignAgent,
    "activity_repair": ActivityMaterialAgent,
    "implementation_repair": ImplementationPlanAgent,
    "evaluation_repair": EvaluationRevisionAgent,
}

_LOOP_NODES = (
    *GENERATION_AGENTS, "single_agent", "verifier",
    *_REPAIR_AGENTS,
)


def build_graph(config, graph, trajectory, context_pack, design_brief):
    from langgraph.graph import StateGraph, START, END
    from langgraph.checkpoint.memory import MemorySaver

    nf = NodeFactory(config, graph, trajectory, context_pack, design_brief)
    wf = StateGraph(ISDState)

    wf.add_node("audit", nf.audit_node())
    wf.add_node("task_planner", nf.task_planner_node())
    for name in GENERATION_AGENTS:
        wf.add_node(name, nf.generation_node(name))
    wf.add_node("single_agent", nf.single_agent_node())
    wf.add_node("verifier", nf.verifier_node())
    for name, agent_cls in _REPAIR_AGENTS.items():
        wf.add_node(name, nf.specialist_repair_node(agent_cls, name))
    wf.add_node("aggregate", nf.aggregate_node())

    wf.add_edge(START, "audit")
    wf.add_edge("audit", "task_planner")
    wf.add_conditional_edges(
        "task_planner",
        lambda state: state.get("next_task", "aggregate"),
        {**{n: n for n in _LOOP_NODES}, "aggregate": "aggregate"},
    )
    for name in _LOOP_NODES:
        wf.add_edge(name, "audit")
    wf.add_edge("aggregate", END)
    return wf.compile(checkpointer=MemorySaver())
