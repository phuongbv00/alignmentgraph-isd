"""Shared run scaffolding: memory session, context pack, invoke, metadata.

Every workflow shares this scaffolding; only the graph wiring differs. A
workflow supplies a ``build_graph(config, graph, trajectory, context_pack,
design_brief) -> CompiledGraph`` function and ``run_workflow`` handles the rest.
"""
from __future__ import annotations

import uuid
from typing import Callable

from ..config import HarnessRunConfig
from .context import ContextPlanner
from .memory import HarnessMemory
from .nodes import empty_addie, initial_state
from .schema import DesignBrief
from .trajectory import TrajectoryLogger

BuildGraph = Callable


def run_workflow(config: HarnessRunConfig, design_brief: DesignBrief, build_graph: BuildGraph) -> dict:
    memory = HarnessMemory(config)
    memory_session = memory.begin_session(design_brief)
    graph = memory_session.graph
    trajectory = TrajectoryLogger()
    if design_brief.refinement_request and memory_session.session_type == "refinement":
        from .refinement import RefinementRequest, apply_refinement_request
        apply_refinement_request(
            graph, trajectory,
            RefinementRequest.model_validate(design_brief.refinement_request),
        )
    # Context pack from two upfront sources: brief-derived preparation
    # (ContextPlanner — not retrieval) and memory retrieval (core, always on).
    # External-corpus RAG is on-demand inside specialists, not part of this pack.
    context_pack = ContextPlanner().build(design_brief)
    context_pack = memory_session.augment_context_pack(context_pack)

    compiled = build_graph(config, graph, trajectory, context_pack, design_brief)

    invoke_config = {"recursion_limit": 80, "configurable": {"thread_id": str(uuid.uuid4())}}
    final_state = compiled.invoke(initial_state(), invoke_config)

    addie_output = final_state.get("addie_output") or empty_addie()
    residual_violation_count = len(final_state.get("violations", []))
    repair_metrics = trajectory.summary_metrics(residual_violation_count)
    trajectory_payload = trajectory.finalize()
    memory_metadata = memory_session.commit(
        design_brief=design_brief, graph=graph, trajectory=trajectory_payload,
        final_state=final_state, addie_output=addie_output,
    )
    return {
        "addie_output": addie_output,
        "trajectory": trajectory_payload,
        "metadata": {
            "ablation": config.ablation.model_dump(),
            "llm": config.llm.model_dump(),
            "memory": memory_metadata,
            "design_brief_id": design_brief.id,
            "violations": final_state.get("violations", []),
            "errors": final_state.get("errors", []),
            "validation_errors": final_state.get("validation_errors", []),
            "schema_violations": final_state.get("audit", {}).get("schema_violations", {}),
            "audit": final_state.get("audit", {}),
            "pending_tasks": final_state.get("pending_tasks", []),
            "task_attempts": final_state.get("task_attempts", {}),
            "planner_decisions": final_state.get("planner_decisions", []),
            "repair_rounds": final_state.get("repair_rounds", 0),
            "repair_metrics": repair_metrics,
        },
    }


class MetaAgent:
    """Public entry point. Selects the workflow the config's arm maps to and runs
    it through the shared scaffolding. Kept as a thin shim for backward
    compatibility (benchmark adapter, tests)."""

    def __init__(self, config: HarnessRunConfig) -> None:
        self.config = config

    def run(self, design_brief: DesignBrief) -> dict:
        from ..workflows import WORKFLOWS
        build_graph = WORKFLOWS[self.config.ablation.workflow_name]
        return run_workflow(self.config, design_brief, build_graph)
