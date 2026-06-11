from __future__ import annotations
import re
from .base import BaseISDAgent
from .pedagogical_verifier import VerifierViolation

_BLOOM_VERB_BY_LEVEL = {
    "Remember": "Recall",
    "Understand": "Explain",
    "Apply": "Apply",
    "Analyze": "Analyze",
    "Evaluate": "Evaluate",
    "Create": "Design",
}

_VERB_REPLACEMENTS = {
    "comprehend": "Explain",
    "understand": "Explain",
    "grasp": "Explain",
    "learn": "Identify",
    "know": "Identify",
}


class RepairAgent(BaseISDAgent):
    def run(self, scenario: dict, context_pack: dict) -> None:
        pass  # not used directly; call repair()

    def repair(self, violations: list[VerifierViolation]) -> None:
        if not self.config.ablation.use_repair:
            return
        for v in violations:
            if v.violation_type == "bloom":
                self._repair_bloom_verb(v)
            elif v.violation_type == "activity_support":
                self._repair_activity_support(v)
            else:
                self._repair_assessment_coverage(v)

    def _repair_bloom_verb(self, violation: VerifierViolation) -> None:
        obj = self.graph.get_node(violation.node_id)
        if not obj:
            return

        lo_id = self._extract_lo_id(violation)
        objectives = list(obj["data"].get("learning_objectives", []))
        repaired = False

        for lo in objectives:
            if not isinstance(lo, dict):
                continue
            if lo_id and lo.get("id") != lo_id:
                continue
            old_verb = str(lo.get("bloom_verb", "")).strip()
            replacement = (
                _VERB_REPLACEMENTS.get(old_verb.lower())
                or _BLOOM_VERB_BY_LEVEL.get(lo.get("level"), "Explain")
            )
            lo["bloom_verb"] = replacement
            statement = str(lo.get("statement", ""))
            if old_verb and re.search(re.escape(old_verb), statement, flags=re.IGNORECASE):
                lo["statement"] = re.sub(
                    re.escape(old_verb),
                    replacement.lower(),
                    statement,
                    count=1,
                    flags=re.IGNORECASE,
                )
            elif replacement.lower() not in statement.lower():
                lo["statement"] = f"{statement} This is measured by asking learners to {replacement.lower()} the target skill in context."
            repaired = True

        if repaired:
            self.graph.update_node(violation.node_id, {"learning_objectives": objectives})
            self.graph.mark_repaired(violation.node_id, violation.message)
            self.trajectory.log_node_edit("update", violation.node_id, "objective")
            self.trajectory.log_step(
                "RepairAgent",
                "repair_bloom_verb",
                violation.message,
                f"Updated Bloom verb for {lo_id or violation.node_id}.",
            )

    def _repair_activity_support(self, violation: VerifierViolation) -> None:
        obj = self.graph.get_node(violation.node_id)
        if not obj:
            return

        activity_nodes = self.graph.get_nodes("activity")
        if activity_nodes:
            activity_id = activity_nodes[0]["id"]
            activity_data = activity_nodes[0]["data"]
        else:
            activity_id = f"activity_repair_{violation.node_id}"
            activity_data = {
                "alignment_notes": [],
                "repaired": True,
            }
            self.graph.add_node("activity", activity_id, activity_data, repair_history=[violation.message])
            self.trajectory.log_node_edit("add", activity_id, "activity")

        alignment_notes = list(activity_data.get("alignment_notes", []))
        for lo_id in self._lo_ids(obj):
            rationale = f"Learning activity/materials explicitly support {lo_id} after verifier repair."
            self.graph.add_edge(
                "supports",
                activity_id,
                violation.node_id,
                evidence=lo_id,
                rationale=rationale,
                verified=True,
            )
            self.trajectory.log_edge_edit("add", activity_id, violation.node_id, "supports", lo_id, rationale)
            alignment_notes.append(rationale)

        self.graph.update_node(activity_id, {"alignment_notes": alignment_notes, "repaired": True})
        self.graph.mark_repaired(violation.node_id, violation.message)
        self.trajectory.log_step(
            "RepairAgent",
            "repair_activity_support",
            violation.message,
            f"Added supports edges from {activity_id} to {violation.node_id}.",
        )

    def _repair_assessment_coverage(self, violation: VerifierViolation) -> None:
        obj = self.graph.get_node(violation.node_id)
        if not obj:
            return

        assessment_nodes = self.graph.get_nodes("assessment")
        if assessment_nodes:
            assessment_id = assessment_nodes[0]["id"]
            assessment_data = assessment_nodes[0]["data"]
        else:
            assessment_id = f"assessment_repair_{violation.node_id}"
            assessment_data = {"assessment_tools": [], "expert_review": {}, "repaired": True}
            self.graph.add_node("assessment", assessment_id, assessment_data, repair_history=[violation.message])
            self.trajectory.log_node_edit("add", assessment_id, "assessment")

        assessment_tools = list(assessment_data.get("assessment_tools", []))
        existing_lo_ids = {
            item.get("aligned_objective")
            for item in assessment_tools
            if isinstance(item, dict) and item.get("aligned_objective")
        }

        for lo in obj["data"].get("learning_objectives", []):
            if not isinstance(lo, dict):
                continue
            lo_id = lo.get("id")
            if not lo_id or lo_id in existing_lo_ids:
                continue
            item_id = f"AT-R-{lo_id}"
            assessment_tools.append({
                "item_id": item_id,
                "type": "performance_task",
                "question": f"Demonstrate the target skill for {lo_id}: {lo.get('statement', '')}",
                "aligned_objective": lo_id,
                "scoring_criteria": "Score accuracy, context appropriateness, learner independence, and evidence of transfer.",
                "repaired": True,
            })
            rationale = f"Verifier repair added {item_id} to measure {lo_id}."
            self.graph.add_edge(
                "measures",
                assessment_id,
                violation.node_id,
                evidence=lo_id,
                rationale=rationale,
                verified=True,
            )
            self.trajectory.log_edge_edit("add", assessment_id, violation.node_id, "measures", lo_id, rationale)

        self.graph.update_node(assessment_id, {"assessment_tools": assessment_tools, "repaired": True})
        self.graph.mark_repaired(violation.node_id, violation.message)
        self.trajectory.log_step(
            "RepairAgent",
            "repair_assessment_coverage",
            violation.message,
            f"Assessment coverage repaired for {violation.node_id}.",
        )

    def _extract_lo_id(self, violation: VerifierViolation) -> str:
        lo_id = str(violation.metadata.get("lo_id", "") or "")
        if lo_id:
            return lo_id
        match = re.search(r"LO-\d+", violation.message)
        return match.group(0) if match else ""

    def _lo_ids(self, objective_node: dict) -> list[str]:
        return [
            lo.get("id")
            for lo in objective_node["data"].get("learning_objectives", [])
            if isinstance(lo, dict) and lo.get("id")
        ]
