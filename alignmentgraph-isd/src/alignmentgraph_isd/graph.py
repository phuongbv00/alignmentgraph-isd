from __future__ import annotations


class AlignmentGraph:
    NODE_TYPES = {"objective", "assessment", "activity", "material", "constraint", "evaluation", "needs_context"}
    EDGE_TYPES = {"measures", "supports", "requires", "constrains", "evaluates", "revises", "depends_on"}

    def __init__(self) -> None:
        self._nodes: dict[str, dict] = {}
        self._edges: list[dict] = []

    def add_node(
        self,
        node_type: str,
        node_id: str,
        data: dict | None = None,
        *,
        verified: bool = False,
        repair_history: list | None = None,
    ) -> None:
        self._nodes[node_id] = {
            "type": node_type,
            "id": node_id,
            "data": data or {},
            "verified": verified,
            "repair_history": repair_history or [],
        }

    def update_node(self, node_id: str, data: dict) -> None:
        """Merge new data into an existing node (used by RepairAgent)."""
        if node_id in self._nodes:
            self._nodes[node_id]["data"].update(data)

    def mark_repaired(self, node_id: str, reason: str) -> None:
        if node_id in self._nodes:
            self._nodes[node_id]["repair_history"].append(reason)

    def add_edge(
        self,
        edge_type: str,
        source_id: str,
        target_id: str,
        *,
        evidence: str = "",
        rationale: str = "",
        verified: bool = False,
    ) -> None:
        self._edges.append({
            "type": edge_type,
            "source": source_id,
            "target": target_id,
            "evidence": evidence,
            "rationale": rationale,
            "verified": verified,
        })

    def get_nodes(self, node_type: str | None = None) -> list[dict]:
        if node_type is None:
            return list(self._nodes.values())
        return [n for n in self._nodes.values() if n["type"] == node_type]

    def get_node(self, node_id: str) -> dict | None:
        return self._nodes.get(node_id)

    def get_edges(self, edge_type: str | None = None) -> list[dict]:
        if edge_type is None:
            return list(self._edges)
        return [e for e in self._edges if e["type"] == edge_type]

    def get_node_context(self, node_types: list[str], max_chars_per_node: int = 600) -> str:
        """Return a compact text summary of nodes for injection into agent prompts.

        This is the graph-subgraph RAG entry point: later agents call this to
        see what earlier agents already put in G_t before generating their section.
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

    def is_empty(self, node_type: str) -> bool:
        """True if no non-empty node of this type exists."""
        return all(not n["data"] for n in self.get_nodes(node_type))

    def to_dict(self) -> dict:
        return {"nodes": list(self._nodes.values()), "edges": list(self._edges)}
