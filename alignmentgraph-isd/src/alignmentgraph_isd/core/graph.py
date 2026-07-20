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

    def __init__(self) -> None:
        self._nodes: dict[str, dict] = {}
        self._edges: list[dict] = []
        # Adjacency index for neighbors()/traverse(). Rebuilt lazily on read
        # after any add_edge; edge dicts are shared by reference.
        self._adj_dirty: bool = True
        self._out_index: dict[str, list[dict]] = {}
        self._in_index: dict[str, list[dict]] = {}

    # ── nodes ───────────────────────────────────────────────────────────────
    def add_node(self, node_type: NodeType | str, node_id: str, data: dict | None = None) -> None:
        self._nodes[node_id] = {"type": node_type, "id": node_id, "data": data or {}}

    def update_node(self, node_id: str, data: dict) -> None:
        """Merge new data into an existing node."""
        if node_id in self._nodes:
            self._nodes[node_id]["data"].update(data)

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
            return list(self._nodes.values())
        return [n for n in self._nodes.values() if n["type"] == node_type]

    def section_nodes(self, node_type: NodeType | str) -> list[dict]:
        """Section nodes (the aggregate payload), excluding element nodes."""
        return [n for n in self._nodes.values() if n["type"] == node_type and not self.is_element(n["id"])]

    def element_nodes(self, node_type: NodeType | str) -> list[dict]:
        """First-class element nodes for one artifact type."""
        return [n for n in self._nodes.values() if n["type"] == node_type and self.is_element(n["id"])]

    def get_node(self, node_id: str) -> dict | None:
        return self._nodes.get(node_id)

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
        self._ensure_index()
        index = self._out_index if direction == "out" else self._in_index
        result: list[dict] = []
        for edge in index.get(node_id, []):
            if edge_type is not None and edge["type"] != edge_type:
                continue
            if relation_id is not None and edge.get("relation_id") != relation_id:
                continue
            other_id = edge["target"] if direction == "out" else edge["source"]
            node = self.get_node(other_id)
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
        for edge_type in rel_path:
            next_ids: list[str] = []
            seen: set[str] = set()
            for node_id in frontier_ids:
                for node in self.neighbors(node_id, edge_type, direction=direction):
                    if node["id"] not in seen:
                        seen.add(node["id"])
                        next_ids.append(node["id"])
            frontier_ids = next_ids
        return [n for n in (self.get_node(nid) for nid in frontier_ids) if n is not None]

    def get_node_context(self, node_types: list[NodeType | str], max_chars_per_node: int = 600) -> str:
        """Return a compact text summary of nodes for injection into agent prompts.

        This is the graph-context retrieval entry point (core, not RAG): later
        agents call this to see what earlier agents already put in the graph
        before generating their section.
        """
        import json
        lines: list[str] = []
        for nt in node_types:
            for node in self.get_nodes(nt):
                data_str = json.dumps(node["data"], ensure_ascii=False)
                if len(data_str) > max_chars_per_node:
                    data_str = data_str[:max_chars_per_node] + "…"
                lines.append(f"[{nt.upper()}:{node['id']}]\n{data_str}")
        return "\n\n".join(lines)

    def is_empty(self, node_type: NodeType | str) -> bool:
        """True if no non-empty node of this type exists."""
        return all(not n["data"] for n in self.get_nodes(node_type))

    def to_dict(self) -> dict:
        return {"nodes": list(self._nodes.values()), "edges": list(self._edges)}

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
