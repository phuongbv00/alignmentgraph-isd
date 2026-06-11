from __future__ import annotations
from .base import BaseISDAgent, _format_scenario, parse_json_response

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
    def run(self, scenario: dict, context_pack: dict) -> None:
        prompt = _format_scenario(scenario)
        # Graph-subgraph RAG: inject prior G_t nodes into this agent's prompt
        prior_ctx = self._graph_context(['needs_context', 'objective'])
        user_content = prompt
        if prior_ctx:
            user_content = f"=== ANALYSIS + DESIGN RESULTS (from prior agents) ===\n{prior_ctx}\n\n=== SCENARIO ===\n{prompt}"
        messages = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_content},
        ]
        response = self._call_llm(messages)
        parsed = parse_json_response(response)
        for node_type, node_id in [("activity", "activity_0"), ("material", "material_0")]:
            self.graph.add_node(node_type, node_id, parsed)
            self.trajectory.log_node_edit("add", node_id, node_type)
        self.trajectory.log_step("ActivityMaterialAgent", "develop_activities", prompt[:200], response[:200] if response else "")
