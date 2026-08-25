"""The canonical rulebook: generation schema + rules per artifact family.

Single source of the ISD generation contract, shared by BOTH decomposition
arms. Each specialist prompt in ``core/agents/*`` composes persona + intro +
``SCHEMA_<FAMILY>`` + ``RULES_<FAMILY>``; the single arm's state machine asks
``rules_for(state)`` for the same rule text (merged across the artifact
families a collapsed state covers) and pairs it with its own merged schemas.
Neither arm derives anything from the other's prompts: the dependency points
here from both sides, so the rules are identical by construction and a wording
change lands in both arms at once. ``tests/fixtures/golden_prompts.json``
pins the composed prompts byte-for-byte.

Schemas and rules are DATA (what a valid artifact is); personas and task
granularity are the decomposition axis and live with the agents.
"""
from __future__ import annotations

#: The one closing line every generation prompt ends with.
JSON_ONLY = (
    "Every <angle-bracket text> in the schema is a placeholder: replace it with real, "
    "scenario-specific content, never copy it into the output. "
    "Output ONLY the JSON object, no markdown, no explanation."
)

SCHEMA_ANALYSIS = """\
{
  "needs_analysis": {
    "problem_definition": "<2-3 sentences describing the gap between current and desired state>",
    "gaps": [
      {"id": "GAP-01", "description": "<gap>", "evidence": "<why this is a real gap>"}
    ],
    "performance_analysis": "<2-3 sentences on whether an instructional solution is needed>",
    "priority_matrix": {"high": ["<gap id>"], "medium": ["<gap id>"], "low": ["<gap id>"]}
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
    "constraints": [
      {"id": "CON-01", "description": "<a specific environmental/resource/policy constraint>"}
    ],
    "environment": "<learning environment>",
    "duration": "<total learning time>",
    "resources": ["<resource1>", "<resource2>"]
  },
  "task_analysis": {
    "topics": [
      {"id": "TOP-01", "topic": "<topic>", "subtopics": ["<sub1>", "<sub2>"]}
    ],
    "prerequisites": ["<prereq1>", "<prereq2>"],
    "entry_behaviors": ["<what learners can already do before instruction starts>"],
    "initial_objectives": [
      {"draft": "<preliminary learning objective phrased from the gaps above>",
       "critique": "<why this draft is or is not yet clear and measurable>",
       "revision": "<the sharpened, observable version>"}
    ],
    "review_summary": "<synthesis of analysis results in 3-4 sentences: are the topics consistent with the gaps and the learner profile, and what needs revising>"
  },
  "improvement_plan": {
    "feedback_summary": "<1-2 sentences on what the gaps above imply needs improving>",
    "improvements": [
      {"id": "IMP-01", "addresses_gap": "GAP-01", "action": "<concrete improvement action>"}
    ],
    "next_iteration_goals": ["<goal1>", "<goal2>"],
    "feedback_loop": "<how and how often learner/instructor feedback is collected, and how it feeds the next design iteration>"
  }
}"""

RULES_ANALYSIS = """\
Every improvement in improvement_plan.improvements must set addresses_gap to an existing gap id
from needs_analysis.gaps."""

SCHEMA_OUTCOMES = """\
{
  "course_goal": {"statement": "<one overarching goal for the whole course/program>"},
  "learning_objectives": [
    {"id": "ILO-01", "level": "<bloom level>", "statement": "<objective>", "bloom_verb": "<verb>"},
    {"id": "ILO-02", "level": "<bloom level>", "statement": "<objective>", "bloom_verb": "<verb>"}
  ]
}"""

RULES_OUTCOMES = """\
Each objective (ILO = Intended Learning Outcome) decomposes course_goal and is grounded in the
gaps/topics/learner profile given.

Return at least 1 objective; never an empty list. Beyond that YOU decide how many the scenario
needs. Derive that number from the analysis: every gap and topic identified must be addressed by
at least one objective, at a grain the stated duration, scope and learner profile can
realistically deliver. A short workshop and a semester-long course do not need the same number.
Do not pad to a round number, and do not merge unrelated gaps into one objective to hit a count.

Set each objective's ``level`` from the performance its gap actually demands, not from a
fixed progression. A gap about professional judgement yields an evaluate-level objective even if
no lower-level objective precedes it; a gap about terminology yields a remember-level one even if
it is the only such objective.

``level`` must be one of: remember, understand, apply, analyze, evaluate, create.
Use only these bloom_verb values: recall, explain, apply, analyze, evaluate, design."""

# SCHEMA_OUTCOMES/RULES_OUTCOMES stay byte-identical (core/agentic/specialists.py
# references both directly, not through rules_for) — the 2026-08-28 course-goal/
# objectives split below is additive, not a rename. Only the multi arm's own
# Hop B actually splits into two calls (course goal, then objectives grounded
# in it — see OutcomeDesignerAgent._run_goal/_run_design); the single arm's
# "outcomes" state keeps asking for both in one merged call (collapsing that
# split is what the decomposition axis measures), so it composes BOTH rule
# blocks below via rules_for("outcomes") (see _STATE_FAMILIES).

SCHEMA_COURSE_GOAL = """\
{
  "course_goal": {"statement": "<one overarching goal for the whole course/program>"}
}"""

RULES_COURSE_GOAL = """\
course_goal.statement must be ONE overarching outcome for the whole course/program — broad enough
that every learning objective can be read as decomposing it, concrete enough to name the actual
capability learners end up with (not a restatement of the topic, and not a generic "learners will
understand X"). Always return a non-empty statement; this call produces nothing else."""

SCHEMA_LEARNING_OBJECTIVES = """\
{
  "learning_objectives": [
    {"id": "ILO-01", "level": "<bloom level>", "statement": "<objective>", "bloom_verb": "<verb>"},
    {"id": "ILO-02", "level": "<bloom level>", "statement": "<objective>", "bloom_verb": "<verb>"}
  ]
}"""

SCHEMA_ASSESSMENT_PLAN = """\
{
  "assessment_plan": {
    "diagnostic": ["<diagnostic intent 1>", "<diagnostic intent 2>"],
    "formative": ["<formative intent 1>", "<formative intent 2>"],
    "summative": ["<summative intent 1>", "<summative intent 2>"],
    "lo_coverage_targets": {"ILO-01": ["diagnostic", "summative"], "ILO-02": ["formative", "summative"]},
    "expected_evidence": {"ILO-01": "<what evidence would demonstrate mastery of ILO-01>"},
    "formative_methods": ["<method1>", "<method2>", "<method3>"],
    "pilot_data_plan": {
      "collection_points": ["<when during the pilot run data is captured, e.g. 'after module 2'>"],
      "anticipated_difficulties": [
        {"area": "<the objective or content module learners are most likely to struggle with>",
         "rationale": "<why this is expected to be hard for THESE learners>",
         "detected_by": "<which formative method above would surface it>",
         "first_revision": "<the concrete first-round change to make if it does>"}
      ]
    }
  }
}"""

RULES_ASSESSMENT_PLAN = """\
lo_coverage_targets and expected_evidence must have one entry per learning objective given.
formative_methods must each name an instrument and a cadence (e.g. "exit tickets after each
module"), consistent with the formative intent above.
pilot_data_plan.anticipated_difficulties must name at least two SPECIFIC areas, each anchored to
BOTH the content module or session where learners would struggle AND the objective id affected
(e.g. "Module 3 (interactive content design) — ILO-02", never "general comprehension"), each
with a rationale grounded in the learner profile and a first_revision that is concrete enough
to act on without further analysis."""

SCHEMA_ASSESSMENT_ITEMS = """\
{
  "assessment_tools": [
    {"item_id": "AT-01", "type": "multiple_choice", "question": "<question>", "options": ["<option A>", "<option B>", "<option C>", "<option D>"], "correct_answer": "<the correct option, verbatim>", "aligned_objective": "ILO-01", "plan_category": "diagnostic", "required_cognitive_process": "remember", "scoring_criteria": "<criteria>"},
    {"item_id": "AT-02", "type": "short_answer", "question": "<question>", "aligned_objective": "ILO-02", "plan_category": "formative", "required_cognitive_process": "understand", "scoring_criteria": "<criteria>"},
    {"item_id": "AT-03", "type": "performance_task", "question": "<question>", "aligned_objective": "ILO-03", "plan_category": "summative", "required_cognitive_process": "apply", "scoring_criteria": "<criteria>"}
  ]
}"""

# expert_review is deliberately NOT in any generation schema: a review written
# by the same model, in the same call, before the artifacts it purports to
# review exist, is fiction. The aggregator always synthesizes
# development.expert_review from the verification that actually ran
# (self-validation rounds, repairs, relation coverage) and says so.

RULES_ASSESSMENT_ITEMS = """\
The assessment plan's lo_coverage_targets already fixes how many items are needed: produce one
item for every (objective, plan_category) pair it names, and no filler beyond that. Do not aim
for a round number of items -- a plan covering three objectives in two categories needs six
items, not ten. required_cognitive_process must be one of:
remember, understand, apply, analyze, evaluate, create — and must be honestly achievable by the
item's format (a multiple_choice/true_false item cannot honestly claim apply-or-higher; use
short_answer or performance_task for that). Every Apply-or-higher objective must be measured by
a performance_task or short_answer item, never multiple_choice/true_false alone.
The question must make the learner PERFORM the required_cognitive_process on the subject matter
itself. Never write meta-questions that ask the learner to name, identify, or describe which
cognitive process, Bloom level, or objective is involved (e.g. "Which cognitive process is
required to ...?"), and never restate an objective's wording as the question -- ask for the
performance the objective describes.
A selectable-response item is not administrable without its response set: every multiple_choice
or matching item must carry ``options`` (the actual answer choices, plausible distractors
included) and ``correct_answer`` (the right option, verbatim); every true_false item must carry
``correct_answer``. short_answer and performance_task items take no options — their
scoring_criteria carry the judgment instead."""

SCHEMA_ASSESSMENT_DEV_PLAN = """\
{
  "instrument_sets": [
    {"set_id": "SET-01", "objectives": ["ILO-01", "ILO-02"], "plan_categories": ["formative"],
     "instrument_hint": "<what kind of instrument, e.g. one integrated case scenario>",
     "rationale": "<why these objectives/categories belong in one instrument, or why one alone>"}
  ]
}"""

RULES_ASSESSMENT_DEV_PLAN = """\
Group the assessment plan's lo_coverage_targets into instrument sets: every (objective,
plan_category) pair it names must appear in exactly one set. Most sets should cover a single
objective and category — only group several objectives into one set when a single instrument
genuinely assesses them together (e.g. one integrated scenario testing two related skills at
once), never merely to produce fewer sets. Never invent an objective or category the plan did
not name."""

#: Per-set rewrite of RULES_ASSESSMENT_ITEMS: a Developer sees only its own
#: instrument set, not the whole plan, so the count/filler rule is scoped to
#: that set instead of the plan's full lo_coverage_targets.
RULES_ASSESSMENT_ITEMS_SET = """\
YOUR ASSIGNED SET below already fixes how many items are needed: produce exactly one item for
every (objective, plan_category) pair it lists, and no filler beyond that. If the set spans more
than one objective, its items must share a common stem/scenario (the instrument the set
describes), but each individual item still carries a SINGLE ``aligned_objective`` — never a list.
required_cognitive_process must be one of:
remember, understand, apply, analyze, evaluate, create — and must be honestly achievable by the
item's format (a multiple_choice/true_false item cannot honestly claim apply-or-higher; use
short_answer or performance_task for that). Every Apply-or-higher objective must be measured by
a performance_task or short_answer item, never multiple_choice/true_false alone.
The question must make the learner PERFORM the required_cognitive_process on the subject matter
itself. Never write meta-questions that ask the learner to name, identify, or describe which
cognitive process, Bloom level, or objective is involved (e.g. "Which cognitive process is
required to ...?"), and never restate an objective's wording as the question -- ask for the
performance the objective describes.
A selectable-response item is not administrable without its response set: every multiple_choice
or matching item must carry ``options`` (the actual answer choices, plausible distractors
included) and ``correct_answer`` (the right option, verbatim); every true_false item must carry
``correct_answer``. short_answer and performance_task items take no options — their
scoring_criteria carry the judgment instead."""

SCHEMA_ACTIVITY_PLAN = """\
{
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
  }
}"""

RULES_ACTIVITY_PLAN = """\
Must include ALL 9 Gagné events. Every part of this plan must serve the learning objectives
given — do not introduce content unrelated to them."""

SCHEMA_ACTIVITIES = """\
{
  "learning_activities": [
    {"id": "TLA-01", "activity_name": "<name>", "duration": "<time>", "description": "<desc>", "materials_needed": "<free-text description of what content/resources this activity needs>", "aligned_objectives": ["ILO-01"], "prepares_for_assessment": ["AT-01"], "learner_cognitive_process": "apply", "prerequisite_activities": []},
    {"id": "TLA-02", "activity_name": "<name>", "duration": "<time>", "description": "<desc>", "materials_needed": "<...>", "aligned_objectives": ["ILO-02"], "prepares_for_assessment": ["AT-02"], "learner_cognitive_process": "understand", "prerequisite_activities": ["TLA-01"]}
  ]
}"""

RULES_ACTIVITIES = """\
Every activity must list ``aligned_objectives`` (existing ILO ids it practices, TLA = Teaching/
Learning Activity) and ``prepares_for_assessment`` (existing assessment item ids it prepares
learners for). ``materials_needed`` is free text, NOT an id — describe what content/resource
would help, a later step will source it. ``learner_cognitive_process`` must be one of: remember,
understand, apply, analyze, evaluate, create — and must be at or above the level of
every objective it aligns to (an Apply+ objective needs a hands-on activity: lab, exercise,
project, simulation — never only lecture/reading/video). ``prerequisite_activities`` lists
earlier activity ids this one builds on, if any."""

SCHEMA_ACTIVITY_DEV_PLAN = """\
{
  "activity_blocks": [
    {"set_id": "BLOCK-01", "objectives": ["ILO-01", "ILO-02"],
     "block_theme": "<what ties these activities together, e.g. a shared progression>",
     "rationale": "<why these objectives belong in one block, or why one alone>"}
  ]
}"""

RULES_ACTIVITY_DEV_PLAN = """\
Group the learning objectives into activity blocks: every objective must appear in exactly one
block. Most blocks should cover a single objective — only group several into one block when the
activities for them genuinely form one theme or progression, never merely to produce fewer
blocks. Never invent an objective the plan did not name."""

#: Per-set rewrite of RULES_ACTIVITIES: a Developer sees only its own block.
RULES_ACTIVITIES_SET = """\
Every activity must list ``aligned_objectives`` (existing ILO ids it practices, TLA = Teaching/
Learning Activity, drawn ONLY from YOUR ASSIGNED BLOCK's objectives) and
``prepares_for_assessment`` (existing assessment item ids it prepares learners for).
``materials_needed`` is free text, NOT an id — describe what content/resource would help, a
later step will source it. ``learner_cognitive_process`` must be one of: remember,
understand, apply, analyze, evaluate, create — and must be at or above the level of
every objective it aligns to (an Apply+ objective needs a hands-on activity: lab, exercise,
project, simulation — never only lecture/reading/video). ``prerequisite_activities`` may only
reference activity ids YOU produce in this same response — an activity in another block is not a
valid prerequisite here."""

SCHEMA_CONTENT_MODULES = """\
{
  "content_modules": [
    {"id": "MOD-01", "title": "<module title>", "description": "<what this module covers>", "supports_activities": ["TLA-01"], "covers_topics": ["TOP-01"]}
  ],
  "media_selections": [
    {"id": "MED-01", "media_type": "video", "purpose": "<purpose>", "rationale": "<rationale>", "respects_constraints": ["CON-01"], "for_modules": ["MOD-01"]}
  ]
}"""

RULES_CONTENT_MODULES = """\
Every content module must set ``supports_activities`` to existing activity ids whose
``materials_needed`` hint it is addressing — do not invent a module nothing needs. Every module
should set ``covers_topics`` to existing topic ids. Every media selection should set
``respects_constraints`` to existing constraint ids it was chosen in light of (e.g. avoid
bandwidth-heavy video under a low-bandwidth constraint). media_type must be one of: video,
slides, simulation, document, audio. Every media selection should also set ``for_modules`` to
the content module id(s) it serves — a later step develops materials one module at a time and
needs to know which media belong to which module."""

SCHEMA_MATERIALS = """\
{
  "learner_materials": [
    {"id": "MAT-01", "title": "<material title>", "type": "video", "format": "mp4", "content": "<description of the actual content>", "linked_module": "MOD-01"}
  ]
}"""

RULES_MATERIALS = """\
Every material's ``linked_module`` must name an existing content module id it belongs to, and
its ``type``/``format`` should realize one of the media selections given (e.g. a media selection
of type "video" should be realized by a material whose type/format is video-like).
``content`` must BE the learner-facing substance of the material, ready to hand to a learner —
the actual text, worked example, exercise instructions, or a scene-by-scene script for
video/slides — several sentences of scenario-specific detail, never a one-line description of
what the content would contain."""

#: Per-module rewrite of RULES_MATERIALS: a Developer sees ONE module + its
#: own media selections + the constraints those media declared.
RULES_MATERIALS_UNIT = """\
Produce materials ONLY for the ONE content module given — ``linked_module`` must be that
module's id on every material. Its ``type``/``format`` must realize one of the media selections
given for this module, respecting the constraints those media declared.
``content`` must BE the learner-facing substance of the material, ready to hand to a learner —
the actual text, worked example, exercise instructions, or a scene-by-scene script for
video/slides — several sentences of scenario-specific detail, never a one-line description of
what the content would contain. Because you are developing one module at a time, give this
module's materials the full length and detail a learner would actually need."""

SCHEMA_RUBRICS = """\
{
  "rubric_criteria": [
    {"id": "RC-01", "aligned_assessment": "AT-01", "aligned_objective": "ILO-01", "description": "<observable, scorable description of what full marks looks like>", "evidence_type": "written_response", "levels": {"excellent": "<descriptor>", "satisfactory": "<descriptor>", "needs_improvement": "<descriptor>"}}
  ]
}"""

RULES_RUBRICS = """\
Every assessment item must have at least one rubric criterion. ``aligned_assessment`` must name
an existing assessment item id; ``aligned_objective`` must name the SAME objective that item
already measures. ``description`` must be observable and scorable (avoid vague words like
"good"/"appropriate" without a rubric/score/percent/criteria anchor). ``evidence_type`` must be
one of: true_false, matching, multiple_choice, quiz, short_answer, performance_task — and must
be achievable by the assessment item's own format (do not require performance_task evidence from
a multiple_choice item)."""

#: Per-item rewrite of RULES_RUBRICS: a Developer sees ONE assessment item.
RULES_RUBRICS_ITEM = """\
Write at least one rubric criterion for the ONE assessment item given. ``aligned_assessment``
must name that item's id; ``aligned_objective`` must name the SAME objective that item already
measures. ``description`` must be observable and scorable (avoid vague words like
"good"/"appropriate" without a rubric/score/percent/criteria anchor). ``evidence_type`` must be
one of: true_false, matching, multiple_choice, quiz, short_answer, performance_task — and must
be achievable by the assessment item's own format (do not require performance_task evidence from
a multiple_choice item)."""

SCHEMA_IMPLEMENTATION = """\
{
  "instructor_orientation": {
    "orientation_objectives": ["<obj1>", "<obj2>", "<obj3>"],
    "schedule": "<schedule plan>",
    "materials": ["<material1>", "<material2>"],
    "competency_checklist": ["<comp1>", "<comp2>", "<comp3>"]
  },
  "system_check": {
    "checklist": ["<check1>", "<check2>", "<check3>", "<check4>", "<check5>"],
    "technical_validation": "<technical validation results description>",
    "contingency_plans": ["<contingency1>", "<contingency2>"]
  },
  "prototype_execution": {
    "pilot_scope": "<pilot scope description>",
    "participants": "<participant size and characteristics>",
    "execution_log": ["<log1>", "<log2>", "<log3>"],
    "issues_encountered": ["<issue1>", "<issue2>"]
  },
  "monitoring": {
    "monitoring_criteria": ["<criterion1>", "<criterion2>", "<criterion3>"],
    "support_channels": ["<channel1>", "<channel2>"],
    "issue_resolution_log": ["<resolution1>", "<resolution2>"],
    "real_time_adjustments": ["<adjustment1>", "<adjustment2>"]
  },
  "instructor_guide": {
    "overview": "<overall guide overview>",
    "session_guides": [
      {"session": 1, "objectives": ["<obj>"], "activities": ["<what happens in this session>"],
       "activity_ids": ["TLA-01"], "material_ids": ["MAT-01"], "notes": "<notes>"}
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
}"""

RULES_IMPLEMENTATION = """\
Implementation requirements:
- instructor_orientation must be for instructors/operators, not learner learning objectives.
- system_check must include concrete learning platform, lab/resource access, login, network, data capture, accessibility, and fallback checks.
- prototype_execution must describe a realistic pilot, participant sample, execution records, issues, success criteria, and data collection.
- monitoring must include operational support, issue resolution, and real-time instructional adjustments.
- instructor_guide and operator_manual must reference the actual activities/materials given, not generic boilerplate.
- Every session guide must list the EXACT ids it delivers in ``activity_ids`` and hands out in
  ``material_ids`` (e.g. "TLA-01", "MAT-03"), as ids only, separate from the prose in
  ``activities``. Between them, the session guides should account for every activity and every
  material in the design — anything you leave out is something nobody scheduled.
- Write every session guide out in full (real objectives, what actually happens, real notes) and
  make operator_manual.system_setup concrete, stepwise setup instructions for THIS delivery
  environment (platform, accounts, tools, resources named in the scenario) that an operator
  could follow verbatim."""


#: Artifact families each single-arm state covers, in its state-machine order.
_STATE_FAMILIES: dict[str, tuple[str, ...]] = {
    "analysis": ("ANALYSIS",),
    "outcomes": ("COURSE_GOAL", "OUTCOMES"),
    "assessment": ("ASSESSMENT_PLAN", "ASSESSMENT_ITEMS"),
    "activities": ("ACTIVITY_PLAN", "ACTIVITIES"),
    "content": ("CONTENT_MODULES", "MATERIALS"),
    "rubrics": ("RUBRICS",),
    "implementation": ("IMPLEMENTATION",),
}


def rules_for(state: str) -> str:
    """The generation rules for one single-arm state: the ``RULES_*`` blocks of
    every artifact family that state covers, merged in order and deduplicated.
    This is the rulebook lookup the single agent's state machine performs per
    step — the same rule text the specialist prompts state, fetched from the
    same constants."""
    seen: list[str] = []
    for family in _STATE_FAMILIES[state]:
        text = globals()[f"RULES_{family}"].strip()
        if text and text not in seen:
            seen.append(text)
    return "\n\n".join(seen)
