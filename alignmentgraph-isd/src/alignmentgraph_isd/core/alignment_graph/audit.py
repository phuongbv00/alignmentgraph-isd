from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..validation import validate_section
from . import alignment
from .graph import AlignmentGraph, NodeType

REQUIRED_NODE_TYPES = tuple(NodeType)

# Violation types that are audit-only by design (reported, never claimed for
# repair by any specialist — see checks.py::measurability and
# alignment.py::match_p6_realizes's docstring). A finding of these types can
# legitimately persist forever, so it must not block ready_to_aggregate —
# only violation types a specialist can actually resolve gate readiness.
# P10/P11 join P6 as audit-only for the HARNESS: the honest fix for an
# unscheduled activity is for the planner to schedule it, and auto-appending
# an id to the session guide to satisfy coverage would invent a delivery
# record that never happened — the exact "pad it to pass" failure the P6
# rationale rejects. They are also OWNED by the implementation planner
# (``repairs.OWNED_BY_FAMILY``, report-only), so the
# planner is shown them as a repair turn inside its own loop and can write
# the session guide that closes them; what it leaves is counted here and
# never blocks readiness.
AUDIT_ONLY_VIOLATION_TYPES = frozenset({"measurability", "P6", "P10", "P11"})

#: Element-backed list fields. A section node (objective_0/assessment_0/
#: activity_0) carries no element list, so the audit reconstructs each list
#: from the element pool — the single source of truth — and validates the
#: schema the deliverable declares.
_ELEMENT_LIST_KEYS = {
    NodeType.OBJECTIVE: "learning_objectives",
    NodeType.ASSESSMENT: "assessment_tools",
    NodeType.ACTIVITY: "learning_activities",
}

#: Element-backed list fields held one level DOWN, inside a section field.
#: ``instructor_guide.session_guides`` is the one: the guides are element nodes
#: (``NodeType.SESSION_GUIDE``) and the section holds only the
#: guide's framing, but the ADDIE output contract still declares them there
#: (``validation._NESTED_FIELDS``), so the audit validates the SAME document
#: the aggregator ships — reconstructed from the element pool, the single
#: source of truth, exactly as ``_ELEMENT_LIST_KEYS`` does one level up.
_ELEMENT_NESTED_LIST_KEYS = {
    NodeType.IMPLEMENTATION_PLAN: (NodeType.SESSION_GUIDE, "instructor_guide", "session_guides"),
}

REQUIRED_SECTION_KEYS = {
    NodeType.OBJECTIVE: ("learning_objectives",),
    NodeType.ASSESSMENT_PLAN: ("instruments", "lo_coverage_targets"),
    NodeType.ASSESSMENT: ("assessment_tools",),
    NodeType.ACTIVITY_PLAN: ("instructional_strategies",),
    NodeType.ACTIVITY: ("learning_activities",),
    NodeType.IMPLEMENTATION_PLAN: ("instructor_orientation", "system_check", "prototype_execution",
                                   "monitoring", "instructor_guide", "operator_manual"),
}

#: Section node types that carry a structured payload worth schema-validating.
_SCHEMA_VALIDATED_TYPES = tuple(REQUIRED_SECTION_KEYS)


@dataclass
class GraphAuditResult:
    """What the residual audit found, and everything it needed to decide it.

    The FIELDS are the audit's working state; ``to_dict`` is narrower. See its
    docstring for why, and for who owns what it leaves out.
    """

    node_counts: dict[str, int]
    missing_node_types: list[str]
    missing_section_keys: dict[str, list[str]]
    schema_violations: dict[str, list[str]] = field(default_factory=dict)
    objective_ids: list[str] = field(default_factory=list)
    objective_count: int = 0
    unmeasured_objectives: list[str] = field(default_factory=list)
    unsupported_objectives: list[str] = field(default_factory=list)
    violations: list[dict] = field(default_factory=list)
    ready_to_aggregate: bool = False
    # Per-relation coverage for all 18 relations (C1..C4 core + P1..P14
    # secondary), computed from established edges as data (see alignment.py).
    relation_coverage: dict[str, dict] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """``metadata.audit``: the audit's VERDICT, and what stopped it.

        Not a second copy of the graph. Five of this dataclass's fields are
        measurements OF the graph or of the run's findings, and each already
        has an owner in the same results directory — carried here too they were
        a second copy that can only drift:

        * ``violations`` is the ``residual`` list ``audit()`` is HANDED, and
          the same list settles the ledger in the same breath
          (``runner._reconcile`` → ``memory.settle`` → ``violations.json``).
          Measured on run 16cef50d: key-for-key the ledger's ``outcome ==
          "open"`` subset, 23 of 66, in an older field vocabulary
          (``msg``/``owner`` for ``messages``/``target_designer``) — so the
          copy was also the lossy one, saying nothing about whether a finding
          was repaired, converged or ran out of budget.
        * ``relation_coverage`` is ``graph.json``'s, from the same
          ``alignment.all_relations_coverage`` call on the same graph — and
          ``graph.json``'s is what every renderer already reads (``viz``, the
          webapp inspector, the phase timeline).
        * ``node_counts`` equals ``graph.json``'s
          ``metadata.node_counts_by_type``.
        * ``unmeasured_objectives``/``unsupported_objectives`` are the C2 and
          C3 legs of ``graph.json``'s ``objective_alignment`` — and were a
          SECOND IMPLEMENTATION of that predicate (``_uncovered_objectives``
          here, ``viz.objective_annotations`` there), which is how one comes to
          answer differently from the other.

        They stay FIELDS because the verdict is derived from them:
        ``ready_to_aggregate`` turns on the objectives and the blocking
        violations, ``summary`` names the relation gaps, and
        ``trajectory.log_audit_result`` reads the coverage. What is dropped is
        the second copy on disk, not the audit's own reasoning.

        Precedent: ``metadata.violations``/``metadata.schema_violations`` went
        the same way on 2026-08-27, for being copies of these very fields.
        """
        return {
            "missing_node_types": self.missing_node_types,
            "missing_section_keys": self.missing_section_keys,
            "schema_violations": self.schema_violations,
            # The subject the verdict is about: readiness turns on there being
            # objectives at all, so the audit says which ones it judged.
            "objective_ids": self.objective_ids,
            "objective_count": self.objective_count,
            "ready_to_aggregate": self.ready_to_aggregate,
            "summary": self.summary,
        }

    @property
    def residual_gap_count(self) -> int:
        """Total uncovered elements across all 18 relations — the audit
        summary's residual."""
        return sum(len(info["uncovered"]) for info in self.relation_coverage.values())

    @property
    def summary(self) -> str:
        parts: list[str] = []
        if self.missing_node_types:
            parts.append(f"missing_nodes={','.join(self.missing_node_types)}")
        if self.unmeasured_objectives:
            parts.append(f"unmeasured={','.join(self.unmeasured_objectives)}")
        if self.unsupported_objectives:
            parts.append(f"unsupported={','.join(self.unsupported_objectives)}")
        if self.schema_violations:
            parts.append(f"schema_invalid={','.join(self.schema_violations)}")
        if self.violations:
            parts.append(f"violations={len(self.violations)}")
        gapped_relations = [rid for rid, info in self.relation_coverage.items() if info["uncovered"]]
        if gapped_relations:
            parts.append(f"relation_gaps={','.join(sorted(gapped_relations))}({self.residual_gap_count})")
        return "; ".join(parts) if parts else "graph_ready"


class GraphAuditor:
    def __init__(self, graph: AlignmentGraph) -> None:
        self.graph = graph

    def audit(self, violations: list[dict] | None = None) -> GraphAuditResult:
        node_counts = {node_type: len(self.graph.get_nodes(node_type)) for node_type in REQUIRED_NODE_TYPES}
        missing_node_types = [
            node_type
            for node_type, count in node_counts.items()
            if count == 0 or self.graph.is_empty(node_type)
        ]
        missing_section_keys = self._missing_section_keys()
        schema_violations = self._schema_violations(missing_node_types)
        # Route structural problems (e.g. wrong type, malformed id) back to the
        # owning specialist by registering them as regeneration triggers, even
        # when the field is present and non-empty so missing_section_keys is blank.
        for node_type in schema_violations:
            if not missing_section_keys.get(node_type):
                missing_section_keys[node_type] = [f"__schema__:{node_type}"]

        objective_ids = self._objective_ids()

        # C2/C3 are id-reverse: the objective is the edge SOURCE, not target.
        unmeasured = self._uncovered_objectives("C2")
        unsupported = self._uncovered_objectives("C3")
        violations = violations or []
        blocking_violations = [v for v in violations if v.get("type") not in AUDIT_ONLY_VIOLATION_TYPES]
        relation_cov = alignment.all_relations_coverage(self.graph)

        ready = (
            not missing_node_types
            and not any(missing_section_keys.values())
            and not schema_violations
            and bool(objective_ids)
            and not unmeasured
            and not unsupported
            and not blocking_violations
        )

        return GraphAuditResult(
            node_counts=node_counts,
            missing_node_types=missing_node_types,
            missing_section_keys=missing_section_keys,
            schema_violations=schema_violations,
            objective_ids=objective_ids,
            objective_count=len(objective_ids),
            unmeasured_objectives=unmeasured,
            unsupported_objectives=unsupported,
            violations=violations,
            ready_to_aggregate=ready,
            relation_coverage=relation_cov,
        )

    def _uncovered_objectives(self, relation_id: alignment.RelationId) -> list[str]:
        """Objective element ids with no edge of this relation. Every relation
        this is asked about (C2/C3) is id-reverse: the LO is the edge's
        SOURCE, so coverage is checked on the source side."""
        covered = {edge.get("source") for edge in self.graph.get_edges(relation_id=relation_id)}
        uncovered: list[str] = []
        for element in self.graph.element_nodes(NodeType.OBJECTIVE):
            if element["id"] not in covered:
                uncovered.append(str(element["data"].get("id")
                                     or element["id"].split(self.graph.ELEMENT_SEP, 1)[-1]))
        return uncovered

    def _missing_section_keys(self) -> dict[str, list[str]]:
        missing: dict[str, list[str]] = {}
        for node_type, keys in REQUIRED_SECTION_KEYS.items():
            data = self._merged_data(node_type)
            missing[node_type] = [key for key in keys if _is_empty(data.get(key))]
        return missing

    def _schema_violations(self, missing_node_types: list[str]) -> dict[str, list[str]]:
        violations: dict[str, list[str]] = {}
        for node_type in _SCHEMA_VALIDATED_TYPES:
            if node_type in missing_node_types:
                continue  # absence is already reported via missing_node_types
            errors = validate_section(node_type, self._merged_data(node_type))
            if errors:
                violations[node_type] = errors
        return violations

    def _merged_data(self, node_type: str) -> dict:
        merged: dict = {}
        for node in self.graph.section_nodes(node_type):
            data = node.get("data", {})
            if isinstance(data, dict):
                merged.update(data)
        list_key = _ELEMENT_LIST_KEYS.get(node_type)
        if list_key is not None:
            # virtual section: the list lives solely on element nodes
            merged[list_key] = [n.get("data", {}) for n in self.graph.element_nodes(node_type)]
        nested = _ELEMENT_NESTED_LIST_KEYS.get(node_type)
        if nested is not None:
            element_type, field, inner_key = nested
            elements = [n.get("data", {}) for n in self.graph.element_nodes(element_type)]
            if elements:
                parent = merged.get(field)
                parent = dict(parent) if isinstance(parent, dict) else {}
                parent[inner_key] = elements
                merged[field] = parent
        return merged

    def _objective_ids(self) -> list[str]:
        return [
            str(n["data"]["id"])
            for n in self.graph.element_nodes(NodeType.OBJECTIVE)
            if isinstance(n.get("data"), dict) and n["data"].get("id")
        ]


def _is_empty(value: Any) -> bool:
    return value in ({}, [], "", None)
