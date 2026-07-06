"""Tuning entrypoint: turn an explicit edit request into targeted graph invalidation.

A tuning session loads a committed AlignmentGraph and must express "what changed"
before the audit → planner → repair loop can regenerate only the affected parts.
This module is that translation step. The ``tuning_request:`` reason prefix is the
contract the case-study metrics rely on to tell tuning cascades apart from the
cascades that ordinary in-run repairs emit.
"""

from __future__ import annotations

from .graph import AlignmentGraph
from .schema import _LenientModel
from .trajectory import TrajectoryLogger

TUNING_REASON_PREFIX = "tuning_request:"


class TuningRequest(_LenientModel):
    """One edit request against an existing training-program graph.

    ``target_node_id`` names the graph node the request changes (e.g.
    ``objective_0``); downstream impact is derived from ``IMPACT_POLICY``, not
    listed here.
    """

    id: str = ""
    target_node_id: str = ""
    summary: str = ""
    instruction: str = ""
    changed_fields: list[str] = []
    # "targeted": stale the target + its IMPACT_POLICY downstream (proposed
    # mechanism). "regenerate_all": stale every node — the fair full-regeneration
    # baseline that sees the same prior graph/context but has no scoping.
    scope: str = "targeted"


def apply_tuning_request(
    graph: AlignmentGraph,
    trajectory: TrajectoryLogger,
    request: TuningRequest,
) -> dict[str, list]:
    """Mark the target node and its IMPACT_POLICY downstream as stale.

    Returns the impact dict from ``invalidate_impacted`` (empty lists when the
    target node does not exist, in which case a ``tuning_error`` step is logged
    instead of raising — the run then behaves like a plain re-verify session).
    """
    reason = f"{TUNING_REASON_PREFIX}{request.id}: {request.summary or request.instruction[:120]}"

    if request.scope == "regenerate_all":
        stale_nodes = [node["id"] for node in graph.to_dict()["nodes"]]
        for node_id in stale_nodes:
            graph.mark_stale(node_id, reason)
        trajectory.log_cascade_event(request.target_node_id or "*", stale_nodes, [], reason)
        trajectory.log_step(
            "TuningEntrypoint",
            "apply_tuning_request",
            request.id,
            f"scope=regenerate_all stale nodes={len(stale_nodes)}",
        )
        return {"nodes": stale_nodes, "edges": []}

    if not graph.mark_stale(request.target_node_id, reason):
        trajectory.log_step(
            "TuningEntrypoint",
            "tuning_error",
            request.id,
            f"target node not found: {request.target_node_id!r}",
        )
        return {"nodes": [], "edges": []}

    impact = graph.invalidate_impacted(
        request.target_node_id,
        changed_fields=list(request.changed_fields or []),
        reason=reason,
    )
    stale_nodes = [request.target_node_id] + impact["nodes"]
    trajectory.log_cascade_event(request.target_node_id, stale_nodes, impact["edges"], reason)
    trajectory.log_step(
        "TuningEntrypoint",
        "apply_tuning_request",
        request.id,
        f"stale nodes={stale_nodes} stale edges={len(impact['edges'])}",
    )
    return impact
