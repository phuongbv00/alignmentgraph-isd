from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import alignment
from .graph import AlignmentGraph, NodeType
from ..validation import validate_section


REQUIRED_NODE_TYPES = tuple(NodeType)

# Section node types that carry a structured payload worth schema-validating.
# NEEDS_CONTEXT/EVALUATION no longer exist as node types (see graph.py's
# NodeType docstring) — their fields are computed by ADDIEOutputAggregator
# directly from Gap/Topic/LearnerProfile/Constraint/Improvement elements.
_SCHEMA_VALIDATED_TYPES = (
    NodeType.OBJECTIVE,
    NodeType.ASSESSMENT_PLAN,
    NodeType.ASSESSMENT,
    NodeType.ACTIVITY_PLAN,
    NodeType.ACTIVITY,
    NodeType.IMPLEMENTATION_PLAN,
)

# Violation types that are audit-only by design (reported, never claimed for
# repair by any specialist — see checks.py::measurability and
# alignment.py::match_p6_realizes's docstring). A finding of these types can
# legitimately persist forever, so it must not block ready_to_aggregate —
# only violation types a specialist can actually resolve gate readiness.
# P10/P11 join P6 as audit-only for the HARNESS: the honest fix for an
# unscheduled activity is for the planner to schedule it, and auto-appending
# an id to the session guide to satisfy coverage would invent a delivery
# record that never happened — the exact "pad it to pass" failure the P6
# rationale rejects. Since 2026-09-05 they are also OWNED by the
# implementation planner (``repairs.OWNED_BY_FAMILY``, report-only), so the
# planner is shown them as a repair turn inside its own loop and can write
# the session guide that closes them; what it leaves is counted here and
# never blocks readiness.
AUDIT_ONLY_VIOLATION_TYPES = frozenset({"measurability", "P6", "P10", "P11"})

#: Element-backed list fields: since the legacy full-list sections were
#: retired (objective_0/assessment_0/activity_0 no longer carry their element
#: list), the audit reconstructs each list from the element pool — the single
#: source of truth — and validates the SAME schema as before.
_ELEMENT_LIST_KEYS = {
    NodeType.OBJECTIVE: "learning_objectives",
    NodeType.ASSESSMENT: "assessment_tools",
    NodeType.ACTIVITY: "learning_activities",
}

REQUIRED_SECTION_KEYS = {
    NodeType.OBJECTIVE: ("learning_objectives",),
    NodeType.ASSESSMENT_PLAN: ("lo_coverage_targets",),
    NodeType.ASSESSMENT: ("assessment_tools",),
    NodeType.ACTIVITY_PLAN: ("instructional_strategies",),
    NodeType.ACTIVITY: ("learning_activities",),
    NodeType.IMPLEMENTATION_PLAN: ("instructor_orientation", "system_check", "prototype_execution",
                                   "monitoring", "instructor_guide", "operator_manual"),
}


@dataclass
class GraphAuditResult:
    node_counts: dict[str, int]
    missing_node_types: list[str]
    missing_section_keys: dict[str, list[str]]
    schema_violations: dict[str, list[str]] = field(default_factory=dict)
    objective_node_id: str = ""
    objective_ids: list[str] = field(default_factory=list)
    objective_count: int = 0
    unmeasured_objectives: list[str] = field(default_factory=list)
    unsupported_objectives: list[str] = field(default_factory=list)
    violations: list[dict] = field(default_factory=list)
    ready_to_aggregate: bool = False
    # Per-relation coverage for all 16 relations (C1..C5 core + P1..P11
    # secondary), computed from established edges as data (see alignment.py).
    relation_coverage: dict[str, dict] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_counts": self.node_counts,
            "missing_node_types": self.missing_node_types,
            "missing_section_keys": self.missing_section_keys,
            "schema_violations": self.schema_violations,
            "objective_node_id": self.objective_node_id,
            "objective_ids": self.objective_ids,
            "objective_count": self.objective_count,
            "unmeasured_objectives": self.unmeasured_objectives,
            "unsupported_objectives": self.unsupported_objectives,
            "violations": self.violations,
            "ready_to_aggregate": self.ready_to_aggregate,
            "relation_coverage": self.relation_coverage,
            "summary": self.summary,
        }

    @property
    def residual_gap_count(self) -> int:
        """Total uncovered elements across all 16 relations — the "39->12"
        style number RQ2 reports, now spanning the full matrix."""
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

        objective_node = self._first_node(NodeType.OBJECTIVE)
        objective_node_id = objective_node.get("id", "") if objective_node else ""
        objective_ids = self._objective_ids(objective_node)

        # C2/C3 are id-reverse: the objective is the edge SOURCE, not target.
        #
        # ``unevaluated`` is gone with C7 (2026-09-02): it asked which
        # objectives no rubric criterion measured, and a criterion is now a
        # field of the item that measures the objective — so the question
        # collapsed into ``unmeasured`` and could not have a different answer.
        unmeasured = self._uncovered_objectives("C2", objective_node_id, objective_ids)
        unsupported = self._uncovered_objectives("C3", objective_node_id, objective_ids)
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
            objective_node_id=objective_node_id,
            objective_ids=objective_ids,
            objective_count=len(objective_ids),
            unmeasured_objectives=unmeasured,
            unsupported_objectives=unsupported,
            violations=violations,
            ready_to_aggregate=ready,
            relation_coverage=relation_cov,
        )

    def _first_node(self, node_type: str) -> dict | None:
        nodes = self.graph.section_nodes(node_type)
        return nodes[0] if nodes else None

    def _uncovered_objectives(
        self,
        relation_id: str,
        objective_node_id: str,
        objective_ids: list[str],
    ) -> list[str]:
        """Coverage over objective element nodes (first-class), not just objective_0.

        Every relation this is asked about (C2/C3) is id-reverse: the LO is the
        edge's SOURCE, not its target, so coverage is checked on the source
        side. The target-side variant went with C7 (2026-09-02), its only
        caller. Falls back to the legacy evidence-on-section check when no
        element nodes exist yet.
        """
        elements = self.graph.element_nodes(NodeType.OBJECTIVE)
        edges = self.graph.get_edges(relation_id=relation_id)
        covered_side = {edge.get("source") for edge in edges}
        covered_evidence = {edge.get("evidence") for edge in edges if edge.get("evidence")}
        if elements:
            uncovered: list[str] = []
            for element in elements:
                element_id = element["id"]
                lo_id = str(element["data"].get("id") or element_id.split(self.graph.ELEMENT_SEP, 1)[-1])
                if element_id not in covered_side and lo_id not in covered_evidence:
                    uncovered.append(lo_id)
            return uncovered
        return self._missing_edge_evidence(relation_id, objective_node_id, objective_ids)

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
        return merged

    def _objective_ids(self, objective_node: dict | None) -> list[str]:
        # Element nodes first (single source of truth); the section-node path
        # remains only for graphs built by older dumps/tests.
        ids = [
            str(n["data"]["id"])
            for n in self.graph.element_nodes(NodeType.OBJECTIVE)
            if isinstance(n.get("data"), dict) and n["data"].get("id")
        ]
        if ids or not objective_node:
            return ids
        for item in objective_node.get("data", {}).get("learning_objectives", []):
            if isinstance(item, dict) and item.get("id"):
                ids.append(str(item["id"]))
        return ids

    def _missing_edge_evidence(
        self,
        relation_id: str,
        objective_node_id: str,
        objective_ids: list[str],
    ) -> list[str]:
        if not objective_node_id or not objective_ids:
            return []
        covered = {
            edge.get("evidence")
            for edge in self.graph.get_edges(relation_id=relation_id)
            if edge.get("target") == objective_node_id and edge.get("evidence")
        }
        return [objective_id for objective_id in objective_ids if objective_id not in covered]


def _is_empty(value: Any) -> bool:
    return value in ({}, [], "", None)
