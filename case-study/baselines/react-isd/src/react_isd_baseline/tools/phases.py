"""ADDIE 5-phase tools (English translation of the benchmark's react-isd prompts).

Each function performs one ADDIE phase with a single LLM call and returns the
corresponding section of the shared output schema. The prompts preserve the
structure, sub-item requirements and JSON output format of the Korean originals
in isd-agent-benchmark/agents/react-isd/src/react_isd/tools/phases.py; only the
language changed (documented as a threat to validity in the thesis/paper).

Two entry points per experiment condition:
- ``run_<phase>(llm, ...)``      — full generation from the scenario.
- ``refine_phase(llm, ...)``     — revision given the phase's previous output and
                                   a user edit request, with an "unchanged"
                                   short-circuit so untouched phases cost no
                                   completion tokens and pass through verbatim.

Every function returns ``(section_dict, fallback_used)``.
"""
from __future__ import annotations

import json


def parse_json_response(content: str) -> dict:
    if "```json" in content:
        json_str = content.split("```json")[1].split("```")[0]
    elif "```" in content:
        json_str = content.split("```")[1].split("```")[0]
    else:
        json_str = content
    return json.loads(json_str.strip())


# ============================================================
# 1. Analysis phase (sub-items 1-10)
# ============================================================

ANALYSIS_PROMPT = """You are an instructional design expert. Perform the ADDIE Analysis phase for the following scenario.

## Scenario information
- Title: {title}
- Target learners: {target_audience}
- Learning environment: {learning_environment}
- Duration: {duration}
- Prior knowledge: {prior_knowledge}
- Learning goals: {learning_goals}

## Analysis phase requirements (10 sub-items)

### A-1~4. Needs analysis (needs_analysis)
- problem_definition: gap between the current state and the target state (2-3 sentences)
- gap_analysis: gaps between expected and actual performance (at least 3)
- performance_analysis: judgement on whether an instructional solution is needed (2-3 sentences)
- priority_matrix: high/medium/low priority classification

### A-5. Learner analysis (learner_analysis)
- target_audience: clearly defined target group
- characteristics: at least 5 concrete characteristics
- prior_knowledge: prior knowledge level (2-3 sentences)
- learning_preferences: at least 4 learning preferences
- motivation: motivation level and reasons (2-3 sentences)
- challenges: at least 3 expected difficulties

### A-6. Context analysis (context_analysis)
- environment: learning environment
- duration: total learning time
- constraints: at least 3 constraints
- resources: at least 3 available resources
- technical_requirements: at least 2 technical requirements

### A-7~10. Task analysis (task_analysis)
- main_topics: at least 3 main learning topics
- subtopics: at least 6 detailed learning contents
- prerequisites: at least 2 prerequisite requirements
- review_summary: synthesis of the analysis results (3-4 sentences)

## Output format (JSON)
```json
{{
  "needs_analysis": {{
    "problem_definition": "...",
    "gap_analysis": ["gap 1", "gap 2", "gap 3"],
    "performance_analysis": "...",
    "priority_matrix": {{
      "high": ["item 1", "item 2"],
      "medium": ["item 3"],
      "low": ["item 4"]
    }}
  }},
  "learner_analysis": {{
    "target_audience": "...",
    "characteristics": ["trait 1", "trait 2", "trait 3", "trait 4", "trait 5"],
    "prior_knowledge": "...",
    "learning_preferences": ["preference 1", "preference 2", "preference 3", "preference 4"],
    "motivation": "...",
    "challenges": ["challenge 1", "challenge 2", "challenge 3"]
  }},
  "context_analysis": {{
    "environment": "...",
    "duration": "...",
    "constraints": ["constraint 1", "constraint 2", "constraint 3"],
    "resources": ["resource 1", "resource 2", "resource 3"],
    "technical_requirements": ["requirement 1", "requirement 2"]
  }},
  "task_analysis": {{
    "main_topics": ["topic 1", "topic 2", "topic 3"],
    "subtopics": ["subtopic 1", "subtopic 2", "subtopic 3", "subtopic 4", "subtopic 5", "subtopic 6"],
    "prerequisites": ["prerequisite 1", "prerequisite 2"],
    "review_summary": "..."
  }}
}}
```

Output JSON only."""


def run_analysis(llm, title, target_audience, learning_environment, duration, prior_knowledge, learning_goals):
    prompt = ANALYSIS_PROMPT.format(
        title=title,
        target_audience=target_audience,
        learning_environment=learning_environment,
        duration=duration,
        prior_knowledge=prior_knowledge or "not specified",
        learning_goals=json.dumps(learning_goals, ensure_ascii=False),
    )
    try:
        return parse_json_response(llm.invoke(prompt).content), False
    except Exception as e:
        print(f"[WARN] run_analysis failed: {e}")
        return _fallback_analysis(target_audience, learning_environment, duration, learning_goals), True


def _fallback_analysis(target_audience, learning_environment, duration, learning_goals):
    return {
        "needs_analysis": {
            "problem_definition": f"Systematic training is needed to raise the competency of {target_audience}",
            "gap_analysis": [f"Current: lacking {g} -> Target: achieving {g}" for g in learning_goals[:3]],
            "performance_analysis": "The competency gap is judged solvable through training",
            "priority_matrix": {"high": learning_goals[:2], "medium": learning_goals[2:3], "low": []},
        },
        "learner_analysis": {
            "target_audience": target_audience,
            "characteristics": ["Motivated to learn", "Has basic knowledge", "Interested in practical application", "Capable of self-directed study", "Prefers collaboration"],
            "prior_knowledge": "Basic level of related knowledge",
            "learning_preferences": ["Hands-on practice", "Step-by-step guidance", "Visual materials", "Immediate feedback"],
            "motivation": "High motivation to improve work/study performance",
            "challenges": ["Time constraints", "Limited practice opportunities", "Individual differences"],
        },
        "context_analysis": {
            "environment": learning_environment,
            "duration": duration,
            "constraints": ["Time constraints", "Limited resources", "Technical environment"],
            "resources": ["Learning platform", "Course materials", "Mentoring"],
            "technical_requirements": ["Internet connection", "Learning device"],
        },
        "task_analysis": {
            "main_topics": learning_goals[:3],
            "subtopics": [f"{g} basics" for g in learning_goals[:3]] + [f"{g} practice" for g in learning_goals[:3]],
            "prerequisites": ["Understanding of basic concepts", "Familiarity with learning tools"],
            "review_summary": f"Analysis complete. A {duration} program for {target_audience} targeting {len(learning_goals)} goals.",
        },
    }


# ============================================================
# 2. Design phase (sub-items 11-18)
# ============================================================

DESIGN_PROMPT = """You are an instructional design expert. Perform the ADDIE Design phase based on the analysis results.

## Scenario information
- Title: {title}
- Target learners: {target_audience}
- Duration: {duration}
- Learning goals: {learning_goals}

## Design phase requirements (8 sub-items)

### D-11. Refined learning objectives (learning_objectives)
- At least 5 measurable learning objectives
- Spread across Bloom's Taxonomy levels (2 remember/understand, 2 apply/analyze, 1 evaluate/create)
- Each objective includes: id, level, statement, bloom_verb, measurable

### D-12. Assessment plan (assessment_plan)
- diagnostic: at least 2 diagnostic assessment methods
- formative: at least 2 formative assessment methods
- summative: at least 2 summative assessment methods

### D-13. Content selection (content_structure)
- modules: at least 3 modules
- topics: topics per module
- sequencing: explanation of the learning order

### D-14. Instructional strategies (instructional_strategies)
- model: "Gagné's 9 Events"
- sequence: ALL 9 events included (required!)
- methods: at least 3 instructional methods
- rationale: justification of the chosen strategy

### D-15. Non-instructional strategies (non_instructional_strategies)
- motivation_strategies: 2-3 motivation strategies
- self_directed_learning: 2-3 supports for self-directed learning
- support_strategies: other support measures

### D-16. Media selection (media_selection)
- At least 3 media choices suited to the learning activities

### D-17. Learning activities and time structure (learning_activities)
- At least 3 designed learning activities

### D-18. Storyboard (storyboard)
- At least 3 frames

## Gagné's 9 Events (all must be included)
1. Gain attention, 2. Inform learners of objectives, 3. Stimulate recall of prior learning,
4. Present the content, 5. Provide learning guidance, 6. Elicit performance,
7. Provide feedback, 8. Assess performance, 9. Enhance retention and transfer

## Output format (JSON)
```json
{{
  "learning_objectives": [
    {{"id": "LO-01", "level": "Remember", "statement": "...", "bloom_verb": "define", "measurable": true}},
    {{"id": "LO-02", "level": "Understand", "statement": "...", "bloom_verb": "explain", "measurable": true}},
    {{"id": "LO-03", "level": "Apply", "statement": "...", "bloom_verb": "apply", "measurable": true}},
    {{"id": "LO-04", "level": "Analyze", "statement": "...", "bloom_verb": "analyze", "measurable": true}},
    {{"id": "LO-05", "level": "Evaluate", "statement": "...", "bloom_verb": "evaluate", "measurable": true}}
  ],
  "assessment_plan": {{
    "diagnostic": ["diagnostic 1", "diagnostic 2"],
    "formative": ["formative 1", "formative 2"],
    "summative": ["summative 1", "summative 2"]
  }},
  "content_structure": {{
    "modules": ["module 1", "module 2", "module 3"],
    "topics": ["topic 1", "topic 2", "topic 3"],
    "sequencing": "..."
  }},
  "instructional_strategies": {{
    "model": "Gagné's 9 Events",
    "sequence": [
      {{"event": "Gain attention", "activity": "...", "duration": "5 min", "resources": ["..."]}},
      {{"event": "Inform learners of objectives", "activity": "...", "duration": "5 min", "resources": ["..."]}},
      {{"event": "Stimulate recall of prior learning", "activity": "...", "duration": "10 min", "resources": ["..."]}},
      {{"event": "Present the content", "activity": "...", "duration": "20 min", "resources": ["..."]}},
      {{"event": "Provide learning guidance", "activity": "...", "duration": "10 min", "resources": ["..."]}},
      {{"event": "Elicit performance", "activity": "...", "duration": "15 min", "resources": ["..."]}},
      {{"event": "Provide feedback", "activity": "...", "duration": "10 min", "resources": ["..."]}},
      {{"event": "Assess performance", "activity": "...", "duration": "15 min", "resources": ["..."]}},
      {{"event": "Enhance retention and transfer", "activity": "...", "duration": "10 min", "resources": ["..."]}}
    ],
    "methods": ["method 1", "method 2", "method 3"],
    "rationale": "..."
  }},
  "non_instructional_strategies": {{
    "motivation_strategies": ["motivation 1", "motivation 2"],
    "self_directed_learning": ["self-directed 1", "self-directed 2"],
    "support_strategies": ["support 1", "support 2"]
  }},
  "learning_activities": [
    {{"activity_name": "activity 1", "duration": "20 min", "description": "...", "materials": ["..."]}},
    {{"activity_name": "activity 2", "duration": "30 min", "description": "...", "materials": ["..."]}},
    {{"activity_name": "activity 3", "duration": "20 min", "description": "...", "materials": ["..."]}}
  ],
  "media_selection": [
    {{"media_type": "medium 1", "purpose": "...", "rationale": "..."}},
    {{"media_type": "medium 2", "purpose": "...", "rationale": "..."}},
    {{"media_type": "medium 3", "purpose": "...", "rationale": "..."}}
  ],
  "storyboard": [
    {{"frame_number": 1, "screen_title": "...", "visual_description": "...", "interaction": "...", "notes": "..."}},
    {{"frame_number": 2, "screen_title": "...", "visual_description": "...", "interaction": "...", "notes": "..."}},
    {{"frame_number": 3, "screen_title": "...", "visual_description": "...", "interaction": "...", "notes": "..."}}
  ]
}}
```

Output JSON only."""


def run_design(llm, title, target_audience, duration, learning_goals):
    prompt = DESIGN_PROMPT.format(
        title=title,
        target_audience=target_audience,
        duration=duration,
        learning_goals=json.dumps(learning_goals, ensure_ascii=False),
    )
    try:
        return parse_json_response(llm.invoke(prompt).content), False
    except Exception as e:
        print(f"[WARN] run_design failed: {e}")
        return _fallback_design(learning_goals, duration), True


def _fallback_design(learning_goals, duration):
    objectives = [
        {"id": f"LO-0{i+1}", "level": ["Remember", "Understand", "Apply", "Analyze", "Evaluate"][i % 5],
         "statement": f"Be able to {g}", "bloom_verb": ["define", "explain", "apply", "analyze", "evaluate"][i % 5],
         "measurable": True}
        for i, g in enumerate(learning_goals[:5])
    ]
    events = ["Gain attention", "Inform learners of objectives", "Stimulate recall of prior learning",
              "Present the content", "Provide learning guidance", "Elicit performance",
              "Provide feedback", "Assess performance", "Enhance retention and transfer"]
    return {
        "learning_objectives": objectives,
        "assessment_plan": {
            "diagnostic": ["Pre-quiz", "Self-checklist"],
            "formative": ["Practice assignment", "Peer review"],
            "summative": ["Final assessment", "Project presentation"],
        },
        "content_structure": {
            "modules": learning_goals[:3],
            "topics": [f"{g} details" for g in learning_goals[:3]],
            "sequencing": "Basics -> advanced -> application",
        },
        "instructional_strategies": {
            "model": "Gagné's 9 Events",
            "sequence": [{"event": e, "activity": f"{e} activity", "duration": "10 min", "resources": ["Course materials"]} for e in events],
            "methods": ["Lecture", "Hands-on practice", "Discussion"],
            "rationale": "Gagné's 9 Events applied for systematic lesson design",
        },
        "non_instructional_strategies": {
            "motivation_strategies": ["Recognition of achievement", "Link to real work"],
            "self_directed_learning": ["Learning checklist", "Self-assessment"],
            "support_strategies": ["Mentoring", "Q&A"],
        },
        "learning_activities": [
            {"activity_name": "Concept study", "duration": "30 min", "description": "Study of the core concepts", "materials": ["Course materials"]},
            {"activity_name": "Practice", "duration": "40 min", "description": "Practice assignment", "materials": ["Practice materials"]},
            {"activity_name": "Discussion", "duration": "20 min", "description": "Group discussion", "materials": ["Discussion topics"]},
        ],
        "media_selection": [
            {"media_type": "Slides", "purpose": "Concept delivery", "rationale": "Supports visual learning"},
            {"media_type": "Video", "purpose": "Demonstration", "rationale": "Conveys procedural knowledge"},
            {"media_type": "Practice environment", "purpose": "Application", "rationale": "Experiential learning"},
        ],
        "storyboard": [
            {"frame_number": i+1, "screen_title": f"Screen {i+1}", "visual_description": "Learning content", "interaction": "Next button", "notes": ""}
            for i in range(3)
        ],
    }


# ============================================================
# 3. Development phase (sub-items 17, 19-23)
# ============================================================

DEVELOPMENT_PROMPT = """You are an instructional design expert. Perform the ADDIE Development phase.

## Scenario information
- Title: {title}
- Target learners: {target_audience}
- Learning environment: {learning_environment}
- Learning goals: {learning_goals}

## Development phase requirements (5 sub-items)

### Dev-19. Learner materials (learner_materials)
- At least 3 learner-facing materials
- Each material includes: title, type, content (actual content, 500+ characters), format

### Dev-20. Instructor guide (instructor_guide)
- overview: overall course overview
- session_guides: at least 3 per-session guides
- facilitation_tips: at least 3 facilitation tips
- troubleshooting: at least 2 troubleshooting guides

### Dev-21. Operator manual (operator_manual)
- system_setup: system setup guide
- operation_procedures: operating procedures
- support_procedures: support procedures
- escalation_process: escalation process

### Dev-22. Assessment tools/items (assessment_tools)
- At least 10 items (3-4 easy, 4-5 medium, 2-3 hard)
- Each item includes: item_id, type, question, options (4), answer, aligned_objective, scoring_criteria

### Dev-23. Expert review (expert_review)
- reviewers: at least 2 reviewer types
- review_criteria: at least 5 review criteria
- feedback_summary: feedback summary
- revisions_made: revisions applied

## Output format (JSON)
```json
{{
  "learner_materials": [
    {{"title": "material 1", "type": "handout", "content": "detailed content...", "format": "PDF"}},
    {{"title": "material 2", "type": "slides", "content": "detailed content...", "format": "PPT"}},
    {{"title": "material 3", "type": "practice guide", "content": "detailed content...", "format": "PDF"}}
  ],
  "instructor_guide": {{
    "overview": "Overall course overview...",
    "session_guides": [
      {{"session": 1, "objectives": ["objective 1"], "activities": ["activity 1"], "notes": "..."}},
      {{"session": 2, "objectives": ["objective 2"], "activities": ["activity 2"], "notes": "..."}},
      {{"session": 3, "objectives": ["objective 3"], "activities": ["activity 3"], "notes": "..."}}
    ],
    "facilitation_tips": ["tip 1", "tip 2", "tip 3"],
    "troubleshooting": ["troubleshooting 1", "troubleshooting 2"]
  }},
  "operator_manual": {{
    "system_setup": "System setup guide...",
    "operation_procedures": ["procedure 1", "procedure 2", "procedure 3"],
    "support_procedures": ["support 1", "support 2"],
    "escalation_process": "Escalation process..."
  }},
  "assessment_tools": [
    {{"item_id": "Q-01", "type": "multiple_choice", "question": "item 1", "options": ["A", "B", "C", "D"], "answer": "A", "aligned_objective": "LO-01", "scoring_criteria": "1 point for correct answer"}},
    {{"item_id": "Q-02", "type": "multiple_choice", "question": "item 2", "options": ["A", "B", "C", "D"], "answer": "B", "aligned_objective": "LO-02", "scoring_criteria": "1 point for correct answer"}}
  ],
  "expert_review": {{
    "reviewers": ["subject-matter expert", "instructional design expert"],
    "review_criteria": ["content accuracy", "instructional appropriateness", "technical quality", "user experience", "accessibility"],
    "feedback_summary": "Generally sound with a few improvements needed...",
    "revisions_made": ["content revision 1", "design improvement 2"]
  }}
}}
```

Output JSON only."""


def run_development(llm, title, target_audience, learning_environment, learning_goals):
    prompt = DEVELOPMENT_PROMPT.format(
        title=title,
        target_audience=target_audience,
        learning_environment=learning_environment,
        learning_goals=json.dumps(learning_goals, ensure_ascii=False),
    )
    try:
        return parse_json_response(llm.invoke(prompt).content), False
    except Exception as e:
        print(f"[WARN] run_development failed: {e}")
        return _fallback_development(learning_goals), True


def _fallback_development(learning_goals):
    return {
        "learner_materials": [
            {"title": f"Learning material {i+1}", "type": ["handout", "slides", "practice guide"][i % 3],
             "content": f"Detailed learning content for the goal '{learning_goals[i % len(learning_goals)]}'. " * 10,
             "format": "PDF"}
            for i in range(3)
        ],
        "instructor_guide": {
            "overview": "This course is designed to improve learner competency.",
            "session_guides": [
                {"session": i+1, "objectives": [learning_goals[i % len(learning_goals)]], "activities": ["Lecture", "Practice"], "notes": "Points of attention"}
                for i in range(3)
            ],
            "facilitation_tips": ["Encourage learner participation", "Manage time", "Invite questions"],
            "troubleshooting": ["Use alternatives on technical issues", "Give extra explanation when learners struggle"],
        },
        "operator_manual": {
            "system_setup": "LMS access and content registration procedure",
            "operation_procedures": ["Pre-check", "Operation monitoring", "Post-session wrap-up"],
            "support_procedures": ["Answer learner inquiries", "Technical support"],
            "escalation_process": "Escalate in order: coordinator -> manager -> technical team",
        },
        "assessment_tools": [
            {"item_id": f"Q-{i+1:02d}", "type": "multiple_choice", "question": f"Item {i+1}",
             "options": ["A", "B", "C", "D"], "answer": ["A", "B", "C", "D"][i % 4],
             "aligned_objective": f"LO-{(i % 5) + 1:02d}", "scoring_criteria": "1 point for correct answer"}
            for i in range(10)
        ],
        "expert_review": {
            "reviewers": ["subject-matter expert", "instructional design expert"],
            "review_criteria": ["content accuracy", "instructional appropriateness", "technical quality", "user experience", "accessibility"],
            "feedback_summary": "Generally sound",
            "revisions_made": ["Minor content revisions", "Design improvements"],
        },
    }


# ============================================================
# 4. Implementation phase (sub-items 24-27)
# ============================================================

IMPLEMENTATION_PROMPT = """You are an instructional design expert. Perform the ADDIE Implementation phase.

## Scenario information
- Title: {title}
- Target learners: {target_audience}
- Learning environment: {learning_environment}
- Class size: {class_size}

## Implementation phase requirements (4 sub-items)

### I-24. Instructor/operator orientation (instructor_orientation)
- orientation_objectives: at least 3 orientation objectives
- schedule: schedule plan
- materials: at least 2 required materials
- competency_checklist: at least 3 competency checklist items

### I-25. System/environment check (system_check)
- checklist: at least 5 check items
- technical_validation: technical validation result
- contingency_plans: at least 2 contingency plans

### I-26. Prototype execution plan (prototype_execution)
- pilot_scope: pilot scope
- participants: participant size and characteristics
- execution_log: at least 3 execution records
- issues_encountered: at least 2 issues

### I-27. Operation monitoring (monitoring)
- monitoring_criteria: at least 3 monitoring criteria
- support_channels: at least 2 support channels
- issue_resolution_log: at least 2 issue resolution records
- real_time_adjustments: at least 2 real-time adjustments

## Output format (JSON)
```json
{{
  "instructor_orientation": {{
    "orientation_objectives": ["objective 1", "objective 2", "objective 3"],
    "schedule": "Schedule plan...",
    "materials": ["material 1", "material 2"],
    "competency_checklist": ["competency 1", "competency 2", "competency 3"]
  }},
  "system_check": {{
    "checklist": ["check 1", "check 2", "check 3", "check 4", "check 5"],
    "technical_validation": "Technical validation complete...",
    "contingency_plans": ["contingency 1", "contingency 2"]
  }},
  "prototype_execution": {{
    "pilot_scope": "Pilot scope...",
    "participants": "Participant details...",
    "execution_log": ["record 1", "record 2", "record 3"],
    "issues_encountered": ["issue 1", "issue 2"]
  }},
  "monitoring": {{
    "monitoring_criteria": ["criterion 1", "criterion 2", "criterion 3"],
    "support_channels": ["channel 1", "channel 2"],
    "issue_resolution_log": ["resolution 1", "resolution 2"],
    "real_time_adjustments": ["adjustment 1", "adjustment 2"]
  }}
}}
```

Output JSON only."""


def run_implementation(llm, title, target_audience, learning_environment, class_size):
    prompt = IMPLEMENTATION_PROMPT.format(
        title=title,
        target_audience=target_audience,
        learning_environment=learning_environment,
        class_size=class_size or "not specified",
    )
    try:
        return parse_json_response(llm.invoke(prompt).content), False
    except Exception as e:
        print(f"[WARN] run_implementation failed: {e}")
        return _fallback_implementation(learning_environment), True


def _fallback_implementation(learning_environment):
    return {
        "instructor_orientation": {
            "orientation_objectives": ["Understand the course", "Use the tools", "Manage learners"],
            "schedule": "2-hour orientation one week before the course starts",
            "materials": ["Instructor guide", "System manual"],
            "competency_checklist": ["Content understanding", "Tool usage", "Facilitation skills"],
        },
        "system_check": {
            "checklist": ["LMS access", "Content loading", "Assessment features", "Communication tools", "Backup system"],
            "technical_validation": "All functions verified as working",
            "contingency_plans": ["Prepare offline materials", "Technical support contacts"],
        },
        "prototype_execution": {
            "pilot_scope": f"Small-scale pilot in the {learning_environment} environment",
            "participants": "10-15 learners selected from the target group",
            "execution_log": ["Pilot start", "Mid-point check", "Pilot end"],
            "issues_encountered": ["Some technical problems", "Schedule adjustment needed"],
        },
        "monitoring": {
            "monitoring_criteria": ["Learning progress", "Participation", "Satisfaction"],
            "support_channels": ["Real-time chat", "Email support"],
            "issue_resolution_log": ["Technical issues resolved", "Learning support provided"],
            "real_time_adjustments": ["Schedule adjustment", "Extra explanations provided"],
        },
    }


# ============================================================
# 5. Evaluation phase (sub-items 22, 28-33)
# ============================================================

EVALUATION_PROMPT = """You are an instructional design expert. Perform the ADDIE Evaluation phase.

## Scenario information
- Title: {title}
- Target learners: {target_audience}
- Learning goals: {learning_goals}

## Evaluation phase requirements (6 sub-items)

### E-28. Pilot data collection (formative.data_collection)
- methods: at least 3 collection methods
- learner_feedback: at least 3 learner feedback items
- performance_data: performance data indicators
- observations: at least 2 observation items

### E-29. Formative-evaluation-based improvements (formative.improvements)
- At least 3 improvement items
- Each item includes: issue_identified, improvement_action, priority

### E-30. Summative assessment items (summative.assessment_tools)
- At least 5 summative assessment items
- Each item includes: item_id, type, question, scoring_rubric

### E-31. Summative effectiveness analysis (summative.effectiveness_analysis)
- learning_outcomes: learning outcome analysis
- goal_achievement_rate: goal achievement rate
- statistical_analysis: statistical analysis result
- recommendations: at least 3 recommendations

### E-32. Program adoption decision (summative.adoption_decision)
- decision: one of adopt/modify/reject
- rationale: rationale for the decision (2-3 sentences)
- conditions: at least 2 adoption conditions
- stakeholder_approval: stakeholder approval status

### E-33. Program improvement and feedback loop (improvement_plan)
- feedback_summary: feedback summary
- improvement_areas: at least 3 improvement areas
- action_items: at least 3 action items
- feedback_loop: description of the feedback loop
- next_iteration_goals: at least 2 goals for the next iteration

## Output format (JSON)
```json
{{
  "formative": {{
    "data_collection": {{
      "methods": ["method 1", "method 2", "method 3"],
      "learner_feedback": ["feedback 1", "feedback 2", "feedback 3"],
      "performance_data": {{"metric1": "indicator 1", "metric2": "indicator 2"}},
      "observations": ["observation 1", "observation 2"]
    }},
    "improvements": [
      {{"issue_identified": "issue 1", "improvement_action": "improvement 1", "priority": "high"}},
      {{"issue_identified": "issue 2", "improvement_action": "improvement 2", "priority": "medium"}},
      {{"issue_identified": "issue 3", "improvement_action": "improvement 3", "priority": "low"}}
    ]
  }},
  "summative": {{
    "assessment_tools": [
      {{"item_id": "SA-01", "type": "comprehensive", "question": "item 1", "scoring_rubric": "scoring criteria 1"}},
      {{"item_id": "SA-02", "type": "comprehensive", "question": "item 2", "scoring_rubric": "scoring criteria 2"}}
    ],
    "effectiveness_analysis": {{
      "learning_outcomes": {{"achievement_rate": "85%", "details": "outcome analysis..."}},
      "goal_achievement_rate": "85%",
      "statistical_analysis": "Statistical analysis result...",
      "recommendations": ["recommendation 1", "recommendation 2", "recommendation 3"]
    }},
    "adoption_decision": {{
      "decision": "adopt",
      "rationale": "Rationale for the adoption decision...",
      "conditions": ["condition 1", "condition 2"],
      "stakeholder_approval": "approved"
    }}
  }},
  "improvement_plan": {{
    "feedback_summary": "Feedback summary...",
    "improvement_areas": ["area 1", "area 2", "area 3"],
    "action_items": ["action 1", "action 2", "action 3"],
    "feedback_loop": "Description of the feedback loop...",
    "next_iteration_goals": ["goal 1", "goal 2"]
  }}
}}
```

Output JSON only."""


def run_evaluation(llm, title, target_audience, learning_goals):
    prompt = EVALUATION_PROMPT.format(
        title=title,
        target_audience=target_audience,
        learning_goals=json.dumps(learning_goals, ensure_ascii=False),
    )
    try:
        return parse_json_response(llm.invoke(prompt).content), False
    except Exception as e:
        print(f"[WARN] run_evaluation failed: {e}")
        return _fallback_evaluation(learning_goals), True


def _fallback_evaluation(learning_goals):
    return {
        "formative": {
            "data_collection": {
                "methods": ["Survey", "Learning log analysis", "Interviews"],
                "learner_feedback": ["Content satisfaction", "Difficulty appropriateness", "Practical usefulness"],
                "performance_data": {"completion_rate": "course completion rate", "assessment_score": "assessment score"},
                "observations": ["Learner engagement", "Interaction frequency"],
            },
            "improvements": [
                {"issue_identified": "Some content too difficult", "improvement_action": "Provide extra explanation", "priority": "high"},
                {"issue_identified": "Not enough time", "improvement_action": "Adjust schedule", "priority": "medium"},
                {"issue_identified": "Not enough practice", "improvement_action": "Extend practice time", "priority": "high"},
            ],
        },
        "summative": {
            "assessment_tools": [
                {"item_id": f"SA-{i+1:02d}", "type": "comprehensive", "question": f"Summative item {i+1}",
                 "scoring_rubric": "Scoring criteria"}
                for i in range(5)
            ],
            "effectiveness_analysis": {
                "learning_outcomes": {"achievement_rate": "85%", "details": "Most learning goals achieved"},
                "goal_achievement_rate": "85%",
                "statistical_analysis": "Mean score 85, standard deviation 10",
                "recommendations": ["Supplement content", "Strengthen practice", "Improve feedback"],
            },
            "adoption_decision": {
                "decision": "adopt",
                "rationale": "High goal achievement rate and good learner satisfaction",
                "conditions": ["Apply after minor content revisions", "Incorporate pilot results"],
                "stakeholder_approval": "approved",
            },
        },
        "improvement_plan": {
            "feedback_summary": "Positive overall with some improvements needed",
            "improvement_areas": ["Content difficulty", "Practice opportunities", "Feedback system"],
            "action_items": ["Revise content", "Add practice", "Strengthen feedback"],
            "feedback_loop": "Quarterly review and improvement cycle",
            "next_iteration_goals": ["Reach 90% satisfaction", "Reach 95% completion"],
        },
    }


# ============================================================
# Refine mode (targeted refinement without alignment control)
# ============================================================

REFINE_SUFFIX = """

## PREVIOUS OUTPUT (current version of this phase)
```json
{previous_output}
```

## EDIT REQUEST (from the user)
{edit_request}

Revise this phase's output so that it satisfies the edit request. Change only
what the request requires and keep everything else exactly as it is in the
previous output. If this phase does not need any change for this request,
output exactly:
```json
{{"unchanged": true}}
```

Output JSON only."""


def refine_phase(llm, base_prompt: str, previous_section: dict, edit_request: str):
    """One refine call for one phase.

    Returns ``(section_dict, unchanged, fallback_used)``. On any failure the
    previous section is kept — the safe interpretation of a broken edit.
    """
    prompt = base_prompt + REFINE_SUFFIX.format(
        previous_output=json.dumps(previous_section, ensure_ascii=False),
        edit_request=edit_request,
    )
    try:
        parsed = parse_json_response(llm.invoke(prompt).content)
    except Exception as e:
        print(f"[WARN] refine_phase failed: {e}")
        return previous_section, False, True
    if isinstance(parsed, dict) and parsed.get("unchanged") is True:
        return previous_section, True, False
    return parsed, False, False


__all__ = [
    "run_analysis",
    "run_design",
    "run_development",
    "run_implementation",
    "run_evaluation",
    "refine_phase",
    "ANALYSIS_PROMPT",
    "DESIGN_PROMPT",
    "DEVELOPMENT_PROMPT",
    "IMPLEMENTATION_PROMPT",
    "EVALUATION_PROMPT",
]
