"""Shared run scaffolding: build the graph, invoke it, assemble metadata.

``run_workflow`` creates a fresh ``AlignmentGraph``, calls ``nodes.build_graph``
(which branches on the arm), invokes the compiled StateGraph, and packages the
ADDIE output + trajectory + metadata.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

from ..config import HarnessRunConfig
from .graph import AlignmentGraph
from .nodes import build_graph, empty_addie, initial_state
from .schema import DesignBrief
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


def _maybe_dump_graph(graph, design_brief: DesignBrief, arm: str, metadata: dict) -> None:
    """Write ``<stem>.json`` + ``<stem>.dot`` for visualization when opted in
    via the ``ALIGNMENTGRAPH_DUMP_DIR`` env var. Opt-in and best-effort: a dump
    failure never breaks a run, it only annotates metadata."""
    dump_dir = os.environ.get("ALIGNMENTGRAPH_DUMP_DIR")
    if not dump_dir:
        return
    from . import viz

    brief_id = design_brief.id or "brief"
    stem = Path(dump_dir) / f"{brief_id}_{arm}_graph"
    try:
        written = viz.dump(graph, stem, title=f"{brief_id} · {arm}")
        metadata["graph_dump"] = [str(path) for path in written]
    except Exception as exc:  # noqa: BLE001 - visualization is never load-bearing
        metadata["graph_dump_error"] = str(exc)


def run_workflow(config: HarnessRunConfig, design_brief: DesignBrief) -> dict:
    graph = AlignmentGraph()
    trajectory = TrajectoryLogger()
    compiled = build_graph(config, graph, trajectory, design_brief)

    invoke_config = {"recursion_limit": 80, "configurable": {"thread_id": str(uuid.uuid4())}}
    final_state = compiled.invoke(initial_state(), invoke_config)

    addie_output = final_state.get("addie_output") or empty_addie()
    residual_violation_count = len(final_state.get("violations", []))
    repair_metrics = trajectory.summary_metrics(residual_violation_count)
    trajectory_payload = trajectory.finalize()
    # Snapshot the real internal alignment graph (node-link + per-objective and
    # per-relation annotations) so every run's _trajectory.json carries it.
    from . import viz
    graph_snapshot = viz.to_node_link(graph, include_data=False)
    metadata = {
        "ablation": config.ablation.model_dump(),
        "llm": _llm_metadata(config),
        "design_brief_id": design_brief.id,
        "violations": final_state.get("violations", []),
        "errors": final_state.get("errors", []),
        "validation_errors": final_state.get("validation_errors", []),
        "schema_violations": final_state.get("audit", {}).get("schema_violations", {}),
        "audit": final_state.get("audit", {}),
        "task_attempts": final_state.get("task_attempts", {}),
        "repair_metrics": repair_metrics,
        "graph": graph_snapshot,
    }
    # Name the dump by the ARM identity (full/wo_graph/wo_ma/…) so one arm's
    # dump never overwrites another's.
    _maybe_dump_graph(graph, design_brief, config.ablation.arm or "run", metadata)
    return {
        "addie_output": addie_output,
        "trajectory": trajectory_payload,
        "metadata": metadata,
    }


class MetaAgent:
    """Public entry point. Runs the design brief through the shared scaffolding.
    Kept as a thin shim for backward compatibility (benchmark adapter, tests)."""

    def __init__(self, config: HarnessRunConfig) -> None:
        self.config = config

    def run(self, design_brief: DesignBrief) -> dict:
        return run_workflow(self.config, design_brief)
