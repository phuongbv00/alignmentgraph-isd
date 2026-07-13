"""Per-arm workflow registry.

Each workflow assembles core nodes into a complete LangGraph graph with no
ablation flags — the arm IS the configuration. ``build_graph`` has a uniform
signature ``(config, graph, trajectory, context_pack, design_brief) -> CompiledGraph``.
"""
from __future__ import annotations

from . import dynamic, full, wo_ma, wo_qc

WORKFLOWS = {
    "full": full.build_graph,
    "wo_ma": wo_ma.build_graph,
    "wo_qc": wo_qc.build_graph,
    "dynamic": dynamic.build_graph,
}

__all__ = ["WORKFLOWS"]
