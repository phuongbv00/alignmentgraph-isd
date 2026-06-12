from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .audit import GraphAuditResult
from .config import HarnessRunConfig


@dataclass
class Task:
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
class PolicyDecision:
    next_task: str
    reason: str
    selected_task: Task | None = None
    pending_tasks: list[Task] = field(default_factory=list)
    should_stop: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "next_task": self.next_task,
            "reason": self.reason,
            "selected_task": self.selected_task.to_dict() if self.selected_task else None,
            "pending_tasks": [task.to_dict() for task in self.pending_tasks],
            "should_stop": self.should_stop,
        }


@dataclass
class HarnessPolicy:
    min_objectives: int = 5
    max_task_attempts: int = 2
    max_verifier_attempts: int = 3
    max_repair_rounds: int = 2
    max_policy_steps: int = 30

    @classmethod
    def from_config(cls, config: HarnessRunConfig) -> "HarnessPolicy":
        return cls()

    def decide(self, audit: GraphAuditResult, state: dict, config: HarnessRunConfig) -> PolicyDecision:
        attempts = dict(state.get("task_attempts", {}) or {})
        decisions_so_far = len(state.get("policy_decisions", []) or [])
        if decisions_so_far >= self.max_policy_steps:
            return PolicyDecision(
                next_task="aggregate",
                reason=f"max_policy_steps reached ({self.max_policy_steps}); aggregate best available graph",
                should_stop=True,
            )

        if not config.ablation.multi_agent:
            return self._decide_single_agent(audit, state, config, attempts)

        pending = self._build_tasks(audit, state, config, attempts)
        runnable = [task for task in pending if self._can_run(task, attempts, state)]
        if runnable:
            runnable.sort(key=lambda task: task.priority, reverse=True)
            selected = runnable[0]
            return PolicyDecision(
                next_task=selected.type,
                reason=selected.reason,
                selected_task=selected,
                pending_tasks=pending,
            )

        if pending:
            return PolicyDecision(
                next_task="aggregate",
                reason="pending tasks exceeded attempt policy; aggregate best available graph",
                pending_tasks=pending,
                should_stop=True,
            )

        return PolicyDecision(
            next_task="aggregate",
            reason="audit reports graph is ready or no policy task remains",
            pending_tasks=[],
            should_stop=True,
        )

    def _decide_single_agent(
        self,
        audit: GraphAuditResult,
        state: dict,
        config: HarnessRunConfig,
        attempts: dict[str, int],
    ) -> PolicyDecision:
        if attempts.get("single_agent", 0) < 1:
            task = Task(
                id="single-agent-generate",
                type="single_agent",
                target="addie_output",
                reason="single_agent ablation selected",
                priority=100,
                attempts=attempts.get("single_agent", 0),
            )
            return PolicyDecision("single_agent", task.reason, task, [task])
        verifier_task = self._verifier_task_if_needed(audit, state, config, attempts)
        if verifier_task and self._can_run(verifier_task, attempts, state):
            return PolicyDecision("verifier", verifier_task.reason, verifier_task, [verifier_task])
        repair_task = self._repair_task_if_needed(audit, state, config, attempts)
        if repair_task and self._can_run(repair_task, attempts, state):
            return PolicyDecision("repair", repair_task.reason, repair_task, [repair_task])
        return PolicyDecision("aggregate", "single_agent output is ready to aggregate", should_stop=True)

    def _build_tasks(
        self,
        audit: GraphAuditResult,
        state: dict,
        config: HarnessRunConfig,
        attempts: dict[str, int],
    ) -> list[Task]:
        tasks: list[Task] = []

        repair_task = self._repair_task_if_needed(audit, state, config, attempts)
        if repair_task:
            tasks.append(repair_task)
            return tasks

        if "needs_context" in audit.missing_node_types or audit.missing_section_keys.get("needs_context"):
            tasks.append(self._task(
                "needs-context",
                "needs_context",
                "needs_context_0",
                "analysis/context graph node is missing or incomplete",
                95,
                attempts,
            ))

        if (
            "objective" in audit.missing_node_types
            or audit.objective_count < self.min_objectives
            or audit.missing_section_keys.get("objective")
        ):
            reason = (
                f"objective graph has {audit.objective_count}/{self.min_objectives} objectives"
                if audit.objective_count
                else "objective graph node is missing"
            )
            tasks.append(self._task("objective-design", "objective_design", "objective_0", reason, 90, attempts))

        if (
            "assessment" in audit.missing_node_types
            or audit.missing_section_keys.get("assessment")
            or audit.unmeasured_objectives
        ):
            target = ",".join(audit.unmeasured_objectives) or "assessment_0"
            reason = (
                f"objectives lack measures edges: {target}"
                if audit.unmeasured_objectives
                else "assessment graph node is missing or incomplete"
            )
            tasks.append(self._task("assessment-design", "assessment_design", target, reason, 85, attempts))

        if (
            "activity" in audit.missing_node_types
            or "material" in audit.missing_node_types
            or audit.missing_section_keys.get("activity")
            or audit.missing_section_keys.get("material")
            or audit.unsupported_objectives
        ):
            target = ",".join(audit.unsupported_objectives) or "activity_0"
            reason = (
                f"objectives lack supports edges: {target}"
                if audit.unsupported_objectives
                else "activity/material graph nodes are missing or incomplete"
            )
            tasks.append(self._task("activity-material", "activity_material", target, reason, 80, attempts))

        if "constraint" in audit.missing_node_types or audit.missing_section_keys.get("constraint"):
            tasks.append(self._task(
                "implementation-constraint",
                "implementation_constraint",
                "constraint_0",
                "implementation constraint graph node is missing or incomplete",
                70,
                attempts,
            ))

        if (
            "evaluation" in audit.missing_node_types
            or audit.missing_section_keys.get("evaluation")
            or audit.unevaluated_objectives
        ):
            target = ",".join(audit.unevaluated_objectives) or "evaluation_0"
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
    ) -> Task:
        return Task(
            id=task_id,
            type=task_type,
            target=target,
            reason=reason,
            priority=priority,
            attempts=attempts.get(task_type, 0),
        )

    def _repair_task_if_needed(
        self,
        audit: GraphAuditResult,
        state: dict,
        config: HarnessRunConfig,
        attempts: dict[str, int],
    ) -> Task | None:
        if not config.ablation.use_repair or not audit.verifier_violations:
            return None
        repair_rounds = int(state.get("repair_rounds", 0) or 0)
        return Task(
            id=f"repair-round-{repair_rounds + 1}",
            type="repair",
            target=";".join(v.get("node_id", "") for v in audit.verifier_violations),
            reason=f"verifier reported {len(audit.verifier_violations)} violation(s)",
            priority=100,
            attempts=attempts.get("repair", 0),
        )

    def _verifier_task_if_needed(
        self,
        audit: GraphAuditResult,
        state: dict,
        config: HarnessRunConfig,
        attempts: dict[str, int],
    ) -> Task | None:
        if not config.ablation.use_verifier:
            return None
        if not state.get("needs_verification", True):
            return None
        if audit.missing_node_types or any(audit.missing_section_keys.values()):
            return None
        if audit.unmeasured_objectives or audit.unsupported_objectives or audit.unevaluated_objectives:
            return None
        return Task(
            id="pedagogical-verification",
            type="verifier",
            target="alignment_graph",
            reason="graph complete enough for pedagogical verification",
            priority=60,
            attempts=attempts.get("verifier", 0),
        )

    def _can_run(self, task: Task, attempts: dict[str, int], state: dict) -> bool:
        if task.type == "verifier":
            return attempts.get(task.type, 0) < self.max_verifier_attempts
        if task.type == "repair":
            return int(state.get("repair_rounds", 0) or 0) < self.max_repair_rounds
        return attempts.get(task.type, 0) < self.max_task_attempts
