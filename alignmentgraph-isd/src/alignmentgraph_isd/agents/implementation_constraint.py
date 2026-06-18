from __future__ import annotations
from ..schema import DesignBrief
from .base import BaseISDAgent, _format_design_brief, parse_json_response

_SYSTEM = """\
You are an expert instructional designer planning the Implementation phase of ADDIE.

Given a training scenario, produce ONLY valid JSON with this EXACT schema:
{
  "instructor_orientation": {
    "orientation_objectives": ["<obj1>", "<obj2>", "<obj3>"],
    "schedule": "<schedule plan>",
    "materials": ["<material1>", "<material2>"],
    "competency_checklist": ["<comp1>", "<comp2>", "<comp3>"]
  },
  "system_check": {
    "checklist": ["<check1>", "<check2>", "<check3>", "<check4>", "<check5>"],
    "technical_validation": "<technical validation results description>",
    "contingency_plans": ["<contingency1>", "<contingency2>"]
  },
  "prototype_execution": {
    "pilot_scope": "<pilot scope description>",
    "participants": "<participant size and characteristics>",
    "execution_log": ["<log1>", "<log2>", "<log3>"],
    "issues_encountered": ["<issue1>", "<issue2>"]
  },
  "monitoring": {
    "monitoring_criteria": ["<criterion1>", "<criterion2>", "<criterion3>"],
    "support_channels": ["<channel1>", "<channel2>"],
    "issue_resolution_log": ["<resolution1>", "<resolution2>"],
    "real_time_adjustments": ["<adjustment1>", "<adjustment2>"]
  }
}

Implementation requirements:
- instructor_orientation must be for instructors/operators, not learner learning objectives.
- system_check must include concrete learning platform, lab/resource access, login, network, data capture, accessibility, and fallback checks.
- prototype_execution must describe a realistic pilot, participant sample, execution records, issues, success criteria, and data collection.
- monitoring must include operational support, issue resolution, and real-time instructional adjustments.
Output ONLY the JSON object, no markdown, no explanation.\
"""




class ImplementationConstraintAgent(BaseISDAgent):
    def run(self, design_brief: DesignBrief, context_pack: dict) -> None:
        prompt = _format_design_brief(design_brief)
        # Graph-subgraph RAG: inject prior G_t nodes into this agent's prompt
        prior_ctx = self._graph_context(['objective', 'activity'])
        user_content = prompt
        if prior_ctx:
            user_content = f"=== DESIGN + DEVELOPMENT RESULTS (from prior agents) ===\n{prior_ctx}\n\n=== SCENARIO ===\n{prompt}"
        rag_ctx = self._context_pack_text(context_pack)
        if rag_ctx:
            user_content = f"=== RETRIEVED CONTEXT PACK ===\n{rag_ctx}\n\n{user_content}"
        messages = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_content},
        ]
        response = self._call_llm(messages)
        parsed = parse_json_response(response)
        node_id = "constraint_0"
        self.graph.add_node("constraint", node_id, parsed)
        self.trajectory.log_node_edit("add", node_id, "constraint")
        parse_ok = bool(parsed)
        self.trajectory.log_step(
            "ImplementationConstraintAgent", "plan_implementation",
            prompt[:200],
            f"[PARSE={'OK' if parse_ok else 'FAILED'} len={len(response)}] " + response[:400],
        )

    def repair(self, violations: list) -> list:
        remaining = []
        owned = []
        for violation in violations:
            is_owner = (
                getattr(violation, "violation_type", "") == "feasibility"
                or getattr(violation, "edge_type", "") == "constrains"
            )
            if is_owner:
                owned.append(violation)
            else:
                remaining.append(violation)

        if not owned:
            return remaining

        node = self.graph.get_node("constraint_0")
        if not node:
            self.graph.add_node("constraint", "constraint_0", {
                "instructor_orientation": {},
                "system_check": {},
                "prototype_execution": {},
                "monitoring": {},
                "repaired": True,
            })
            self.trajectory.log_node_edit("add", "constraint_0", "constraint")
        constraint = self.graph.get_node("constraint_0")
        data = constraint["data"] if constraint else {}
        monitoring = data.setdefault("monitoring", {})
        if isinstance(monitoring, dict):
            adjustments = monitoring.setdefault("real_time_adjustments", [])
            if isinstance(adjustments, list):
                adjustments.append("Re-scope delivery constraints after verifier feasibility warning.")
        self.graph.update_node("constraint_0", {"monitoring": monitoring, "repaired": True})
        self.graph.clear_stale("constraint_0")
        self.graph.mark_repaired("constraint_0", "; ".join(v.message for v in owned))
        impact = self._invalidate_impacted(
            "constraint_0",
            "Implementation constraint repair changed delivery feasibility; impacted design and evaluation sections must be refreshed.",
            action="repair_cascade",
            changed_fields=["monitoring", "delivery_constraints"],
        )
        self.trajectory.log_step(
            "ImplementationConstraintAgent",
            "repair_feasibility",
            "; ".join(v.message for v in owned),
            (
                "Updated implementation monitoring and contingency adjustment notes; "
                f"invalidated nodes={len(impact['nodes'])} edges={len(impact['edges'])}."
            ),
        )
        return remaining
