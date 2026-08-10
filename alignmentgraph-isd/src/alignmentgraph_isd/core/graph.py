from __future__ import annotations

from enum import StrEnum


class NodeType(StrEnum):
    """Artifact category of a graph node (one per ADDIE-phase concern).

    ``StrEnum`` members ARE their string value, so they stay JSON-serializable
    and interoperate with the plain strings that output deserialization produces
    (``NodeType.OBJECTIVE == "objective"``).
    """

    NEEDS_CONTEXT = "needs_context"
    OBJECTIVE = "objective"
    ASSESSMENT = "assessment"
    ACTIVITY = "activity"
    MATERIAL = "material"
    IMPLEMENTATION_PLAN = "implementation_plan"
    EVALUATION = "evaluation"


class AlignmentGraph:
    """Alignment-dependency graph of ISD artifacts.

    Nodes carry only ``{type, id, data}``. Edges carry
    ``{type, source, target, relation_id, established_by, evidence, rationale}``
    where ``type`` is the human-readable relation key ("R3-measures") and
    ``relation_id`` is the bare matrix id ("R3") used for coverage indexing. An
    edge exists iff a deterministic establisher (see ``alignment.py``) confirmed
    it — there is no ``verified``/``stale`` state, no cascade invalidation.
    """

    NODE_TYPES = frozenset(NodeType)
    SECTION_SUFFIX = "_0"
    # Element node ids are namespaced as "<type>:<element_id>" (e.g.
    # "objective:LO-01"). Section nodes keep the legacy "<type>_0" form.
    ELEMENT_SEP = ":"

    @classmethod
    def section_id(cls, node_type: NodeType | str) -> str:
        """Canonical id of the singleton section node for a type (e.g. ``objective_0``)."""
        return f"{node_type}{cls.SECTION_SUFFIX}"

    def __init__(self, observer=None) -> None:
        # Every read and write passes through this object, which makes it the
        # one place that can see what an agent actually did with the graph —
        # instrumenting the ~40 call sites individually would drift the first
        # time one moved. Default None: no observer, no behaviour change, and
        # nothing for the benchmark to notice.
        self._observer = observer
        self._nodes: dict[str, dict] = {}
        self._edges: list[dict] = []
        # Adjacency index for neighbors()/traverse(). Rebuilt lazily on read
        # after any add_edge; edge dicts are shared by reference.
        self._adj_dirty: bool = True
        self._out_index: dict[str, list[dict]] = {}
        self._in_index: dict[str, list[dict]] = {}

    def set_observer(self, observer) -> None:
        """Attach the observer after construction.

        Needed because the recorder and the graph each want a reference to the
        other: the graph reports to the trajectory, and the trajectory's own
        live-event wrapper needs the graph in order to attach snapshots.
        """
        self._observer = observer

    def _observe(self, kind: str, **fields) -> None:
        """Report one graph operation. Never load-bearing.

        ``Exception`` only, so a cancellation raised by the consumer still
        propagates — the same rule the trajectory hook follows.
        """
        if self._observer is None:
            return
        try:
            self._observer(kind, fields)
        except Exception:  # noqa: BLE001 - observation must not break a run
            pass

    # ── nodes ───────────────────────────────────────────────────────────────
    def add_node(self, node_type: NodeType | str, node_id: str, data: dict | None = None) -> None:
        existed = node_id in self._nodes
        self._nodes[node_id] = {"type": node_type, "id": node_id, "data": data or {}}
        self._observe(
            "node_write",
            op="replace" if existed else "add",
            node_id=node_id,
            node_type=str(node_type),
            fields=sorted(data or {}),
        )

    def update_node(self, node_id: str, data: dict) -> None:
        """Merge new data into an existing node."""
        if node_id in self._nodes:
            self._nodes[node_id]["data"].update(data)
            self._observe(
                "node_write",
                op="update",
                node_id=node_id,
                node_type=str(self._nodes[node_id]["type"]),
                fields=sorted(data or {}),
            )

    def add_element_node(
        self, node_type: NodeType | str, element_id: str, data: dict | None = None
    ) -> str:
        """Add a first-class element node (one artifact item) and return its id."""
        node_id = f"{node_type}{self.ELEMENT_SEP}{element_id}"
        self.add_node(node_type, node_id, data)
        return node_id

    def is_element(self, node_id: str) -> bool:
        return self.ELEMENT_SEP in node_id

    def get_nodes(self, node_type: NodeType | str | None = None) -> list[dict]:
        if node_type is None:
            found = list(self._nodes.values())
        else:
            found = [n for n in self._nodes.values() if n["type"] == node_type]
        self._observe("node_read", query="get_nodes", node_type=str(node_type or "*"),
                      result_count=len(found))
        return found

    def section_nodes(self, node_type: NodeType | str) -> list[dict]:
        """Section nodes (the aggregate payload), excluding element nodes."""
        found = [
            n for n in self._nodes.values()
            if n["type"] == node_type and not self.is_element(n["id"])
        ]
        self._observe("node_read", query="section_nodes", node_type=str(node_type),
                      result_count=len(found))
        return found

    def element_nodes(self, node_type: NodeType | str) -> list[dict]:
        """First-class element nodes for one artifact type."""
        found = [
            n for n in self._nodes.values()
            if n["type"] == node_type and self.is_element(n["id"])
        ]
        self._observe("node_read", query="element_nodes", node_type=str(node_type),
                      result_count=len(found))
        return found

    def get_node(self, node_id: str) -> dict | None:
        found = self._nodes.get(node_id)
        self._observe("node_read", query="get_node", node_id=node_id,
                      result_count=1 if found else 0)
        return found

    # ── edges ───────────────────────────────────────────────────────────────
    def add_edge(
        self,
        edge_type: str,
        source_id: str,
        target_id: str,
        *,
        evidence: str = "",
        rationale: str = "",
        relation_id: str = "",
        established_by: str = "",
    ) -> None:
        """Add an alignment edge.

        ``edge_type`` is the relation key ("R3-measures"); ``relation_id``
        (R1..R13) and ``established_by`` (id|type|provenance) are resolved by
        callers from the (source_type, target_type) pair via ``alignment.py``'s
        registry, not here (avoids a graph<->alignment import cycle).

        Edge identity is ``(type, source, target, relation_id)``. Re-establishing
        the same link refreshes its evidence/rationale in place instead of
        appending a duplicate.
        """
        existing = self._find_edge(edge_type, source_id, target_id, relation_id)
        if existing is not None:
            if evidence:
                existing["evidence"] = evidence
            if rationale:
                existing["rationale"] = rationale
            if established_by:
                existing["established_by"] = established_by
            self._observe(
                "edge_write", op="refresh", edge_type=edge_type, source=source_id,
                target=target_id, relation_id=relation_id,
                established_by=established_by, evidence=evidence,
            )
            return
        self._edges.append({
            "type": edge_type,
            "source": source_id,
            "target": target_id,
            "evidence": evidence,
            "rationale": rationale,
            "relation_id": relation_id,
            "established_by": established_by,
        })
        self._adj_dirty = True
        # The alignment relations are the contribution, and until now the only
        # trace of them was the finished dump — nothing said which step drew
        # which link, or on what evidence.
        self._observe(
            "edge_write", op="add", edge_type=edge_type, source=source_id,
            target=target_id, relation_id=relation_id,
            established_by=established_by, evidence=evidence, rationale=rationale,
        )

    def _find_edge(
        self, edge_type: str, source_id: str, target_id: str, relation_id: str
    ) -> dict | None:
        """The edge with this (type, source, target, relation_id) identity, if any."""
        for edge in self._edges:
            if (
                edge["type"] == edge_type
                and edge["source"] == source_id
                and edge["target"] == target_id
                and edge.get("relation_id", "") == relation_id
            ):
                return edge
        return None

    def get_edges(
        self,
        edge_type: str | None = None,
        *,
        relation_id: str | None = None,
        target: str | None = None,
        source: str | None = None,
    ) -> list[dict]:
        edges = self._edges
        if edge_type is not None:
            edges = [e for e in edges if e["type"] == edge_type]
        if relation_id is not None:
            edges = [e for e in edges if e.get("relation_id") == relation_id]
        if target is not None:
            edges = [e for e in edges if e.get("target") == target]
        if source is not None:
            edges = [e for e in edges if e.get("source") == source]
        self._observe(
            "edge_read", query="get_edges", edge_type=edge_type or "*",
            relation_id=relation_id or "*", result_count=len(edges),
        )
        return list(edges)

    # ── traversal (adjacency index, lazily rebuilt) ─────────────────────────
    def _ensure_index(self) -> None:
        if not self._adj_dirty:
            return
        self._out_index = {}
        self._in_index = {}
        for edge in self._edges:
            self._out_index.setdefault(edge["source"], []).append(edge)
            self._in_index.setdefault(edge["target"], []).append(edge)
        self._adj_dirty = False

    def neighbors(
        self,
        node_id: str,
        edge_type: str | None = None,
        *,
        relation_id: str | None = None,
        direction: str = "out",
    ) -> list[dict]:
        """Nodes reachable from ``node_id`` by one alignment edge.

        ``direction="out"`` follows edges where ``node_id`` is the source
        (default); ``"in"`` follows edges where it is the target.
        """
        result = self._neighbors_raw(node_id, edge_type, relation_id=relation_id, direction=direction)
        self._observe(
            "edge_walk", query="neighbors", node_id=node_id,
            edge_type=edge_type or "*", direction=direction, result_count=len(result),
        )
        return result

    def _neighbors_raw(
        self,
        node_id: str,
        edge_type: str | None = None,
        *,
        relation_id: str | None = None,
        direction: str = "out",
    ) -> list[dict]:
        """One hop, unobserved — the shared body of ``neighbors`` and
        ``traverse``. Kept separate so a multi-hop traversal reports itself once
        as the relation walk an agent actually asked for, rather than once per
        hop and once per node visited."""
        self._ensure_index()
        index = self._out_index if direction == "out" else self._in_index
        result: list[dict] = []
        for edge in index.get(node_id, []):
            if edge_type is not None and edge["type"] != edge_type:
                continue
            if relation_id is not None and edge.get("relation_id") != relation_id:
                continue
            other_id = edge["target"] if direction == "out" else edge["source"]
            node = self._nodes.get(other_id)
            if node is not None:
                result.append(node)
        return result

    def traverse(
        self,
        start_id: str,
        rel_path: list[str | None],
        *,
        direction: str = "out",
    ) -> list[dict]:
        """Follow a chain of edge types from ``start_id``, hop by hop.

        Each entry in ``rel_path`` is an edge type to follow at that hop (or
        ``None`` to follow any edge type). Returns the node dicts reached after
        the last hop. This is the multi-hop primitive Development specialists use
        to reach an objective through an intervening Design "plan" node.
        """
        frontier_ids = [start_id]
        # Each hop is recorded with the frontier it started from and where it
        # landed, so the walk can be replayed edge by edge rather than shown as
        # a single before/after. Reaching an objective from a Development
        # artifact is a two-hop path through a Design plan node, and seeing the
        # intermediate hop is the whole point.
        hops: list[dict] = []
        for edge_type in rel_path:
            next_ids: list[str] = []
            seen: set[str] = set()
            edges_followed: list[dict] = []
            for node_id in frontier_ids:
                for node in self._neighbors_raw(node_id, edge_type, direction=direction):
                    edges_followed.append({"from": node_id, "to": node["id"]})
                    if node["id"] not in seen:
                        seen.add(node["id"])
                        next_ids.append(node["id"])
            hops.append({
                "edge_type": str(edge_type) if edge_type is not None else "*",
                "from": list(frontier_ids),
                "to": list(next_ids),
                "edges": edges_followed,
            })
            frontier_ids = next_ids
        reached = [n for n in (self._nodes.get(nid) for nid in frontier_ids) if n is not None]
        self._observe(
            "edge_walk", query="traverse", node_id=start_id,
            rel_path=[str(r) if r is not None else "*" for r in rel_path],
            direction=direction, hops=hops, result_count=len(reached),
        )
        return reached

    def is_empty(self, node_type: NodeType | str) -> bool:
        """True if no non-empty node of this type exists."""
        return all(not n["data"] for n in self.get_nodes(node_type))

    def to_dict(self) -> dict:
        return {"nodes": list(self._nodes.values()), "edges": list(self._edges)}

    def to_full_dict(self, *, design_brief_id: str | None = None) -> dict:
        """Complete, JSON-serializable dump of the alignment state for auditing.

        Everything is included: every node (id, type, full ``data`` payload),
        every edge (source, target, relation key like "R3-measures",
        ``relation_id``, ``established_by``, evidence, rationale), the
        per-objective / per-relation alignment annotations from the single
        alignment definition (``alignment.py`` via ``viz.py``), plus a
        ``metadata`` block (design brief id, UTC timestamp, node/edge counts by
        type). This is the payload written to ``*_graph.json`` — separate from
        the trajectory — so a human can audit or visualize the run's alignment
        state directly.
        """
        from datetime import datetime, timezone
        from . import viz  # lazy: viz imports this module

        payload = viz.to_node_link(self, include_data=True)
        node_counts: dict[str, int] = {}
        for node in self._nodes.values():
            node_counts[str(node["type"])] = node_counts.get(str(node["type"]), 0) + 1
        edge_counts: dict[str, int] = {}
        for edge in self._edges:
            edge_counts[str(edge["type"])] = edge_counts.get(str(edge["type"]), 0) + 1
        payload["metadata"] = {
            "design_brief_id": design_brief_id or "",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "node_count": len(self._nodes),
            "edge_count": len(self._edges),
            "node_counts_by_type": node_counts,
            "edge_counts_by_type": edge_counts,
        }
        return payload

    def to_dot(self, *, title: str = "") -> str:
        """GraphViz DOT rendering of the alignment graph (see ``viz.to_dot``):
        node shape/fill by node type and alignment state, edge labels by
        relation key, DOT-escaped labels (unicode content stays valid). Render
        with ``dot -Tsvg out.dot -o out.svg``."""
        from . import viz  # lazy: viz imports this module

        return viz.to_dot(self, title=title)

    @classmethod
    def from_dict(cls, payload: dict) -> "AlignmentGraph":
        graph = cls()
        for node in payload.get("nodes", []):
            if not isinstance(node, dict):
                continue
            node_id = node.get("id")
            node_type = node.get("type")
            if not node_id or not node_type:
                continue
            graph._nodes[node_id] = {"type": node_type, "id": node_id, "data": node.get("data", {})}
        for edge in payload.get("edges", []):
            if isinstance(edge, dict):
                graph._edges.append({
                    "type": edge.get("type", ""),
                    "source": edge.get("source", ""),
                    "target": edge.get("target", ""),
                    "evidence": edge.get("evidence", ""),
                    "rationale": edge.get("rationale", ""),
                    "relation_id": edge.get("relation_id", ""),
                    "established_by": edge.get("established_by", ""),
                })
        graph._adj_dirty = True
        return graph
