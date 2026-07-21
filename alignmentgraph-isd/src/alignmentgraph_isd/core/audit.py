from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import alignment
from .graph import AlignmentGraph, NodeType
from .validation import validate_section


REQUIRED_NODE_TYPES = tuple(NodeType)

# Section node types that carry a structured payload worth schema-validating.
_SCHEMA_VALIDATED_TYPES = (
    NodeType.NEEDS_CONTEXT,
    NodeType.OBJECTIVE,
    NodeType.ASSESSMENT,
    NodeType.ACTIVITY,
    NodeType.IMPLEMENTATION_PLAN,
    NodeType.EVALUATION,
)

# Design is now decomposed across several singleton nodes (objective_design.py's
# 2-call split) — objective_0 only holds learning_objectives; instructional_strategies
# lives in its own node (still required, addie_output.json requires it at the top level).
# Violation types that are audit-only by design (reported, never claimed for
# repair by any specialist — see pedagogical_verifier.py::_check_measurability
# and activity_material.py's R9 comment). A finding of these types can
# legitimately persist forever, so it must not block ready_to_aggregate —
# only violation types a specialist can actually resolve gate readiness.
AUDIT_ONLY_VIOLATION_TYPES = frozenset({"measurability", "R9"})

REQUIRED_SECTION_KEYS = {
    NodeType.NEEDS_CONTEXT: ("needs_analysis", "learner_analysis", "context_analysis", "task_analysis"),
    # instructional_strategies lives in its own node under graph coordination but
    # inside the objective_0 blob in the wo-graph arm — so it is NOT a required
    # section-node key here; the output-level validate_addie checks it instead.
    NodeType.OBJECTIVE: ("learning_objectives",),
    NodeType.ASSESSMENT: ("assessment_tools",),
    NodeType.ACTIVITY: ("learner_materials", "instructor_guide"),
    NodeType.MATERIAL: ("learner_materials",),
    NodeType.IMPLEMENTATION_PLAN: ("instructor_orientation", "system_check", "prototype_execution", "monitoring"),
    NodeType.EVALUATION: ("formative", "summative", "improvement_plan"),
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
    unevaluated_objectives: list[str] = field(default_factory=list)
    verifier_violations: list[dict] = field(default_factory=list)
    ready_to_aggregate: bool = False
    # Per-relation coverage for all 13 matrix relations (R1..R13), computed
    # from established edges as data (see alignment.py).
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
            "unevaluated_objectives": self.unevaluated_objectives,
            "verifier_violations": self.verifier_violations,
            "ready_to_aggregate": self.ready_to_aggregate,
            "relation_coverage": self.relation_coverage,
            "summary": self.summary,
        }

    @property
    def coverage_gaps(self) -> dict[str, list[str]]:
        gaps = {
            "measures": self.unmeasured_objectives,
            "supports": self.unsupported_objectives,
            "evaluates": self.unevaluated_objectives,
        }
        gaps.update({
            relation_id: info["uncovered"]
            for relation_id, info in self.relation_coverage.items()
        })
        return gaps

    @property
    def residual_gap_count(self) -> int:
        """Total uncovered targets across all 13 relations — the "39->12"
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
        if self.unevaluated_objectives:
            parts.append(f"unevaluated={','.join(self.unevaluated_objectives)}")
        if self.schema_violations:
            parts.append(f"schema_invalid={','.join(self.schema_violations)}")
        if self.verifier_violations:
            parts.append(f"violations={len(self.verifier_violations)}")
        gapped_relations = [rid for rid, info in self.relation_coverage.items() if info["uncovered"]]
        if gapped_relations:
            parts.append(f"relation_gaps={','.join(sorted(gapped_relations))}({self.residual_gap_count})")
        return "; ".join(parts) if parts else "graph_ready"


class GraphAuditor:
    def __init__(self, graph: AlignmentGraph) -> None:
        self.graph = graph

    def audit(self, verifier_violations: list[dict] | None = None) -> GraphAuditResult:
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

        unmeasured = self._uncovered_objectives("R3", objective_node_id, objective_ids)
        unsupported = self._uncovered_objectives("R4", objective_node_id, objective_ids)
        unevaluated = self._uncovered_objectives("R5", objective_node_id, objective_ids)
        violations = verifier_violations or []
        blocking_violations = [v for v in violations if v.get("type") not in AUDIT_ONLY_VIOLATION_TYPES]
        relation_cov = alignment.all_relations_coverage(self.graph)

        ready = (
            not missing_node_types
            and not any(missing_section_keys.values())
            and not schema_violations
            and bool(objective_ids)
            and not unmeasured
            and not unsupported
            and not unevaluated
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
            unevaluated_objectives=unevaluated,
            verifier_violations=violations,
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

        An objective is covered when an alignment edge of ``relation_id`` targets
        its element node OR carries its LO id as evidence. Falls back to the
        legacy evidence-on-section check when no element nodes exist yet.
        """
        elements = self.graph.element_nodes(NodeType.OBJECTIVE)
        edges = self.graph.get_edges(relation_id=relation_id)
        covered_targets = {edge.get("target") for edge in edges}
        covered_evidence = {edge.get("evidence") for edge in edges if edge.get("evidence")}
        if elements:
            uncovered: list[str] = []
            for element in elements:
                element_id = element["id"]
                lo_id = str(element["data"].get("id") or element_id.split(self.graph.ELEMENT_SEP, 1)[-1])
                if element_id not in covered_targets and lo_id not in covered_evidence:
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
        return merged

    def _objective_ids(self, objective_node: dict | None) -> list[str]:
        if not objective_node:
            return []
        ids: list[str] = []
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
