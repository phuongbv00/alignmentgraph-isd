from __future__ import annotations
from ..graph import EdgeType, NodeType
from ..schema import DesignBrief
from .base import BaseISDAgent, _format_design_brief, parse_json_response

_SYSTEM = """\
You are an expert instructional designer developing learning materials (ADDIE Development phase).

Given a training scenario, produce ONLY valid JSON with this EXACT schema:
{
  "learner_materials": [
    {"title": "<material1 title>", "type": "<type>", "content": "<description>", "format": "<format>"},
    {"title": "<material2 title>", "type": "<type>", "content": "<description>", "format": "<format>"},
    {"title": "<material3 title>", "type": "<type>", "content": "<description>", "format": "<format>"}
  ],
  "instructor_guide": {
    "overview": "<overall guide overview>",
    "session_guides": [
      {"session": 1, "objectives": ["<obj>"], "activities": ["<activity>"], "notes": "<notes>"},
      {"session": 2, "objectives": ["<obj>"], "activities": ["<activity>"], "notes": "<notes>"},
      {"session": 3, "objectives": ["<obj>"], "activities": ["<activity>"], "notes": "<notes>"}
    ],
    "facilitation_tips": ["<tip1>", "<tip2>", "<tip3>"],
    "troubleshooting": ["<troubleshoot1>", "<troubleshoot2>"]
  },
  "operator_manual": {
    "system_setup": "<detailed system setup guide>",
    "operation_procedures": ["<proc1>", "<proc2>", "<proc3>"],
    "support_procedures": ["<support1>", "<support2>"],
    "escalation_process": "<escalation process description>"
  }
}

Output ONLY the JSON object, no markdown, no explanation.\
"""




class ActivityMaterialAgent(BaseISDAgent):
    def run(self, design_brief: DesignBrief, context_pack: dict) -> None:
        prompt = _format_design_brief(design_brief)
        # Graph-context retrieval (core, not RAG): inject prior G_t nodes into this prompt
        prior_ctx = self._graph_context([NodeType.NEEDS_CONTEXT, NodeType.OBJECTIVE])
        user_content = prompt
        if prior_ctx:
            user_content = f"=== ANALYSIS + DESIGN RESULTS (from prior agents) ===\n{prior_ctx}\n\n=== SCENARIO ===\n{prompt}"
        pack_ctx = self._context_pack_text(context_pack)
        if pack_ctx:
            user_content = f"=== RETRIEVED CONTEXT PACK ===\n{pack_ctx}\n\n{user_content}"
        messages = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_content},
        ]
        response = self._call_llm(messages)
        parsed = parse_json_response(response)
        for node_type, node_id in [(NodeType.ACTIVITY, self.graph.section_id(NodeType.ACTIVITY)), (NodeType.MATERIAL, self.graph.section_id(NodeType.MATERIAL))]:
            self.graph.add_node(node_type, node_id, parsed)
            self.trajectory.log_node_edit("add", node_id, node_type)
        # No per-item element nodes: material stays section-level (no per-item
        # consumer — only objective is element-level, for coverage).
        if self.graph.get_nodes(NodeType.OBJECTIVE):
            obj = self.graph.get_nodes(NodeType.OBJECTIVE)[0]
            obj_id = obj["id"]
            lo_ids = [
                lo.get("id")
                for lo in obj["data"].get("learning_objectives", [])
                if isinstance(lo, dict) and lo.get("id")
            ]
            for lo_id in lo_ids:
                rationale = f"Developed learning materials and session guides support {lo_id}."
                self.graph.add_edge(
                    EdgeType.SUPPORTS,
                    self.graph.section_id(NodeType.ACTIVITY),
                    obj_id,
                    evidence=lo_id,
                    rationale=rationale,
                    verified=True,
                )
                self._add_element_edge(EdgeType.SUPPORTS, self.graph.section_id(NodeType.ACTIVITY), lo_id, rationale=rationale)
                self.trajectory.log_edge_edit("add", self.graph.section_id(NodeType.ACTIVITY), obj_id, EdgeType.SUPPORTS, lo_id, rationale)
        self.trajectory.log_step("ActivityMaterialAgent", "develop_activities", prompt[:200], response[:200] if response else "")

    def repair(self, violations: list) -> list:
        remaining = []
        for violation in violations:
            is_owner = (
                getattr(violation, "violation_type", "") == "activity_support"
                or getattr(violation, "edge_type", "") == EdgeType.SUPPORTS
            )
            if not is_owner:
                remaining.append(violation)
                continue
            self._repair_activity_support(violation)
        return remaining

    def _repair_activity_support(self, violation) -> None:
        objective = self.graph.get_node(violation.node_id)
        if not objective:
            return

        activity = self.graph.get_node(self.graph.section_id(NodeType.ACTIVITY))
        if activity:
            activity_data = activity["data"]
        else:
            activity_data = {"alignment_notes": [], "repaired": True}
            self.graph.add_node(NodeType.ACTIVITY, self.graph.section_id(NodeType.ACTIVITY), activity_data, repair_history=[violation.message])
            self.trajectory.log_node_edit("add", self.graph.section_id(NodeType.ACTIVITY), NodeType.ACTIVITY)

        alignment_notes = list(activity_data.get("alignment_notes", []))
        repaired_ids: list[str] = []
        for lo in objective["data"].get("learning_objectives", []):
            if not isinstance(lo, dict) or not lo.get("id"):
                continue
            lo_id = lo["id"]
            rationale = f"ActivityMaterialAgent repair explicitly supports {lo_id}."
            self.graph.add_edge(
                EdgeType.SUPPORTS,
                self.graph.section_id(NodeType.ACTIVITY),
                violation.node_id,
                evidence=lo_id,
                rationale=rationale,
                verified=True,
            )
            self._add_element_edge(EdgeType.SUPPORTS, self.graph.section_id(NodeType.ACTIVITY), lo_id, rationale=rationale)
            self.trajectory.log_edge_edit("add", self.graph.section_id(NodeType.ACTIVITY), violation.node_id, EdgeType.SUPPORTS, lo_id, rationale)
            alignment_notes.append(rationale)
            repaired_ids.append(lo_id)

        self.graph.update_node(self.graph.section_id(NodeType.ACTIVITY), {"alignment_notes": alignment_notes, "repaired": True})
        self.graph.clear_stale(self.graph.section_id(NodeType.ACTIVITY))
        self.graph.clear_stale(self.graph.section_id(NodeType.MATERIAL))
        self.graph.mark_repaired(self.graph.section_id(NodeType.ACTIVITY), violation.message)
        impact = self._invalidate_impacted(
            self.graph.section_id(NodeType.ACTIVITY),
            "Activity/material repair changed learning support; dependent assessment, constraints, and evaluation must be refreshed.",
            action="repair_cascade",
            changed_fields=["alignment_notes", "supports_edges"],
            violation_type=getattr(violation, "violation_type", "activity_support"),
        )
        self.trajectory.log_step(
            "ActivityMaterialAgent",
            "repair_activity_support",
            violation.message,
            (
                f"Added supports edges for {', '.join(repaired_ids) or 'existing objectives'}; "
                f"invalidated nodes={len(impact['nodes'])} edges={len(impact['edges'])}."
            ),
        )
