"""Shared test fixtures: a network-free fake LLM and ready-made run configs.

The fake model inspects the system prompt of each specialist agent and returns
a canned, schema-valid JSON payload. This lets the whole harness run end-to-end
with no network or API key, so smoke tests stay deterministic and fast.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from alignmentgraph_isd import DesignBrief, HarnessRunConfig

FIXTURES = Path(__file__).parent / "fixtures"


# ── Canned, schema-valid agent payloads ──────────────────────────────────────

def _objectives() -> list[dict]:
    return [
        {"id": "LO-01", "level": "Remember", "statement": "List the four pillars of OOP.", "bloom_verb": "list", "measurable": True},
        {"id": "LO-02", "level": "Understand", "statement": "Explain encapsulation with an example.", "bloom_verb": "explain", "measurable": True},
        {"id": "LO-03", "level": "Apply", "statement": "Apply inheritance to a given domain model with at least 80% of unit tests passing.", "bloom_verb": "apply", "measurable": True},
        {"id": "LO-04", "level": "Analyze", "statement": "Analyze a provided class design and identify at least three coupling issues.", "bloom_verb": "analyze", "measurable": True},
        {"id": "LO-05", "level": "Evaluate", "statement": "Evaluate composition versus inheritance for a given scenario, justifying the choice against two criteria.", "bloom_verb": "evaluate", "measurable": True},
    ]


def _assessment_tools() -> list[dict]:
    tools = []
    los = ["LO-01", "LO-02", "LO-03", "LO-04", "LO-05"]
    types = ["multiple_choice", "short_answer", "performance_task"]
    categories = ["diagnostic", "formative", "summative"]
    for i in range(10):
        lo = los[i % 5]
        tools.append({
            "item_id": f"AT-{i + 1:02d}",
            "type": types[i % 3],
            "question": f"Demonstrate mastery of {lo} in a realistic scenario.",
            "aligned_objective": lo,
            "plan_category": categories[i % 3],
            "scoring_criteria": "Rubric scores correctness, design quality, and explanation against observable criteria (0-4 each).",
            "difficulty": ["easy", "medium", "hard"][i % 3],
        })
    return tools


_ANALYSIS = {
    "needs_analysis": {
        "problem_definition": "Fresher developers cannot apply OOP concepts in real code.",
        "gap_analysis": ["No OOP modeling skill", "Weak abstraction habits", "No code review exposure"],
        "performance_analysis": "An instructional solution combining concepts and hands-on labs is appropriate.",
        "priority_matrix": {"high": ["OOP modeling"], "medium": ["Refactoring"], "low": ["Build tooling"]},
    },
    "learner_analysis": {
        "target_audience": "Junior backend engineers",
        "characteristics": ["Recent graduates", "Java syntax familiarity", "Limited design experience", "Motivated", "Team-based"],
        "prior_knowledge": "Basic Java syntax and data structures.",
        "learning_preferences": ["Hands-on", "Pair work", "Examples", "Feedback"],
        "motivation": "High; tied to job performance.",
        "challenges": ["Abstraction", "Design trade-offs", "Time pressure"],
    },
    "context_analysis": {
        "environment": "Instructor-led classroom with lab machines",
        "duration": "2 days",
        "constraints": ["Fixed schedule", "Shared lab", "Mixed levels"],
        "resources": ["IDE", "Git repository", "Lab machines"],
        "technical_requirements": ["JDK 17", "IDE"],
    },
    "task_analysis": {
        "main_topics": ["Encapsulation", "Inheritance", "Polymorphism"],
        "subtopics": ["Classes", "Interfaces", "Abstract classes", "Overriding", "Composition", "SOLID"],
        "prerequisites": ["Java syntax", "Basic data structures"],
        "review_summary": "Learners progress from concepts to applied class design with feedback loops.",
    },
}

_DESIGN = {
    "learning_objectives": _objectives(),
    "assessment_plan": {"diagnostic": ["Pre-quiz"], "formative": ["Lab checks"], "summative": ["Capstone"]},
    "content_structure": {"modules": ["Concepts", "Inheritance", "Design"], "topics": ["OOP", "SOLID"], "sequencing": "Concepts first, then applied design."},
    "instructional_strategies": {
        "model": "Gagné's 9 Events",
        "sequence": [{"event": e, "activity": "Guided lab", "duration": "30m", "resources": ["IDE"]} for e in [
            "Gain attention", "Inform learners of objectives", "Stimulate recall of prior learning",
            "Present content", "Provide learning guidance", "Elicit performance",
            "Provide feedback", "Assess performance", "Enhance retention and transfer"]],
        "methods": ["Live coding", "Pair programming", "Code review"],
        "rationale": "Active, scaffolded practice aligns with applied objectives.",
    },
    "non_instructional_strategies": {"motivation_strategies": ["Real tasks"], "self_directed_learning": ["Reading"], "support_strategies": ["Mentor"]},
    "learning_activities": [
        {"id": "ACT-01", "activity_name": "Encapsulation lab", "duration": "60m", "description": "Build a class with invariants.", "materials": ["Starter repo"], "aligned_objectives": ["LO-01", "LO-02"], "linked_module": "MOD-01"},
        {"id": "ACT-02", "activity_name": "Inheritance lab", "duration": "60m", "description": "Model a hierarchy.", "materials": ["Starter repo"], "aligned_objectives": ["LO-03"], "linked_module": "MOD-02"},
        {"id": "ACT-03", "activity_name": "Design review", "duration": "60m", "description": "Critique a design.", "materials": ["Checklist"], "aligned_objectives": ["LO-04", "LO-05"], "linked_module": "MOD-03"},
    ],
    "media_selection": [{"media_type": "slides", "purpose": "Concepts", "rationale": "Clarity"}, {"media_type": "repo", "purpose": "Practice", "rationale": "Transfer"}],
    "storyboard": [
        {"frame_number": 1, "screen_title": "Intro", "visual_description": "Agenda", "interaction": "Discuss", "notes": ""},
        {"frame_number": 2, "screen_title": "Lab", "visual_description": "Editor", "interaction": "Code", "notes": ""},
        {"frame_number": 3, "screen_title": "Review", "visual_description": "Diff", "interaction": "Critique", "notes": ""},
    ],
}

_DEVELOPMENT = {
    "learner_materials": [
        {"id": "MAT-01", "title": "OOP concepts handout", "type": "reading", "content": "Covers the four pillars with examples.", "format": "pdf", "linked_module": "MOD-01"},
        {"id": "MAT-02", "title": "Starter repository", "type": "code", "content": "Lab scaffolding with TODOs and tests.", "format": "git", "linked_module": "MOD-02"},
        {"id": "MAT-03", "title": "Design checklist", "type": "job_aid", "content": "SOLID review checklist with concrete prompts.", "format": "pdf", "linked_module": "MOD-03"},
    ],
    "instructor_guide": {
        "overview": "Three-session flow from concepts to applied design.",
        "session_guides": [
            {"session": 1, "objectives": ["LO-01", "LO-02"], "activities": ["Encapsulation lab"], "notes": "Pair learners by level."},
            {"session": 2, "objectives": ["LO-03"], "activities": ["Inheritance lab"], "notes": "Watch for deep hierarchies."},
            {"session": 3, "objectives": ["LO-04", "LO-05"], "activities": ["Design review"], "notes": "Time-box critiques to 10 minutes."},
        ],
        "facilitation_tips": ["Circulate during labs", "Surface real defects", "Use think-aloud"],
        "troubleshooting": ["IDE setup failures: use the cloud lab", "Slow learners: provide a checkpoint commit"],
    },
    "operator_manual": {
        "system_setup": "Provision lab machines with JDK 17 and clone the starter repo.",
        "operation_procedures": ["Verify access", "Distribute repo", "Open dashboards"],
        "support_procedures": ["Escalate IDE failures", "Hand out backup laptops"],
        "escalation_process": "Notify lab support within 5 minutes of a blocking issue.",
    },
    "assessment_tools": _assessment_tools(),
    "expert_review": {
        "reviewers": ["Senior engineer (SME)", "Instructional designer"],
        "review_criteria": ["Alignment", "Difficulty spread", "Clarity", "Feasibility", "Bias"],
        "feedback_summary": "Items align to objectives; difficulty spread is adequate.",
        "revisions_made": ["Clarified AT-06 wording", "Added rubric anchors"],
    },
}

_IMPLEMENTATION = {
    "instructor_orientation": {
        "orientation_objectives": [
            "Instructors can prepare the lab environment and assign learner roles.",
            "Instructors can facilitate labs and apply the scoring rubric consistently.",
            "Support staff can resolve access issues and escalate incidents.",
        ],
        "schedule": "90-minute facilitator orientation plus a 30-minute delivery rehearsal.",
        "materials": ["Facilitator runbook", "Rubric pack", "Troubleshooting checklist"],
        "competency_checklist": ["Launch and reset the lab", "Score a sample with the rubric", "Resolve access issues"],
    },
    "system_check": {
        "checklist": [
            "Verify lab machines, IDE, and Git access before each session.",
            "Confirm learner grouping and submission channels.",
            "Validate accessibility alternatives and fallback materials.",
        ],
        "technical_validation": "Platform, access, network, and fallback checks completed before launch.",
        "contingency_plans": ["Switch to cloud IDE on failure", "Use offline handouts if network drops"],
    },
    "prototype_execution": {
        "pilot_scope": "One cohort of 16 learners across two days.",
        "participants": "16 fresher developers",
        "execution_log": ["Day 1 labs ran on time", "Day 2 design review extended 15 minutes", "No blocking incidents"],
        "issues_encountered": ["Two IDE setup failures", "One slow learner needed a checkpoint"],
    },
    "monitoring": {
        "monitoring_criteria": ["Lab completion rate", "Rubric score distribution", "Help-request volume"],
        "support_channels": ["Lab chat", "Floating mentor"],
        "issue_resolution_log": ["IDE failures resolved via cloud lab", "Checkpoint commit shared"],
        "real_time_adjustments": ["Extended design review", "Re-paired struggling learners"],
    },
}

_EVALUATION = {
    "formative": {
        "data_collection": {
            "methods": ["Lab observation", "Rubric scoring", "Exit tickets"],
            "learner_feedback": ["Labs were useful", "More time for design review", "Clear rubric"],
            "performance_data": {"lab_completion": "92% completed core labs", "rubric_mean": "3.1 / 4"},
            "observations": ["Strong on encapsulation", "Weaker on design trade-offs"],
        },
        "improvements": [
            {"issue_identified": "Design review rushed", "improvement_action": "Add 15 minutes", "priority": "high"},
            {"issue_identified": "Setup friction", "improvement_action": "Pre-provision cloud labs", "priority": "medium"},
            {"issue_identified": "Uneven pacing", "improvement_action": "Add checkpoint commits", "priority": "low"},
        ],
    },
    "summative": {
        "assessment_tools": [
            {"item_id": "SA-01", "type": "comprehensive", "question": "Design a class hierarchy for LO-05.", "scoring_rubric": "Rubric scores cohesion, coupling, and clarity.", "aligned_objective": "LO-05"},
            {"item_id": "SA-02", "type": "performance", "question": "Refactor for LO-04.", "scoring_rubric": "Rubric scores coupling reduction.", "aligned_objective": "LO-04"},
            {"item_id": "SA-03", "type": "comprehensive", "question": "Apply inheritance for LO-03.", "scoring_rubric": "Rubric scores correctness.", "aligned_objective": "LO-03"},
            {"item_id": "SA-04", "type": "comprehensive", "question": "Explain encapsulation for LO-02.", "scoring_rubric": "Rubric scores accuracy.", "aligned_objective": "LO-02"},
            {"item_id": "SA-05", "type": "comprehensive", "question": "List the pillars for LO-01.", "scoring_rubric": "Rubric scores completeness.", "aligned_objective": "LO-01"},
        ],
        "effectiveness_analysis": {
            "learning_outcomes": {"achievement_rate": "85%", "details": "Most learners met applied objectives."},
            "goal_achievement_rate": "85%",
            "statistical_analysis": "Pre/post gain of 1.4 rubric points on average.",
            "recommendations": ["Extend design review", "Add more worked examples", "Pre-provision labs"],
        },
        "adoption_decision": {
            "decision": "adopt",
            "rationale": "Outcomes meet the threshold with minor revisions.",
            "conditions": ["Apply formative improvements", "Re-pilot the revised design review"],
            "stakeholder_approval": "Approved by the engineering lead",
        },
    },
    "improvement_plan": {
        "feedback_summary": "Positive overall; design review needs more time.",
        "improvement_areas": ["Pacing", "Setup", "Design depth"],
        "action_items": ["Extend design review", "Pre-provision cloud labs", "Add worked examples"],
        "feedback_loop": "Collect exit tickets and rubric data each cohort and revise quarterly.",
        "next_iteration_goals": ["Raise rubric mean to 3.4", "Reduce setup failures to zero"],
    },
}


def _payload_for_system(system_prompt: str) -> dict:
    s = system_prompt
    if "Analysis phase of ADDIE" in s:
        return _ANALYSIS
    if "Design phase of ADDIE" in s:
        return _DESIGN
    if "assessment instruments" in s:
        return {"assessment_tools": _DEVELOPMENT["assessment_tools"], "expert_review": _DEVELOPMENT["expert_review"]}
    if "developing learning activities and materials" in s:
        return {
            "learning_activities": _DESIGN["learning_activities"],
            "learner_materials": _DEVELOPMENT["learner_materials"],
            "instructor_guide": _DEVELOPMENT["instructor_guide"],
            "operator_manual": _DEVELOPMENT["operator_manual"],
        }
    if "Implementation phase of ADDIE" in s:
        return _IMPLEMENTATION
    if "SUMMATIVE evaluation" in s:
        return {"summative": _EVALUATION["summative"]}
    if "FORMATIVE evaluation" in s:
        return {"formative": _EVALUATION["formative"], "improvement_plan": _EVALUATION["improvement_plan"]}
    return {}


class _Result:
    def __init__(self, content: str) -> None:
        self.content = content
        self.usage_metadata = None


class FakeChatModel:
    """Network-free chat model that returns canned, schema-valid JSON."""

    def bind(self, **_kwargs) -> "FakeChatModel":
        return self

    def invoke(self, messages):
        system = ""
        for message in messages:
            role = message.get("role") if isinstance(message, dict) else getattr(message, "type", "")
            if role in ("system",):
                system = message.get("content", "") if isinstance(message, dict) else ""
                break
        payload = _payload_for_system(system)
        return _Result(json.dumps(payload, ensure_ascii=False))


@pytest.fixture
def fake_llm_factory():
    return lambda: FakeChatModel()


@pytest.fixture
def fake_config(fake_llm_factory):
    config = HarnessRunConfig()
    config.llm_factory = fake_llm_factory
    return config


def load_brief(name: str) -> DesignBrief:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return DesignBrief.model_validate(payload)
