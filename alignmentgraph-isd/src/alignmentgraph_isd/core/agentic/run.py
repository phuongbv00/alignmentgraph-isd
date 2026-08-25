"""Entry point of the agentic arm: run a design brief as 7 tool-loop steps.

EXPERIMENTAL ARM — selected only via the benchmark registry
(``alignmentgraph-isd-agentic``) or a direct call; nothing in ``core/``
dispatches here. Always graph-mode, multi-persona: the arm varies CONTROL
(scripted pipeline vs. act→observe loops), not the ablation axes.

Macro control stays deterministic on purpose: the step order is the fixed
artifact-family order and there is no cross-agent routing — violations
surface inside each step's own loop (rejected submits) and through the same
deterministic repair net the scripted arms use (``core/repairs.py``). The
result dict has full key parity with ``core/runner.py::run_workflow`` (the
packaging below is copied from it — keep in sync manually), plus
``metadata.run_config.control_mode = "agentic"``.
"""
from __future__ import annotations

import time
from contextlib import contextmanager

from .. import repairs
from ..agents.addie_aggregator import ADDIEOutputAggregator
from ..alignment_graph import AlignmentGraph
from ..alignment_graph.audit import GraphAuditor
from ..brief import DesignBrief
from ..trajectory import TrajectoryLogger, WORKFLOW_ORCHESTRATOR
from ..validation import validate_addie
from ..runner import (
    _graph_attaching, _llm_metadata, _maybe_dump_graph, _safe_emit,
    _token_usage_metadata,
)
from ..workflow import SELF_VALIDATION_BUDGET, _collect_violations, empty_addie
from .loop import AgenticLLM, ToolLoop
from .specialists import STEPS, step_done


@contextmanager
def _phase(trajectory: TrajectoryLogger, phase: str, index: int, total: int):
    """Copied from ``NodeFactory._phase`` (core/workflow.py) — keep in sync
    manually — so live consumers see the same phase_started/phase_finished
    stream an ordinary run emits."""
    trajectory.emit("phase_started", {"phase": phase, "index": index, "total": total})
    started = time.time()
    with trajectory.acting_as("", phase=phase):
        # Explicit agent: see the matching comment on NodeFactory._phase.
        trajectory.log_action("phase_started", agent=WORKFLOW_ORCHESTRATOR,
                              phase=phase, index=index, total=total)
        try:
            yield
        finally:
            duration_ms = (time.time() - started) * 1000
            trajectory.log_action(
                "phase_finished", agent=WORKFLOW_ORCHESTRATOR,
                phase=phase, index=index, total=total, duration_ms=duration_ms)
            trajectory.emit("phase_finished", {
                "phase": phase, "index": index, "total": total, "duration_ms": duration_ms})


def _serialize(violations: list, owner: str) -> list[dict]:
    return [
        {"node_id": v.node_id, "type": v.violation_type, "msg": v.message,
         "severity": v.severity, "owner": owner}
        for v in violations
    ]


def run_agentic_brief(config, design_brief: DesignBrief, *, on_event=None) -> dict:
    graph = AlignmentGraph()
    attach_graph = on_event is not None
    trajectory = TrajectoryLogger(
        _graph_attaching(on_event, graph, design_brief) if attach_graph else on_event)
    graph.set_observer(trajectory.graph_observer())

    phase_total = len(STEPS) + 1  # steps + aggregate
    regen_budget = max(0, int(getattr(config, "regen_budget", 2)))
    backoff = max(0.0, float(getattr(config, "regen_backoff_seconds", 0.0)))

    errors: list[str] = []
    residual: list[dict] = []
    task_attempts: dict[str, int] = {}

    for index, step in enumerate(STEPS, start=1):
        with _phase(trajectory, step.name, index, phase_total):
            llm = AgenticLLM(config, trajectory, step.identity)
            with trajectory.acting_as(step.identity):
                # ── generation: the tool loop, with the shared regen posture ──
                for attempt in range(regen_budget + 1):
                    if attempt > 0 and backoff:
                        time.sleep(backoff * attempt)
                    try:
                        ToolLoop(config, graph, trajectory, design_brief, step, llm).run()
                    except Exception as exc:  # noqa: BLE001 - same containment as run_generation_step
                        errors.append(f"{step.identity}: {exc}")
                        trajectory.log_recovery_event(
                            step.identity, "agent_error", "", str(exc)[:400])
                        continue
                    if step_done(step, graph):
                        break
                    trajectory.log_recovery_event(
                        step.identity, "regen_empty_section", f"attempt {attempt + 1}", step.name)

                # ── deterministic repair net: same checks, same budget, same
                # toolbox as the scripted arms ──
                ctx = repairs.RepairContext(
                    graph=graph, store=None, trajectory=trajectory,
                    call_llm=llm, actor=step.identity)
                owned: list = []
                for _ in range(SELF_VALIDATION_BUDGET):
                    violations = _collect_violations(step.family, graph, design_brief)
                    owned = [v for v in violations
                             if v.violation_type in repairs.OWNED_BY_FAMILY[step.family]]
                    trajectory.log_violations_result(_serialize(owned, step.identity))
                    if not owned:
                        break
                    repairs.repair(step.family, owned, ctx)
                residual += _serialize(owned, step.identity)
            task_attempts[step.name] = task_attempts.get(step.name, 0) + 1

    # ── aggregation + residual audit (mirrors NodeFactory.aggregate_node) ────
    with _phase(trajectory, "aggregate", phase_total, phase_total):
        # One scope for assembly + its own validation, so log_validation_result
        # doesn't fall back to a stale actor once aggregate() returns.
        with trajectory.acting_as(ADDIEOutputAggregator.__name__):
            try:
                addie_output = ADDIEOutputAggregator(config, graph, trajectory).aggregate()
            except Exception:  # noqa: BLE001 - aggregation failure must not lose the run
                addie_output = empty_addie()
            validation_errors = validate_addie(addie_output)
            trajectory.log_validation_result("addie_output", validation_errors)
        # Reads the final settled graph across every step's work, not the
        # aggregator's own — same WorkflowOrchestrator attribution as the
        # multi arm's routing checkpoints (there is no router here, but the
        # audit is the same whole-pipeline operation).
        with trajectory.acting_as(WORKFLOW_ORCHESTRATOR):
            audit_result = GraphAuditor(graph).audit(residual)
            trajectory.log_audit_result(audit_result, agent=WORKFLOW_ORCHESTRATOR)
            audit = audit_result.to_dict()

    repair_metrics = trajectory.summary_metrics(len(residual))
    trajectory_payload = trajectory.finalize()
    metadata = {
        "llm": _llm_metadata(config),
        "token_usage": _token_usage_metadata(trajectory),
        "run_config": {
            "agent_mode": "multi",
            "context_mode": "graph",
            "control_mode": "agentic",
            "max_turns": ToolLoop.MAX_TURNS,
            "submit_budget": ToolLoop.SUBMIT_BUDGET,
            "use_rag": config.use_rag,
            "regen_budget": regen_budget,
            "regen_backoff_seconds": backoff,
            # Serving posture: a results dir has to say how many requests
            # the run was allowed to keep in flight, because that is the
            # difference between a 429-throttled arm and a clean one.
            "llm_max_concurrency": config.llm_max_concurrency,
            "llm_min_interval_seconds": config.llm_min_interval_seconds,
        },
        "design_brief_id": design_brief.id,
        "errors": errors,
        "validation_errors": validation_errors,
        "audit": audit,
        "task_attempts": task_attempts,
        "repair_metrics": repair_metrics,
    }
    result = {
        "addie_output": addie_output,
        "trajectory": trajectory_payload,
        "trajectory_deep": trajectory.to_dict_deep(),
        "metadata": metadata,
    }
    # Report writing — detach the observer so the deep trajectory ends with
    # the last thing an agent did (same as core/runner.py).
    graph.set_observer(None)
    _maybe_dump_graph(graph, design_brief, metadata)
    final_graph = graph.to_full_dict(design_brief_id=design_brief.id)
    _safe_emit(on_event, "graph_snapshot", final_graph)
    result["graph"] = final_graph
    result["graph_dot"] = graph.to_dot(title=design_brief.id or "alignment-graph")
    return result
