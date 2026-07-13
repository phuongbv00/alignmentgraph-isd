from __future__ import annotations
from ..graph import NodeType
from ..schema import DesignBrief
import re
from .base import BaseISDAgent, _format_design_brief, parse_json_response

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

_SYSTEM = """\
You are an expert instructional designer working on the Design phase of ADDIE.

Given a training scenario, produce ONLY valid JSON for the design section with this EXACT schema:
{
  "learning_objectives": [
    {"id": "LO-01", "level": "Remember", "statement": "<objective>", "bloom_verb": "<verb>", "measurable": true},
    {"id": "LO-02", "level": "Understand", "statement": "<objective>", "bloom_verb": "<verb>", "measurable": true},
    {"id": "LO-03", "level": "Apply", "statement": "<objective>", "bloom_verb": "<verb>", "measurable": true},
    {"id": "LO-04", "level": "Analyze", "statement": "<objective>", "bloom_verb": "<verb>", "measurable": true},
    {"id": "LO-05", "level": "Evaluate", "statement": "<objective>", "bloom_verb": "<verb>", "measurable": true}
  ],
  "assessment_plan": {
    "diagnostic": ["<diagnostic1>", "<diagnostic2>"],
    "formative": ["<formative1>", "<formative2>"],
    "summative": ["<summative1>", "<summative2>"]
  },
  "content_structure": {
    "modules": ["<module1>", "<module2>", "<module3>"],
    "topics": ["<topic1>", "<topic2>", "<topic3>"],
    "sequencing": "<learning sequence description>"
  },
  "instructional_strategies": {
    "model": "Gagné's 9 Events",
    "sequence": [
      {"event": "Gain attention", "activity": "<activity>", "duration": "<time>", "resources": ["<resource>"]},
      {"event": "Inform learners of objectives", "activity": "<activity>", "duration": "<time>", "resources": ["<resource>"]},
      {"event": "Stimulate recall of prior learning", "activity": "<activity>", "duration": "<time>", "resources": ["<resource>"]},
      {"event": "Present content", "activity": "<activity>", "duration": "<time>", "resources": ["<resource>"]},
      {"event": "Provide learning guidance", "activity": "<activity>", "duration": "<time>", "resources": ["<resource>"]},
      {"event": "Elicit performance", "activity": "<activity>", "duration": "<time>", "resources": ["<resource>"]},
      {"event": "Provide feedback", "activity": "<activity>", "duration": "<time>", "resources": ["<resource>"]},
      {"event": "Assess performance", "activity": "<activity>", "duration": "<time>", "resources": ["<resource>"]},
      {"event": "Enhance retention and transfer", "activity": "<activity>", "duration": "<time>", "resources": ["<resource>"]}
    ],
    "methods": ["<method1>", "<method2>", "<method3>"],
    "rationale": "<strategy selection rationale>"
  },
  "non_instructional_strategies": {
    "motivation_strategies": ["<motivation1>", "<motivation2>"],
    "self_directed_learning": ["<self1>", "<self2>"],
    "support_strategies": ["<support1>", "<support2>"]
  },
  "learning_activities": [
    {"activity_name": "<activity1>", "duration": "<time>", "description": "<desc>", "materials": ["<material>"]},
    {"activity_name": "<activity2>", "duration": "<time>", "description": "<desc>", "materials": ["<material>"]},
    {"activity_name": "<activity3>", "duration": "<time>", "description": "<desc>", "materials": ["<material>"]}
  ],
  "media_selection": [
    {"media_type": "<type>", "purpose": "<purpose>", "rationale": "<rationale>"},
    {"media_type": "<type>", "purpose": "<purpose>", "rationale": "<rationale>"},
    {"media_type": "<type>", "purpose": "<purpose>", "rationale": "<rationale>"}
  ],
  "storyboard": [
    {"frame_number": 1, "screen_title": "<title>", "visual_description": "<visual>", "interaction": "<interaction>", "notes": "<notes>"},
    {"frame_number": 2, "screen_title": "<title>", "visual_description": "<visual>", "interaction": "<interaction>", "notes": "<notes>"},
    {"frame_number": 3, "screen_title": "<title>", "visual_description": "<visual>", "interaction": "<interaction>", "notes": "<notes>"}
  ]
}

Must include ALL 9 Gagné events. Must have at least 5 learning objectives spanning multiple Bloom's levels.
Use only these Bloom verbs in bloom_verb: Recall, Explain, Apply, Analyze, Evaluate, Design.
Output ONLY the JSON object, no markdown, no explanation.\
"""




class ObjectiveDesignAgent(BaseISDAgent):
    # measurability is audit-only (over-strict statement rewrites hurt quality and
    # the vague verb it targets is already fixed by the bloom repair).
    OWNED_VIOLATION_TYPES = frozenset({"bloom", "activity_engagement"})

    def run(self, design_brief: DesignBrief, context_pack: dict) -> None:
        prompt = _format_design_brief(design_brief)
        # Graph-context retrieval (core, not RAG): inject prior G_t nodes into this prompt
        prior_ctx = self._graph_context([NodeType.NEEDS_CONTEXT])
        user_content = prompt
        if prior_ctx:
            user_content = f"=== ANALYSIS RESULTS (from NeedsContextAgent) ===\n{prior_ctx}\n\n=== SCENARIO ===\n{prompt}"
        pack_ctx = self._context_pack_text(context_pack)
        if pack_ctx:
            user_content = f"=== RETRIEVED CONTEXT PACK ===\n{pack_ctx}\n\n{user_content}"
        user_content = self._with_retrieval(design_brief, "objective_design", user_content)
        messages = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_content},
        ]
        response = self._call_llm(messages)
        parsed = parse_json_response(response)
        node_id = self.graph.section_id(NodeType.OBJECTIVE)
        self.graph.add_node(NodeType.OBJECTIVE, node_id, parsed)
        self.trajectory.log_node_edit("add", node_id, NodeType.OBJECTIVE)
        # Element-level nodes: each learning objective is a first-class node.
        for lo in parsed.get("learning_objectives", []):
            if isinstance(lo, dict) and lo.get("id"):
                element_id = self.graph.add_element_node(NodeType.OBJECTIVE, str(lo["id"]), dict(lo))
                self.trajectory.log_node_edit("add", element_id, NodeType.OBJECTIVE)
        self.trajectory.log_step("ObjectiveDesignAgent", "design_objectives", prompt[:200], response[:200] if response else "")

    def repair(self, violations: list) -> list:
        remaining = []
        content_violations = []
        for violation in violations:
            vtype = getattr(violation, "violation_type", "")
            if vtype == "bloom":
                self._repair_bloom_verb(violation)
            elif vtype in ("measurability", "activity_engagement"):
                content_violations.append(violation)
            else:
                remaining.append(violation)
        if content_violations:
            self._repair_design_content(content_violations)
        return remaining

    def _repair_design_content(self, violations: list) -> None:
        """Resolve measurability / activity_engagement findings on the design section.

        One LLM call revises every flagged objective statement and drafts the
        missing practice activities; a deterministic fallback then guarantees
        each finding is resolved even when the model output is unusable, so the
        verify-repair loop always converges.
        """
        node_id = self.graph.section_id(NodeType.OBJECTIVE)
        node = self.graph.get_node(node_id)
        if not node:
            return
        from .pedagogical_verifier import _CONDITION_PATTERN, _DEGREE_PATTERN

        objectives = [dict(lo) if isinstance(lo, dict) else lo for lo in node["data"].get("learning_objectives", []) or []]
        activities = [dict(a) if isinstance(a, dict) else a for a in node["data"].get("learning_activities", []) or []]
        measurability_ids = [
            str(v.metadata.get("lo_id", "") or "")
            for v in violations if v.violation_type == "measurability"
        ]
        engagement_ids = [
            str(v.metadata.get("lo_id", "") or "")
            for v in violations if v.violation_type == "activity_engagement"
        ]

        revised = self._llm_design_revision(violations, objectives, activities)
        revised_los = {
            str(lo["id"]): lo
            for lo in revised.get("learning_objectives", []) or []
            if isinstance(lo, dict) and lo.get("id")
        }
        for lo in objectives:
            if isinstance(lo, dict) and str(lo.get("id")) in revised_los:
                statement = str(revised_los[str(lo["id"])].get("statement") or "").strip()
                if statement:
                    lo["statement"] = statement
        for act in revised.get("learning_activities", []) or []:
            if not isinstance(act, dict) or not act.get("activity_name"):
                continue
            act.setdefault("aligned_objectives", engagement_ids)
            existing = next(
                (a for a in activities if isinstance(a, dict) and a.get("activity_name") == act["activity_name"]),
                None,
            )
            if existing:
                existing.update(act)
            else:
                activities.append(act)

        # Deterministic fallback: every finding must end up resolved.
        for lo_id in measurability_ids:
            lo = next((x for x in objectives if isinstance(x, dict) and str(x.get("id")) == lo_id), None)
            if not lo:
                continue
            statement = str(lo.get("statement", ""))
            if not (_DEGREE_PATTERN.search(statement) or _CONDITION_PATTERN.search(statement)):
                lo["statement"] = (
                    statement.rstrip(". ")
                    + ", achieving at least 80% accuracy against the scoring rubric."
                )
                lo["measurable"] = True
        for lo_id in engagement_ids:
            covered = any(
                isinstance(a, dict)
                and lo_id in (a.get("aligned_objectives") or [])
                and any(
                    marker in f"{a.get('activity_name', '')} {a.get('description', '')}".lower()
                    for marker in ("lab", "practice", "exercise", "project", "hands-on", "workshop", "simulation")
                )
                for a in activities
            )
            if not covered:
                activities.append({
                    "activity_name": f"Guided practice lab for {lo_id}",
                    "duration": "45m",
                    "description": (
                        f"Learners practice the skill behind {lo_id} on a realistic task "
                        "with instructor feedback and a completion checklist."
                    ),
                    "materials": ["Practice task sheet"],
                    "aligned_objectives": [lo_id],
                })

        self.graph.update_node(node_id, {
            "learning_objectives": objectives,
            "learning_activities": activities,
        })
        for violation in violations:
            self.graph.mark_repaired(node_id, violation.message)
        impact = self._invalidate_impacted(
            node_id,
            "Design-content repair revised objective statements and practice activities; downstream alignment must be refreshed.",
            action="repair_cascade",
            changed_fields=["learning_objectives", "learning_activities"],
            violation_type="measurability" if measurability_ids else "activity_engagement",
        )
        self.trajectory.log_node_edit("update", node_id, NodeType.OBJECTIVE)
        self.trajectory.log_step(
            "ObjectiveDesignAgent",
            "repair_design_content",
            "; ".join(v.message for v in violations)[:200],
            (
                f"Revised {len(measurability_ids)} objective statement(s), ensured active practice "
                f"for {len(engagement_ids)} objective(s); invalidated nodes={len(impact['nodes'])} "
                f"edges={len(impact['edges'])}."
            ),
        )

    def _llm_design_revision(self, violations: list, objectives: list, activities: list) -> dict:
        import json

        findings = [
            {
                "type": v.violation_type,
                "lo_id": v.metadata.get("lo_id"),
                "message": v.message,
                "hint": v.repair_hint,
            }
            for v in violations
        ]
        flagged_ids = {str(f["lo_id"]) for f in findings if f["lo_id"]}
        flagged_los = [
            lo for lo in objectives
            if isinstance(lo, dict) and str(lo.get("id")) in flagged_ids
        ]
        system = (
            "You are an expert instructional designer revising a course design to resolve "
            "verifier findings. Return ONLY valid JSON with this schema:\n"
            '{"learning_objectives": [{"id": "<existing id>", "statement": "<revised statement>"}],\n'
            ' "learning_activities": [{"activity_name": "<name>", "duration": "<duration>", '
            '"description": "<description>", "materials": ["<material>"], "aligned_objectives": ["<LO id>"]}]}\n'
            "Rules: keep objective ids, levels, and Bloom verbs unchanged; rewrite only the flagged "
            "statements so each states a performance condition and a measurable criterion; add one "
            "hands-on practice activity per flagged higher-order objective. Include only revised or "
            "new entries."
        )
        user = json.dumps(
            {"findings": findings, "flagged_objectives": flagged_los, "existing_activities": activities},
            ensure_ascii=False,
        )
        response = self._call_llm(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_retries=0,
        )
        return parse_json_response(response, warn=False) or {}

    def _repair_bloom_verb(self, violation) -> None:
        obj = self.graph.get_node(violation.node_id)
        if not obj:
            return

        lo_id = str(violation.metadata.get("lo_id", "") or "")
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
                lo["statement"] = (
                    f"{statement} This is measured by asking learners to "
                    f"{replacement.lower()} the target skill in context."
                )
            repaired = True

        if not repaired:
            return

        self.graph.update_node(violation.node_id, {"learning_objectives": objectives})
        self.graph.mark_repaired(violation.node_id, violation.message)
        impact = self._invalidate_impacted(
            violation.node_id,
            f"Objective repair changed {lo_id or violation.node_id}; downstream alignment must be refreshed.",
            action="repair_cascade",
            changed_fields=["learning_objectives", "bloom_verb"],
            evidence=lo_id,
            violation_type=getattr(violation, "violation_type", "bloom"),
        )
        self.trajectory.log_node_edit("update", violation.node_id, NodeType.OBJECTIVE)
        self.trajectory.log_step(
            "ObjectiveDesignAgent",
            "repair_objective",
            violation.message,
            (
                f"Updated Bloom verb for {lo_id or violation.node_id}; "
                f"invalidated nodes={len(impact['nodes'])} edges={len(impact['edges'])}."
            ),
        )
