from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .audit import GraphAuditResult
from ..config import HarnessRunConfig
from .graph import AlignmentGraph, EdgeType, NodeType


@dataclass
class PlannedTask:
    id: str
    type: str
    target: str
    reason: str
    priority: int
    attempts: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "target": self.target,
            "reason": self.reason,
            "priority": self.priority,
            "attempts": self.attempts,
        }


@dataclass
class TaskPlanDecision:
    next_task: str
    reason: str
    selected_task: PlannedTask | None = None
    pending_tasks: list[PlannedTask] = field(default_factory=list)
    should_stop: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "next_task": self.next_task,
            "reason": self.reason,
            "selected_task": self.selected_task.to_dict() if self.selected_task else None,
            "pending_tasks": [planned_task.to_dict() for planned_task in self.pending_tasks],
            "should_stop": self.should_stop,
        }


@dataclass
class ISDTaskPlanner:
    """Audit-driven router that selects the next internal PlannedTask.

    This component does not decompose a DesignBrief into a complete upfront
    plan. It inspects the current graph audit, builds the currently relevant
    candidate tasks, and routes execution to the highest-priority runnable one.
    """

    min_objectives: int = 5
    max_task_attempts: int = 2
    max_verifier_attempts: int = 3
    max_repair_rounds: int = 4
    max_planner_steps: int = 30

    @classmethod
    def from_config(cls, config: HarnessRunConfig) -> "ISDTaskPlanner":
        return cls()

    def decide(self, audit: GraphAuditResult, state: dict, config: HarnessRunConfig) -> TaskPlanDecision:
        attempts = dict(state.get("task_attempts", {}) or {})
        decisions_so_far = len(state.get("planner_decisions", []) or [])
        if decisions_so_far >= self.max_planner_steps:
            return TaskPlanDecision(
                next_task="aggregate",
                reason=f"max_planner_steps reached ({self.max_planner_steps}); aggregate best available graph",
                should_stop=True,
            )

        if not config.ablation.multi_agent:
            return self._decide_single_agent(audit, state, config, attempts)

        pending = self._build_tasks(audit, state, config, attempts)
        runnable = [planned_task for planned_task in pending if self._can_run(planned_task, attempts, state)]
        if runnable:
            runnable.sort(key=lambda planned_task: planned_task.priority, reverse=True)
            selected = runnable[0]
            return TaskPlanDecision(
                next_task=selected.type,
                reason=selected.reason,
                selected_task=selected,
                pending_tasks=pending,
            )

        if pending:
            return TaskPlanDecision(
                next_task="aggregate",
                reason="pending tasks exceeded planner attempt limits; aggregate best available graph",
                pending_tasks=pending,
                should_stop=True,
            )

        unowned_violations = self._unowned_violation_count(audit)
        if config.ablation.use_repair and unowned_violations:
            return TaskPlanDecision(
                next_task="aggregate",
                reason=(
                    f"{unowned_violations} verifier violation(s) have no specialist repair owner; "
                    "aggregate with residual violations"
                ),
                pending_tasks=[],
                should_stop=True,
            )

        return TaskPlanDecision(
            next_task="aggregate",
            reason="audit reports graph is ready or no planner task remains",
            pending_tasks=[],
            should_stop=True,
        )

    def _decide_single_agent(
        self,
        audit: GraphAuditResult,
        state: dict,
        config: HarnessRunConfig,
        attempts: dict[str, int],
    ) -> TaskPlanDecision:
        if attempts.get("single_agent", 0) < 1:
            planned_task = PlannedTask(
                id="single-agent-generate",
                type="single_agent",
                target="addie_output",
                reason="single_agent ablation selected",
                priority=100,
                attempts=attempts.get("single_agent", 0),
            )
            return TaskPlanDecision("single_agent", planned_task.reason, planned_task, [planned_task])
        verifier_task = self._verifier_task_if_needed(audit, state, config, attempts)
        if verifier_task and self._can_run(verifier_task, attempts, state):
            return TaskPlanDecision("verifier", verifier_task.reason, verifier_task, [verifier_task])
        repair_tasks = self._repair_tasks_if_needed(audit, state, config, attempts)
        runnable_repairs = [
            planned_task for planned_task in repair_tasks if self._can_run(planned_task, attempts, state)
        ]
        if runnable_repairs:
            runnable_repairs.sort(key=lambda planned_task: planned_task.priority, reverse=True)
            selected = runnable_repairs[0]
            return TaskPlanDecision(selected.type, selected.reason, selected, repair_tasks)
        unowned_violations = self._unowned_violation_count(audit)
        if config.ablation.use_repair and unowned_violations:
            return TaskPlanDecision(
                "aggregate",
                (
                    f"{unowned_violations} verifier violation(s) have no specialist repair owner; "
                    "aggregate single_agent output with residual violations"
                ),
                should_stop=True,
            )
        return TaskPlanDecision("aggregate", "single_agent output is ready to aggregate", should_stop=True)

    def _build_tasks(
        self,
        audit: GraphAuditResult,
        state: dict,
        config: HarnessRunConfig,
        attempts: dict[str, int],
    ) -> list[PlannedTask]:
        tasks: list[PlannedTask] = []

        repair_tasks = self._repair_tasks_if_needed(audit, state, config, attempts)
        if repair_tasks:
            tasks.extend(repair_tasks)
            return tasks

        if (
            NodeType.NEEDS_CONTEXT in audit.missing_node_types
            or NodeType.NEEDS_CONTEXT in audit.stale_node_types
            or audit.missing_section_keys.get(NodeType.NEEDS_CONTEXT)
        ):
            tasks.append(self._task(
                "needs-context",
                "needs_context",
                AlignmentGraph.section_id(NodeType.NEEDS_CONTEXT),
                "analysis/context graph node is missing or incomplete",
                95,
                attempts,
            ))

        if (
            NodeType.OBJECTIVE in audit.missing_node_types
            or NodeType.OBJECTIVE in audit.stale_node_types
            or audit.objective_count < self.min_objectives
            or audit.missing_section_keys.get(NodeType.OBJECTIVE)
        ):
            reason = (
                f"objective graph has {audit.objective_count}/{self.min_objectives} objectives"
                if audit.objective_count
                else "objective graph node is missing"
            )
            tasks.append(self._task("objective-design", "objective_design", AlignmentGraph.section_id(NodeType.OBJECTIVE), reason, 90, attempts))

        if (
            NodeType.ASSESSMENT in audit.missing_node_types
            or NodeType.ASSESSMENT in audit.stale_node_types
            or audit.missing_section_keys.get(NodeType.ASSESSMENT)
            or audit.unmeasured_objectives
        ):
            target = ",".join(audit.unmeasured_objectives) or AlignmentGraph.section_id(NodeType.ASSESSMENT)
            reason = (
                f"objectives lack measures edges: {target}"
                if audit.unmeasured_objectives
                else "assessment graph node is missing or incomplete"
            )
            tasks.append(self._task("assessment-design", "assessment_design", target, reason, 85, attempts))

        if (
            NodeType.ACTIVITY in audit.missing_node_types
            or NodeType.MATERIAL in audit.missing_node_types
            or NodeType.ACTIVITY in audit.stale_node_types
            or NodeType.MATERIAL in audit.stale_node_types
            or audit.missing_section_keys.get(NodeType.ACTIVITY)
            or audit.missing_section_keys.get(NodeType.MATERIAL)
            or audit.unsupported_objectives
        ):
            target = ",".join(audit.unsupported_objectives) or AlignmentGraph.section_id(NodeType.ACTIVITY)
            reason = (
                f"objectives lack supports edges: {target}"
                if audit.unsupported_objectives
                else "activity/material graph nodes are missing or incomplete"
            )
            tasks.append(self._task("activity-material", "activity_material", target, reason, 80, attempts))

        if (
            NodeType.IMPLEMENTATION_PLAN in audit.missing_node_types
            or NodeType.IMPLEMENTATION_PLAN in audit.stale_node_types
            or audit.missing_section_keys.get(NodeType.IMPLEMENTATION_PLAN)
        ):
            tasks.append(self._task(
                "implementation-plan",
                "implementation_plan",
                AlignmentGraph.section_id(NodeType.IMPLEMENTATION_PLAN),
                "implementation plan graph node is missing or incomplete",
                70,
                attempts,
            ))

        if (
            NodeType.EVALUATION in audit.missing_node_types
            or NodeType.EVALUATION in audit.stale_node_types
            or audit.missing_section_keys.get(NodeType.EVALUATION)
            or audit.unevaluated_objectives
        ):
            target = ",".join(audit.unevaluated_objectives) or AlignmentGraph.section_id(NodeType.EVALUATION)
            reason = (
                f"objectives lack evaluates edges: {target}"
                if audit.unevaluated_objectives
                else "evaluation graph node is missing or incomplete"
            )
            tasks.append(self._task("evaluation-revision", "evaluation_revision", target, reason, 65, attempts))

        verifier_task = self._verifier_task_if_needed(audit, state, config, attempts)
        if verifier_task:
            tasks.append(verifier_task)

        return tasks

    def _task(
        self,
        task_id: str,
        task_type: str,
        target: str,
        reason: str,
        priority: int,
        attempts: dict[str, int],
    ) -> PlannedTask:
        return PlannedTask(
            id=task_id,
            type=task_type,
            target=target,
            reason=reason,
            priority=priority,
            attempts=attempts.get(task_type, 0),
        )

    def _repair_tasks_if_needed(
        self,
        audit: GraphAuditResult,
        state: dict,
        config: HarnessRunConfig,
        attempts: dict[str, int],
    ) -> list[PlannedTask]:
        if not config.ablation.use_repair or not audit.verifier_violations:
            return []
        repair_rounds = int(state.get("repair_rounds", 0) or 0)
        tasks: list[PlannedTask] = []
        seen: set[str] = set()
        for violation in audit.verifier_violations:
            task_type = self._repair_owner(violation)
            if task_type is None or task_type in seen:
                continue
            seen.add(task_type)
            owned = [v for v in audit.verifier_violations if self._repair_owner(v) == task_type]
            target = ";".join(v.get("node_id", "") for v in owned)
            priority = self._repair_priority(task_type)
            tasks.append(PlannedTask(
                id=f"{task_type}-round-{repair_rounds + 1}",
                type=task_type,
                target=target,
                reason=f"{task_type} owns {len(owned)} verifier violation(s)",
                priority=priority,
                attempts=attempts.get(task_type, 0),
            ))
        return tasks

    def _repair_owner(self, violation: dict) -> str | None:
        violation_type = violation.get("type", "")
        edge_type = violation.get("edge_type", "")
        # measurability and activity_engagement are Design-section content
        # defects, so they belong to the agent that owns the design payload.
        if violation_type in ("bloom", "measurability", "activity_engagement"):
            return "objective_repair"
        if violation_type == "activity_support" or edge_type == EdgeType.SUPPORTS:
            return "activity_repair"
        if violation_type in ("feasibility", "actionability") or edge_type == "constrains":
            return "implementation_repair"
        if violation_type in ("evaluation_alignment", "evaluation_quality") or edge_type == EdgeType.EVALUATES:
            return "evaluation_repair"
        if violation_type in ("coverage", "rubric_consistency", "bloom_mismatch") or edge_type == EdgeType.MEASURES:
            return "assessment_repair"
        return None

    def _repair_priority(self, task_type: str) -> int:
        return {
            "objective_repair": 100,
            "assessment_repair": 98,
            "activity_repair": 96,
            "implementation_repair": 94,
            "evaluation_repair": 92,
        }.get(task_type, 80)

    def _unowned_violation_count(self, audit: GraphAuditResult) -> int:
        return sum(1 for violation in audit.verifier_violations if self._repair_owner(violation) is None)

    def _verifier_task_if_needed(
        self,
        audit: GraphAuditResult,
        state: dict,
        config: HarnessRunConfig,
        attempts: dict[str, int],
    ) -> PlannedTask | None:
        if not config.ablation.use_verifier:
            return None
        if not state.get("needs_verification", True):
            return None
        if audit.missing_node_types or any(audit.missing_section_keys.values()):
            return None
        if audit.unmeasured_objectives or audit.unsupported_objectives or audit.unevaluated_objectives:
            return None
        return PlannedTask(
            id="pedagogical-verification",
            type="verifier",
            target="alignment_graph",
            reason="graph complete enough for pedagogical verification",
            priority=60,
            attempts=attempts.get("verifier", 0),
        )

    def _can_run(self, planned_task: PlannedTask, attempts: dict[str, int], state: dict) -> bool:
        if planned_task.type == "verifier":
            return attempts.get(planned_task.type, 0) < self.max_verifier_attempts
        if planned_task.type.endswith("_repair"):
            return int(state.get("repair_rounds", 0) or 0) < self.max_repair_rounds
        return attempts.get(planned_task.type, 0) < self.max_task_attempts
