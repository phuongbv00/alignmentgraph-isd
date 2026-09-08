"""The canonical rulebook: generation RULES per artifact family, plus the
enum vocabularies both the rules' prose and the deep tool schema share.

Single source of the ISD generation RULES contract, shared by BOTH
decomposition arms. Each stage prompt (``core/agentic/specialists.py``)
composes persona + intro + ``RULES_<FAMILY>``; the single arm's state machine
asks ``rules_for(state)`` for the same rule text (merged across the artifact
families a collapsed state covers). Neither arm derives anything from the
other's prompts: the dependency points here from both sides, so the rules are
identical by construction and a wording change lands in both arms at once.
``tests/fixtures/golden_prompts.json`` pins the composed prompts byte-for-byte.

An artifact's SHAPE (types, nesting, enums) is no longer declared here as
``SCHEMA_<FAMILY>`` JSON-example text (removed 2026-09-08) — it lives in
``core/agentic/artifact_schemas.py``, as the deep ``parameters`` of the
artifact's ``submit_*`` tool, which the model sees on every turn regardless of
what the prompt itself still holds. This module keeps only what a JSON Schema
cannot express (cross-field, referential and judgment-call constraints) plus
the enum constants (``BLOOM_LEVELS``, ``MEDIA_TYPES``, etc.) both that schema
module and this one's own ``%``-interpolated prose read from, so a value list
is typed exactly once.
"""
from __future__ import annotations

#: Enum vocabularies shared between the deep tool-call schema
#: (``core/agentic/artifact_schemas.py``) and this module's own ``RULES_*``
#: prose, so a value list is typed exactly once. Same pattern as
#: ``MEDIA_TYPES`` below, just declared earlier because ``RULES_OUTCOMES``
#: (which needs ``BLOOM_LEVELS``) is defined before that constant used to be.
BLOOM_LEVELS = ("remember", "understand", "apply", "analyze", "evaluate", "create")
BLOOM_VERBS = ("recall", "explain", "apply", "analyze", "evaluate", "design")
EVIDENCE_TYPES = ("true_false", "matching", "multiple_choice", "quiz",
                  "short_answer", "performance_task")
#: Not extracted from a RULES_* sentence (there wasn't a hand-typed one to
#: dedupe) — declared here anyway so the deep tool schema has one place to
#: pull the assessment-plan/item `plan_category` vocabulary from.
PLAN_CATEGORIES = ("diagnostic", "formative", "summative")

RULES_ANALYSIS = """\
Every improvement in improvement_plan.improvements must set addresses_gap to an existing gap id
from needs_analysis.gaps."""

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

``level`` must be one of: %(bloom_levels)s.
Use only these bloom_verb values: %(bloom_verbs)s."""

RULES_OUTCOMES = RULES_OUTCOMES % {
    "bloom_levels": ", ".join(BLOOM_LEVELS), "bloom_verbs": ", ".join(BLOOM_VERBS)}

# ``RULES_COURSE_GOAL`` is reachable only through ``rules_for("outcomes")``,
# which nothing currently calls — kept because that lookup is generic over
# ``_STATE_FAMILIES``. The matching SCHEMA_COURSE_GOAL / SCHEMA_LEARNING_OBJECTIVES
# split constants were removed 2026-09-04: SCHEMA_OUTCOMES carries both verbatim
# and is what every live step uses.
RULES_COURSE_GOAL = """\
course_goal.statement must be ONE overarching outcome for the whole course/program — broad enough
that every learning objective can be read as decomposing it, concrete enough to name the actual
capability learners end up with (not a restatement of the topic, and not a generic "learners will
understand X"). Always return a non-empty statement; this call produces nothing else."""

RULES_ASSESSMENT_PLAN = """\
lo_coverage_targets and expected_evidence must have one entry per learning objective given.
formative_methods must each name an instrument and a cadence (e.g. "exit tickets after each
module"), consistent with the formative intent above.
pilot_data_plan.anticipated_difficulties must name at least two SPECIFIC areas, each anchored to
BOTH the content module or session where learners would struggle AND the objective id affected
(e.g. "Module 3 (interactive content design) — ILO-02", never "general comprehension"), each
with a rationale grounded in the learner profile and a first_revision that is concrete enough
to act on without further analysis."""

# expert_review is deliberately NOT in any generation schema: a review written
# by the same model, in the same call, before the artifacts it purports to
# review exist, is fiction. The aggregator always synthesizes
# development.expert_review from the verification that actually ran
# (self-validation rounds, repairs, relation coverage) and says so.

RULES_ASSESSMENT_ITEMS = """\
Every (objective, plan_category) pair the assessment plan's lo_coverage_targets names needs at
least one item; the dev plan's expected_items says how many each instrument set writes, and
there is no filler beyond that. Do not aim for a round number of items -- a plan covering three
objectives in two categories needs six items, not ten. required_cognitive_process must be one of:
%(bloom_levels)s — and must be honestly achievable by the
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

RULES_ASSESSMENT_ITEMS = RULES_ASSESSMENT_ITEMS % {"bloom_levels": ", ".join(BLOOM_LEVELS)}

RULES_ASSESSMENT_DEV_PLAN = """\
Group the assessment plan's lo_coverage_targets into instrument sets: every (objective,
plan_category) pair it names must appear in exactly one set. Most sets should cover a single
objective and category — only group several objectives into one set when a single instrument
genuinely assesses them together (e.g. one integrated scenario testing two related skills at
once), never merely to produce fewer sets. Never invent an objective or category the plan did
not name.

``expected_items`` is how many items that instrument actually needs: at least one per (objective,
plan_category) pair the set lists, at most %(max_items)d, and no filler beyond what the instrument
genuinely requires."""

#: Per-set rewrite of RULES_ASSESSMENT_ITEMS: a Developer sees only its own
#: instrument set, not the whole plan, so the count/filler rule is scoped to
#: that set instead of the plan's full lo_coverage_targets.
RULES_ASSESSMENT_ITEMS_SET = """\
Do NOT write an id for the artifacts you produce — ids are assigned when your set is
committed, so that two Developers working at the same time cannot name the same thing.
YOUR ASSIGNED SET below states how many items to write: cover every (objective, plan_category)
pair it lists with at least one item, and write no filler beyond the stated count. If the set spans
more than one objective, its items must share a common stem/scenario (the instrument the set
describes), but each individual item still carries a SINGLE ``aligned_objective`` — never a list.
required_cognitive_process must be one of:
%(bloom_levels)s — and must be honestly achievable by the
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

RULES_ASSESSMENT_ITEMS_SET = RULES_ASSESSMENT_ITEMS_SET % {"bloom_levels": ", ".join(BLOOM_LEVELS)}

RULES_ACTIVITY_PLAN = """\
Must include ALL 9 Gagné events. Every part of this plan must serve the learning objectives
given — do not introduce content unrelated to them."""

RULES_ACTIVITIES = """\
Every activity must list ``aligned_objectives`` (existing ILO ids it practices, TLA = Teaching/
Learning Activity) and ``prepares_for_assessment`` (existing assessment item ids it prepares
learners for). ``materials_needed`` is free text, NOT an id — describe what content/resource
would help, a later step will source it. ``learner_cognitive_process`` must be one of:
%(bloom_levels)s — and must be at or above the level of
every objective it aligns to (an Apply+ objective needs a hands-on activity: lab, exercise,
project, simulation — never only lecture/reading/video). ``prerequisite_activities`` lists
earlier activities in YOUR OWN submission that this one builds on, by position ([1] = the
first you wrote), if any."""

RULES_ACTIVITIES = RULES_ACTIVITIES % {"bloom_levels": ", ".join(BLOOM_LEVELS)}

RULES_ACTIVITY_DEV_PLAN = """\
Group the learning objectives into activity blocks. Every objective must appear in at least one
block, and no two blocks may cover the same ground: a separate developer writes each block
without seeing the others, so two blocks whose scopes overlap produce duplicate activities.
Never invent an objective the plan did not name.

``expected_activities`` is how many activities that block actually needs — you are the only step
that knows whether a block is one exercise or a six-step progression.

Keep every block small enough to write in ONE response: at most %(max_activities)d activities. An
objective that needs more than that gets SEVERAL blocks, and each one must carry a
``block_theme`` that states its own distinct scope — the stage of the progression it covers
("first contact with the tool", "unaided practice on a real case", "peer critique and revision"),
not a restatement of the objective. The theme is what keeps two blocks for the same objective
from being written twice.

Only group several objectives into one block when their activities genuinely form one theme or
progression, never merely to produce fewer blocks."""

# The budget the planner is held to is the SAME number the deterministic split
# uses, imported rather than written twice: a planner told "at most 8" while the
# harness splits at 6 would have its own grouping taken apart behind it, and the
# scopes it wrote would stop matching the sets that were actually dispatched.
from .dev_plans import max_units as _max_units  # noqa: E402  (cycle-free: dev_plans imports nothing local)

RULES_ACTIVITY_DEV_PLAN = RULES_ACTIVITY_DEV_PLAN % {"max_activities": _max_units("activity")}
RULES_ASSESSMENT_DEV_PLAN = RULES_ASSESSMENT_DEV_PLAN % {"max_items": _max_units("assessment")}

#: Per-set rewrite of RULES_ACTIVITIES: a Developer sees only its own block.
RULES_ACTIVITIES_SET = """\
Do NOT write an id for the artifacts you produce — ids are assigned when your set is
committed, so that two Developers working at the same time cannot name the same thing.
``prerequisite_activities`` therefore names activities BY POSITION in the list you are
submitting: [1] is the first activity you wrote, [2] the second. Leave it empty unless one
of your own activities genuinely has to come first.
Every activity must list ``aligned_objectives`` (existing ILO ids it practices, TLA = Teaching/
Learning Activity, drawn ONLY from YOUR ASSIGNED BLOCK's objectives) and
``prepares_for_assessment`` (existing assessment item ids it prepares learners for).
``materials_needed`` is free text, NOT an id — describe what content/resource would help, a
later step will source it. ``learner_cognitive_process`` must be one of:
%(bloom_levels)s — and must be at or above the level of
every objective it aligns to (an Apply+ objective needs a hands-on activity: lab, exercise,
project, simulation — never only lecture/reading/video). ``prerequisite_activities`` may only
reference activity ids YOU produce in this same response — an activity in another block is not a
valid prerequisite here."""

RULES_ACTIVITIES_SET = RULES_ACTIVITIES_SET % {"bloom_levels": ", ".join(BLOOM_LEVELS)}

#: The media vocabulary, typed ONCE. `RULES_CONTENT_MODULES` used to hand-type
#: the list and `SCHEMA_MATERIALS` used to hand-type one of its values as its
#: exemplar; the canonical keys of `alignment._MEDIA_TYPE_ALIASES`, which is
#: what P6 actually matches on, are a third copy (asserted equal in
#: `tests/test_ablation_flags.py` — this module must not import the graph
#: package, since the prose arm composes from it).
MEDIA_TYPES = ("video", "slides", "simulation", "document", "audio")


RULES_CONTENT_MODULES = """\
Every content module must set ``supports_activities`` to existing activity ids whose
``materials_needed`` hint it is addressing — do not invent a module nothing needs, and between
them the modules should cover every activity. ``read_nodes`` already lists every activity with
its name and cognitive process, which is what this decision needs; read one in full only when
its listing line leaves you unsure. Every module
should set ``covers_topics`` to existing topic ids. Every media selection should set
``respects_constraints`` to existing constraint ids it was chosen in light of (e.g. avoid
bandwidth-heavy video under a low-bandwidth constraint). media_type must be one of:
%(media_types)s. Every media selection should also set ``for_modules`` to
the content module id(s) it serves — a later step develops materials one module at a time and
needs to know which media belong to which module.

``expected_materials`` is how many learner materials that module actually needs — you are the only
step that knows whether a module is one handout or a broad topic needing several. At least one
per media selection the module receives, at most %(max_materials)d; a module that needs more than
that is really two modules."""

RULES_CONTENT_MODULES = RULES_CONTENT_MODULES % {
    "max_materials": _max_units("material"), "media_types": ", ".join(MEDIA_TYPES)}

#: The whole-family rules. Not composed by any fan-out spec — a grep for the
#: name finds only this line — but reached by ``rules_for("content")`` through
#: ``globals()``, which is how the content STAGE prompt states what the family
#: it is planning will be held to. Deleting it on the grep's word raises
#: KeyError at import.
RULES_MATERIALS = """\
Every material's ``linked_module`` must name an existing content module id it belongs to, and
its ``type`` must be the ``media_type`` of the media selection it realizes — one of
%(media_types)s — with ``format`` a delivery format for that type.
``content`` must BE the learner-facing substance of the material, ready to hand to a learner —
the actual text, worked example, exercise instructions, or a scene-by-scene script for
video/slides — several sentences of scenario-specific detail, never a one-line description of
what the content would contain."""

RULES_MATERIALS = RULES_MATERIALS % {"media_types": ", ".join(MEDIA_TYPES)}

#: Per-module rewrite of RULES_MATERIALS: a Developer sees ONE module + its
#: own media selections + the constraints those media declared.
RULES_MATERIALS_UNIT = """\
Do NOT write an id for the artifacts you produce — ids are assigned when your set is
committed, so that two Developers working at the same time cannot name the same thing.
Produce materials ONLY for the ONE content module given — ``linked_module`` must be that
module's id on every material. YOUR ASSIGNED MODULE below states how many materials to write:
realize every media selection given for this module with at least one material, and write no
filler beyond the stated count. Each material's ``type`` must be the ``media_type`` of the
media selection it realizes — one of %(media_types)s — and its ``format`` a delivery format for
that type, respecting the constraints those media declared. Do not copy the type from the schema
example: it is a placeholder, and your module's own media list above is what decides.
``content`` must BE the learner-facing substance of the material, ready to hand to a learner —
the actual text, worked example, exercise instructions, or a scene-by-scene script for
video/slides — several sentences of scenario-specific detail, never a one-line description of
what the content would contain. Because you are developing one module at a time, give this
module's materials the full length and detail a learner would actually need."""

RULES_MATERIALS_UNIT = RULES_MATERIALS_UNIT % {"media_types": ", ".join(MEDIA_TYPES)}


#: The rubric rules a Developer gets: it writes the criteria inside the very
#: items it is writing, so there is no id to point back at. There is no
#: whole-family variant any more — the `rubrics` state went with the stage.
RULES_RUBRICS_ITEM = """\
Give every item you write at least one entry in its own ``rubric`` list — the criterion goes
INSIDE the item, never in a separate list. ``description`` must be observable and scorable
(avoid vague words like "good"/"appropriate" without a rubric/score/percent/criteria anchor).
``evidence_type`` must be one of: %(evidence_types)s — and must be achievable by that item's own
``type`` (do not require performance_task evidence from a multiple_choice item)."""

RULES_RUBRICS_ITEM = RULES_RUBRICS_ITEM % {"evidence_types": ", ".join(EVIDENCE_TYPES)}

RULES_IMPLEMENTATION = """\
Implementation requirements:
- instructor_orientation must be for instructors/operators, not learner learning objectives.
- system_check must include concrete learning platform, lab/resource access, login, network, data capture, accessibility, and fallback checks.
- prototype_execution must describe a realistic pilot, participant sample, execution records, issues, success criteria, and data collection.
- monitoring must include operational support, issue resolution, and real-time instructional adjustments.
- instructor_guide and operator_manual must reference the actual activities/materials given, not generic boilerplate.
- instructor_guide here is the guide's FRAMING only — its overview, facilitation tips and
  troubleshooting. The session-by-session guides are written one block at a time, after this,
  from the dev_plan you produce.
- Make operator_manual.system_setup concrete, stepwise setup instructions for THIS delivery
  environment (platform, accounts, tools, resources named in the scenario) that an operator
  could follow verbatim."""

RULES_IMPLEMENTATION_DEV_PLAN = """\
Divide the delivery into session blocks. Every activity id and every material id in the design
must appear in exactly one block: an activity in no block is an activity nobody scheduled, and
an id in two blocks is two developers writing the same session. Never invent an id that is not
in the design.

``expected_sessions`` is how many delivery sessions that block covers — you are the only step
that knows whether a block is one long workshop or five short classes.

Keep every block small enough to write in ONE response: at most %(max_scheduled)d activities and
materials together. A stretch of delivery bigger than that gets SEVERAL blocks, each with its own
``block_theme`` stating the ground it covers, because a separate developer writes each block
without seeing the others."""

# Same rule as the other two dev plans: the budget the planner is held to IS
# the number the deterministic split uses, imported rather than written twice.
RULES_IMPLEMENTATION_DEV_PLAN = RULES_IMPLEMENTATION_DEV_PLAN % {
    "max_scheduled": _max_units("session_guide")}

RULES_SESSION_GUIDES_SET = """\
Do NOT write an id for the artifacts you produce — ids are assigned when your set is
committed, so that two Developers working at the same time cannot name the same thing.
``session`` IS yours to write: YOUR ASSIGNED BLOCK states which session numbers are yours, and
another developer holds the others.
Every session guide must list the EXACT ids it delivers in ``activity_ids`` and hands out in
``material_ids`` (e.g. "TLA-0101", "MAT-0103"), as ids only, drawn ONLY from YOUR ASSIGNED
BLOCK, separate from the prose in ``activities``. Between your guides, every activity and every
material your block names must appear at least once — anything you leave out is something nobody
scheduled.
Write every guide out in full: the real objectives that session serves, what actually happens in
it, and notes an instructor could act on. ``activities`` is prose describing the session, never a
list of ids."""



#: Artifact families each single-arm state covers, in its state-machine order.
_STATE_FAMILIES: dict[str, tuple[str, ...]] = {
    "analysis": ("ANALYSIS",),
    "outcomes": ("COURSE_GOAL", "OUTCOMES"),
    "assessment": ("ASSESSMENT_PLAN", "ASSESSMENT_ITEMS"),
    "activities": ("ACTIVITY_PLAN", "ACTIVITIES"),
    "content": ("CONTENT_MODULES", "MATERIALS"),
    # The dev plan is part of the implementation DISPATCH artifact (the session
    # guides it divides are written by the Developer tier), so its rules belong
    # in the stage text the same way the plan schema does.
    "implementation": ("IMPLEMENTATION", "IMPLEMENTATION_DEV_PLAN"),
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
