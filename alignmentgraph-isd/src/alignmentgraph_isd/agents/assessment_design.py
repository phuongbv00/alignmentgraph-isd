from __future__ import annotations
from ..schema import TaskRequest
from .base import BaseISDAgent, _format_task, parse_json_response

_SYSTEM = """\
You are an expert instructional designer creating assessment instruments (ADDIE Development phase).

Given a training scenario, produce ONLY valid JSON with this EXACT schema:
{
  "assessment_tools": [
    {"item_id": "AT-01", "type": "multiple_choice", "question": "<question>", "aligned_objective": "LO-01", "scoring_criteria": "<criteria>"},
    {"item_id": "AT-02", "type": "multiple_choice", "question": "<question>", "aligned_objective": "LO-02", "scoring_criteria": "<criteria>"},
    {"item_id": "AT-03", "type": "multiple_choice", "question": "<question>", "aligned_objective": "LO-03", "scoring_criteria": "<criteria>"},
    {"item_id": "AT-04", "type": "short_answer", "question": "<question>", "aligned_objective": "LO-03", "scoring_criteria": "<criteria>"},
    {"item_id": "AT-05", "type": "short_answer", "question": "<question>", "aligned_objective": "LO-04", "scoring_criteria": "<criteria>"},
    {"item_id": "AT-06", "type": "performance_task", "question": "<question>", "aligned_objective": "LO-04", "scoring_criteria": "<criteria>"},
    {"item_id": "AT-07", "type": "performance_task", "question": "<question>", "aligned_objective": "LO-05", "scoring_criteria": "<criteria>"},
    {"item_id": "AT-08", "type": "multiple_choice", "question": "<question>", "aligned_objective": "LO-01", "scoring_criteria": "<criteria>"},
    {"item_id": "AT-09", "type": "short_answer", "question": "<question>", "aligned_objective": "LO-02", "scoring_criteria": "<criteria>"},
    {"item_id": "AT-10", "type": "performance_task", "question": "<question>", "aligned_objective": "LO-05", "scoring_criteria": "<criteria>"}
  ],
  "expert_review": {
    "reviewers": ["<SME reviewer>", "<instructional designer reviewer>"],
    "review_criteria": ["<criterion1>", "<criterion2>", "<criterion3>", "<criterion4>", "<criterion5>"],
    "feedback_summary": "<summary of expected feedback and validation>",
    "revisions_made": ["<revision1>", "<revision2>"]
  }
}

Must include at least 10 assessment items distributed across difficulty levels (easy/medium/hard).
Every learning objective LO-01 through LO-05 must have at least one assessment item, and LO-05 must be measured by a performance_task or rubric-based peer-feedback task.
Output ONLY the JSON object, no markdown, no explanation.\
"""




class AssessmentDesignAgent(BaseISDAgent):
    def run(self, task: TaskRequest, context_pack: dict) -> None:
        prompt = _format_task(task)
        # Graph-subgraph RAG: inject prior G_t nodes into this agent's prompt
        prior_ctx = self._graph_context(['needs_context', 'objective'])
        user_content = prompt
        if prior_ctx:
            user_content = f"=== ANALYSIS + DESIGN RESULTS (from prior agents) ===\n{prior_ctx}\n\n=== SCENARIO ===\n{prompt}"
        rag_ctx = self._context_pack_text(context_pack)
        if rag_ctx:
            user_content = f"=== RETRIEVED CONTEXT PACK ===\n{rag_ctx}\n\n{user_content}"
        messages = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_content},
        ]
        response = self._call_llm(messages)
        parsed = parse_json_response(response)
        node_id = "assessment_0"
        if self.graph.get_nodes("objective"):
            objective_data = self.graph.get_nodes("objective")[0]["data"]
            self._ensure_assessment_coverage(parsed, objective_data.get("learning_objectives", []))
        self.graph.add_node("assessment", node_id, parsed)
        self.trajectory.log_node_edit("add", node_id, "assessment")
        if self.graph.get_nodes("objective"):
            obj_id = self.graph.get_nodes("objective")[0]["id"]
            objective_data = self.graph.get_nodes("objective")[0]["data"]
            lo_ids = [
                lo.get("id")
                for lo in objective_data.get("learning_objectives", [])
                if isinstance(lo, dict) and lo.get("id")
            ]
            aligned_ids = {
                item.get("aligned_objective")
                for item in parsed.get("assessment_tools", [])
                if isinstance(item, dict) and item.get("aligned_objective")
            }
            for lo_id in sorted(set(aligned_ids).union(lo_ids)):
                rationale = f"Assessment tool set includes an item aligned to {lo_id}."
                self.graph.add_edge(
                    "measures",
                    node_id,
                    obj_id,
                    evidence=lo_id,
                    rationale=rationale,
                    verified=True,
                )
                self.trajectory.log_edge_edit("add", node_id, obj_id, "measures", lo_id, rationale)
        self.trajectory.log_step("AssessmentDesignAgent", "design_assessments", prompt[:200], response[:200] if response else "")

    def repair(self, violations: list) -> list:
        remaining = []
        for violation in violations:
            is_owner = (
                getattr(violation, "violation_type", "") == "coverage"
                or getattr(violation, "edge_type", "") == "measures"
            )
            if not is_owner:
                remaining.append(violation)
                continue
            self._repair_assessment_coverage(violation)
        return remaining

    def _ensure_assessment_coverage(self, parsed: dict, objectives: list) -> None:
        tools = parsed.setdefault("assessment_tools", [])
        if not isinstance(tools, list):
            parsed["assessment_tools"] = []
            tools = parsed["assessment_tools"]

        covered = {
            item.get("aligned_objective")
            for item in tools
            if isinstance(item, dict) and item.get("aligned_objective")
        }

        for lo in objectives:
            if not isinstance(lo, dict):
                continue
            lo_id = lo.get("id")
            if not lo_id or lo_id in covered:
                continue
            tools.append({
                "item_id": f"AT-R-{lo_id}",
                "type": "performance_task",
                "question": f"Use scenario evidence to demonstrate and evaluate mastery of {lo_id}: {lo.get('statement', '')}",
                "aligned_objective": lo_id,
                "scoring_criteria": "Rubric scores observable performance, communication accuracy, peer-feedback quality, and transfer to a realistic scenario.",
                "difficulty": "hard",
                "coverage_repair": True,
            })
            covered.add(lo_id)

    def _repair_assessment_coverage(self, violation) -> None:
        objective = self.graph.get_node(violation.node_id)
        if not objective:
            return

        assessment = self.graph.get_node("assessment_0")
        if assessment:
            assessment_data = assessment["data"]
        else:
            assessment_data = {"assessment_tools": [], "expert_review": {}, "repaired": True}
            self.graph.add_node("assessment", "assessment_0", assessment_data, repair_history=[violation.message])
            self.trajectory.log_node_edit("add", "assessment_0", "assessment")

        assessment_tools = assessment_data.setdefault("assessment_tools", [])
        if not isinstance(assessment_tools, list):
            assessment_data["assessment_tools"] = []
            assessment_tools = assessment_data["assessment_tools"]

        covered = {
            item.get("aligned_objective")
            for item in assessment_tools
            if isinstance(item, dict) and item.get("aligned_objective")
        }
        repaired_ids: list[str] = []
        for lo in objective["data"].get("learning_objectives", []):
            if not isinstance(lo, dict):
                continue
            lo_id = lo.get("id")
            if not lo_id or lo_id in covered:
                continue
            item_id = f"AT-R-{lo_id}"
            assessment_tools.append({
                "item_id": item_id,
                "type": "performance_task",
                "question": f"Demonstrate the target skill for {lo_id}: {lo.get('statement', '')}",
                "aligned_objective": lo_id,
                "scoring_criteria": "Score accuracy, context appropriateness, learner independence, and evidence of transfer.",
                "difficulty": "hard",
                "repaired": True,
            })
            rationale = f"AssessmentDesignAgent repair added {item_id} to measure {lo_id}."
            self.graph.add_edge(
                "measures",
                "assessment_0",
                violation.node_id,
                evidence=lo_id,
                rationale=rationale,
                verified=True,
            )
            self.trajectory.log_edge_edit("add", "assessment_0", violation.node_id, "measures", lo_id, rationale)
            covered.add(lo_id)
            repaired_ids.append(lo_id)

        self.graph.update_node("assessment_0", {"assessment_tools": assessment_tools, "repaired": True})
        self.graph.clear_stale("assessment_0")
        self.graph.mark_repaired("assessment_0", violation.message)
        impact = self._invalidate_impacted(
            "assessment_0",
            "Assessment repair changed evidence coverage; dependent practice and evaluation plans must be refreshed.",
            action="repair_cascade",
            changed_fields=["assessment_tools", "measures_edges"],
        )
        self.trajectory.log_step(
            "AssessmentDesignAgent",
            "repair_assessment_coverage",
            violation.message,
            (
                f"Added assessment coverage for {', '.join(repaired_ids) or 'existing objectives'}; "
                f"invalidated nodes={len(impact['nodes'])} edges={len(impact['edges'])}."
            ),
        )
