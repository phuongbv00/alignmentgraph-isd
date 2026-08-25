"""Step definitions for the agentic arm: 7 artifact-family steps, each run as
a tool loop by ``core/agentic/loop.py``.

EXPERIMENTAL ARM. Granularity mirrors ``SingleDesignerAgent.STATES`` (one step
per artifact family, plan and execution together) because the tool loop
subsumes the multi arm's plan/execute hop split: how much context to gather
and when the artifact is ready are the agent's own decisions inside the loop,
not separate scripted calls. Personas stay specialist (one per family) — this
arm varies CONTROL (scripted pipeline vs. act-observe loop), not the
decomposition axis.

Schemas and rules come from the shared rulebook (``core/rulebook.py``); the
three merged schemas (assessment, activities, content) and the per-step commit
bodies are copied from ``core/agents/single_designer.py`` — experimental arm,
keep in sync manually. Commits call only the shared establishers
(``alignment.record_provenance``/``match_*``/``establish_delivery``), so the
graph an agentic run ships is shaped exactly like the classic arms'.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .. import rulebook as rules
from ..alignment_graph import NodeType, alignment
from ..validation import validate_section

# ── merged schemas (copied from core/agents/single_designer.py) ─────────────

_SCHEMA_ASSESSMENT_MERGED = """\
{
  "assessment_plan": {
    "diagnostic": ["<intent>"], "formative": ["<intent>"], "summative": ["<intent>"],
    "lo_coverage_targets": {"ILO-01": ["diagnostic", "summative"]},
    "expected_evidence": {"ILO-01": "<what would demonstrate mastery>"},
    "formative_methods": ["<instrument + cadence>"],
    "pilot_data_plan": {
      "collection_points": ["<when during the pilot data is captured>"],
      "anticipated_difficulties": [
        {"area": "<objective or module learners will struggle with>", "rationale": "<why, for THESE learners>",
         "detected_by": "<which formative method surfaces it>", "first_revision": "<the concrete fix>"}
      ]
    }
  },
  "assessment_tools": [
    {"item_id": "AT-01", "type": "performance_task", "question": "<question>", "aligned_objective": "ILO-01",
     "plan_category": "summative", "required_cognitive_process": "apply", "scoring_criteria": "<criteria>"}
  ],
  "expert_review": {
    "reviewers": ["<SME reviewer>", "<instructional designer reviewer>"],
    "review_criteria": ["<criterion1>", "<criterion2>", "<criterion3>"],
    "feedback_summary": "<summary of expected feedback and validation>"
  }
}"""

_SCHEMA_ACTIVITIES_MERGED = """\
{
  "instructional_strategies": {
    "model": "Gagné's 9 Events",
    "sequence": [{"event": "<one of the 9 events>", "activity": "<activity>", "duration": "<time>",
                  "resources": ["<resource>"]}],
    "methods": ["<m1>", "<m2>"],
    "rationale": "<why this approach for these learners>"
  },
  "non_instructional_strategies": {
    "motivation_strategies": ["<m1>"], "self_directed_learning": ["<s1>"], "support_strategies": ["<s1>"]
  },
  "learning_activities": [
    {"id": "TLA-01", "activity_name": "<name>", "duration": "<time>", "description": "<what learners do>",
     "materials_needed": "<free text: what content this needs>", "aligned_objectives": ["ILO-01"],
     "prepares_for_assessment": ["AT-01"], "learner_cognitive_process": "apply",
     "prerequisite_activities": []}
  ]
}"""

_SCHEMA_CONTENT_MERGED = """\
{
  "content_modules": [
    {"id": "MOD-01", "title": "<title>", "description": "<what it covers>",
     "supports_activities": ["TLA-01"], "covers_topics": ["TOP-01"]}
  ],
  "media_selections": [
    {"id": "MED-01", "media_type": "video", "purpose": "<purpose>", "rationale": "<why this form>",
     "respects_constraints": ["CON-01"]}
  ],
  "learner_materials": [
    {"id": "MAT-01", "title": "<title>", "type": "video", "format": "mp4",
     "content": "<what the material actually contains>", "linked_module": "MOD-01"}
  ]
}"""


# ── shared commit helpers (copied from core/agents/base.py + single_designer.py) ──

def _decompose(graph, node_type: str, items: object, *, id_field: str = "id") -> list[str]:
    """Copied from ``BaseISDAgent._decompose_elements`` — keep in sync manually."""
    node_ids: list[str] = []
    if not isinstance(items, list):
        return node_ids
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_id = item.get(id_field)
        if not raw_id:
            continue
        node_ids.append(graph.add_element_node(node_type, str(raw_id), dict(item)))
    return node_ids


def _store_narrative(graph, node_type: str, section: dict, element_key: str) -> None:
    """Copied from ``SingleDesignerAgent._store_narrative`` — keep in sync manually."""
    if not isinstance(section, dict):
        return
    narrative = {k: v for k, v in section.items() if k != element_key}
    if narrative:
        graph.add_node(node_type, graph.section_id(node_type), narrative)
        graph.link_section_narrative(node_type)


# ── per-step commits (copied from SingleDesignerAgent._commit_* ) ───────────
# Signature: (graph, trajectory, parsed) -> None. Keep in sync manually.

def commit_analysis(graph, trajectory, parsed: dict) -> None:
    needs = parsed.get("needs_analysis") or {}
    gap_ids = _decompose(graph, NodeType.GAP, needs.get("gaps"))
    _store_narrative(graph, NodeType.GAP, needs, "gaps")

    task = parsed.get("task_analysis") or {}
    _decompose(graph, NodeType.TOPIC, task.get("topics"))
    _store_narrative(graph, NodeType.TOPIC, task, "topics")

    context = parsed.get("context_analysis") or {}
    _decompose(graph, NodeType.CONSTRAINT, context.get("constraints"))
    _store_narrative(graph, NodeType.CONSTRAINT, context, "constraints")

    learner = parsed.get("learner_analysis") or {}
    if learner:
        graph.add_node(NodeType.LEARNER_PROFILE, graph.section_id(NodeType.LEARNER_PROFILE), learner)

    improvement = parsed.get("improvement_plan") or {}
    _decompose(graph, NodeType.IMPROVEMENT, improvement.get("improvements"))
    _store_narrative(graph, NodeType.IMPROVEMENT, improvement, "improvements")
    gap_by_id = {n["data"].get("id"): n["id"] for n in graph.element_nodes(NodeType.GAP)}
    for item in improvement.get("improvements") or []:
        if not isinstance(item, dict):
            continue
        source = gap_by_id.get(item.get("addresses_gap"))
        if source:
            alignment.record_provenance(
                graph, "P9", [source],
                f"{NodeType.IMPROVEMENT}{graph.ELEMENT_SEP}{item.get('id')}")
    for node_id in gap_ids:
        trajectory.log_node_edit("add", node_id, NodeType.GAP)


def commit_outcomes(graph, trajectory, parsed: dict) -> None:
    goal_id = graph.section_id(NodeType.COURSE_GOAL)
    graph.add_node(NodeType.COURSE_GOAL, goal_id, parsed.get("course_goal") or {})

    objectives = parsed.get("learning_objectives") or []
    objective_ids = _decompose(graph, NodeType.OBJECTIVE, objectives)
    gap_ids = [n["id"] for n in graph.element_nodes(NodeType.GAP)]
    topic_ids = [n["id"] for n in graph.element_nodes(NodeType.TOPIC)]
    learner_id = graph.section_id(NodeType.LEARNER_PROFILE)
    for node_id in objective_ids:
        trajectory.log_node_edit("add", node_id, NodeType.OBJECTIVE)
        alignment.record_provenance(graph, "C1", [goal_id], node_id)
        if gap_ids or topic_ids:
            alignment.record_provenance(graph, "P1", gap_ids + topic_ids, node_id)
        if graph.get_node(learner_id):
            alignment.record_provenance(graph, "P2", [learner_id], node_id)


def commit_assessment(graph, trajectory, parsed: dict) -> None:
    plan = parsed.get("assessment_plan") or {}
    graph.add_node(NodeType.ASSESSMENT_PLAN, graph.section_id(NodeType.ASSESSMENT_PLAN), plan)
    tools = parsed.get("assessment_tools") or []
    for node_id in _decompose(graph, NodeType.ASSESSMENT, tools, id_field="item_id"):
        trajectory.log_node_edit("add", node_id, NodeType.ASSESSMENT)
    alignment.match_id_reverse(graph, "C2", field="aligned_objective")
    alignment.match_p3_realizes(graph)


def commit_activities(graph, trajectory, parsed: dict) -> None:
    plan_id = graph.section_id(NodeType.ACTIVITY_PLAN)
    graph.add_node(NodeType.ACTIVITY_PLAN, plan_id, {
        "instructional_strategies": parsed.get("instructional_strategies") or {},
        "non_instructional_strategies": parsed.get("non_instructional_strategies") or {},
    })
    activities = parsed.get("learning_activities") or []
    activity_ids = _decompose(graph, NodeType.ACTIVITY, activities)
    for node_id in activity_ids:
        trajectory.log_node_edit("add", node_id, NodeType.ACTIVITY)
    alignment.match_list_reverse(graph, "C3", field="aligned_objectives")
    alignment.match_list(graph, "C4", field="prepares_for_assessment")
    for node_id in activity_ids:
        alignment.record_provenance(graph, "P4", [plan_id], node_id)
    for activity in activities:
        if not isinstance(activity, dict):
            continue
        target = f"{NodeType.ACTIVITY}{graph.ELEMENT_SEP}{activity.get('id')}"
        for prior in activity.get("prerequisite_activities") or []:
            source = f"{NodeType.ACTIVITY}{graph.ELEMENT_SEP}{prior}"
            if graph.get_node(source) and graph.get_node(target):
                graph.add_edge("precedes", source, target, relation_id="",
                               established_by="id", evidence=str(prior))


def commit_content(graph, trajectory, parsed: dict) -> None:
    module_ids = _decompose(graph, NodeType.CONTENT, parsed.get("content_modules"))
    media_ids = _decompose(graph, NodeType.MEDIA_SELECTION, parsed.get("media_selections"))
    for node_id in module_ids:
        trajectory.log_node_edit("add", node_id, NodeType.CONTENT)
        data = graph.get_node(node_id)["data"]
        for ref in data.get("supports_activities") or []:
            alignment.record_provenance(
                graph, "C5", [node_id],
                f"{NodeType.ACTIVITY}{graph.ELEMENT_SEP}{ref}")
        topics = [f"{NodeType.TOPIC}{graph.ELEMENT_SEP}{r}"
                  for r in data.get("covers_topics") or []]
        alignment.record_provenance(graph, "P7", topics, node_id)
    for node_id in media_ids:
        data = graph.get_node(node_id)["data"]
        constraints = [f"{NodeType.CONSTRAINT}{graph.ELEMENT_SEP}{r}"
                       for r in data.get("respects_constraints") or []]
        alignment.record_provenance(graph, "P8", constraints, node_id)

    material_ids = _decompose(graph, NodeType.MATERIAL, parsed.get("learner_materials"))
    for node_id in material_ids:
        trajectory.log_node_edit("add", node_id, NodeType.MATERIAL)
        ref = str(graph.get_node(node_id)["data"].get("linked_module", "") or "")
        module_id = f"{NodeType.CONTENT}{graph.ELEMENT_SEP}{ref}" if ref else ""
        if ref and graph.get_node(module_id):
            alignment.record_provenance(graph, "P5", [module_id], node_id)
    alignment.match_p6_realizes(graph)


def commit_rubrics(graph, trajectory, parsed: dict) -> None:
    for node_id in _decompose(graph, NodeType.RUBRIC, parsed.get("rubric_criteria")):
        trajectory.log_node_edit("add", node_id, NodeType.RUBRIC)
        ref = str(graph.get_node(node_id)["data"].get("aligned_assessment", "") or "")
        item_id = f"{NodeType.ASSESSMENT}{graph.ELEMENT_SEP}{ref}" if ref else ""
        if ref and graph.get_node(item_id):
            alignment.record_provenance(graph, "C6", [item_id], node_id)
    alignment.match_id(graph, "C7", field="aligned_objective")


def commit_implementation(graph, trajectory, parsed: dict) -> None:
    node_id = graph.section_id(NodeType.IMPLEMENTATION_PLAN)
    graph.add_node(NodeType.IMPLEMENTATION_PLAN, node_id, parsed)
    trajectory.log_node_edit("add", node_id, NodeType.IMPLEMENTATION_PLAN)
    alignment.establish_delivery(graph, node_id, parsed)


# ── deterministic submit validation per step ────────────────────────────────
# Errors here are returned to the model as an observation (a rejected submit),
# so they must be actionable sentences, not exception dumps.

def _require_list(parsed: dict, path: tuple[str, ...], errors: list[str]) -> None:
    value: object = parsed
    for key in path:
        value = (value or {}).get(key) if isinstance(value, dict) else None
    if not isinstance(value, list) or not value:
        errors.append(f"{'.'.join(path)} must be a non-empty list")


def validate_analysis(parsed: dict) -> list[str]:
    errors: list[str] = []
    _require_list(parsed, ("needs_analysis", "gaps"), errors)
    # improvement_plan.improvements feeds P9 provenance AND is the sole source
    # the aggregator builds evaluation.improvement_plan from — a submit that
    # drops it (measured: a 2B model trimmed it away after a truncation
    # rejection) zeroes the program-improvement rubric item outright.
    _require_list(parsed, ("improvement_plan", "improvements"), errors)
    for key in ("learner_analysis", "context_analysis", "task_analysis"):
        if not isinstance(parsed.get(key), dict) or not parsed.get(key):
            errors.append(f"{key} must be a non-empty object")
    return errors


def validate_outcomes(parsed: dict) -> list[str]:
    errors = validate_section("objective", {
        "learning_objectives": parsed.get("learning_objectives"),
    })
    if not str(((parsed.get("course_goal") or {}) if isinstance(parsed.get("course_goal"), dict)
                else {}).get("statement") or "").strip():
        errors.append("course_goal.statement must be a non-empty string")
    return errors


def validate_assessment(parsed: dict) -> list[str]:
    errors = validate_section("assessment_plan", parsed.get("assessment_plan") or {})
    errors += validate_section("assessment", {
        "assessment_tools": parsed.get("assessment_tools"),
        "expert_review": parsed.get("expert_review") or {},
    })
    # pilot_data_plan feeds the whole formative half of ADDIE Evaluation (the
    # aggregator surfaces it as evaluation.formative); a submit without it
    # zeroes two rubric items (measured on a 2B run). The shared
    # evaluation_quality check + repair are the net; this asks the model
    # itself first.
    _require_list(parsed, ("assessment_plan", "pilot_data_plan", "anticipated_difficulties"), errors)
    return errors


def validate_activities(parsed: dict) -> list[str]:
    errors = validate_section("activity_plan", {
        "instructional_strategies": parsed.get("instructional_strategies") or {},
    })
    errors += validate_section("activity", {
        "learning_activities": parsed.get("learning_activities"),
    })
    return errors


def validate_content(parsed: dict) -> list[str]:
    errors: list[str] = []
    _require_list(parsed, ("content_modules",), errors)
    _require_list(parsed, ("learner_materials",), errors)
    return errors


def validate_rubrics(parsed: dict) -> list[str]:
    errors: list[str] = []
    _require_list(parsed, ("rubric_criteria",), errors)
    return errors


def validate_implementation(parsed: dict) -> list[str]:
    # instructor_guide / operator_manual are required in the shared section
    # schema (two rubric items score them directly), so the shared validator
    # already rejects a submit that ships a Development hole.
    return validate_section("implementation_plan", parsed or {})


# ── the step table ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AgenticStep:
    """One artifact-family step run as a tool loop."""

    name: str                     #: state name ("analysis", "outcomes", ...)
    identity: str                 #: trajectory agent identity
    family: str                   #: key into repairs.OWNED_BY_FAMILY / _collect_violations
    persona: str                  #: specialist persona sentence(s)
    intro: str                    #: one-line task framing
    schema: str                   #: the exact JSON schema asked for
    rules: str                    #: rulebook rules text
    primary_type: str | None      #: element type whose pool proves the step produced
    readable_types: tuple[str, ...] = ()   #: node types read_nodes/read_node may serve
    relations: tuple[str, ...] = ()        #: relation ids read_edges/coverage_gaps may serve
    docket: dict = field(default_factory=dict)  #: alignment_docket kwargs (scope per state,
                                                #: mirrors SingleDesignerAgent._STATE_ALIGNMENT_SCOPE)
    validate: Callable[[dict], list[str]] = lambda parsed: []
    commit: Callable[[object, object, dict], None] = lambda graph, trajectory, parsed: None

    def task_block(self) -> str:
        """Task + schema + rules for the tool-loop prompt. Deliberately does
        NOT end with the rulebook's JSON_ONLY line: that instruction tells the
        model to output the artifact directly, which contradicts the action
        protocol and (measured on a 2B model) suppresses every tool call. The
        loop's protocol block already pins the output contract; the fallback
        single-shot re-adds JSON_ONLY via :meth:`fallback_block`."""
        return (f"{self.intro}\n\nThe artifact you will submit must follow this EXACT schema:\n"
                f"{self.schema}\n\n{self.rules}")

    def fallback_block(self) -> str:
        """The scripted single-shot composition (no tool protocol) — here the
        rulebook's JSON_ONLY closing line is correct again."""
        return (f"{self.intro}\n\nProduce ONLY valid JSON with this EXACT schema:\n"
                f"{self.schema}\n\n{self.rules}\n{rules.JSON_ONLY}")


STEPS: tuple[AgenticStep, ...] = (
    AgenticStep(
        name="analysis",
        identity="AgenticOutcomeDesigner",
        family="outcome_designer",
        persona="You are an expert instructional designer performing the Analysis phase of ADDIE.",
        intro=("Analyse the situation: the performance gaps, who the learners are, what constrains "
               "delivery, what has to be taught, and what you would improve."),
        schema=rules.SCHEMA_ANALYSIS,
        rules=rules.RULES_ANALYSIS,
        primary_type=NodeType.GAP,
        validate=validate_analysis,
        commit=commit_analysis,
    ),
    AgenticStep(
        name="outcomes",
        identity="AgenticOutcomeDesigner",
        family="outcome_designer",
        persona=("You are an expert instructional designer working on the Design phase of ADDIE, "
                 "responsible for the course goal and learning objectives."),
        intro=("State what this course is for and what learners will be able to do, grounded in "
               "the analysis already in the design graph."),
        schema=rules.SCHEMA_OUTCOMES,
        rules=rules.RULES_OUTCOMES,
        primary_type=NodeType.OBJECTIVE,
        readable_types=(NodeType.GAP, NodeType.TOPIC, NodeType.LEARNER_PROFILE, NodeType.CONSTRAINT),
        validate=validate_outcomes,
        commit=commit_outcomes,
    ),
    AgenticStep(
        name="assessment",
        identity="AgenticAssessmentDesigner",
        family="assessment_designer",
        persona=("You are an expert assessment designer, responsible for how mastery of each "
                 "learning objective will be evidenced and measured."),
        intro=("Decide how you will know learners met each objective AND write the actual items — "
               "the strategy and the items together, in one object."),
        schema=_SCHEMA_ASSESSMENT_MERGED,
        rules=rules.rules_for("assessment"),
        primary_type=NodeType.ASSESSMENT,
        readable_types=(NodeType.OBJECTIVE,),
        relations=("C2",),
        docket={"edges": ("C2",), "gaps": ("C2",), "plan_pairs": True},
        validate=validate_assessment,
        commit=commit_assessment,
    ),
    AgenticStep(
        name="activities",
        identity="AgenticActivityDesigner",
        family="activity_designer",
        persona=("You are an expert learning-activity designer, responsible for how learners "
                 "spend their time practising toward the objectives."),
        intro=("Design how learners spend their time: the instructional approach and the concrete "
               "activities that realise it, in one object."),
        schema=_SCHEMA_ACTIVITIES_MERGED,
        rules=rules.rules_for("activities"),
        primary_type=NodeType.ACTIVITY,
        readable_types=(NodeType.OBJECTIVE, NodeType.ASSESSMENT),
        relations=("C2", "C3", "C4"),
        docket={"edges": ("C2",), "gaps": ("C3", "C4")},
        validate=validate_activities,
        commit=commit_activities,
    ),
    AgenticStep(
        name="content",
        identity="AgenticContentDesigner",
        family="content_designer",
        persona=("You are an expert content designer, responsible for the modules, media and "
                 "materials the activities need."),
        intro=("Produce the content learners work with: how it is organised, what form it takes, "
               "and the actual materials — in one object."),
        schema=_SCHEMA_CONTENT_MERGED,
        rules=rules.rules_for("content"),
        primary_type=NodeType.MATERIAL,
        readable_types=(NodeType.ACTIVITY, NodeType.TOPIC, NodeType.CONSTRAINT),
        relations=("C5",),
        docket={"gaps": ("C5",)},
        validate=validate_content,
        commit=commit_content,
    ),
    AgenticStep(
        name="rubrics",
        identity="AgenticRubricDesigner",
        family="rubric_designer",
        persona=("You are an expert rubric designer, responsible for the scoring criteria of "
                 "every assessment item."),
        intro="Write the scoring criteria for the assessment items already in the design graph.",
        schema=rules.SCHEMA_RUBRICS,
        rules=rules.rules_for("rubrics"),
        primary_type=NodeType.RUBRIC,
        readable_types=(NodeType.OBJECTIVE, NodeType.ASSESSMENT),
        relations=("C2", "C6", "C7"),
        docket={"edges": ("C2",), "gaps": ("C6", "C7")},
        validate=validate_rubrics,
        commit=commit_rubrics,
    ),
    AgenticStep(
        name="implementation",
        identity="AgenticImplementationPlanner",
        family="implementation_planner",
        persona=("You are an expert implementation planner, responsible for how this design is "
                 "actually delivered by instructors and operators."),
        intro=("Plan how this design is actually delivered: what instructors and operators need, "
               "and which activities and materials each session carries."),
        schema=rules.SCHEMA_IMPLEMENTATION,
        rules=rules.RULES_IMPLEMENTATION,
        primary_type=None,  # section-only artifact — done-check on required fields
        readable_types=(NodeType.ACTIVITY, NodeType.MATERIAL),
        relations=("P10", "P11"),
        docket={"gaps": ("P10", "P11")},
        validate=validate_implementation,
        commit=commit_implementation,
    ),
)


def step_done(step: AgenticStep, graph) -> bool:
    """Idempotence/produced guard — mirrors ``SingleDesignerAgent._already_done``
    and ``NodeFactory._produced`` (graph mode)."""
    if step.primary_type is None:
        from ..workflow import _empty_required_fields

        node = graph.get_node(graph.section_id(NodeType.IMPLEMENTATION_PLAN))
        data = (node or {}).get("data") or {}
        return bool(data) and not _empty_required_fields(NodeType.IMPLEMENTATION_PLAN, data)
    return bool(graph.element_nodes(step.primary_type))
