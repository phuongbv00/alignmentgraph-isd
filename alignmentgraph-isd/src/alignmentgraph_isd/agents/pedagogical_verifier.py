from __future__ import annotations
from ..schema import TaskRequest
from dataclasses import dataclass, field
from .base import BaseISDAgent

# Bloom's taxonomy verbs by level — used to verify measurability of objectives
_BLOOM_VERBS: dict[str, list[str]] = {
    "Remember":  ["define","list","recall","recognize","identify","name","state","describe","label","match"],
    "Understand":["explain","summarize","paraphrase","classify","compare","interpret","translate","discuss","distinguish","infer"],
    "Apply":     ["apply","use","demonstrate","solve","execute","implement","calculate","construct","produce","operate"],
    "Analyze":   ["analyze","differentiate","examine","compare","contrast","organize","attribute","deconstruct","outline","relate"],
    "Evaluate":  ["evaluate","judge","justify","assess","critique","argue","defend","recommend","prioritize","rate"],
    "Create":    ["design","create","formulate","develop","compose","plan","generate","synthesize","construct","propose"],
}
_ALL_BLOOM_VERBS = {v for verbs in _BLOOM_VERBS.values() for v in verbs}


@dataclass
class VerifierViolation:
    node_id: str
    edge_type: str
    message: str
    violation_type: str = "coverage"          # coverage | bloom | activity_support | feasibility
    severity: str = "error"                   # error | warning
    repair_hint: str = ""
    metadata: dict = field(default_factory=dict)


class PedagogicalVerifierAgent(BaseISDAgent):
    def run(self, task: TaskRequest, context_pack: dict) -> None:
        pass  # not used directly; call verify()

    def verify(self) -> list[VerifierViolation]:
        if not self.config.ablation.use_verifier:
            return []
        violations: list[VerifierViolation] = []
        violations.extend(self._check_assessment_coverage())
        violations.extend(self._check_bloom_verbs())
        violations.extend(self._check_activity_support())
        return violations

    # ── Check 1: every objective has ≥1 assessment measuring it ───────────────
    def _check_assessment_coverage(self) -> list[VerifierViolation]:
        violations: list[VerifierViolation] = []
        objective_nodes = self.graph.get_nodes("objective")
        measures_edges = self.graph.get_edges("measures")
        measured_targets = {e["target"] for e in measures_edges}

        for obj in objective_nodes:
            if obj["id"] not in measured_targets:
                violations.append(VerifierViolation(
                    node_id=obj["id"],
                    edge_type="measures",
                    violation_type="coverage",
                    severity="error",
                    message=f"Objective '{obj['id']}' has no assessment measuring it.",
                    repair_hint="Create an assessment item aligned with this objective and add a 'measures' edge.",
                    metadata={"objective_data": obj["data"]},
                ))

        # Also check per-LO items inside the objective node's learning_objectives list
        for obj in objective_nodes:
            lo_list = obj["data"].get("learning_objectives", [])
            measured_lo_ids = set()
            for edge in measures_edges:
                assessed_lo = edge.get("evidence", "")
                if assessed_lo:
                    measured_lo_ids.add(assessed_lo)
            for lo in lo_list:
                lo_id = lo.get("id", "")
                if lo_id and lo_id not in measured_lo_ids:
                    # Soft warning only (not all LOs are individually tracked at edge level)
                    self.trajectory.log_step(
                        "PedagogicalVerifier", "coverage_warning",
                        lo_id, f"LO '{lo_id}' not explicitly tracked by a measures edge",
                    )

        return violations

    # ── Check 2: learning objectives use measurable Bloom's verbs ─────────────
    def _check_bloom_verbs(self) -> list[VerifierViolation]:
        violations: list[VerifierViolation] = []
        for obj in self.graph.get_nodes("objective"):
            lo_list = obj["data"].get("learning_objectives", [])
            for lo in lo_list:
                verb = lo.get("bloom_verb", "").lower().strip(".,;")
                statement = lo.get("statement", "")
                lo_id = lo.get("id", obj["id"])
                if not verb:
                    violations.append(VerifierViolation(
                        node_id=obj["id"],
                        edge_type="",
                        violation_type="bloom",
                        severity="warning",
                        message=f"LO '{lo_id}' missing bloom_verb field.",
                        repair_hint="Add a measurable Bloom's taxonomy verb.",
                        metadata={"lo_id": lo_id, "statement": statement},
                    ))
                elif verb not in _ALL_BLOOM_VERBS:
                    # Check if verb appears in the statement as a fallback
                    stmt_lower = statement.lower()
                    has_bloom = any(bv in stmt_lower for bv in _ALL_BLOOM_VERBS)
                    if not has_bloom:
                        violations.append(VerifierViolation(
                            node_id=obj["id"],
                            edge_type="",
                            violation_type="bloom",
                            severity="warning",
                            message=f"LO '{lo_id}' uses non-standard verb '{verb}' not in Bloom's taxonomy.",
                            repair_hint=f"Use a standard Bloom's verb such as: {', '.join(list(_ALL_BLOOM_VERBS)[:8])}...",
                            metadata={"lo_id": lo_id, "verb": verb},
                        ))
        return violations

    # ── Check 3: every objective has ≥1 activity supporting it ───────────────
    def _check_activity_support(self) -> list[VerifierViolation]:
        violations: list[VerifierViolation] = []
        objective_nodes = self.graph.get_nodes("objective")
        supports_edges = self.graph.get_edges("supports")
        supported_targets = {e["target"] for e in supports_edges}

        # Only flag this if we have activity nodes (not in single-agent mode where
        # activities are embedded inside the design section)
        if not self.graph.get_nodes("activity"):
            return []

        for obj in objective_nodes:
            if obj["id"] not in supported_targets:
                violations.append(VerifierViolation(
                    node_id=obj["id"],
                    edge_type="supports",
                    violation_type="activity_support",
                    severity="warning",
                    message=f"Objective '{obj['id']}' has no learning activity explicitly supporting it.",
                    repair_hint="Create a learning activity that explicitly supports this objective and add a 'supports' edge.",
                    metadata={"objective_data": obj["data"]},
                ))
        return violations
