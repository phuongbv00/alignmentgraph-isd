from __future__ import annotations
from ..graph import EdgeType, NodeType
from ..schema import DesignBrief
from .base import BaseISDAgent, _format_design_brief, parse_json_response

_SYSTEM = """\
You are an expert instructional designer planning the Evaluation phase of ADDIE.

Given a training scenario, produce ONLY valid JSON with this EXACT schema:
{
  "formative": {
    "data_collection": {
      "methods": ["<method1>", "<method2>", "<method3>"],
      "learner_feedback": ["<feedback1>", "<feedback2>", "<feedback3>"],
      "performance_data": {"metric1": "<metric1 description>", "metric2": "<metric2 description>"},
      "observations": ["<observation1>", "<observation2>"]
    },
    "improvements": [
      {"issue_identified": "<issue1>", "improvement_action": "<action1>", "priority": "high"},
      {"issue_identified": "<issue2>", "improvement_action": "<action2>", "priority": "medium"},
      {"issue_identified": "<issue3>", "improvement_action": "<action3>", "priority": "low"}
    ]
  },
  "summative": {
    "assessment_tools": [
      {"item_id": "SA-01", "type": "comprehensive", "question": "<question>", "scoring_rubric": "<rubric>"},
      {"item_id": "SA-02", "type": "comprehensive", "question": "<question>", "scoring_rubric": "<rubric>"},
      {"item_id": "SA-03", "type": "comprehensive", "question": "<question>", "scoring_rubric": "<rubric>"},
      {"item_id": "SA-04", "type": "performance", "question": "<question>", "scoring_rubric": "<rubric>"},
      {"item_id": "SA-05", "type": "performance", "question": "<question>", "scoring_rubric": "<rubric>"}
    ],
    "effectiveness_analysis": {
      "learning_outcomes": {"achievement_rate": "85%", "details": "<outcome analysis>"},
      "goal_achievement_rate": "<rate>",
      "statistical_analysis": "<statistical analysis description>",
      "recommendations": ["<rec1>", "<rec2>", "<rec3>"]
    },
    "adoption_decision": {
      "decision": "adopt",
      "rationale": "<decision rationale in 2-3 sentences>",
      "conditions": ["<condition1>", "<condition2>"],
      "stakeholder_approval": "<stakeholder approval status>"
    }
  },
  "improvement_plan": {
    "feedback_summary": "<feedback summary>",
    "improvement_areas": ["<area1>", "<area2>", "<area3>"],
    "action_items": ["<action1>", "<action2>", "<action3>"],
    "feedback_loop": "<feedback loop description>",
    "next_iteration_goals": ["<goal1>", "<goal2>"]
  }
}

Output ONLY the JSON object, no markdown, no explanation.\
"""




class EvaluationRevisionAgent(BaseISDAgent):
    def run(self, design_brief: DesignBrief, context_pack: dict) -> None:
        prompt = _format_design_brief(design_brief)
        # Graph-context retrieval (core, not RAG): inject prior G_t nodes into this prompt
        prior_ctx = self._graph_context([NodeType.OBJECTIVE, NodeType.ASSESSMENT, NodeType.ACTIVITY])
        user_content = prompt
        if prior_ctx:
            user_content = f"=== DESIGN + DEVELOPMENT RESULTS (from prior agents) ===\n{prior_ctx}\n\n=== SCENARIO ===\n{prompt}"
        pack_ctx = self._context_pack_text(context_pack)
        if pack_ctx:
            user_content = f"=== RETRIEVED CONTEXT PACK ===\n{pack_ctx}\n\n{user_content}"
        messages = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_content},
        ]
        response = self._call_llm(messages)
        parsed = parse_json_response(response)
        node_id = self.graph.section_id(NodeType.EVALUATION)
        self.graph.add_node(NodeType.EVALUATION, node_id, parsed)
        self.trajectory.log_node_edit("add", node_id, NodeType.EVALUATION)
        if self.graph.get_nodes(NodeType.OBJECTIVE):
            obj = self.graph.get_nodes(NodeType.OBJECTIVE)[0]
            obj_id = obj["id"]
            lo_ids = [
                lo.get("id")
                for lo in obj["data"].get("learning_objectives", [])
                if isinstance(lo, dict) and lo.get("id")
            ]
            for lo_id in lo_ids:
                rationale = f"Evaluation plan reports learning evidence for {lo_id}."
                self.graph.add_edge(
                    EdgeType.EVALUATES,
                    node_id,
                    obj_id,
                    evidence=lo_id,
                    rationale=rationale,
                    verified=True,
                )
                self._add_element_edge(EdgeType.EVALUATES, node_id, lo_id, rationale=rationale)
                self.trajectory.log_edge_edit("add", node_id, obj_id, EdgeType.EVALUATES, lo_id, rationale)
        self.trajectory.log_step("EvaluationRevisionAgent", "plan_evaluation", prompt[:200], response[:200] if response else "")

    def repair(self, violations: list) -> list:
        remaining = []
        for violation in violations:
            if getattr(violation, "edge_type", "") != EdgeType.EVALUATES:
                remaining.append(violation)
                continue
            self._repair_evaluation_alignment(violation)
        return remaining

    def _repair_evaluation_alignment(self, violation) -> None:
        objective = self.graph.get_node(violation.node_id)
        if not objective:
            return

        evaluation = self.graph.get_node(self.graph.section_id(NodeType.EVALUATION))
        if evaluation:
            evaluation_data = evaluation["data"]
        else:
            evaluation_data = {"formative": {}, "summative": {}, "improvement_plan": {}, "repaired": True}
            self.graph.add_node(NodeType.EVALUATION, self.graph.section_id(NodeType.EVALUATION), evaluation_data, repair_history=[violation.message])
            self.trajectory.log_node_edit("add", self.graph.section_id(NodeType.EVALUATION), NodeType.EVALUATION)

        repaired_ids: list[str] = []
        for lo in objective["data"].get("learning_objectives", []):
            if not isinstance(lo, dict) or not lo.get("id"):
                continue
            lo_id = lo["id"]
            rationale = f"EvaluationRevisionAgent repair adds evaluation evidence for {lo_id}."
            self.graph.add_edge(
                EdgeType.EVALUATES,
                self.graph.section_id(NodeType.EVALUATION),
                violation.node_id,
                evidence=lo_id,
                rationale=rationale,
                verified=True,
            )
            self._add_element_edge(EdgeType.EVALUATES, self.graph.section_id(NodeType.EVALUATION), lo_id, rationale=rationale)
            self.trajectory.log_edge_edit("add", self.graph.section_id(NodeType.EVALUATION), violation.node_id, EdgeType.EVALUATES, lo_id, rationale)
            repaired_ids.append(lo_id)

        improvement = evaluation_data.setdefault("improvement_plan", {})
        if isinstance(improvement, dict):
            action_items = improvement.setdefault("action_items", [])
            if isinstance(action_items, list):
                action_items.append("Re-check evaluation evidence after upstream repair cascade.")
        self.graph.update_node(self.graph.section_id(NodeType.EVALUATION), {"improvement_plan": improvement, "repaired": True})
        self.graph.clear_stale(self.graph.section_id(NodeType.EVALUATION))
        self.graph.mark_repaired(self.graph.section_id(NodeType.EVALUATION), violation.message)
        impact = self._invalidate_impacted(
            self.graph.section_id(NodeType.EVALUATION),
            "Evaluation repair changed evidence plan; assessment evidence should be rechecked for consistency.",
            action="repair_cascade",
            changed_fields=["improvement_plan", "evaluates_edges"],
            violation_type=getattr(violation, "violation_type", "evaluation_alignment"),
        )
        self.trajectory.log_step(
            "EvaluationRevisionAgent",
            "repair_evaluation_alignment",
            violation.message,
            (
                f"Added evaluates edges for {', '.join(repaired_ids) or 'existing objectives'}; "
                f"invalidated nodes={len(impact['nodes'])} edges={len(impact['edges'])}."
            ),
        )
