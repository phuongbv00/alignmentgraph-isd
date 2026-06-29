from __future__ import annotations
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
    def run(self, design_brief: DesignBrief, context_pack: dict) -> None:
        prompt = _format_design_brief(design_brief)
        # Graph-context retrieval (core, not RAG): inject prior G_t nodes into this prompt
        prior_ctx = self._graph_context(['needs_context'])
        user_content = prompt
        if prior_ctx:
            user_content = f"=== ANALYSIS RESULTS (from NeedsContextAgent) ===\n{prior_ctx}\n\n=== SCENARIO ===\n{prompt}"
        rag_ctx = self._context_pack_text(context_pack)
        if rag_ctx:
            user_content = f"=== RETRIEVED CONTEXT PACK ===\n{rag_ctx}\n\n{user_content}"
        messages = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_content},
        ]
        response = self._call_llm(messages)
        parsed = parse_json_response(response)
        node_id = "objective_0"
        self.graph.add_node("objective", node_id, parsed)
        self.trajectory.log_node_edit("add", node_id, "objective")
        # Element-level nodes: each learning objective is a first-class node.
        for lo in parsed.get("learning_objectives", []):
            if isinstance(lo, dict) and lo.get("id"):
                element_id = self.graph.add_element_node("objective", str(lo["id"]), dict(lo))
                self.trajectory.log_node_edit("add", element_id, "objective")
        self.trajectory.log_step("ObjectiveDesignAgent", "design_objectives", prompt[:200], response[:200] if response else "")

    def repair(self, violations: list) -> list:
        remaining = []
        for violation in violations:
            if getattr(violation, "violation_type", "") != "bloom":
                remaining.append(violation)
                continue
            self._repair_bloom_verb(violation)
        return remaining

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
        self.trajectory.log_node_edit("update", violation.node_id, "objective")
        self.trajectory.log_step(
            "ObjectiveDesignAgent",
            "repair_objective",
            violation.message,
            (
                f"Updated Bloom verb for {lo_id or violation.node_id}; "
                f"invalidated nodes={len(impact['nodes'])} edges={len(impact['edges'])}."
            ),
        )
