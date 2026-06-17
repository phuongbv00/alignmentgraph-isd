from __future__ import annotations
from ..schema import DesignBrief
from .base import BaseISDAgent, _format_design_brief, parse_json_response

_SYSTEM = """\
You are an expert instructional designer performing the Analysis phase of ADDIE.

Given a training scenario, produce ONLY valid JSON for the analysis section with this EXACT schema:
{
  "needs_analysis": {
    "problem_definition": "<2-3 sentences describing the gap between current and desired state>",
    "gap_analysis": ["<gap1>", "<gap2>", "<gap3>"],
    "performance_analysis": "<2-3 sentences on whether an instructional solution is needed>",
    "priority_matrix": {
      "high": ["<urgent+important items>"],
      "medium": ["<medium priority items>"],
      "low": ["<low priority items>"]
    }
  },
  "learner_analysis": {
    "target_audience": "<clearly define the audience>",
    "characteristics": ["<char1>", "<char2>", "<char3>", "<char4>", "<char5>"],
    "prior_knowledge": "<prior knowledge level in 2-3 sentences>",
    "learning_preferences": ["<pref1>", "<pref2>", "<pref3>", "<pref4>"],
    "motivation": "<motivation level and reasons in 2-3 sentences>",
    "challenges": ["<challenge1>", "<challenge2>", "<challenge3>"]
  },
  "context_analysis": {
    "environment": "<learning environment>",
    "duration": "<total learning time>",
    "constraints": ["<constraint1>", "<constraint2>", "<constraint3>"],
    "resources": ["<resource1>", "<resource2>", "<resource3>"],
    "technical_requirements": ["<tech_req1>", "<tech_req2>"]
  },
  "task_analysis": {
    "main_topics": ["<topic1>", "<topic2>", "<topic3>"],
    "subtopics": ["<sub1-1>", "<sub1-2>", "<sub2-1>", "<sub2-2>", "<sub3-1>", "<sub3-2>"],
    "prerequisites": ["<prereq1>", "<prereq2>"],
    "review_summary": "<synthesis of analysis results in 3-4 sentences>"
  }
}

Output ONLY the JSON object, no markdown, no explanation.\
"""


class NeedsContextAgent(BaseISDAgent):
    def run(self, design_brief: DesignBrief, context_pack: dict) -> None:
        prompt = _format_design_brief(design_brief)
        user_content = prompt
        rag_ctx = self._context_pack_text(context_pack)
        if rag_ctx:
            user_content = f"=== RETRIEVED CONTEXT PACK ===\n{rag_ctx}\n\n=== SCENARIO ===\n{prompt}"
        messages = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_content},
        ]
        response = self._call_llm(messages)
        parsed = parse_json_response(response)
        node_id = "needs_context_0"
        self.graph.add_node("needs_context", node_id, parsed)
        self.trajectory.log_node_edit("add", node_id, "needs_context")
        self.trajectory.log_step("NeedsContextAgent", "needs_analysis", prompt[:200], response[:200] if response else "")

