from __future__ import annotations
from ..graph import NodeType
from ..schema import DesignBrief
from .. import alignment
from .base import BaseISDAgent, _format_design_brief, parse_json_response

# The Evaluation phase is generated in TWO calls, not one. Its combined JSON
# (formative + summative + improvement_plan, all deeply nested) is the largest
# single section, and on a small model with a hard output cap (e.g. a 2B
# endpoint capping completion at 4096 tokens) it overflows and truncates,
# wiping the whole section. Splitting the summative block (the biggest part)
# from formative+improvement keeps each call well under the cap — the same
# "narrow subtask for a weak model" rationale as the rest of the harness.
_SYSTEM_SUMMATIVE = """\
You are an expert instructional designer planning the SUMMATIVE evaluation (ADDIE Evaluation phase).

Given a training scenario and its learning objectives, produce ONLY valid JSON with this EXACT schema:
{
  "summative": {
    "assessment_tools": [
      {"item_id": "SA-01", "type": "comprehensive", "question": "<question>", "aligned_objective": "LO-01", "scoring_rubric": "<rubric>"},
      {"item_id": "SA-02", "type": "comprehensive", "question": "<question>", "aligned_objective": "LO-02", "scoring_rubric": "<rubric>"},
      {"item_id": "SA-03", "type": "comprehensive", "question": "<question>", "aligned_objective": "LO-03", "scoring_rubric": "<rubric>"},
      {"item_id": "SA-04", "type": "performance", "question": "<question>", "aligned_objective": "LO-04", "scoring_rubric": "<rubric>"},
      {"item_id": "SA-05", "type": "performance", "question": "<question>", "aligned_objective": "LO-05", "scoring_rubric": "<rubric>"}
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
  }
}

Every summative item's ``aligned_objective`` must name an existing learning objective, and every
objective needs at least one summative item.
Output ONLY the JSON object, no markdown, no explanation.\
"""

_SYSTEM_FORMATIVE = """\
You are an expert instructional designer planning the FORMATIVE evaluation and improvement plan
(ADDIE Evaluation phase).

Given a training scenario, its assessment plan's formative intent, and any needs-analysis gaps,
produce ONLY valid JSON with this EXACT schema:
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
  "improvement_plan": {
    "feedback_summary": "<feedback summary>",
    "improvement_areas": ["<area1>", "<area2>", "<area3>"],
    "action_items": ["<action1>", "<action2>", "<action3>"],
    "feedback_loop": "<feedback loop description>",
    "next_iteration_goals": ["<goal1>", "<goal2>"]
  }
}

``formative.data_collection.methods`` must realize the assessment plan's formative intent given.
``improvement_plan.action_items`` must directly address the needs-analysis gaps given, not generic
suggestions.
Output ONLY the JSON object, no markdown, no explanation.\
"""


class EvaluationRevisionAgent(BaseISDAgent):
    # R5/R12/R13 are alignment-tier coverage checks;
    # evaluation_quality is a content-quality check that always runs.
    OWNED_VIOLATION_TYPES = frozenset({"R5", "R12", "R13", "evaluation_quality"})

    def run(self, design_brief: DesignBrief) -> None:
        prompt = _format_design_brief(design_brief)
        gap_nodes = self.graph.element_nodes("gap")
        objective_nodes = self.graph.element_nodes(NodeType.OBJECTIVE)
        plan_node = self.graph.get_node(self.graph.section_id("assessment_plan"))
        prior_ctx = self._element_context(objective_nodes + ([plan_node] if plan_node else []) + gap_nodes)
        base = prompt
        if prior_ctx:
            base = f"=== OBJECTIVES + ASSESSMENT PLAN + NEEDS GAPS ===\n{prior_ctx}\n\n=== SCENARIO ===\n{prompt}"
        base = self._with_retrieval(design_brief, "evaluation_revision", base)

        # Two calls (see the module comment): summative alone, then
        # formative+improvement — each stays under a small model's output cap.
        # Surgical regen: reuse whichever half a prior attempt already produced,
        # so a whole-specialist regen only re-rolls the call that came back empty.
        prior = (self.graph.get_node(self.graph.section_id(NodeType.EVALUATION)) or {}).get("data", {}) or {}
        if prior.get("summative"):
            summative = {"summative": prior["summative"]}
        else:
            summative = parse_json_response(self._call_llm([
                {"role": "system", "content": _SYSTEM_SUMMATIVE},
                {"role": "user", "content": base},
            ]))
        if prior.get("formative"):
            formative = {"formative": prior["formative"], "improvement_plan": prior.get("improvement_plan", {})}
        else:
            formative = parse_json_response(self._call_llm([
                {"role": "system", "content": _SYSTEM_FORMATIVE},
                {"role": "user", "content": base},
            ]))

        parsed = {
            "formative": formative.get("formative", {}),
            "summative": summative.get("summative", {}),
            "improvement_plan": formative.get("improvement_plan", {}),
        }
        node_id = self.graph.section_id(NodeType.EVALUATION)
        self.graph.add_node(NodeType.EVALUATION, node_id, parsed)
        self.trajectory.log_node_edit("add", node_id, NodeType.EVALUATION)

        self._establish_relations(parsed, gap_nodes)
        self.trajectory.log_step("EvaluationRevisionAgent", "plan_evaluation", prompt[:200],
                                 f"summative_items={len(parsed['summative'].get('assessment_tools', []))}")

    def _establish_relations(self, parsed: dict, gap_nodes: list[dict]) -> None:
        # R5/R12 (id/type-match) stay unconditional — no traversal required.
        summative_ids = self._decompose_elements(
            "summative", parsed.get("summative", {}).get("assessment_tools", []), id_field="item_id",
        )
        for sid in summative_ids:
            self.trajectory.log_node_edit("add", sid, "summative")
        alignment.match_id(self.graph, "R5", target_node_type=NodeType.OBJECTIVE, field="aligned_objective")

        alignment.match_r12_realizes(self.graph)

        improvement_ids = self._decompose_auto_id(
            "improvement", parsed.get("improvement_plan", {}).get("action_items"),
            id_prefix="IMP", text_key="action",
        )
        for iid in improvement_ids:
            self.trajectory.log_node_edit("add", iid, "improvement")
        # R13 is provenance: this call was conditioned on the traversed gap nodes.
        gap_ids = [n["id"] for n in gap_nodes]
        for improvement_id in improvement_ids:
            alignment.record_provenance(self.graph, "R13", gap_ids, improvement_id)

    def repair(self, violations: list) -> list:
        remaining = []
        quality_violations = []
        r5_violations = []
        r12_violations = []
        r13_violations = []
        for violation in violations:
            vtype = getattr(violation, "violation_type", "")
            if vtype == "evaluation_quality":
                quality_violations.append(violation)
            elif vtype == "R5":
                r5_violations.append(violation)
            elif vtype == "R12":
                r12_violations.append(violation)
            elif vtype == "R13":
                r13_violations.append(violation)
            else:
                remaining.append(violation)
        for violation in quality_violations:
            self._repair_formative_methods(violation)
        if r5_violations:
            self._repair_evaluation_alignment(r5_violations)
        if r12_violations:
            self._repair_formative_realizes(r12_violations)
        if r13_violations:
            self._repair_improvement_addresses(r13_violations)
        return remaining

    _FALLBACK_METHODS = [
        "Structured observation during activities using a facilitation checklist",
        "Exit tickets after each module scored against the objective criteria",
        "Rubric-scored formative checkpoints with instructor feedback",
    ]

    def _repair_formative_methods(self, violation) -> None:
        """Fill in concrete formative data-collection methods (evaluation_quality).

        One LLM call drafts context-specific methods; the deterministic
        fallback guarantees the finding is resolved either way.
        """
        node_id = self.graph.section_id(NodeType.EVALUATION)
        node = self.graph.get_node(node_id)
        if not node:
            return
        data = node["data"]
        formative = data.get("formative")
        if not isinstance(formative, dict):
            formative = {}
            data["formative"] = formative

        methods = self._llm_formative_methods(data)
        if not methods:
            methods = list(self._FALLBACK_METHODS)

        data_collection = formative.get("data_collection")
        if isinstance(data_collection, dict):
            data_collection["methods"] = methods
        else:
            formative["methods"] = methods

        self.graph.update_node(node_id, {"formative": formative, "repaired": True})
        self._log_repair(node_id, violation_type="evaluation_quality", repaired_fields=["formative"])
        self.trajectory.log_node_edit("update", node_id, NodeType.EVALUATION)
        self.trajectory.log_step(
            "EvaluationRevisionAgent",
            "repair_formative_methods",
            violation.message,
            f"Set {len(methods)} formative data-collection method(s).",
        )

    def _llm_formative_methods(self, evaluation_data: dict) -> list[str]:
        import json

        system = (
            "You are an expert instructional designer fixing a formative evaluation plan that "
            "names no data-collection method. Return ONLY valid JSON: "
            '{"methods": ["<concrete method 1>", "<concrete method 2>", "<concrete method 3>"]}\n'
            "Each method must name an instrument and a cadence (e.g. 'exit tickets after each "
            "module'), consistent with the evaluation plan provided."
        )
        user = json.dumps({"evaluation_plan": evaluation_data}, ensure_ascii=False)[:4000]
        response = self._call_llm(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_retries=0,
        )
        parsed = parse_json_response(response, warn=False) or {}
        methods = parsed.get("methods")
        if isinstance(methods, list):
            cleaned = [str(m).strip() for m in methods if str(m).strip()]
            return cleaned[:5]
        return []

    def _repair_evaluation_alignment(self, violations: list) -> None:
        """R5: add a summative item for every objective with no evaluation
        evidence, then re-run the id-match establisher."""
        node_id = self.graph.section_id(NodeType.EVALUATION)
        evaluation = self.graph.get_node(node_id)
        if evaluation:
            evaluation_data = evaluation["data"]
        else:
            evaluation_data = {"formative": {}, "summative": {}, "improvement_plan": {}, "repaired": True}
            self.graph.add_node(NodeType.EVALUATION, node_id, evaluation_data)
            self.trajectory.log_node_edit("add", node_id, NodeType.EVALUATION)

        summative = evaluation_data.setdefault("summative", {})
        tools = summative.setdefault("assessment_tools", [])
        if not isinstance(tools, list):
            tools = []
            summative["assessment_tools"] = tools
        objective_node = self.graph.get_node(self.graph.section_id(NodeType.OBJECTIVE))
        lo_map = {
            str(lo["id"]): lo
            for lo in (objective_node["data"].get("learning_objectives", []) if objective_node else [])
            if isinstance(lo, dict) and lo.get("id")
        }

        lo_ids = list(lo_map)
        repaired_ids: list[str] = []
        for violation in violations:
            md = violation.metadata
            lo_id = str(md.get("lo_id") or "")
            dangling_item_id = str(md.get("item_id") or "")
            if lo_id:
                # Uncovered objective: add a new summative item measuring it.
                item_id = f"SA-R-{lo_id}"
                tools.append({
                    "item_id": item_id,
                    "type": "comprehensive",
                    "question": f"Summative evidence for {lo_id}: {lo_map.get(lo_id, {}).get('statement', '')}",
                    "aligned_objective": lo_id,
                    "scoring_rubric": "Score against the objective's success criteria.",
                    "repaired": True,
                })
                repaired_ids.append(item_id)
            elif dangling_item_id:
                # Dangling reference: an existing item's aligned_objective
                # doesn't resolve to a real LO — point it at one.
                item = next((t for t in tools if isinstance(t, dict) and str(t.get("item_id")) == dangling_item_id), None)
                if not item:
                    continue
                aligned = str(item.get("aligned_objective") or "")
                if lo_ids and aligned not in lo_map:
                    question = str(item.get("question", "")).lower()
                    item["aligned_objective"] = next(
                        (lo for lo in lo_ids if lo.lower() in question), lo_ids[0]
                    )
                item["repaired"] = True
                repaired_ids.append(dangling_item_id)

        self.graph.update_node(node_id, {"summative": summative, "repaired": True})
        for item in tools:
            if isinstance(item, dict) and item.get("item_id"):
                self.graph.add_element_node("summative", str(item["item_id"]), dict(item))
        alignment.match_id(self.graph, "R5", target_node_type=NodeType.OBJECTIVE, field="aligned_objective")
        self._log_repair(node_id, violation_type="R5", repaired_fields=["summative"])
        self.trajectory.log_step(
            "EvaluationRevisionAgent",
            "repair_evaluation_alignment",
            "; ".join(v.message for v in violations)[:200],
            f"Added summative evidence for {', '.join(repaired_ids) or 'existing objectives'}.",
        )

    def _repair_formative_realizes(self, violations: list) -> None:
        """R12: the formative evaluation doesn't realize the plan's formative
        intent — fill in data-collection methods (reuses the same fix as
        evaluation_quality, since a non-empty concrete methods list is what
        makes the presence check pass) then re-establish."""
        for violation in violations:
            self._repair_formative_methods(violation)
        alignment.match_r12_realizes(self.graph)

    def _repair_improvement_addresses(self, violations: list) -> None:
        """R13: an improvement item wasn't recorded as addressing any gap —
        re-record provenance against all current gap nodes (the item already
        exists; this only needed the specialist to (re-)declare the link)."""
        node_id = self.graph.section_id(NodeType.EVALUATION)
        gap_ids = [n["id"] for n in self.graph.element_nodes("gap")]
        repaired_ids: list[str] = []
        for violation in violations:
            item_id = str(violation.metadata.get("node_id") or violation.node_id or "")
            if item_id and gap_ids:
                alignment.record_provenance(self.graph, "R13", gap_ids, item_id)
                repaired_ids.append(item_id)
        self._log_repair(node_id, violation_type="R13", repaired_fields=["improvement_plan"])
        self.trajectory.log_step(
            "EvaluationRevisionAgent",
            "repair_improvement_addresses",
            "; ".join(v.message for v in violations)[:200],
            f"Re-linked improvement items to gaps: {', '.join(repaired_ids) or 'none'}.",
        )
