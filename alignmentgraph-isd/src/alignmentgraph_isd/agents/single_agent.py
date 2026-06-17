from __future__ import annotations
from ..schema import TaskRequest
from .base import BaseISDAgent, _format_task, parse_json_response

_SYSTEM = """\
You are an expert instructional designer. Given a training scenario, produce a COMPLETE, DETAILED ADDIE instructional design.

Return ONLY valid JSON with EXACTLY this nested schema:
{
  "analysis": {
    "needs_analysis": {
      "problem_definition": "<2-3 sentences on performance gap>",
      "gap_analysis": ["<gap1>", "<gap2>", "<gap3>"],
      "performance_analysis": "<2-3 sentences on instructional solution>",
      "priority_matrix": {"high": ["<item>"], "medium": ["<item>"], "low": ["<item>"]}
    },
    "learner_analysis": {
      "target_audience": "<audience description>",
      "characteristics": ["<char1>", "<char2>", "<char3>", "<char4>", "<char5>"],
      "prior_knowledge": "<prior knowledge>",
      "learning_preferences": ["<pref1>", "<pref2>", "<pref3>"],
      "motivation": "<motivation>",
      "challenges": ["<challenge1>", "<challenge2>", "<challenge3>"]
    },
    "context_analysis": {
      "environment": "<learning environment>",
      "duration": "<total time>",
      "constraints": ["<constraint1>", "<constraint2>", "<constraint3>"],
      "resources": ["<resource1>", "<resource2>"],
      "technical_requirements": ["<tech1>", "<tech2>"]
    },
    "task_analysis": {
      "main_topics": ["<topic1>", "<topic2>", "<topic3>"],
      "subtopics": ["<sub1>", "<sub2>", "<sub3>", "<sub4>"],
      "prerequisites": ["<prereq1>", "<prereq2>"],
      "review_summary": "<synthesis in 3-4 sentences>"
    }
  },
  "design": {
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
      "sequencing": "<sequence rationale>"
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
      "rationale": "<strategy rationale>"
    },
    "non_instructional_strategies": {
      "motivation_strategies": ["<motivation1>", "<motivation2>"],
      "self_directed_learning": ["<self1>", "<self2>"],
      "support_strategies": ["<support1>", "<support2>"]
    },
    "learning_activities": [
      {"activity_name": "<name1>", "duration": "<time>", "description": "<desc>", "materials": ["<material>"]},
      {"activity_name": "<name2>", "duration": "<time>", "description": "<desc>", "materials": ["<material>"]},
      {"activity_name": "<name3>", "duration": "<time>", "description": "<desc>", "materials": ["<material>"]}
    ],
    "media_selection": [
      {"media_type": "<type>", "purpose": "<purpose>", "rationale": "<rationale>"},
      {"media_type": "<type>", "purpose": "<purpose>", "rationale": "<rationale>"}
    ],
    "storyboard": [
      {"frame_number": 1, "screen_title": "<title>", "visual_description": "<visual>", "interaction": "<interaction>", "notes": "<notes>"},
      {"frame_number": 2, "screen_title": "<title>", "visual_description": "<visual>", "interaction": "<interaction>", "notes": "<notes>"},
      {"frame_number": 3, "screen_title": "<title>", "visual_description": "<visual>", "interaction": "<interaction>", "notes": "<notes>"}
    ]
  },
  "development": {
    "learner_materials": [
      {"title": "<title>", "type": "<type>", "content": "<description>", "format": "<format>"},
      {"title": "<title>", "type": "<type>", "content": "<description>", "format": "<format>"},
      {"title": "<title>", "type": "<type>", "content": "<description>", "format": "<format>"}
    ],
    "instructor_guide": {
      "overview": "<guide overview>",
      "session_guides": [
        {"session": 1, "objectives": ["<obj>"], "activities": ["<activity>"], "notes": "<notes>"},
        {"session": 2, "objectives": ["<obj>"], "activities": ["<activity>"], "notes": "<notes>"},
        {"session": 3, "objectives": ["<obj>"], "activities": ["<activity>"], "notes": "<notes>"}
      ],
      "facilitation_tips": ["<tip1>", "<tip2>", "<tip3>"],
      "troubleshooting": ["<issue1>", "<issue2>"]
    },
    "operator_manual": {
      "system_setup": "<setup guide>",
      "operation_procedures": ["<proc1>", "<proc2>", "<proc3>"],
      "support_procedures": ["<support1>", "<support2>"],
      "escalation_process": "<escalation process>"
    },
    "assessment_tools": [
      {"item_id": "AT-01", "type": "multiple_choice", "question": "<question>", "aligned_objective": "LO-01", "scoring_criteria": "<criteria>"},
      {"item_id": "AT-02", "type": "multiple_choice", "question": "<question>", "aligned_objective": "LO-02", "scoring_criteria": "<criteria>"},
      {"item_id": "AT-03", "type": "multiple_choice", "question": "<question>", "aligned_objective": "LO-03", "scoring_criteria": "<criteria>"},
      {"item_id": "AT-04", "type": "short_answer", "question": "<question>", "aligned_objective": "LO-03", "scoring_criteria": "<criteria>"},
      {"item_id": "AT-05", "type": "short_answer", "question": "<question>", "aligned_objective": "LO-04", "scoring_criteria": "<criteria>"},
      {"item_id": "AT-06", "type": "performance_task", "question": "<question>", "aligned_objective": "LO-04", "scoring_criteria": "<criteria>"},
      {"item_id": "AT-07", "type": "performance_task", "question": "<question>", "aligned_objective": "LO-05", "scoring_criteria": "<criteria>"},
      {"item_id": "AT-08", "type": "multiple_choice", "question": "<question>", "aligned_objective": "LO-01", "scoring_criteria": "<criteria>"},
      {"item_id": "AT-09", "type": "short_answer", "question": "<question>", "aligned_objective": "LO-02", "scoring_criteria": "<criteria>"},
      {"item_id": "AT-10", "type": "performance_task", "question": "<question>", "aligned_objective": "LO-05", "scoring_criteria": "<criteria>"}
    ],
    "expert_review": {
      "reviewers": ["<SME1>", "<designer1>"],
      "review_criteria": ["<criterion1>", "<criterion2>", "<criterion3>", "<criterion4>", "<criterion5>"],
      "feedback_summary": "<feedback summary>",
      "revisions_made": ["<revision1>", "<revision2>"]
    }
  },
  "implementation": {
    "instructor_orientation": {
      "orientation_objectives": ["<obj1>", "<obj2>", "<obj3>"],
      "schedule": "<schedule>",
      "materials": ["<material1>", "<material2>"],
      "competency_checklist": ["<comp1>", "<comp2>", "<comp3>"]
    },
    "system_check": {
      "checklist": ["<check1>", "<check2>", "<check3>", "<check4>", "<check5>"],
      "technical_validation": "<validation>",
      "contingency_plans": ["<plan1>", "<plan2>"]
    },
    "prototype_execution": {
      "pilot_scope": "<scope>",
      "participants": "<participants>",
      "execution_log": ["<log1>", "<log2>", "<log3>"],
      "issues_encountered": ["<issue1>", "<issue2>"]
    },
    "monitoring": {
      "monitoring_criteria": ["<criterion1>", "<criterion2>", "<criterion3>"],
      "support_channels": ["<channel1>", "<channel2>"],
      "issue_resolution_log": ["<resolution1>", "<resolution2>"],
      "real_time_adjustments": ["<adjustment1>", "<adjustment2>"]
    }
  },
  "evaluation": {
    "formative": {
      "data_collection": {
        "methods": ["<method1>", "<method2>", "<method3>"],
        "learner_feedback": ["<feedback1>", "<feedback2>", "<feedback3>"],
        "performance_data": {"metric1": "<description>", "metric2": "<description>"},
        "observations": ["<observation1>", "<observation2>"]
      },
      "improvements": [
        {"issue_identified": "<issue>", "improvement_action": "<action>", "priority": "high"},
        {"issue_identified": "<issue>", "improvement_action": "<action>", "priority": "medium"},
        {"issue_identified": "<issue>", "improvement_action": "<action>", "priority": "low"}
      ]
    },
    "summative": {
      "assessment_tools": [
        {"item_id": "SA-01", "type": "comprehensive", "question": "<question>", "scoring_rubric": "<rubric>"},
        {"item_id": "SA-02", "type": "comprehensive", "question": "<question>", "scoring_rubric": "<rubric>"},
        {"item_id": "SA-03", "type": "comprehensive", "question": "<question>", "scoring_rubric": "<rubric>"},
        {"item_id": "SA-04", "type": "performance", "question": "<question>", "scoring_rubric": "<rubric>"},
        {"item_id": "SA-05", "type": "performance", "question": "<question>", "scoring_rubric": "<rubric>"}
      ],
      "effectiveness_analysis": {
        "learning_outcomes": {"achievement_rate": "85%", "details": "<outcome analysis>"},
        "goal_achievement_rate": "<rate>",
        "statistical_analysis": "<analysis>",
        "recommendations": ["<rec1>", "<rec2>", "<rec3>"]
      },
      "adoption_decision": {
        "decision": "adopt",
        "rationale": "<rationale>",
        "conditions": ["<condition1>", "<condition2>"],
        "stakeholder_approval": "<approval status>"
      }
    },
    "improvement_plan": {
      "feedback_summary": "<summary>",
      "improvement_areas": ["<area1>", "<area2>", "<area3>"],
      "action_items": ["<action1>", "<action2>", "<action3>"],
      "feedback_loop": "<feedback loop>",
      "next_iteration_goals": ["<goal1>", "<goal2>"]
    }
  }
}

CRITICAL:
- Replace ALL placeholder values (<...>) with specific, detailed content tailored to the scenario
- instructional_strategies.sequence MUST contain ALL 9 Gagné events in order
- learning_objectives MUST have at least 5 items spanning multiple Bloom's levels
- assessment_tools MUST have at least 10 items
- Return ONLY the JSON, no markdown fences, no explanation\
"""

_SECTION_TO_NODE = {
    "analysis": "needs_context",
    "design": "objective",
    "development": "activity",
    "implementation": "constraint",
    "evaluation": "evaluation",
}


class SingleAgent(BaseISDAgent):
    def run(self, task: TaskRequest, context_pack: dict) -> None:
        prompt = _format_task(task)
        user_content = prompt
        rag_ctx = self._context_pack_text(context_pack)
        if rag_ctx:
            user_content = f"=== RETRIEVED CONTEXT PACK ===\n{rag_ctx}\n\n=== SCENARIO ===\n{prompt}"
        messages = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_content},
        ]
        raw = self._call_llm(messages)
        parsed = parse_json_response(raw)
        for section, node_type in _SECTION_TO_NODE.items():
            node_id = f"{node_type}_0"
            self.graph.add_node(node_type, node_id, parsed.get(section, {}))
            self.trajectory.log_node_edit("add", node_id, node_type)
        development = parsed.get("development", {})
        if development.get("assessment_tools") or development.get("expert_review"):
            self.graph.add_node("assessment", "assessment_0", {
                "assessment_tools": development.get("assessment_tools", []),
                "expert_review": development.get("expert_review", {}),
            })
            self.trajectory.log_node_edit("add", "assessment_0", "assessment")
        self._add_alignment_edges(parsed)
        self.trajectory.log_step("SingleAgent", "generate_addie", prompt[:200], raw[:200] if raw else "(empty)")

    def _add_alignment_edges(self, parsed: dict) -> None:
        objective_node = self.graph.get_node("objective_0")
        if not objective_node:
            return
        objective_ids = [
            lo.get("id")
            for lo in parsed.get("design", {}).get("learning_objectives", [])
            if isinstance(lo, dict) and lo.get("id")
        ]
        assessment_source = "assessment_0" if self.graph.get_node("assessment_0") else "activity_0"
        for lo_id in objective_ids:
            self.graph.add_edge(
                "measures",
                assessment_source,
                "objective_0",
                evidence=lo_id,
                rationale=f"Single-agent assessment output measures {lo_id}.",
                verified=True,
            )
            self.graph.add_edge(
                "supports",
                "activity_0",
                "objective_0",
                evidence=lo_id,
                rationale=f"Single-agent learning activities support {lo_id}.",
                verified=True,
            )
            self.graph.add_edge(
                "evaluates",
                "evaluation_0",
                "objective_0",
                evidence=lo_id,
                rationale=f"Single-agent evaluation plan evaluates {lo_id}.",
                verified=True,
            )
            self.trajectory.log_edge_edit("add", assessment_source, "objective_0", "measures", lo_id)
            self.trajectory.log_edge_edit("add", "activity_0", "objective_0", "supports", lo_id)
            self.trajectory.log_edge_edit("add", "evaluation_0", "objective_0", "evaluates", lo_id)
