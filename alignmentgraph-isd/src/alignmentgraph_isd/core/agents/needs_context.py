from __future__ import annotations
from ..graph import NodeType
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
    def run(self, design_brief: DesignBrief) -> None:
        prompt = _format_design_brief(design_brief)
        user_content = self._with_retrieval(design_brief, "needs_context", prompt)
        messages = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_content},
        ]
        response = self._call_llm(messages)
        parsed = parse_json_response(response)
        node_id = self.graph.section_id(NodeType.NEEDS_CONTEXT)
        self.graph.add_node(NodeType.NEEDS_CONTEXT, node_id, parsed)
        self.trajectory.log_node_edit("add", node_id, NodeType.NEEDS_CONTEXT)
        # gap/task/learner element nodes are the provenance sources for the
        # alignment graph (R1/R2/R10/R11/R13).
        self._decompose(parsed)
        self.trajectory.log_step("NeedsContextAgent", "needs_analysis", prompt[:200], response[:200] if response else "")

    def _decompose(self, parsed: dict) -> None:
        """First-class nodes for the analysis items later specialists traverse
        from (R1/R2/R10/R13's sources): gaps, task topics, and the learner
        profile. Output schema (gap_analysis/main_topics stay string lists) is
        unchanged — ids are assigned positionally, not by the model."""
        needs = parsed.get("needs_analysis", {}) or {}
        gap_ids = self._decompose_auto_id("gap", needs.get("gap_analysis"), id_prefix="GAP")
        for gid in gap_ids:
            self.trajectory.log_node_edit("add", gid, "gap")

        task = parsed.get("task_analysis", {}) or {}
        topic_ids = self._decompose_auto_id("task", task.get("main_topics"), id_prefix="TOPIC", text_key="topic")
        for tid in topic_ids:
            self.trajectory.log_node_edit("add", tid, "task")

        learner = parsed.get("learner_analysis", {}) or {}
        if learner:
            learner_id = self.graph.section_id("learner")
            self.graph.add_node("learner", learner_id, learner)
            self.trajectory.log_node_edit("add", learner_id, "learner")

