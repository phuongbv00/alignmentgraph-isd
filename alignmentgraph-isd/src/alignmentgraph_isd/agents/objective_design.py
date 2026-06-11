from __future__ import annotations
from .base import BaseISDAgent, _format_scenario, parse_json_response

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
Output ONLY the JSON object, no markdown, no explanation.\
"""




class ObjectiveDesignAgent(BaseISDAgent):
    def run(self, scenario: dict, context_pack: dict) -> None:
        prompt = _format_scenario(scenario)
        # Graph-subgraph RAG: inject prior G_t nodes into this agent's prompt
        prior_ctx = self._graph_context(['needs_context'])
        user_content = prompt
        if prior_ctx:
            user_content = f"=== ANALYSIS RESULTS (from NeedsContextAgent) ===\n{prior_ctx}\n\n=== SCENARIO ===\n{prompt}"
        messages = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_content},
        ]
        response = self._call_llm(messages)
        parsed = parse_json_response(response)
        node_id = "objective_0"
        self.graph.add_node("objective", node_id, parsed)
        self.trajectory.log_node_edit("add", node_id, "objective")
        self.trajectory.log_step("ObjectiveDesignAgent", "design_objectives", prompt[:200], response[:200] if response else "")
