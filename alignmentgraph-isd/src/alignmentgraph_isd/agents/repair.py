from __future__ import annotations
from .base import BaseISDAgent
from .pedagogical_verifier import VerifierViolation


class RepairAgent(BaseISDAgent):
    def run(self, scenario: dict, context_pack: dict) -> None:
        pass  # not used directly; call repair()

    def repair(self, violations: list[VerifierViolation]) -> None:
        if not self.config.ablation.use_repair:
            return
        for v in violations:
            messages = [
                {"role": "system", "content": "You are an instructional designer. Fix the following violation in the instructional design by providing a brief assessment that measures the specified objective."},
                {"role": "user", "content": f"Violation: {v.message}\nObjective node: {v.node_id}\nProvide a short assessment description."},
            ]
            response = self._call_llm(messages)
            repair_id = f"assessment_repair_{v.node_id}"
            self.graph.add_node("assessment", repair_id, {"content": response or "Repaired assessment.", "repaired": True})
            self.graph.add_edge("measures", repair_id, v.node_id)
            self.trajectory.log_node_edit("add", repair_id, "assessment")
            self.trajectory.log_edge_edit("add", repair_id, v.node_id, "measures")
            self.trajectory.log_step("RepairAgent", "repair_violation", v.message, (response or "")[:200])
