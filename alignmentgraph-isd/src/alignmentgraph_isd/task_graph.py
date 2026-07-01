"""Dynamic ISD task graph: a first-class artifact of the planner's decisions.

The planner is audit-driven — each round it rebuilds the currently relevant
candidate tasks and routes to the highest-priority runnable one. This module
turns that round's candidates into an explicit task graph (task nodes with
owner/priority/status and dependency edges) so the docs' "MetaAgent builds a
dynamic ISD task graph" claim is backed by a concrete, snapshot-able structure.
A snapshot is logged to the trajectory every planner round.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .audit import GraphAuditResult
    from .planner import TaskPlanDecision

OWNER_BY_TASK = {
    "needs_context": "NeedsContextAgent",
    "objective_design": "ObjectiveDesignAgent",
    "assessment_design": "AssessmentDesignAgent",
    "activity_material": "ActivityMaterialAgent",
    "implementation_plan": "ImplementationPlanAgent",
    "evaluation_revision": "EvaluationRevisionAgent",
    "single_agent": "SingleAgent",
    "verifier": "PedagogicalVerifierAgent",
    "aggregate": "ADDIEOutputAggregator",
    "objective_repair": "ObjectiveDesignAgent",
    "assessment_repair": "AssessmentDesignAgent",
    "activity_repair": "ActivityMaterialAgent",
    "implementation_repair": "ImplementationPlanAgent",
    "evaluation_repair": "EvaluationRevisionAgent",
}

# Generation dependencies (what must exist before a task is runnable).
_GENERATION_DEPS = {
    "objective_design": ["needs_context"],
    "assessment_design": ["objective_design"],
    "activity_material": ["objective_design"],
    "implementation_plan": ["objective_design", "activity_material"],
    "evaluation_revision": ["objective_design", "assessment_design", "activity_material"],
    "verifier": [
        "objective_design", "assessment_design", "activity_material",
        "implementation_plan", "evaluation_revision",
    ],
}


class TaskGraphBuilder:
    @staticmethod
    def build(audit: "GraphAuditResult", decision: "TaskPlanDecision", state: dict) -> dict:
        selected = decision.next_task
        tasks: list[dict] = []
        for planned in decision.pending_tasks:
            tasks.append({
                "id": planned.id,
                "type": planned.type,
                "target": planned.target,
                "owner": OWNER_BY_TASK.get(planned.type, ""),
                "priority": planned.priority,
                "attempts": planned.attempts,
                "reason": planned.reason,
                "status": "selected" if planned.type == selected else "pending",
                "depends_on": _depends_on(planned),
            })

        # The aggregation task is implicit but real: it becomes runnable once the
        # required tasks complete or attempt limits are reached.
        tasks.append({
            "id": "aggregate",
            "type": "aggregate",
            "target": "addie_output",
            "owner": OWNER_BY_TASK["aggregate"],
            "priority": 0,
            "attempts": 0,
            "reason": "assemble ADDIE output",
            "status": "selected" if selected == "aggregate" else "blocked",
            "depends_on": sorted({task["type"] for task in tasks}),
        })

        edges: list[dict] = []
        present_types = {task["type"] for task in tasks}
        for task in tasks:
            for dependency in task["depends_on"]:
                if dependency in present_types:
                    edges.append({"from": dependency, "to": task["type"]})

        return {
            "selected_task": selected,
            "should_stop": decision.should_stop,
            "ready_to_aggregate": audit.ready_to_aggregate,
            "repair_rounds": int(state.get("repair_rounds", 0) or 0),
            "tasks": tasks,
            "edges": edges,
        }


def _depends_on(planned) -> list[str]:
    if planned.type.endswith("_repair"):
        # A repair task depends on the failed node(s) it targets.
        return [node_id for node_id in str(planned.target).replace(",", ";").split(";") if node_id]
    return list(_GENERATION_DEPS.get(planned.type, []))
