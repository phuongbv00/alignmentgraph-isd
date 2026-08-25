"""Shared run scaffolding: build the graph, invoke it, assemble metadata.

``run_workflow`` creates a fresh ``AlignmentGraph``, calls ``workflow.build_workflow``,
invokes the compiled StateGraph, and packages the ADDIE output + trajectory +
metadata + the full alignment-graph dump (``graph`` / ``graph_dot`` — kept
separate from the trajectory so it can be written to its own file and
visualized directly).
"""
from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

from ..config import HarnessRunConfig
from .alignment_graph import AlignmentGraph
from .prose_store import ProseStore
from .workflow import build_workflow, empty_addie, initial_state
from .brief import DesignBrief
from .trajectory import TrajectoryLogger


def _llm_metadata(config: HarnessRunConfig) -> dict:
    """Model provenance for the record, read from the injected factory's model —
    the single source of truth — so it can never drift from what actually ran.
    Best-effort: introspection failures leave the fields blank, never break a run.
    ``model_name`` covers both ChatOpenAI (``model_name``) and ChatAnthropic
    (``model``)."""
    if config.llm_factory is None:
        return {}
    try:
        model = config.llm_factory()
        return {
            "model_name": getattr(model, "model_name", None) or getattr(model, "model", None) or "",
            "temperature": getattr(model, "temperature", None),
            "max_tokens": getattr(model, "max_tokens", None),
        }
    except Exception:  # noqa: BLE001 - metadata is never load-bearing
        return {}


def _token_usage_metadata(trajectory: TrajectoryLogger) -> dict:
    prompt = trajectory.token_usage.get("prompt_tokens", 0)
    completion = trajectory.token_usage.get("completion_tokens", 0)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
        "llm_calls": trajectory.llm_calls,
    }


def _maybe_dump_graph(graph: AlignmentGraph, design_brief: DesignBrief, metadata: dict) -> None:
    """Write ``<brief_id>_graph.json`` + ``<brief_id>_graph.dot`` when opted in
    via the ``ALIGNMENTGRAPH_DUMP_DIR`` env var. Opt-in and best-effort: a dump
    failure never breaks a run, it only annotates metadata."""
    dump_dir = os.environ.get("ALIGNMENTGRAPH_DUMP_DIR")
    if not dump_dir:
        return
    from .alignment_graph import viz

    brief_id = design_brief.id or "brief"
    stem = Path(dump_dir) / f"{brief_id}_graph"
    try:
        written = viz.dump(graph, stem, title=brief_id, design_brief_id=brief_id)
        metadata["graph_dump"] = [str(path) for path in written]
    except Exception as exc:  # noqa: BLE001 - visualization is never load-bearing
        metadata["graph_dump_error"] = str(exc)


# How often the live graph may be re-serialized while a phase is running. The
# graph is only meaningfully different after a specialist writes its nodes, so a
# consumer polling every edit would pay for ~55 snapshots to see ~14 distinct
# states. Phase boundaries are always snapshotted regardless of this floor.
_SNAPSHOT_MIN_INTERVAL_SECONDS = 0.75

# Kinds after which the graph is guaranteed to be in a consistent, worth-showing
# state. Everything else only triggers a snapshot once the interval above passes.
_SNAPSHOT_ALWAYS_AFTER = frozenset({"phase_finished"})


def _safe_emit(on_event, kind: str, payload: dict) -> None:
    """Emit from outside the TrajectoryLogger, with its same guarantees:
    a failing consumer is swallowed, but HarnessCancelled still propagates."""
    if on_event is None:
        return
    try:
        on_event(kind, payload)
    except Exception:  # noqa: BLE001 - observation is never load-bearing.
        pass


def _graph_attaching(on_event, graph: AlignmentGraph, design_brief: DesignBrief):
    """Wrap a consumer so it also receives ``graph_snapshot`` events.

    The alignment graph is the thing a viewer actually wants to watch, but it is
    not part of any recorded stream — it lives in this function's scope. So the
    snapshot is attached here, where the graph object is in hand.

    The snapshot is produced (and must be consumed) synchronously on the worker
    thread: ``to_full_dict`` returns the live node/edge dicts, which later nodes
    keep mutating. A consumer that stashes the object and serializes it later
    will read torn or silently-updated state.
    """
    last_snapshot_at = 0.0

    def emit(kind: str, payload: dict) -> None:
        nonlocal last_snapshot_at
        on_event(kind, payload)
        now = time.monotonic()
        if kind not in _SNAPSHOT_ALWAYS_AFTER and (now - last_snapshot_at) < _SNAPSHOT_MIN_INTERVAL_SECONDS:
            return
        last_snapshot_at = now
        on_event("graph_snapshot", graph.to_full_dict(design_brief_id=design_brief.id))

    return emit


def run_workflow(
    config: HarnessRunConfig,
    design_brief: DesignBrief,
    *,
    on_event=None,
) -> dict:
    # Exactly one context substrate per run (see config.py): the graph arm
    # gets an AlignmentGraph; the prose arm gets a ProseStore blackboard and
    # NO graph object at all — no graph observer, no snapshots, no dump, and
    # no ``graph``/``graph_dot`` result keys. A prose run has nothing to
    # audit; that absence is the auditability contrast, not an omission.
    prose = getattr(config, "context_mode", "graph") == "prose"
    graph = None if prose else AlignmentGraph()
    store = ProseStore() if prose else None
    attach_graph = on_event is not None and graph is not None
    trajectory = TrajectoryLogger(
        _graph_attaching(on_event, graph, design_brief) if attach_graph else on_event
    )
    if graph is not None:
        # The graph reports every read, relation walk, node write and alignment
        # edge to the trajectory, which stamps each with whichever agent is
        # acting. That is what the deep trajectory is made of; the recorded
        # streams are untouched.
        graph.set_observer(trajectory.graph_observer())
    compiled = build_workflow(config, graph, trajectory, design_brief, store)

    invoke_config = {"recursion_limit": 80, "configurable": {"thread_id": str(uuid.uuid4())}}
    final_state = compiled.invoke(initial_state(), invoke_config)

    addie_output = final_state.get("addie_output") or empty_addie()
    residual_violation_count = len(final_state.get("violations", []))
    repair_metrics = trajectory.summary_metrics(residual_violation_count)
    trajectory_payload = trajectory.finalize()
    metadata = {
        "llm": _llm_metadata(config),
        # The package's own accounting, in the benchmark accounter's shape.
        # Under the benchmark this whole dict is overwritten by the uniform
        # thread-local accounter, so exactly one copy ever ships.
        "token_usage": _token_usage_metadata(trajectory),
        # Resolved harness flags, so every result is self-describing — the
        # ablation pooling script verifies an arm actually ran the config its
        # agent id claims.
        "run_config": {
            "agent_mode": config.agent_mode,
            "context_mode": config.context_mode,
            "use_rag": config.use_rag,
            "regen_budget": config.regen_budget,
            "regen_backoff_seconds": config.regen_backoff_seconds,
            # Serving posture: a results dir has to say how many requests
            # the run was allowed to keep in flight, because that is the
            # difference between a 429-throttled arm and a clean one.
            "llm_max_concurrency": config.llm_max_concurrency,
            "llm_min_interval_seconds": config.llm_min_interval_seconds,
        },
        "design_brief_id": design_brief.id,
        "errors": final_state.get("errors", []),
        "validation_errors": final_state.get("validation_errors", []),
        # Residual violations live in audit.violations (the
        # auditor is handed the final state's list); their count is
        # repair_metrics.residual_violation_count. No separate top-level copy.
        "audit": final_state.get("audit", {}),
        "task_attempts": final_state.get("task_attempts", {}),
        "repair_metrics": repair_metrics,
    }
    result = {
        "addie_output": addie_output,
        "trajectory": trajectory_payload,
        # A parallel, far more detailed record of the same run: every graph
        # read, relation walk, node write and alignment edge, attributed to the
        # agent that did it. Its own key so the shape `trajectory` promises to
        # the benchmark and the evaluator is left completely alone.
        "trajectory_deep": trajectory.to_dict_deep(),
        "metadata": metadata,
    }
    if graph is not None:
        # The run is over; what follows is writing the report. Detached here so
        # the deep trajectory ends with the last thing an agent did, rather
        # than trailing the dozens of reads that serializing the graph performs.
        graph.set_observer(None)
        _maybe_dump_graph(graph, design_brief, metadata)
        # The full alignment-graph dump travels as its OWN result keys (not
        # inside trajectory/metadata) so integrations can write it to a
        # separate file (<agent_id>_graph.json / .dot) ready for auditing and
        # visualization. A prose run has no graph and therefore NO such keys —
        # the benchmark writes the files only when the keys exist.
        final_graph = graph.to_full_dict(design_brief_id=design_brief.id)
        # The aggregate node runs after the last phase_finished, so the
        # snapshot a consumer holds at this point is one step stale. Emit the
        # settled one.
        _safe_emit(on_event, "graph_snapshot", final_graph)
        result["graph"] = final_graph
        result["graph_dot"] = graph.to_dot(title=design_brief.id or "alignment-graph")
    if store is not None:
        # The prose arm's counterpart artifact: the blackboard documents
        # verbatim (saved as <agent_id>_prose.json by the benchmark). Raw
        # content for inspection/debugging only — it carries no relations or
        # coverage, so the "prose runs ship no alignment audit" contrast is
        # untouched.
        result["prose"] = store.to_full_dict(design_brief_id=design_brief.id)
    return result


class MetaAgent:
    """Public entry point. Runs the design brief through the shared scaffolding.
    Kept as a thin shim for backward compatibility (benchmark adapter, tests)."""

    def __init__(self, config: HarnessRunConfig) -> None:
        self.config = config

    def run(self, design_brief: DesignBrief, *, on_event=None) -> dict:
        return run_workflow(self.config, design_brief, on_event=on_event)
