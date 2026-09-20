"""The canonical rulebook: generation RULES per artifact family, plus the
enum vocabularies both the rules' prose and the deep tool schema share.

Single source of the ISD generation RULES contract, shared by BOTH
decomposition arms: the step table (``core/agentic/specialists.py``) composes
persona + intro + ``RULES_<FAMILY>`` (via ``rules_for`` for a stage that
covers several families), and both arms read that table. Neither arm derives
anything from the other's prompts, so the rules are identical by construction
and a wording change lands in both arms at once.
``tests/fixtures/golden_prompts.json`` pins the composed prompts byte-for-byte.

An artifact's SHAPE (types, nesting, enums) lives in
``core/agentic/artifact_schemas.py``, as the deep ``parameters`` of the
artifact's ``submit_*`` tool. This module keeps only what a JSON Schema cannot
express (cross-field, referential and judgment-call constraints) plus the enum
constants (``BLOOM_LEVELS``, ``MEDIA_TYPES``, etc.) both that schema module and
this one's own ``%``-interpolated prose read from, so a value list is typed
exactly once.
"""
from __future__ import annotations

# The budget the activity planner is held to is the SAME number the
# deterministic split uses, imported rather than written twice: a planner told
# "at most 8" while the harness splits at 6 would have its own grouping taken
# apart behind it. Cycle-free: dev_plans imports nothing local.
from .dev_plans import MIN_ACTIVITY_MINUTES as _MIN_ACTIVITY_MINUTES
from .dev_plans import MAX_MODULES, MODULES_BY_COURSE_HOURS
from .dev_plans import max_units as _max_units

#: Enum vocabularies shared between the deep tool-call schema
#: (``core/agentic/artifact_schemas.py``) and this module's own ``RULES_*``
#: prose, so a value list is typed exactly once.
BLOOM_LEVELS = ("remember", "understand", "apply", "analyze", "evaluate", "create")
BLOOM_VERBS = ("recall", "explain", "apply", "analyze", "evaluate", "design")

#: How many intended learning outcomes one course carries.
#:
#: Biggs & Tang, *Teaching for Quality Learning at University* — the source
#: this work already cites for constructive alignment (``biggs2011teaching``)
#: — states it four separate times: "programme and course outcomes alike
#: should rarely exceed five or six in number", and "write a set of no more
#: than five or six intended learning outcomes ... for a semester-long
#: course". So the number is FLAT and does not scale with course length: the
#: semester-long case IS the five-or-six case.
#:
#: What makes it the right number here rather than a borrowed one is the
#: REASON given for it: "otherwise it is practically impossible to align
#: teaching/learning activities and assessment tasks to them all". That is the
#: failure this harness exhibits and this thesis measures — objective count is
#: what every downstream family sizes itself off, and a design with 33
#: outcomes reached 161 activities and 0 P10/P11 edges. The pedagogical limit
#: and the engineering limit are the same phenomenon.
#:
#: TOLD, never enforced: nothing trims a longer list (see ``RULES_OUTCOMES``).
#: How often it is respected is therefore a measurement, readable off the
#: objective list in any run's own ADDIE output.
MAX_OBJECTIVES = 6
EVIDENCE_TYPES = ("true_false", "matching", "multiple_choice", "quiz",
                  "short_answer", "performance_task")
#: The assessment-plan/item `plan_category` vocabulary.
PLAN_CATEGORIES = ("diagnostic", "formative", "summative")

RULES_ANALYSIS = """\
Three lists are what the rest of the design is built from: needs_analysis.gaps (the objectives
close them), context_analysis.constraints (every media selection is chosen in light of them) and
task_analysis.topics (the modules cluster them). Each needs at least one entry, and each entry its
own id — write the finding IN the list, not only in a summary field beside it. A list left empty
is not a short analysis, it is a design that stops there.

Every improvement in improvement_plan.improvements must set addresses_gap to an existing gap id
from needs_analysis.gaps."""

RULES_OUTCOMES = """\
Each objective (ILO = Intended Learning Outcome) states what learners will be able to do. Write
them from the learning goals the brief states, grounded in the gaps/topics/learner profile given.
Do not restate the brief's goals back as a goal of your own: what the course is for is already
settled, and your job is the outcomes that deliver it.

A course has a handful of outcomes, not a catalogue: write at least 1 and no more
than %(max_objectives)d. That is what a course can actually align — past it there are more
outcomes than the teaching activities and assessment tasks of one course can cover, and the
design stops hanging together. Within that, YOU decide how many this scenario needs. Do not
pad to a round number, and do not pad to %(max_objectives)d.

Derive the number from the analysis. The gaps and topics must be covered BETWEEN them, which is
not the same as one objective each: where several gaps are facets of one capability, one
objective at the right grain covers them, and that is the grain the stated duration, scope and
learner profile can realistically deliver. Do not merge unrelated gaps to hit a count.

Give each gap the ONE objective its own demanded performance calls for. Do NOT write a series of
objectives climbing the levels for the same gap: apply, then analyze, then evaluate, then create
about one capability is four outcomes where the course has one, and the activities and
assessments built on each of them multiply the same way. A gap about professional judgement
yields a single evaluate-level objective, with no lower-level objective beneath it; a gap about
terminology yields a single remember-level one.

``level`` must be one of: %(bloom_levels)s.
Use only these bloom_verb values: %(bloom_verbs)s."""

RULES_OUTCOMES = RULES_OUTCOMES % {
    "bloom_levels": ", ".join(BLOOM_LEVELS), "bloom_verbs": ", ".join(BLOOM_VERBS),
    "max_objectives": MAX_OBJECTIVES}

RULES_COURSE_MODULES = """\
``course_modules`` divides the course into modules: each is a cluster of objectives and topics
that are learned together, in the order learners meet them — the order of your list IS the
order of the course. Everything designed after this (assessment, activities, materials,
delivery) is divided by your modules, one module at a time, so a module must be a unit that
makes sense on its own.

Every objective must appear in the ``objectives`` of at least one module, by its id; an objective
that genuinely spans the course may appear in more than one. Set ``covers_topics`` to the ids of
the topics the module teaches, copied from your read of the design state — a topic id you did
not read there does not exist. ``minutes`` is the learner time the module gets, and the modules'
minutes must add up to the time the scenario gives the course — this is the budget the
module's activities and assessments have to fit inside, so do not write a round number.

Write no more modules than you have objectives, no more than the analysis has topics, and no
more than the course length carries: about %(short)d for a course within one week, %(medium)d for
one of up to a month, %(long)d for a longer one. Fewer is fine — a short course with two objectives
that belong together is one module."""

RULES_COURSE_MODULES = RULES_COURSE_MODULES % {
    "short": MODULES_BY_COURSE_HOURS[0][1], "medium": MODULES_BY_COURSE_HOURS[1][1],
    "long": MAX_MODULES}

RULES_ASSESSMENT_PLAN = """\
``sets`` is the assessment blueprint: each set is one thing learners actually sit — a quiz, a
practical, a project — module by module. Give each module the sets it needs at the moments it
needs them — ``timing`` is diagnostic (before the module), formative (during it) or summative
(after it); not every module needs all three, but the course as a whole must have at least one
summative set — a course that never grades what it set out to teach has no evidence that it
worked. For each set state its ``format`` (quiz, practical, project, ...), its real scale in
``item_counts`` (item type -> how many the FULL set has, e.g. 20 multiple_choice and 3
short_answer — the true size, even though only a sample of those items is written out later),
the ``covers_objectives`` it assesses (ids from that module's objectives), its ``minutes``, and its
``weight_percent`` of the course grade (0 when ungraded; the graded sets add up to 100).
``module_id`` must be the id of an existing module, copied from your read of the design state.
Every objective must be covered by at least one set.
lo_coverage_targets and expected_evidence must have one entry per learning objective given, and
lo_coverage_targets must agree with the sets: an objective is promised a category exactly
when a set with that ``timing`` covers it.
formative_methods must each name a set and a cadence (e.g. "exit tickets after each
module"), consistent with the formative intent above.
pilot_data_plan.anticipated_difficulties must name at least two SPECIFIC areas, each anchored to
BOTH the content module or session where learners would struggle AND the objective id affected
(e.g. "Module 3 (interactive content design) — ILO-02", never "general comprehension"), each
with a rationale grounded in the learner profile and a first_revision that is concrete enough
to act on without further analysis."""

RULES_ASSESSMENT_ITEMS = """\
Every item belongs to ONE set of the assessment plan: put that set's id in ``set_id``, and
``plan_category`` must be that set's ``timing``.
Every (objective, plan_category) pair the assessment plan's lo_coverage_targets names needs at
least one item, and there is no filler beyond what the sets' ``item_counts`` state. Do not aim for a round number of items -- a plan covering three
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


#: Per-assignment rewrite of RULES_ASSESSMENT_ITEMS: a Developer sees only
#: the sets it was assigned, not the whole plan, so the count/filler rule is
#: scoped to its assignment instead of the plan's full lo_coverage_targets.
RULES_ASSESSMENT_ITEMS_SET = """\
Do NOT write an id for the artifacts you produce — ids are assigned when your assignment is
committed, so that two Developers working at the same time cannot name the same thing.
YOUR ASSIGNMENT below states how many items to write: cover every (objective, plan_category)
pair it lists with at least one item, and write no filler beyond the stated count. If it spans
more than one objective, your items must share a common stem/scenario (the assessment set they
belong to), but each individual item still carries a SINGLE ``aligned_objective`` — never a list.
Every item belongs to ONE of the assessment sets YOUR ASSIGNMENT lists: put that set's id in
``set_id`` and its ``timing`` in ``plan_category``, write the item in one of the item
types its ``item_counts`` names, and spread your items over those types.
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
Every activity belongs to ONE module: set ``module_id`` to the id of the module it is taught in.
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



#: Per-set rewrite of RULES_ACTIVITIES: a Developer sees only its own block.
RULES_ACTIVITIES_SET = """\
Do NOT write an id for the artifacts you produce — ids are assigned when your set is
committed, so that two Developers working at the same time cannot name the same thing.
``prerequisite_activities`` therefore names activities BY POSITION in the list you are
submitting: [1] is the first activity you wrote, [2] the second. Leave it empty unless one
of your own activities genuinely has to come first.
Every activity belongs to the module YOUR ASSIGNED BLOCK names: set ``module_id`` to that
module's id on every activity.
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

#: The media vocabulary, typed ONCE here; the canonical keys of
#: `alignment._MEDIA_TYPE_ALIASES`, which is what P6 actually matches on, are
#: asserted equal in `tests/test_ablation_flags.py` — this module must not
#: import the graph package, since the prose arm composes from it.
MEDIA_TYPES = ("video", "slides", "simulation", "document", "audio")


RULES_MEDIA_SELECTIONS = """\
Choose the media each module's content is delivered through. Every media selection must set
``for_modules`` to the id(s) of the module(s) it serves, copied from your read of the design
state — materials are developed one module at a time and each module is handed ONLY its own
media, so go through the modules one by one and make sure EVERY module id appears in the
``for_modules`` of at least one selection: a module left out gets materials of no chosen medium. Choose in light of what the module's activities
ask for (their ``materials_needed``): your read of the design state lists every activity with
its module, name and cognitive process, which is what this decision needs; read one in full
only when its listing line leaves you unsure.
Every media selection should set ``respects_constraints`` to the ids of the constraints it was
chosen in light of, copied from your read of the design state, which lists every constraint of
this brief with its description — a constraint you did not read there does not exist, and a name
you invent links to nothing.
media_type must be one of: %(media_types)s."""

RULES_MEDIA_SELECTIONS = RULES_MEDIA_SELECTIONS % {"media_types": ", ".join(MEDIA_TYPES)}

#: The whole-family rules. Not composed by any fan-out spec — a grep for the
#: name finds only this line — but reached by ``rules_for("content")`` through
#: ``globals()``, which is how the content STAGE prompt states what the family
#: it is planning will be held to. Deleting it on the grep's word raises
#: KeyError at import.
RULES_MATERIALS = """\
Every material's ``linked_module`` must name an existing module id it belongs to, and
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
Produce materials ONLY for the ONE module given — ``linked_module`` must be that
module's id on every material. YOUR ASSIGNED MODULE below states how many materials to write:
realize every media selection given for this module with at least one material, and write no
filler beyond the stated count. Each material's ``type`` must be the ``media_type`` of the
media selection it realizes — one of %(media_types)s — and its ``format`` a delivery format for
that type, respecting the constraints those media declared: your module's own media list above
is what decides the type.
``content`` must BE the learner-facing substance of the material, ready to hand to a learner —
the actual text, worked example, exercise instructions, or a scene-by-scene script for
video/slides — several sentences of scenario-specific detail, never a one-line description of
what the content would contain. Because you are developing one module at a time, give this
module's materials the full length and detail a learner would actually need."""

RULES_MATERIALS_UNIT = RULES_MATERIALS_UNIT % {"media_types": ", ".join(MEDIA_TYPES)}


#: The rubric rules a Developer gets: it writes the criteria inside the very
#: items it is writing, so there is no id to point back at.
RULES_RUBRICS_ITEM = """\
Give every item you write at least one entry in its own ``rubric`` list — the criterion goes
INSIDE the item, never in a separate list. ``description`` names what is being judged, and
``levels`` is what makes it scorable: say what an excellent, a satisfactory and a
needs_improvement answer each SHOW, in a full sentence each, specific to this item — a marker
must be able to tell the three apart from your words alone.
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
  troubleshooting. The session-by-session guides are written afterwards, one module at a time,
  by a developer per module.
- Make operator_manual.system_setup concrete, stepwise setup instructions for THIS delivery
  environment (platform, accounts, tools, resources named in the scenario) that an operator
  could follow verbatim."""


# Same rule as the other two dev plans: the budget the planner is held to IS
# the number the deterministic split uses, imported rather than written twice.

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



#: Artifact families each multi-family STAGE covers, in order. (``analysis``
#: covers one family and reads its ``RULES_*`` directly.)
_STATE_FAMILIES: dict[str, tuple[str, ...]] = {
    "outcomes": ("OUTCOMES", "COURSE_MODULES"),
    "assessment": ("ASSESSMENT_PLAN", "ASSESSMENT_ITEMS"),
    "activities": ("ACTIVITY_PLAN", "ACTIVITIES"),
    "content": ("MEDIA_SELECTIONS", "MATERIALS"),
    "implementation": ("IMPLEMENTATION",),
}


def rules_for(state: str) -> str:
    """The generation rules for one stage: the ``RULES_*`` blocks of every
    artifact family that stage covers, merged in order and deduplicated."""
    seen: list[str] = []
    for family in _STATE_FAMILIES[state]:
        text = globals()[f"RULES_{family}"].strip()
        if text and text not in seen:
            seen.append(text)
    return "\n\n".join(seen)
