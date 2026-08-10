from __future__ import annotations
import time
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Callable


class TrajectoryLogger:
    """Accumulates the run trace, and — optionally — mirrors it live.

    ``on_event`` is the one observation hook in the harness: it fires as each
    entry is recorded, so a consumer (the demo web app) can show progress while
    a run that takes minutes is still in flight. It is purely additive; with no
    consumer every emit is a no-op and the recorded trace is exactly what it
    was before. A consumer that raises is swallowed — observation must never be
    able to break a run — with one deliberate exception: ``HarnessCancelled``
    derives from ``BaseException`` and so passes through, which is how the app
    asks a run to stop.
    """

    def __init__(self, on_event: Callable[[str, dict], None] | None = None) -> None:
        self._on_event = on_event
        self._start = time.time()

        # ── the deep trajectory ──────────────────────────────────────────────
        # A single ordered log of what each agent actually did: read the graph,
        # walk a relation hop by hop, write a node, draw an alignment edge, call
        # the model, verify, repair. The streams below stay exactly as they are
        # — the benchmark and the evaluator parse those — so this is a parallel,
        # richer record, never a replacement.
        self.actions: list[dict] = []
        self._actor = ""
        self._phase = ""
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

    # ── observation hook ────────────────────────────────────────────────────
    def _emit(self, kind: str, payload: dict) -> None:
        if self._on_event is None:
            return
        try:
            self._on_event(kind, payload)
        except Exception:  # noqa: BLE001 - observation is never load-bearing.
            # Deliberately Exception, not BaseException: HarnessCancelled must
            # propagate so a consumer can stop a run.
            pass

    def emit(self, kind: str, payload: dict) -> None:
        """Progress-only signal: records nothing, changes no state.

        Used for the "started" side of long operations (a phase, an LLM call),
        which the recorded streams cannot express because every ``log_*`` entry
        is written after the work it describes has already finished.
        """
        self._emit(kind, payload)

    # ── the deep trajectory: the action log ─────────────────────────────────

    @contextmanager
    def acting_as(self, actor: str, phase: str | None = None):
        """Attribute everything logged inside this block to one agent.

        Set around a specialist's work rather than passed to each call, because
        most actions are recorded deep inside the graph, which has no idea who
        is asking.
        """
        previous_actor, previous_phase = self._actor, self._phase
        self._actor = actor or previous_actor
        if phase is not None:
            self._phase = phase
        try:
            yield
        finally:
            self._actor, self._phase = previous_actor, previous_phase

    def log_action(self, kind: str, **fields) -> dict:
        """Record one thing an agent did, and mirror it to any live consumer."""
        action = {
            "seq": len(self.actions) + 1,
            "kind": kind,
            "actor": self._actor,
            "phase": self._phase,
            "elapsed_ms": (time.time() - self._start) * 1000,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **fields,
        }
        self.actions.append(action)
        self._emit("action", action)
        return action

    def graph_observer(self):
        """Adapter for ``AlignmentGraph(observer=…)``.

        The graph reports operations without knowing who ran them; this stamps
        each one with whoever is currently acting.
        """
        def observe(kind: str, fields: dict) -> None:
            self.log_action(kind, **fields)

        return observe

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
        # Emitted before the adapter-view early return below, so a consumer sees
        # every step — including the verifier/warning ones agent_steps alone carries.
        self._emit("agent_step", step)
        self.log_action("agent_step", agent=agent_name, action=action,
                        input_summary=input_summary, output_summary=output_summary)

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
        edit = {
            "op": op,
            "node_id": node_id,
            "node_type": node_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.node_edits.append(edit)
        self._emit("node_edit", edit)

    def log_llm_call(self, prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
        self.llm_calls += 1
        self.token_usage["prompt_tokens"] += prompt_tokens
        self.token_usage["completion_tokens"] += completion_tokens
        self._emit("llm_call", {
            "llm_calls": self.llm_calls,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "token_usage": dict(self.token_usage),
        })

    def log_validation_result(self, scope: str, errors: list[str]) -> None:
        """Record a schema-validation pass (scope = node type or 'addie_output')."""
        event = {
            "scope": scope,
            "error_count": len(errors),
            "errors": list(errors),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.validation_events.append(event)
        self._emit("validation_event", event)
        self.log_action("validate", scope=scope, error_count=len(errors), errors=list(errors))

    def log_verifier_result(self, violations: list[dict]) -> None:
        """Record one pedagogical-verification round as structured violations."""
        by_type: dict[str, int] = {}
        for violation in violations:
            vtype = violation.get("type", violation.get("violation_type", "unknown"))
            by_type[vtype] = by_type.get(vtype, 0) + 1
        event = {
            "round": len(self.verifier_events) + 1,
            "violation_count": len(violations),
            "by_type": by_type,
            "violations": list(violations),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.verifier_events.append(event)
        self._emit("verifier_event", event)
        self.log_action("verify", round=event["round"], violation_count=len(violations),
                        by_type=by_type, violations=list(violations))

    def log_repair_event(
        self,
        agent: str,
        violation_type: str,
        node_id: str,
        repaired_fields: list[str],
    ) -> None:
        event = {
            "agent": agent,
            "violation_type": violation_type,
            "node_id": node_id,
            "repaired_fields": list(repaired_fields or []),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.repair_events.append(event)
        self._emit("repair_event", event)
        self.log_action("repair", agent=agent, violation_type=violation_type,
                        node_id=node_id, repaired_fields=list(repaired_fields or []))

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
        event = {
            "agent": agent,
            "task_name": task_name,
            "decision": decision,
            "strategy": strategy,
            "retrieval_agents": list(retrieval_agents or []),
            "executions": list(executions or []),
            "snippets": snippets,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.retrieval_events.append(event)
        self._emit("retrieval_event", event)
        self.log_action("retrieval", agent=agent, task_name=task_name, decision=decision,
                        strategy=strategy, snippet_count=snippets,
                        retrieval_agents=list(retrieval_agents or []))
        # One action per corpus consulted, not just the decision. Retrieval
        # adapters are per-source by nature, so this is where a new one shows up
        # without any further plumbing: whatever the sandbox puts in an
        # execution record travels through unchanged.
        for execution in executions or []:
            self.log_action(
                "retrieval_query",
                agent=agent,
                task_name=task_name,
                retrieval_agent=execution.get("agent", ""),
                status=execution.get("status", ""),
                tool_calls=execution.get("tool_calls", 0),
                detail=execution.get("detail", ""),
            )

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

    def to_dict_deep(self) -> dict:
        """The action log, plus enough summary to read it at a glance.

        Deliberately a separate document from ``to_dict``: that one is the
        artifact the benchmark and the evaluator parse, and its shape is a
        contract. This one is free to describe the run properly.
        """
        by_kind = Counter(action["kind"] for action in self.actions)
        by_actor: dict[str, Counter] = {}
        for action in self.actions:
            by_actor.setdefault(action["actor"] or "(none)", Counter())[action["kind"]] += 1

        return {
            "format": "deep",
            # A copy: the returned document is a snapshot, and anything appended
            # afterwards would otherwise grow the list while the counts beside it
            # stayed put.
            "actions": list(self.actions),
            "summary": {
                "action_count": len(self.actions),
                "by_kind": dict(by_kind),
                "by_actor": {actor: dict(kinds) for actor, kinds in by_actor.items()},
                "actors": [a for a in dict.fromkeys(x["actor"] for x in self.actions) if a],
                "latency_ms": self.latency_ms,
            },
        }
