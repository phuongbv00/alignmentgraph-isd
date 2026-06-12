from __future__ import annotations


class AlignmentGraph:
    NODE_TYPES = {"objective", "assessment", "activity", "material", "constraint", "evaluation", "needs_context"}
    EDGE_TYPES = {"measures", "supports", "requires", "constrains", "evaluates", "revises", "depends_on"}
    IMPACT_POLICY = {
        "needs_context": ("objective", "assessment", "activity", "material", "constraint", "evaluation"),
        "objective": ("assessment", "activity", "material", "evaluation"),
        "assessment": ("activity", "material", "evaluation"),
        "activity": ("material", "assessment", "constraint", "evaluation"),
        "material": ("activity", "assessment", "constraint", "evaluation"),
        "constraint": ("objective", "assessment", "activity", "material", "evaluation"),
        "evaluation": ("assessment",),
    }

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
            "stale": False,
            "stale_reasons": [],
        }

    def update_node(self, node_id: str, data: dict) -> None:
        """Merge new data into an existing node."""
        if node_id in self._nodes:
            self._nodes[node_id]["data"].update(data)

    def mark_repaired(self, node_id: str, reason: str) -> None:
        if node_id in self._nodes:
            self._nodes[node_id]["repair_history"].append(reason)
            self._nodes[node_id]["stale"] = False

    def mark_stale(self, node_id: str, reason: str) -> bool:
        if node_id in self._nodes:
            self._nodes[node_id]["stale"] = True
            reasons = self._nodes[node_id].setdefault("stale_reasons", [])
            if reason and reason not in reasons:
                reasons.append(reason)
            return True
        return False

    def clear_stale(self, node_id: str) -> None:
        if node_id in self._nodes:
            self._nodes[node_id]["stale"] = False
            self._nodes[node_id]["stale_reasons"] = []

    def invalidate_impacted(
        self,
        changed_node_id: str,
        *,
        changed_fields: list[str] | None = None,
        evidence: str = "",
        reason: str = "",
    ) -> dict[str, list]:
        """Mark graph elements impacted by a changed node as stale.

        This is the generic "oil spill" mechanism: any node that acts as a
        source of truth can force dependent nodes and their alignment edges to
        be recomputed by the policy router.
        """
        changed_node = self.get_node(changed_node_id)
        if not changed_node:
            return {"nodes": [], "edges": []}

        changed_type = changed_node.get("type", "")
        impacted_types = set(self.IMPACT_POLICY.get(changed_type, ()))
        if not impacted_types:
            return {"nodes": [], "edges": []}

        stale_reason = reason or f"{changed_type}:{changed_node_id} changed; impacted graph elements need refresh."
        if changed_fields:
            stale_reason = f"{stale_reason} changed_fields={','.join(changed_fields)}"

        affected_nodes: list[str] = []
        for node in self._nodes.values():
            if node.get("id") == changed_node_id:
                continue
            if node.get("type") in impacted_types and self.mark_stale(node["id"], stale_reason):
                affected_nodes.append(node["id"])

        affected_edges: list[dict] = []
        affected_node_ids = set(affected_nodes)
        for edge in self._edges:
            if not self._edge_touches(edge, affected_node_ids):
                continue
            if evidence and edge.get("evidence") and edge.get("evidence") != evidence:
                continue
            edge["verified"] = False
            edge["stale"] = True
            reasons = edge.setdefault("stale_reasons", [])
            if stale_reason not in reasons:
                reasons.append(stale_reason)
            affected_edges.append({
                "type": edge.get("type", ""),
                "source": edge.get("source", ""),
                "target": edge.get("target", ""),
                "evidence": edge.get("evidence", ""),
            })

        return {"nodes": affected_nodes, "edges": affected_edges}

    def _edge_touches(self, edge: dict, node_ids: set[str]) -> bool:
        return edge.get("source") in node_ids or edge.get("target") in node_ids

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
        edge = {
            "type": edge_type,
            "source": source_id,
            "target": target_id,
            "evidence": evidence,
            "rationale": rationale,
            "verified": verified,
            "stale": False,
            "stale_reasons": [],
        }
        if edge not in self._edges:
            self._edges.append(edge)

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
