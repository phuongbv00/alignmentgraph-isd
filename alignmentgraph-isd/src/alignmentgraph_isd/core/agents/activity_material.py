from __future__ import annotations
from ..graph import NodeType
from ..schema import DesignBrief
from .. import alignment
from .base import BaseISDAgent, _format_design_brief, parse_json_response

_SYSTEM = """\
You are an expert instructional designer developing learning activities and materials
(ADDIE Development phase), realizing the instructional strategy and content modules from Design.

Given a training scenario, its learning objectives, instructional strategy, and content modules,
produce ONLY valid JSON with this EXACT schema:
{
  "learning_activities": [
    {"id": "ACT-01", "activity_name": "<name>", "duration": "<time>", "description": "<desc>", "materials": ["<material>"], "aligned_objectives": ["LO-01"], "linked_module": "MOD-01"},
    {"id": "ACT-02", "activity_name": "<name>", "duration": "<time>", "description": "<desc>", "materials": ["<material>"], "aligned_objectives": ["LO-02"], "linked_module": "MOD-01"},
    {"id": "ACT-03", "activity_name": "<name>", "duration": "<time>", "description": "<desc>", "materials": ["<material>"], "aligned_objectives": ["LO-03"], "linked_module": "MOD-02"}
  ],
  "learner_materials": [
    {"id": "MAT-01", "title": "<material1 title>", "type": "<type>", "content": "<description>", "format": "<format>"},
    {"id": "MAT-02", "title": "<material2 title>", "type": "<type>", "content": "<description>", "format": "<format>"},
    {"id": "MAT-03", "title": "<material3 title>", "type": "<type>", "content": "<description>", "format": "<format>"}
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

Every activity must list ``aligned_objectives`` (existing LO ids it practices) and a
``linked_module`` (an existing content module id it belongs to). Every higher-order objective
(Apply+) needs at least one hands-on activity (lab, exercise, project, simulation), not only
passive formats (lecture, reading, video). Activities must enact the instructional strategy given.
Output ONLY the JSON object, no markdown, no explanation.\
"""


class ActivityMaterialAgent(BaseISDAgent):
    # R4/R7/R8 are alignment-tier coverage checks (gated by enable_alignment_graph) this
    # specialist can concretely act on. R9 (media<->material type-match on a fuzzy alias
    # table) is audit-only, same as measurability: there is no deterministic fix that
    # wouldn't risk gaming the metric (e.g. inventing a fake media entry just to pass),
    # so it is reported but never claimed for repair. activity_engagement is a
    # content-quality check (always runs) that moved here from ObjectiveDesignAgent
    # since learning_activities has a single owner now.
    OWNED_VIOLATION_TYPES = frozenset({"R4", "R7", "R8", "activity_engagement"})

    def run(self, design_brief: DesignBrief) -> None:
        prompt = _format_design_brief(design_brief)
        if self._graph_coordination:
            objective_nodes = self.graph.element_nodes(NodeType.OBJECTIVE)
            module_nodes = self.graph.element_nodes("content")
            strategy_node = self.graph.get_node(self.graph.section_id("instructional_strategies"))
            media_nodes = self.graph.element_nodes("media")
            prior_ctx = self._element_context(
                objective_nodes + module_nodes + ([strategy_node] if strategy_node else []) + media_nodes
            )
        else:
            prior_ctx = self._graph_context([NodeType.OBJECTIVE, "content", "instructional_strategies", "media"])
        user_content = prompt
        if prior_ctx:
            user_content = f"=== OBJECTIVES + CONTENT MODULES + INSTRUCTIONAL STRATEGY ===\n{prior_ctx}\n\n=== SCENARIO ===\n{prompt}"
        user_content = self._with_retrieval(design_brief, "activity_material", user_content)
        messages = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_content},
        ]
        response = self._call_llm(messages)
        parsed = parse_json_response(response)
        for node_type, node_id in [(NodeType.ACTIVITY, self.graph.section_id(NodeType.ACTIVITY)), (NodeType.MATERIAL, self.graph.section_id(NodeType.MATERIAL))]:
            self.graph.add_node(node_type, node_id, parsed)
            self.trajectory.log_node_edit("add", node_id, node_type)

        # Element decomposition + edge establishment are the alignment graph;
        # the wo-graph arm ablates them (section blob only).
        if self._graph_coordination:
            activity_ids = self._decompose_elements("activity", parsed.get("learning_activities", []), id_field="id")
            material_ids = self._decompose_elements("material", parsed.get("learner_materials", []), id_field="id")
            for aid in activity_ids:
                self.trajectory.log_node_edit("add", aid, "activity")
            for mid in material_ids:
                self.trajectory.log_node_edit("add", mid, "material")
            self._establish_relations(activity_ids, material_ids)
        self.trajectory.log_step("ActivityMaterialAgent", "develop_activities", prompt[:200], response[:200] if response else "")

    def _establish_relations(self, activity_ids: list[str], material_ids: list[str]) -> None:
        # R4: objective -> activity (list-aware id-match on aligned_objectives).
        # Always on — no traversal required, just reading the item's own field.
        alignment.match_r4_supports(self.graph)

        if self._graph_coordination:
            # R7: instructional_strategies -> activity (provenance; the whole
            # call was conditioned on the strategy node).
            strategy_id = self.graph.section_id("instructional_strategies")
            if self.graph.get_node(strategy_id):
                for activity_id in activity_ids:
                    alignment.record_provenance(self.graph, "R7", [strategy_id], activity_id)

            # R8: content module -> activity/material, via the model-declared linked_module.
            for item_id in activity_ids + material_ids:
                node = self.graph.get_node(item_id)
                if not node:
                    continue
                module_ref = str(node["data"].get("linked_module", "") or "")
                module_id = f"content{self.graph.ELEMENT_SEP}{module_ref}" if module_ref else ""
                if module_ref and self.graph.get_node(module_id):
                    alignment.record_provenance(self.graph, "R8", [module_id], item_id)

        # R9: media_selection -> material (type-match on normalized category).
        # Always on — no traversal required.
        alignment.match_r9_realizes(self.graph)

    def repair(self, violations: list) -> list:
        remaining = []
        coverage_violations = []
        engagement_violations = []
        for violation in violations:
            vtype = getattr(violation, "violation_type", "")
            if vtype in ("R4", "R7", "R8"):
                coverage_violations.append(violation)
            elif vtype == "activity_engagement":
                engagement_violations.append(violation)
            else:
                remaining.append(violation)
        if coverage_violations:
            self._repair_alignment_coverage(coverage_violations)
        if engagement_violations:
            self._repair_activity_engagement(engagement_violations)
        return remaining

    def _repair_alignment_coverage(self, violations: list) -> None:
        """R4 (an objective with no supporting activity) is the only one of
        the four relations this specialist can concretely fix by adding
        content: R7/R8/R9 gaps mean a generated item didn't declare/realize
        its source and are fixed by tagging the existing item, not inventing
        new ones."""
        activity_node_id = self.graph.section_id(NodeType.ACTIVITY)
        activity_section = self.graph.get_node(activity_node_id)
        if not activity_section:
            activity_section_data = {"learning_activities": [], "repaired": True}
            self.graph.add_node(NodeType.ACTIVITY, activity_node_id, activity_section_data)
            self.trajectory.log_node_edit("add", activity_node_id, NodeType.ACTIVITY)
        else:
            activity_section_data = activity_section["data"]
        activities = [
            dict(a) if isinstance(a, dict) else a
            for a in activity_section_data.get("learning_activities", []) or []
        ]
        objective_node = self.graph.get_node(self.graph.section_id(NodeType.OBJECTIVE))
        lo_map = {
            str(lo["id"]): lo
            for lo in (objective_node["data"].get("learning_objectives", []) if objective_node else [])
            if isinstance(lo, dict) and lo.get("id")
        }
        module_nodes = self.graph.element_nodes("content")
        strategy_id = self.graph.section_id("instructional_strategies")

        repaired_ids: list[str] = []
        for violation in violations:
            md = violation.metadata
            if violation.violation_type == "R4":
                lo_id = str(md.get("lo_id") or "")
                if not lo_id:
                    continue
                new_id = f"ACT-R-{lo_id}"
                activities.append({
                    "id": new_id,
                    "activity_name": f"Guided practice for {lo_id}",
                    "duration": "45m",
                    "description": (
                        f"Learners practice the skill behind {lo_id} on a realistic task "
                        "with instructor feedback and a completion checklist."
                    ),
                    "materials": ["Practice task sheet"],
                    "aligned_objectives": [lo_id],
                    "linked_module": module_nodes[0]["id"].split(self.graph.ELEMENT_SEP, 1)[-1] if module_nodes else "",
                    "repaired": True,
                })
                repaired_ids.append(new_id)
            elif violation.violation_type == "R7" and self.graph.get_node(strategy_id):
                item_id = str(md.get("node_id") or "")
                if item_id:
                    alignment.record_provenance(self.graph, "R7", [strategy_id], item_id)
                    repaired_ids.append(item_id)
            elif violation.violation_type == "R8" and module_nodes:
                item_id = str(md.get("node_id") or "")
                node = self.graph.get_node(item_id) if item_id else None
                if node is not None:
                    node["data"]["linked_module"] = module_nodes[0]["id"].split(self.graph.ELEMENT_SEP, 1)[-1]
                    alignment.record_provenance(self.graph, "R8", [module_nodes[0]["id"]], item_id)
                    repaired_ids.append(item_id)

        self.graph.update_node(activity_node_id, {"learning_activities": activities, "repaired": True})
        for activity in activities:
            if isinstance(activity, dict) and activity.get("id"):
                self.graph.add_element_node("activity", str(activity["id"]), dict(activity))
        alignment.match_r4_supports(self.graph)
        alignment.match_r9_realizes(self.graph)
        self._log_repair(activity_node_id, violation_type=violations[0].violation_type, repaired_fields=["learning_activities"])
        self.trajectory.log_step(
            "ActivityMaterialAgent",
            "repair_alignment_coverage",
            "; ".join(v.message for v in violations)[:200],
            f"Fixed/added activities for {', '.join(repaired_ids) or 'existing coverage'}.",
        )

    def _repair_activity_engagement(self, violations: list) -> None:
        """A higher-order objective practiced only through passive formats
        gets a hands-on activity added."""
        activity_node_id = self.graph.section_id(NodeType.ACTIVITY)
        activity_section = self.graph.get_node(activity_node_id)
        activities = [
            dict(a) if isinstance(a, dict) else a
            for a in (activity_section["data"].get("learning_activities", []) if activity_section else []) or []
        ]
        repaired_ids: list[str] = []
        for violation in violations:
            lo_id = str(violation.metadata.get("lo_id") or "")
            if not lo_id:
                continue
            new_id = f"ACT-P-{lo_id}"
            activities.append({
                "id": new_id,
                "activity_name": f"Hands-on practice for {lo_id}",
                "duration": "45m",
                "description": f"Learners actively practice {lo_id} on a realistic task with feedback.",
                "materials": ["Practice task sheet"],
                "aligned_objectives": [lo_id],
                "repaired": True,
            })
            repaired_ids.append(new_id)

        self.graph.update_node(activity_node_id, {"learning_activities": activities, "repaired": True})
        for activity in activities:
            if isinstance(activity, dict) and activity.get("id"):
                self.graph.add_element_node("activity", str(activity["id"]), dict(activity))
        alignment.match_r4_supports(self.graph)
        self._log_repair(activity_node_id, violation_type="activity_engagement", repaired_fields=["learning_activities"])
        self.trajectory.log_step(
            "ActivityMaterialAgent",
            "repair_activity_engagement",
            "; ".join(v.message for v in violations)[:200],
            f"Added active-practice activities for {', '.join(repaired_ids) or 'existing objectives'}.",
        )
