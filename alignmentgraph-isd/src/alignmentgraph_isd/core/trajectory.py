from __future__ import annotations
import time
from datetime import datetime, timezone


class TrajectoryLogger:
    def __init__(self) -> None:
        self._start = time.time()
        self.agent_steps: list[dict] = []
        self.node_edits: list[dict] = []
        self.tool_calls: list[dict] = []
        self.reasoning_steps: list[str] = []
        self.agent_interactions: list[dict] = []
        # Structured event streams so an evaluator/reviewer can compute repair
        # success rate and validation health without parsing prose.
        self.validation_events: list[dict] = []
        self.verifier_events: list[dict] = []
        self.repair_events: list[dict] = []
        self.retrieval_events: list[dict] = []
        self.llm_calls: int = 0
        self.token_usage: dict = {"prompt_tokens": 0, "completion_tokens": 0}
        self.latency_ms: float = 0.0

    def log_step(self, agent_name: str, action: str, input_summary: str, output_summary: str) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        step_index = len(self.agent_steps) + 1
        step = {
            "agent_name": agent_name,
            "action": action,
            "input_summary": input_summary,
            "output_summary": output_summary,
            "timestamp": timestamp,
        }
        self.agent_steps.append(step)

        if action.endswith("_warning") or agent_name.endswith("Verifier"):
            return

        # The benchmark trajectory evaluator expects BFCL-style tool traces.
        # Keep the graph-native trace above, and expose an adapter view here.
        self.tool_calls.append({
            "step": step_index,
            "tool": f"{agent_name}.{action}",
            "args": {
                "agent": agent_name,
                "action": action,
                "input_summary": input_summary[:500],
            },
            "result": output_summary[:1000],
            "timestamp": timestamp,
        })
        self.reasoning_steps.append(
            f"Step {step_index}: {agent_name} performed {action}; "
            f"input={input_summary[:180]}; result={output_summary[:220]}"
        )
        self.agent_interactions.append({
            "iteration": step_index,
            "agent": agent_name,
            "action": action,
            "timestamp": timestamp,
            "output_data": {
                "summary": output_summary[:500],
            },
        })

    def log_node_edit(self, op: str, node_id: str, node_type: str) -> None:
        self.node_edits.append({
            "op": op,
            "node_id": node_id,
            "node_type": node_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def log_llm_call(self, prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
        self.llm_calls += 1
        self.token_usage["prompt_tokens"] += prompt_tokens
        self.token_usage["completion_tokens"] += completion_tokens

    def log_validation_result(self, scope: str, errors: list[str]) -> None:
        """Record a schema-validation pass (scope = node type or 'addie_output')."""
        self.validation_events.append({
            "scope": scope,
            "error_count": len(errors),
            "errors": list(errors),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def log_verifier_result(self, violations: list[dict]) -> None:
        """Record one pedagogical-verification round as structured violations."""
        by_type: dict[str, int] = {}
        for violation in violations:
            vtype = violation.get("type", violation.get("violation_type", "unknown"))
            by_type[vtype] = by_type.get(vtype, 0) + 1
        self.verifier_events.append({
            "round": len(self.verifier_events) + 1,
            "violation_count": len(violations),
            "by_type": by_type,
            "violations": list(violations),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def log_repair_event(
        self,
        agent: str,
        violation_type: str,
        node_id: str,
        repaired_fields: list[str],
    ) -> None:
        self.repair_events.append({
            "agent": agent,
            "violation_type": violation_type,
            "node_id": node_id,
            "repaired_fields": list(repaired_fields or []),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def log_retrieval_event(
        self,
        agent: str,
        task_name: str,
        decision: str,
        *,
        strategy: str = "",
        retrieval_agents: list[str] | None = None,
        executions: list[dict] | None = None,
        snippets: int = 0,
    ) -> None:
        """One on-demand retrieval decision by a specialist (agentic RAG).

        ``decision`` is "retrieve" / "skip" / "decision_error"; ``executions``
        carries the per-retrieval-agent sandbox events (status, tool_calls).
        """
        self.retrieval_events.append({
            "agent": agent,
            "task_name": task_name,
            "decision": decision,
            "strategy": strategy,
            "retrieval_agents": list(retrieval_agents or []),
            "executions": list(executions or []),
            "snippets": snippets,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def summary_metrics(self, residual_violation_count: int) -> dict:
        """Aggregate structured events into headline metrics for metadata.

        ``repair_success_rate`` compares the peak verifier violation count with
        the residual count after all repair rounds, so an evaluator can read it
        directly without replaying the trajectory.
        """
        peak_violations = max((event["violation_count"] for event in self.verifier_events), default=0)
        repaired = max(peak_violations - residual_violation_count, 0)
        repair_success_rate = (repaired / peak_violations) if peak_violations else None
        return {
            "repair_events": len(self.repair_events),
            "repair_success_rate": repair_success_rate,
            "validation_error_count": sum(event["error_count"] for event in self.validation_events),
            "verifier_rounds": len(self.verifier_events),
            "peak_violation_count": peak_violations,
            "residual_violation_count": residual_violation_count,
        }

    def finalize(self) -> dict:
        self.latency_ms = (time.time() - self._start) * 1000
        return self.to_dict()

    def to_dict(self) -> dict:
        return {
            "tool_calls": self.tool_calls,
            "reasoning_steps": self.reasoning_steps,
            "agent_interactions": self.agent_interactions,
            "agent_steps": self.agent_steps,
            "node_edits": self.node_edits,
            "validation_events": self.validation_events,
            "verifier_events": self.verifier_events,
            "repair_events": self.repair_events,
            "retrieval_events": self.retrieval_events,
            "llm_calls": self.llm_calls,
            "token_usage": self.token_usage,
            "latency_ms": self.latency_ms,
        }
