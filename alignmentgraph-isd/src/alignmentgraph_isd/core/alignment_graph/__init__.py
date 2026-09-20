"""The AlignmentGraph subsystem — the artifact graph and everything only it
powers. This package is exactly the bundle the `context_mode` ablation axis
ablates: a `prose` run uses nothing from here (see config.py). Module-level
imports of ``NodeType`` do exist outside this package — it is a ``StrEnum``
whose members double as artifact-family keys — but every call that touches a
real graph is gated on ``context_mode`` (``HarnessRunConfig.context_mode``,
``RepairContext.graph_mode``), and a prose run
holds ``graph = None``, so a stray call raises rather than leaking silently.

- ``graph.py`` — ``AlignmentGraph`` + ``NodeType``: the element/section node
  store and its edge list.
- ``alignment.py`` — the ``REGISTRY`` of every edge kind (C2–C4 core + P1–P14
  provenance + S1–S2 structural) and the deterministic establishers. The
  18-relation alignment matrix is the ``MATRIX`` view of it: everything that
  MEASURES the construct iterates that, never the registry.
- ``audit.py`` — ``GraphAuditor``: the residual audit (unmeasured/
  unsupported/unevaluated objectives, relation coverage).
- ``viz.py`` — node-link/DOT dumps (`<agent_id>_graph.json` / `.dot`).

``AlignmentGraph`` and ``NodeType`` are re-exported here so the package move
kept every ``from .alignment_graph import AlignmentGraph, NodeType`` import
site working unchanged.
"""
from . import alignment, audit, viz
from .graph import AlignmentGraph, NodeType

__all__ = ["AlignmentGraph", "NodeType", "alignment", "audit", "viz"]
