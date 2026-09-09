from __future__ import annotations

import threading
from contextlib import contextmanager
from enum import StrEnum


class NodeType(StrEnum):
    """Artifact category of a graph node.

    ``StrEnum`` members ARE their string value, so they stay JSON-serializable
    and interoperate with the plain strings that output deserialization produces
    (``NodeType.OBJECTIVE == "objective"``).

    Core (participate in the C1-C5 construct-validity relations, see
    ``alignment.py::REGISTRY``): ``COURSE_GOAL``, ``OBJECTIVE`` (Intended Learning
    Outcome / ILO), ``ASSESSMENT`` (Assessment Task / AT), ``ACTIVITY``
    (Teaching/Learning Activity / TLA), ``CONTENT`` (Content Module).

    Support (participate in the P1-P11 secondary/provenance relations, or are
    "plan" artifacts a core type executes against — see ``alignment.py``):
    ``GAP``, ``TOPIC``, ``LEARNER_PROFILE``, ``CONSTRAINT``, ``IMPROVEMENT``,
    ``MEDIA_SELECTION``, ``MATERIAL``, ``ASSESSMENT_PLAN``, ``ACTIVITY_PLAN``.

    ``IMPLEMENTATION_PLAN`` is the Implementation Planner's section document
    (orientation, system check, pilot, monitoring, and the instructor guide's
    and operator manual's narrative fields). ``SESSION_GUIDE`` is the element
    list that used to live inside it as ``instructor_guide.session_guides``:
    one node per delivery session, and the SOURCE of the P10/P11 delivery
    provenance edges. It was promoted to an element type on 2026-09-07 for two
    reasons. It is an ITEM LIST, and the rule since 2026-08-27 is that element
    nodes are the single source of truth for every item list — a section node
    holding one was the last exception. And it is the only part of the
    implementation artifact whose length scales with the design: a planner
    asked to name every activity id in one submit cannot see them all
    (``tools.render_listing`` truncates at ``READ_CHAR_BUDGET``) and cannot
    write them all under the completion cap, which is what the Developer tier
    exists for. ``aggregate`` joins the nodes back under
    ``instructor_guide.session_guides``, so the ADDIE output contract is
    unchanged.

    The ADDIE output's ``analysis``/``evaluation`` phases have no node type of
    their own: ``ADDIEOutputAggregator`` computes them from the real nodes
    (Gap/Topic/LearnerProfile/Constraint/Improvement/the Assessment pool).
    """

    COURSE_GOAL = "course_goal"
    OBJECTIVE = "objective"
    ASSESSMENT = "assessment"
    ACTIVITY = "activity"
    CONTENT = "content"

    GAP = "gap"
    TOPIC = "topic"
    LEARNER_PROFILE = "learner_profile"
    CONSTRAINT = "constraint"
    IMPROVEMENT = "improvement"
    MEDIA_SELECTION = "media_selection"
    MATERIAL = "material"
    ASSESSMENT_PLAN = "assessment_plan"
    ACTIVITY_PLAN = "activity_plan"

    IMPLEMENTATION_PLAN = "implementation_plan"
    SESSION_GUIDE = "session_guide"


class AlignmentGraph:
    """Alignment-dependency graph of ISD artifacts.

    Nodes carry only ``{type, id, data}``. Edges carry
    ``{type, source, target, relation_id, established_by, evidence, rationale}``
    where ``type`` is the human-readable relation key ("C2-assessed_by") and
    ``relation_id`` is the bare matrix id ("C2") used for coverage indexing. An
    edge exists iff a deterministic establisher (see ``alignment.py``) confirmed
    it — there is no ``verified``/``stale`` state, no cascade invalidation.
    """

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
        # Re-entrant: ``add_edge``/``link_section_narrative`` call other
        # locked methods on the same thread. See ``transaction`` for why the
        # lock stays although the executor is sequential.
        self._lock = threading.RLock()

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
    @contextmanager
    def transaction(self):
        """Hold the graph lock across a read-then-write.

        Individual writes are already locked, which is not the same thing: a
        commit that READS the ids already present and then adds nodes based on
        what it saw is only correct if nothing lands in between. The fan-out
        commits one work set at a time and is sequential today, so nothing does
        — this is what keeps that true if it ever stops being sequential, and
        it is re-entrant, so a caller already inside one costs nothing."""
        with self._lock:
            yield self

    def add_node(self, node_type: NodeType | str, node_id: str, data: dict | None = None) -> None:
        # A malformed LLM response can hand a section field back as a bare
        # string/list instead of an object (e.g. "learner_analysis": "..."
        # instead of {...}) — every consumer of node["data"] (viz, checks,
        # alignment.py, the aggregator) assumes a dict, so this is the one
        # choke point that guards the invariant. Treat it exactly like an
        # empty/missing section rather than crashing later (e.g. in
        # viz.to_dot): the existing regen/validation/audit machinery already
        # surfaces "this section came back too thin" as a quality signal,
        # which is the right lens for a wrong-typed field too.
        if data is not None and not isinstance(data, dict):
            data = {}
        with self._lock:
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
        if not isinstance(data, dict):
            data = {}
        with self._lock:
            if node_id not in self._nodes:
                return
            self._nodes[node_id]["data"].update(data)
            node_type = self._nodes[node_id]["type"]
        self._observe(
            "node_write",
            op="update",
            node_id=node_id,
            node_type=str(node_type),
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
        with self._lock:
            if node_type is None:
                found = list(self._nodes.values())
            else:
                found = [n for n in self._nodes.values() if n["type"] == node_type]
        self._observe("node_read", query="get_nodes", node_type=str(node_type or "*"),
                      result_count=len(found))
        return found

    def section_nodes(self, node_type: NodeType | str) -> list[dict]:
        """Section nodes (the aggregate payload), excluding element nodes."""
        with self._lock:
            found = [
                n for n in self._nodes.values()
                if n["type"] == node_type and not self.is_element(n["id"])
            ]
        self._observe("node_read", query="section_nodes", node_type=str(node_type),
                      result_count=len(found))
        return found

    def element_nodes(self, node_type: NodeType | str) -> list[dict]:
        """First-class element nodes for one artifact type."""
        with self._lock:
            found = [
                n for n in self._nodes.values()
                if n["type"] == node_type and self.is_element(n["id"])
            ]
        self._observe("node_read", query="element_nodes", node_type=str(node_type),
                      result_count=len(found))
        return found

    def get_node(self, node_id: str) -> dict | None:
        with self._lock:
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

        ``edge_type`` is the relation key ("C2-assessed_by"); ``relation_id``
        (C1..C5/P1..P11) and ``established_by`` (id|type|provenance) are resolved by
        callers from the (source_type, target_type) pair via ``alignment.py``'s
        registry, not here (avoids a graph<->alignment import cycle).

        Edge identity is ``(type, source, target, relation_id)``. Re-establishing
        the same link refreshes its evidence/rationale in place instead of
        appending a duplicate.
        """
        with self._lock:
            existing = self._find_edge(edge_type, source_id, target_id, relation_id)
            if existing is not None:
                if evidence:
                    existing["evidence"] = evidence
                if rationale:
                    existing["rationale"] = rationale
                if established_by:
                    existing["established_by"] = established_by
            else:
                self._edges.append({
                    "type": edge_type,
                    "source": source_id,
                    "target": target_id,
                    "evidence": evidence,
                    "rationale": rationale,
                    "relation_id": relation_id,
                    "established_by": established_by,
                })
        if existing is not None:
            self._observe(
                "edge_write", op="refresh", edge_type=edge_type, source=source_id,
                target=target_id, relation_id=relation_id,
                established_by=established_by, evidence=evidence,
            )
            return
        # Observed so the trace records which step drew which link, and on
        # what evidence.
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
        with self._lock:
            edges = self._edges
            if edge_type is not None:
                edges = [e for e in edges if e["type"] == edge_type]
            if relation_id is not None:
                edges = [e for e in edges if e.get("relation_id") == relation_id]
            if target is not None:
                edges = [e for e in edges if e.get("target") == target]
            if source is not None:
                edges = [e for e in edges if e.get("source") == source]
            edges = list(edges)
        self._observe(
            "edge_read", query="get_edges", edge_type=edge_type or "*",
            relation_id=relation_id or "*", result_count=len(edges),
        )
        return edges

    def link_section_narrative(self, node_type: NodeType | str,
                               element_type: NodeType | str | None = None) -> None:
        """Structural ``narrates`` edges (non-registry — the ``precedes``
        class) from a narrative section node to every element of its type.

        For the HUMAN auditor: in the dump/DOT/web view the section-level
        judgement (``priority_matrix``, ``review_summary``, ...) is otherwise
        an unreachable island floating next to the very elements it talks
        about. These edges are navigation, not construct-validity claims:
        they carry no ``relation_id``, so the docket, every check and all
        coverage machinery skip them — they exist only in
        the dump and the visualizations. Idempotent (edge identity dedups).

        ``element_type`` names a DIFFERENT element pool when the narrative and
        its elements are two types: ``implementation_plan_0`` carries the
        instructor guide's framing (overview, facilitation tips,
        troubleshooting) while the guides themselves are ``session_guide``
        elements. Same relationship, two type names, and without it the plan
        section is the island this method exists to prevent."""
        section_id = self.section_id(node_type)
        if self.get_node(section_id) is None:
            return
        for node in self.element_nodes(element_type or node_type):
            self.add_edge(
                "narrates", section_id, node["id"], established_by="provenance",
                rationale=f"{section_id} carries the section-level narrative for {node['id']}.",
            )

    def is_empty(self, node_type: NodeType | str) -> bool:
        """True if no non-empty node of this type exists."""
        return all(not n["data"] for n in self.get_nodes(node_type))

    def to_dict(self) -> dict:
        with self._lock:
            return {"nodes": list(self._nodes.values()), "edges": list(self._edges)}

    def to_full_dict(self, *, design_brief_id: str | None = None) -> dict:
        """Complete, JSON-serializable dump of the alignment state for auditing.

        Everything is included: every node (id, type, full ``data`` payload),
        every edge (source, target, relation key like "C2-assessed_by",
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

        # Detach the observer for this read-only reflection pass: a snapshot
        # dump is the harness reporting state for a viewer, not an agent doing
        # anything, and it can run mid-phase (the live `graph_snapshot` fires
        # on a timer, synchronously inside whatever `acting_as` scope happens
        # to be active — sometimes none at all, right at the very start of a
        # run) — either way, `element_nodes`/`get_edges` calls inside
        # `objective_annotations` have no real actor to be attributed to, and
        # `graph_snapshot` is already documented as carried as state, never
        # replayed as an event.
        previous_observer, self._observer = self._observer, None
        try:
            with self._lock:
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
        finally:
            self._observer = previous_observer
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
        """The load side of ``to_full_dict``: a saved ``graph.json`` reloads
        into a graph that can be audited after the fact."""
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
        return graph
