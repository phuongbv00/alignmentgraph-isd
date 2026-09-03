"""Step definitions: 6 artifact-family steps, each run as
a tool loop by ``core/agentic/loop.py``.

Granularity is one step per artifact family, plan and execution together,
because the tool loop
subsumes the multi arm's plan/execute hop split: how much context to gather
and when the artifact is ready are the agent's own decisions inside the loop,
not separate pre-scripted calls. Personas stay specialist (one per family):
what the ``agent_mode`` axis varies is the CONTEXT BOUNDARY, not the roles.

Schemas and rules come from the shared rulebook (``core/rulebook.py``); the
per-step commit bodies were copied from the retired scripted single-designer
arm. Commits call only the shared establishers
(``alignment.record_provenance``/``match_*``/``establish_delivery``), so the
graph an agentic run ships is shaped exactly like the classic arms'.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .. import rulebook as rules
from ..alignment_graph import NodeType, alignment
from ..validation import validate_section

# ── merged schemas (copied from the retired scripted arm) ─────────────

_SCHEMA_ASSESSMENT_DISPATCH = (
    rules.SCHEMA_ASSESSMENT_PLAN.rstrip().rstrip("}").rstrip().rstrip(",")
    + ',\n  "dev_plan": ' + rules.SCHEMA_ASSESSMENT_DEV_PLAN.replace("\n", "\n  ") + "\n}")

_SCHEMA_ACTIVITIES_DISPATCH = (
    rules.SCHEMA_ACTIVITY_PLAN.rstrip().rstrip("}").rstrip().rstrip(",")
    + ',\n  "dev_plan": ' + rules.SCHEMA_ACTIVITY_DEV_PLAN.replace("\n", "\n  ") + "\n}")

# From the rulebook, like the two above — not a hand-written copy. The copy had
# DRIFTED: it omitted ``for_modules`` from the media example while
# ``RULES_CONTENT_MODULES`` (shown in the same prompt) requires it, so the model
# was told to set a field the example never showed. That field is read by
# ``dev_plans.material_work_units``: a media selection without it attaches to
# EVERY module unit, so three modules x three media went out as nine
# media-slots instead of three, and each Developer was asked for three times the
# materials it should write.
_SCHEMA_CONTENT_DISPATCH = rules.SCHEMA_CONTENT_MODULES

def _decompose(graph, trajectory, node_type: str, items: object, *,
               id_field: str = "id") -> list[str]:
    """Turn a just-generated list into element nodes AND log each one.

    The logging is IN here rather than at the call sites for a reason:
    ``node_edit`` events are judge-visible, so a call site that forgets one
    makes whichever arm reaches it look like it did less work — a difference
    the ablation would then read as an axis effect."""
    node_ids: list[str] = []
    if not isinstance(items, list):
        return node_ids
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_id = item.get(id_field)
        if not raw_id:
            continue
        node_id = graph.add_element_node(node_type, str(raw_id), dict(item))
        node_ids.append(node_id)
        trajectory.log_node_edit("add", node_id, node_type)
    return node_ids


def _store_narrative(graph, trajectory, node_type: str, section: dict,
                     element_key: str) -> None:
    """Deposit a narrative section node, with the ``log_node_edit`` every
    section write carries (judge-visible; see ``_decompose``)."""
    if not isinstance(section, dict):
        return
    narrative = {k: v for k, v in section.items() if k != element_key}
    if narrative:
        section_id = graph.section_id(node_type)
        graph.add_node(node_type, section_id, narrative)
        trajectory.log_node_edit("add", section_id, node_type)
        graph.link_section_narrative(node_type)


# ── per-step commits ───────────────────────────────────────────────────────
# Signature: (graph, trajectory, parsed) -> None.

def _merge_section(graph, trajectory, node_type, updates: dict) -> str:
    """Write section fields WITHOUT dropping the ones already there.

    Each artifact of a stage now arrives in its own submit call
    (``tools.submit_specs``), so a stage's section node is built up over
    several commits. ``AlignmentGraph.add_node`` REPLACES a node's data, which
    was right when one submit carried the whole section and silently loses
    work now: ``submit_dev_plan`` after ``submit_assessment_plan`` would leave
    the section holding only the dev plan. Same class of bug as the one
    ``commit_analysis_prose`` already carries a note about.
    """
    node_id = graph.section_id(node_type)
    existing = (graph.get_node(node_id) or {}).get("data") or {}
    graph.add_node(node_type, node_id, {**existing, **updates})
    trajectory.log_node_edit("add" if not existing else "update", node_id, node_type)
    return node_id


def _merge_document(store, trajectory, key: str, updates: dict) -> None:
    """Prose counterpart of :func:`_merge_section`."""
    existing = store.get(key) or {}
    _put(store, trajectory, key, {**existing, **updates})


def commit_analysis(graph, trajectory, parsed: dict) -> None:
    needs = parsed.get("needs_analysis") or {}
    _decompose(graph, trajectory, NodeType.GAP, needs.get("gaps"))
    _store_narrative(graph, trajectory, NodeType.GAP, needs, "gaps")

    task = parsed.get("task_analysis") or {}
    _decompose(graph, trajectory, NodeType.TOPIC, task.get("topics"))
    _store_narrative(graph, trajectory, NodeType.TOPIC, task, "topics")

    context = parsed.get("context_analysis") or {}
    _decompose(graph, trajectory, NodeType.CONSTRAINT, context.get("constraints"))
    _store_narrative(graph, trajectory, NodeType.CONSTRAINT, context, "constraints")

    learner = parsed.get("learner_analysis") or {}
    if learner:
        graph.add_node(NodeType.LEARNER_PROFILE, graph.section_id(NodeType.LEARNER_PROFILE), learner)

    improvement = parsed.get("improvement_plan") or {}
    _decompose(graph, trajectory, NodeType.IMPROVEMENT, improvement.get("improvements"))
    _store_narrative(graph, trajectory, NodeType.IMPROVEMENT, improvement, "improvements")
    gap_by_id = {n["data"].get("id"): n["id"] for n in graph.element_nodes(NodeType.GAP)}
    for item in improvement.get("improvements") or []:
        if not isinstance(item, dict):
            continue
        source = gap_by_id.get(item.get("addresses_gap"))
        if source:
            alignment.record_provenance(
                graph, "P9", [source],
                f"{NodeType.IMPROVEMENT}{graph.ELEMENT_SEP}{item.get('id')}")


def commit_outcomes(graph, trajectory, parsed: dict) -> None:
    goal_id = graph.section_id(NodeType.COURSE_GOAL)
    if isinstance(parsed.get("course_goal"), dict) and parsed["course_goal"]:
        _merge_section(graph, trajectory, NodeType.COURSE_GOAL, parsed["course_goal"])

    objectives = parsed.get("learning_objectives") or []
    objective_ids = _decompose(graph, trajectory, NodeType.OBJECTIVE, objectives)
    gap_ids = [n["id"] for n in graph.element_nodes(NodeType.GAP)]
    topic_ids = [n["id"] for n in graph.element_nodes(NodeType.TOPIC)]
    learner_id = graph.section_id(NodeType.LEARNER_PROFILE)
    for node_id in objective_ids:
        alignment.record_provenance(graph, "C1", [goal_id], node_id)
        if gap_ids or topic_ids:
            alignment.record_provenance(graph, "P1", gap_ids + topic_ids, node_id)
        if graph.get_node(learner_id):
            alignment.record_provenance(graph, "P2", [learner_id], node_id)


def _without_dev_plan(plan: object) -> dict:
    """The assessment plan as the deliverable defines it.

    ``dev_plan`` is a SIBLING of ``assessment_plan`` in the submit schema, but
    a model that sees both in one object nests a copy inside the plan as well
    (observed on a 2B run: the same ``instrument_sets`` at both levels). Left
    alone it is committed into the plan node and reaches the judged output —
    orchestration metadata inside a scored artifact, which ``dev_plans``'s own
    contract forbids. Dropped here rather than validated away: the top-level
    copy is the one the fan-out reads, so the nested one costs nothing to lose.
    """
    return {k: v for k, v in (plan or {}).items() if k != "dev_plan"} if isinstance(plan, dict) else {}


def commit_assessment(graph, trajectory, parsed: dict) -> None:
    """Dispatch commit: the PLAN and the DEV PLAN. The items are produced one
    work set at a time by the Developer tier (see ``fanout.py``) — a single
    submit cannot carry a whole family's item list under the 8192 completion
    cap.

    The dev plan is STORED (2026-09-03). It used to be stripped here and never
    written anywhere, while ``_dispatch_payload`` reads the fan-out's input
    back out of the graph — so ``normalize_assessment_dev_plan`` was handed
    ``None`` on every run and the deterministic fallback always ran. Measured
    on the test fixture: assessment and activities both reported
    ``source=fallback`` every time, meaning the planning the agent was asked
    for, and the ``expected_activities`` field added to its rules, reached
    nothing. It is kept on the plan section and stripped at AGGREGATION
    instead (``aggregate._merge_node_data``), so the graph and its dump hold
    the plan the agent actually made while the ADDIE output does not.
    """
    updates: dict = {}
    plan = parsed.get("assessment_plan")
    if isinstance(plan, dict):
        updates.update(_without_dev_plan(plan))
        if isinstance(plan.get("dev_plan"), dict):
            updates["dev_plan"] = plan["dev_plan"]
    if isinstance(parsed.get("dev_plan"), dict):
        updates["dev_plan"] = parsed["dev_plan"]
    if updates:
        _merge_section(graph, trajectory, NodeType.ASSESSMENT_PLAN, updates)


def commit_activities(graph, trajectory, parsed: dict) -> None:
    updates = {key: parsed[key] for key in
               ("instructional_strategies", "non_instructional_strategies", "dev_plan")
               if isinstance(parsed.get(key), dict) and parsed[key]}
    if updates:
        _merge_section(graph, trajectory, NodeType.ACTIVITY_PLAN, updates)


def commit_content(graph, trajectory, parsed: dict) -> None:
    module_ids = _decompose(graph, trajectory, NodeType.CONTENT, parsed.get("content_modules"))
    media_ids = _decompose(graph, trajectory, NodeType.MEDIA_SELECTION, parsed.get("media_selections"))
    for node_id in module_ids:
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




def commit_implementation(graph, trajectory, parsed: dict) -> None:
    node_id = _merge_section(graph, trajectory, NodeType.IMPLEMENTATION_PLAN,
                             {k: v for k, v in (parsed or {}).items() if v})
    alignment.establish_delivery(
        graph, node_id, (graph.get_node(node_id) or {}).get("data") or {})


def _put(store, trajectory, key: str, document: dict) -> None:
    """Write one blackboard document AND record it. Logging lives here rather
    than at each call site for the same reason ``_decompose`` logs: a call site
    that forgets makes whichever arm reaches it look like it did less work,
    which the ablation would then read as an axis effect."""
    store.put(key, document)
    trajectory.log_doc_write(key, document)


# ── prose-arm commits ───────────────────────────────────────────────────────
# The graph-free counterpart of the commits above: one ``store.put`` per
# document the graph arm would have decomposed into element nodes. Both
# decomposition arms write the same document keys and the same list fields, so
# a prose blackboard is identical either way — no id index, no edges, no
# derived facts, because their absence IS the ``context_mode`` treatment.


def commit_analysis_prose(store, trajectory, parsed: dict) -> None:
    """ADDITIVE at the top level, because analysis arrives in parts.

    ``ProseStore.put`` overwrites, which is right for a step that submits its
    artifact whole and wrong here: a second submit carrying only
    ``task_analysis`` would drop the ``needs_analysis`` the first one wrote.
    The graph arm never had this problem — ``commit_analysis`` writes each
    section independently — so leaving it would have made the prose arm lose
    work the graph arm keeps, on the axis that compares them.
    """
    if not parsed:
        return
    existing = store.get("analysis") or {}
    merged = {**existing, **{k: v for k, v in parsed.items() if v}}
    _put(store, trajectory, "analysis", merged)


def commit_outcomes_prose(store, trajectory, parsed: dict) -> None:
    _merge_document(store, trajectory, "objective",
                    {k: v for k, v in (parsed or {}).items() if v})


def commit_assessment_prose(store, trajectory, parsed: dict) -> None:
    updates: dict = {}
    plan = parsed.get("assessment_plan")
    if isinstance(plan, dict):
        updates.update(_without_dev_plan(plan))
        if isinstance(plan.get("dev_plan"), dict):
            updates["dev_plan"] = plan["dev_plan"]
    if isinstance(parsed.get("dev_plan"), dict):
        updates["dev_plan"] = parsed["dev_plan"]
    if updates:
        _merge_document(store, trajectory, "assessment_plan", updates)


def commit_activities_prose(store, trajectory, parsed: dict) -> None:
    updates = {key: parsed[key] for key in
               ("instructional_strategies", "non_instructional_strategies", "dev_plan")
               if isinstance(parsed.get(key), dict) and parsed[key]}
    if updates:
        _merge_document(store, trajectory, "activity_plan", updates)


def commit_content_prose(store, trajectory, parsed: dict) -> None:
    updates = {key: parsed[key] for key in ("content_modules", "media_selections")
               if isinstance(parsed.get(key), list) and parsed[key]}
    if updates:
        _merge_document(store, trajectory, "content", updates)


def commit_implementation_prose(store, trajectory, parsed: dict) -> None:
    _merge_document(store, trajectory, "implementation_plan",
                    {k: v for k, v in (parsed or {}).items() if v})


# ── what has landed, per step ───────────────────────────────────────────────
# The read half of the commits above, keyed the way `submit_fields` names each
# artifact. `missing_parts` asks these, so a stage stops when every REQUIRED
# artifact has arrived rather than after the first submit — which is what one
# submit tool per artifact would otherwise mean.

#: Where each analysis part LANDS. Analysis is the one stage whose artifacts
#: are decomposed into several node types rather than one section, so its view
#: needs the map; every other stage reads its own section or element pool.
_ANALYSIS_PART_NODE = {
    "needs_analysis": NodeType.GAP,
    "learner_analysis": NodeType.LEARNER_PROFILE,
    "context_analysis": NodeType.CONSTRAINT,
    "task_analysis": NodeType.TOPIC,
    "improvement_plan": NodeType.IMPROVEMENT,
}


def _section(graph, node_type) -> dict:
    node = graph.get_node(graph.section_id(node_type))
    return (node or {}).get("data") or {}


def view_analysis(graph) -> dict:
    return {part: bool(_section(graph, node_type) or graph.element_nodes(node_type))
            for part, node_type in _ANALYSIS_PART_NODE.items()}


def view_analysis_prose(store) -> dict:
    return store.get("analysis") or {}


def view_outcomes(graph) -> dict:
    return {"course_goal": _section(graph, NodeType.COURSE_GOAL),
            "learning_objectives": graph.element_nodes(NodeType.OBJECTIVE)}


def view_outcomes_prose(store) -> dict:
    return store.get("objective") or {}


def view_assessment(graph) -> dict:
    plan = _section(graph, NodeType.ASSESSMENT_PLAN)
    return {"assessment_plan": _without_dev_plan(plan), "dev_plan": plan.get("dev_plan")}


def view_assessment_prose(store) -> dict:
    plan = store.get("assessment_plan") or {}
    return {"assessment_plan": _without_dev_plan(plan), "dev_plan": plan.get("dev_plan")}


def view_activities(graph) -> dict:
    return dict(_section(graph, NodeType.ACTIVITY_PLAN))


def view_activities_prose(store) -> dict:
    return store.get("activity_plan") or {}


def view_content(graph) -> dict:
    return {"content_modules": graph.element_nodes(NodeType.CONTENT),
            "media_selections": graph.element_nodes(NodeType.MEDIA_SELECTION)}


def view_content_prose(store) -> dict:
    return store.get("content") or {}


def view_implementation(graph) -> dict:
    return dict(_section(graph, NodeType.IMPLEMENTATION_PLAN))


def view_implementation_prose(store) -> dict:
    return store.get("implementation_plan") or {}


# ── deterministic submit validation per step ────────────────────────────────
# Errors here are returned to the model as an observation (a rejected submit),
# so they must be actionable sentences, not exception dumps.

def _nothing_arrived(parsed: dict, keys: tuple[str, ...]) -> list[str]:
    """A submit carrying none of this stage's artifacts is an error.

    Every validator judges only what ARRIVED, because each artifact has its own
    submit tool and demanding the whole stage would reject each correct
    instalment in turn. That tolerance has to stop at empty: without this,
    ``validate({})`` returns no errors, and ``unwrap_section`` — which decides
    a payload is already unwrapped when the validator accepts it — would then
    accept ``{"artifact": {...}}`` as the artifact itself and commit the
    wrapper. That is the exact 2B failure ``unwrap_section`` exists to undo.
    """
    if any(parsed.get(key) is not None for key in keys):
        return []
    return [f"the submit is empty; send one of: {', '.join(keys)}"]


def _require_list(parsed: dict, path: tuple[str, ...], errors: list[str]) -> None:
    """Require a non-empty list at ``path``, unless a container on the way
    there is already the wrong type.

    That exception is the whole point. MEASURED (run single_20260901_205901):
    ``assessment_plan`` arrived as an unparseable string, so the model was told
    BOTH "assessment_plan: section payload must be a JSON object, got str" AND
    "assessment_plan.pilot_data_plan.anticipated_difficulties must be a
    non-empty list". The second is a consequence of the first and cannot be
    acted on while the first holds — but it is the more concrete-sounding of
    the two, and the model chased it 61 times in a row. One root fact must
    produce one error: fix the container and the derived error goes with it.
    """
    value: object = parsed
    for depth, key in enumerate(path[:-1]):
        if not isinstance(value, dict):
            return
        value = value.get(key)
        if value is None or isinstance(value, dict):
            continue
        # A container that is present but the wrong type: say THAT, once, and
        # stop — the leaf inside it cannot be judged and naming it as well is
        # what sent the model chasing the wrong field.
        container = ".".join(path[:depth + 1])
        if not any(e.startswith(container) for e in errors):
            errors.append(f"{container} must be a JSON object, "
                          f"got {type(value).__name__}")
        return
    leaf = value.get(path[-1]) if isinstance(value, dict) else None
    if not isinstance(leaf, list) or not leaf:
        errors.append(f"{'.'.join(path)} must be a non-empty list")


#: The five top-level objects the Analysis artifact is made of. Declared once
#: and read by the validator, the completeness probe and the step table.
_ANALYSIS_PARTS = ("needs_analysis", "learner_analysis", "context_analysis",
                   "task_analysis", "improvement_plan")


def validate_analysis(parsed: dict) -> list[str]:
    """Judge only the parts that ARRIVED.

    Analysis may be submitted piecemeal (see ``AgenticStep.submit_parts``), so
    demanding all five here would reject the first correct instalment. What is
    still missing is not an error, it is the reason the step is not finished
    yet, and the loop says so in those words. What is enforced: something must
    be there, and whatever is there must be well-formed.

    ``improvement_plan.improvements`` and ``needs_analysis.gaps`` are checked
    when their part is present — the first feeds P9 provenance and is the sole
    source the aggregator builds ``evaluation.improvement_plan`` from, so a
    part that arrives hollow zeroes the program-improvement rubric item.
    """
    errors: list[str] = []
    if not any(parsed.get(part) for part in _ANALYSIS_PARTS):
        return ["the submit is empty; send at least one part of the analysis"]
    if parsed.get("needs_analysis") is not None:
        _require_list(parsed, ("needs_analysis", "gaps"), errors)
    if parsed.get("improvement_plan") is not None:
        _require_list(parsed, ("improvement_plan", "improvements"), errors)
    for key in ("learner_analysis", "context_analysis", "task_analysis"):
        value = parsed.get(key)
        if value is None:
            continue
        if not isinstance(value, dict) or not value:
            errors.append(f"{key} must be a non-empty object")
    return errors


def validate_outcomes(parsed: dict) -> list[str]:
    """Judge only the artifacts that ARRIVED — see :func:`validate_analysis`.

    Every stage submits one artifact per call now (``tools.submit_specs``), so
    demanding the whole stage here would reject each correct instalment in
    turn. What is still missing is not an error, it is the reason the stage is
    not finished, and the loop says so in those words."""
    errors = _nothing_arrived(parsed, ("course_goal", "learning_objectives"))
    if errors:
        return errors
    if parsed.get("learning_objectives") is not None:
        errors += validate_section("objective", {
            "learning_objectives": parsed.get("learning_objectives")})
    if parsed.get("course_goal") is not None:
        goal = parsed["course_goal"] if isinstance(parsed["course_goal"], dict) else {}
        if not str(goal.get("statement") or "").strip():
            errors.append("course_goal.statement must be a non-empty string")
    return errors


def validate_assessment(parsed: dict) -> list[str]:
    """Dispatch validation: the PLAN. Items are validated per work set by the
    Developer tier, so requiring them here would reject a correct dispatch."""
    empty = _nothing_arrived(parsed, ("assessment_plan", "dev_plan"))
    if empty:
        return empty
    plan = parsed.get("assessment_plan")
    if plan is None:
        # A dev_plan-only submit: nothing to judge here. `dev_plans`
        # normalizes it and reports what it had to drop.
        return []
    errors = validate_section("assessment_plan", plan)
    # pilot_data_plan feeds the whole formative half of ADDIE Evaluation (the
    # aggregator surfaces it as evaluation.formative); a submit without it
    # zeroes two rubric items (measured on a 2B run). The shared
    # evaluation_quality check + repair are the net; this asks the model
    # itself first.
    _require_list(parsed, ("assessment_plan", "pilot_data_plan", "anticipated_difficulties"), errors)
    return errors


def validate_activities(parsed: dict) -> list[str]:
    """Dispatch validation: the instructional approach. The activities
    themselves are validated per work set by the Developer tier."""
    empty = _nothing_arrived(
        parsed, ("instructional_strategies", "non_instructional_strategies", "dev_plan"))
    if empty:
        return empty
    if parsed.get("instructional_strategies") is None:
        return []
    return validate_section("activity_plan", {
        "instructional_strategies": parsed["instructional_strategies"],
    })


def validate_content(parsed: dict) -> list[str]:
    """Dispatch validation: the modules and media. The materials that realise
    them are validated per work set by the Developer tier."""
    empty = _nothing_arrived(parsed, ("content_modules", "media_selections"))
    if empty:
        return empty
    if parsed.get("content_modules") is None:
        return []
    errors: list[str] = []
    _require_list(parsed, ("content_modules",), errors)
    return errors


#: The six artifacts the implementation stage is made of, each with its own
#: submit tool. Declared once, read by the validator and the step table.
_IMPLEMENTATION_ARTIFACTS = ("instructor_orientation", "system_check",
                            "prototype_execution", "monitoring",
                            "instructor_guide", "operator_manual")


def validate_implementation(parsed: dict) -> list[str]:
    # instructor_guide / operator_manual are required in the shared section
    # schema (two rubric items score them directly), so the shared validator
    # already rejects a submit that ships a Development hole — but only once
    # that artifact is the one being submitted. Each of the six arrives in its
    # own call, so the validator judges the arrival, not the whole stage.
    arrived = {k: v for k, v in (parsed or {}).items() if v is not None}
    if not arrived:
        return _nothing_arrived({}, _IMPLEMENTATION_ARTIFACTS)
    return [e for e in validate_section("implementation_plan", arrived)
            if e.split(".", 1)[0].split(" ", 1)[0] in arrived]


# ── the step table ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AgenticStep:
    """One artifact-family step run as a tool loop."""

    name: str                     #: state name ("analysis", "outcomes", ...)
    identity: str                 #: trajectory agent identity
    #: Key into ``_collect_violations`` and, when it owns any, into
    #: ``repairs.OWNED_BY_FAMILY``. A family may own NO checks —
    #: ``needs_analyst`` writes the analysis narrative, which no deterministic
    #: check inspects — and is then absent from the ownership table entirely,
    #: the same way the audit-only relations are. Read it with ``.get``.
    family: str
    persona: str                  #: specialist persona sentence(s)
    intro: str                    #: one-line task framing
    schema: str                   #: the exact JSON schema asked for
    rules: str                    #: rulebook rules text
    primary_type: str | None      #: element type whose pool proves the step produced
    #: Extra families whose checks and repairs run after this step, because
    #: this step's Developer produced their artifacts too. Rubrics is the case:
    #: it has no stage of its own any more, but ``repairs.OWNED_BY_FAMILY``
    #: still assigns it `rubric_consistency`/`evidence_alignment`, and those
    #: must keep running somewhere. (C6/C7/orphan_rubric went with the rubric
    #: node type on 2026-09-02.)
    also_repairs: tuple[str, ...] = ()
    #: Whether this step's own ``commit`` writes into the run state.
    #:
    #: False for a fan-out work set: ``fanout.set_step`` gives it a no-op
    #: commit because the driver deposits every set together after the loops
    #: close (ids have to be remapped as a group). So at the moment a
    #: Developer's loop would run its check round, the state does not yet hold
    #: what that Developer just submitted — every violation it could be shown
    #: is one its own work has already answered. Measured on the test fixture:
    #: all five AssessmentDevelopers were handed the same `C2`/`plan_coverage`
    #: gap they had each just filled.
    commits_to_state: bool = True
    #: The top-level keys this artifact is made of, when it may be submitted
    #: PIECEMEAL: the agent generates and submits one part at a time and the
    #: step is finished when all of them have arrived. Empty (every other step)
    #: means one whole submit, as before.
    #:
    #: MEASURED FAILURE this answers (run single_20260901_205901): `analysis` is
    #: five independent top-level objects in one call — the largest artifact in
    #: the system — and on a 2B model the generation hit the 8192-token cap
    #: partway through the tool call's arguments. The loop then reported the
    #: fields that never arrived as if they were wrong, the model rewrote the
    #: whole artifact, and it was cut off at the same place. Three attempts,
    #: then the stage gave up; three times over, through the regen loop.
    #:
    #: Splitting the artifact rather than the STAGE keeps `stage_order` at six
    #: and forces no extra call: an agent that can fit it in one submit still
    #: does, and only one that cannot pays for a second turn.
    submit_parts: tuple[str, ...] = ()
    readable_types: tuple[str, ...] = ()   #: node types read_nodes/read_node may serve
    relations: tuple[str, ...] = ()        #: relation ids read_edges/coverage_gaps may serve
    docket: dict = field(default_factory=dict)  #: alignment_docket kwargs: which
                                                #: relations this step is shown
    #: TOP-LEVEL keys of the submit artifact, as ``(key, json_type, required)``.
    #: This is what the ``submit`` tool's parameter schema is built from, so the
    #: serving-side tool-call parser rejects a wrapped or key-less artifact
    #: before it ever reaches :attr:`validate`. It is deliberately a STRICTLY
    #: WEAKER front line than the validator, never a second source of truth:
    #: ``test_submit_schema_matches_the_validator`` pins every required key
    #: here to an actual :attr:`validate` error and to the :attr:`schema` text.
    submit_fields: tuple[tuple[str, str, bool], ...] = ()
    #: Prose-arm counterpart of :attr:`readable_types`: the blackboard document
    #: keys ``read_document`` may serve this step. Deliberately NOT derived from
    #: ``readable_types`` — prose has no id index and no node-type vocabulary,
    #: it names whole documents (see core/prose_store.py).
    readable_docs: tuple[str, ...] = ()
    #: ``node_type -> heading`` for artifact pools this step's prompt already
    #: renders in full (a Developer's assignment). A read of one of these is
    #: answered with a pointer instead of a second copy — see
    #: ``ToolLoop._already_in_assignment``. Empty for a stage agent, which
    #: reads live state it was not handed.
    resolved_labels: dict = field(default_factory=dict)
    validate: Callable[[dict], list[str]] = lambda parsed: []
    commit: Callable[[object, object, dict], None] = lambda graph, trajectory, parsed: None
    commit_prose: Callable[[object, object, dict], None] = lambda store, trajectory, parsed: None
    #: What of this step's artifact the state currently holds, keyed the way
    #: :attr:`submit_fields` names it. The read half of ``commit`` and declared
    #: beside it, because "has this part arrived" is the same question
    #: ``commit`` answers in the other direction, and a step that grows a field
    #: has to answer both or the loop stops at the wrong point.
    #:
    #: Asked of the STATE in both substrates, never of a counter the loop
    #: keeps: a counter is reset by the regen loop and would then disagree
    #: between the two arms, which is the axis.
    view: Callable[[object], dict] = lambda graph: {}
    view_prose: Callable[[object], dict] = lambda store: {}
    #: Overrides the produced-guard for a step whose completion is not "this
    #: family's pool is non-empty". A fan-out WORK SET is the case: its family
    #: pool fills up as its siblings commit, so from the second set onward the
    #: default guard would report the set finished before its Developer had
    #: taken a single turn. It asks instead whether THIS set's own items are
    #: in the state. (Only reachable since sets began committing one at a time
    #: — while the family was deposited in one batch at the end, the pool was
    #: empty for every set and the default guard happened to be right.)
    done: Callable[[object], bool] | None = None
    #: Whether this step's artifact contract (schema + rules) travels IN its
    #: prompt rather than behind the ``stage_brief`` tool.
    #:
    #: True for a fan-out work set. Fetching exists because a stage turn can be
    #: compacted away and the contract has to be recoverable — but a Developer
    #: runs at most ``DEVELOPER_MAX_TURNS`` turns on one assignment and does
    #: not reach the window, so it would pay a call per set for a risk it does
    #: not carry (measured: +10 calls on the test fixture, and nine identical
    #: `tool_stage_brief` entries under one Developer identity, which the
    #: trajectory judge scores as redundancy).
    contract_inline: bool = False

    def task_block(self) -> str:
        """Task + schema + rules for the tool-loop prompt. Deliberately does
        NOT end with an "output ONLY the JSON object" line: that instruction
        tells the model to emit the artifact directly, which contradicts the
        action protocol and (measured on a 2B model) suppresses every tool
        call. The loop's protocol block already pins the output contract. The
        rulebook carried such a line (``JSON_ONLY``) for the single-shot
        composition; both went with the scripted rescue on 2026-09-01."""
        return (f"{self.intro}\n\nThe artifact you will submit must follow this EXACT schema:\n"
                f"{self.schema}\n\n{self.rules}{self.parts_block()}")

    def parts_block(self) -> str:
        """The instalment instruction, for a step whose artifact is declared in
        parts. Composed from ``submit_parts`` rather than written into the
        step's prose so it cannot drift from the flag, and so BOTH arms get the
        identical wording — the axis is the context boundary, and an
        instruction present in one arm and not the other would be a second
        variable."""
        parts = parts_of(self)
        if len(parts) < 2:
            return ""
        return (
            "\n\nONE ARTIFACT PER CALL. This stage has "
            f"{len(parts)} of them: {', '.join(parts)}.\n"
            "Each has its own submit tool, named after it. Write one artifact, "
            "submit it with its own tool, then move to the next — a submit ADDS "
            "to what you have already committed and never replaces it, so never "
            "resend one you have already sent. After each submit you are told "
            "which artifacts are still missing; the stage is finished when none "
            "are.\n"
            "Do not try to write them all in one call: a long argument list IS "
            "cut off at the length limit mid-write, and everything after the cut "
            "never arrives."
        )


STEPS: tuple[AgenticStep, ...] = (
    AgenticStep(
        name="analysis",
        # Its own role, not the Outcome Designer's second job (2026-09-01).
        # Front-end analysis and outcome design are different ISD concerns —
        # different ADDIE phases, different deliverables, different expertise —
        # and the persona here already said "performing the Analysis phase"
        # under a name that says Design. A role decomposition that spans two
        # phases is the one seam a reviewer would push on, and it cost nothing
        # to keep: `multi` already starts each stage in a fresh context, so the
        # identity was only ever the RECORD of who did the work.
        identity="NeedsAnalystAgent",
        family="needs_analyst",
        persona=("You are an expert instructional analyst performing the Analysis phase of "
                 "ADDIE. You do not design the course — you establish what the design will "
                 "have to answer to."),
        intro=("Analyse the situation: the performance gaps, who the learners are, what constrains "
               "delivery, what has to be taught, and what you would improve."),
        schema=rules.SCHEMA_ANALYSIS,
        rules=rules.RULES_ANALYSIS,
        primary_type=NodeType.GAP,
        submit_fields=(
            ("needs_analysis", "object", False), ("learner_analysis", "object", False),
            ("context_analysis", "object", False), ("task_analysis", "object", False),
            ("improvement_plan", "object", False),
        ),
        # None of the five is `required` in the tool schema above, because any
        # ONE of them is a valid submit; `submit_parts` is what says all five
        # are needed before the step is finished.
        submit_parts=_ANALYSIS_PARTS,
        validate=validate_analysis,
        commit=commit_analysis,
        commit_prose=commit_analysis_prose,
        view=view_analysis,
        view_prose=view_analysis_prose,
    ),
    AgenticStep(
        name="outcomes",
        identity="OutcomeDesignerAgent",
        family="outcome_designer",
        persona=("You are an expert instructional designer working on the Design phase of ADDIE, "
                 "responsible for the course goal and learning objectives."),
        intro=("State what this course is for and what learners will be able to do, grounded in "
               "the analysis already in the design graph."),
        schema=rules.SCHEMA_OUTCOMES,
        rules=rules.RULES_OUTCOMES,
        primary_type=NodeType.OBJECTIVE,
        readable_types=(NodeType.GAP, NodeType.TOPIC, NodeType.LEARNER_PROFILE, NodeType.CONSTRAINT),
        readable_docs=("analysis",),
        submit_fields=(
            ("course_goal", "object", True), ("learning_objectives", "array", True),
        ),
        validate=validate_outcomes,
        commit=commit_outcomes,
        commit_prose=commit_outcomes_prose,
        view=view_outcomes,
        view_prose=view_outcomes_prose,
    ),
    AgenticStep(
        name="assessment",
        identity="AssessmentDesignerAgent",
        family="assessment_designer",
        # The rubric family's checks and repairs run after this stage: its
        # artifacts are written here now, by this family's Developer, in the
        # same call as the items they mark.
        also_repairs=("rubric_designer",),
        persona=("You are an expert assessment designer, responsible for how mastery of each "
                 "learning objective will be evidenced and measured."),
        intro=("Decide how you will know learners met each objective, and group the plan's "
               "coverage targets into instrument sets. You write the STRATEGY here; the items "
               "themselves are written one set at a time, after this. The grouping is YOUR "
               "call and it decides how many Developer calls follow — group work that one "
               "instrument genuinely covers together, and do not split for the sake of it."),
        schema=_SCHEMA_ASSESSMENT_DISPATCH,
        rules=rules.rules_for("assessment"),
        primary_type=NodeType.ASSESSMENT,
        readable_types=(NodeType.OBJECTIVE,),
        relations=("C2",),
        docket={"edges": ("C2",), "gaps": ("C2",), "plan_pairs": True},
        readable_docs=("analysis", "objective"),
        submit_fields=(
            ("assessment_plan", "object", True),
            # OPTIONAL, and deliberately: `dev_plans.normalize_*` derives the
            # work sets from `lo_coverage_targets` when no plan arrives, so a
            # missing dev plan costs the agent's grouping, not the stage. Made
            # required, it becomes a give-up mode — the smallest models are the
            # ones most likely to omit it and the least able to recover.
            ("dev_plan", "object", False),
        ),
        validate=validate_assessment,
        commit=commit_assessment,
        commit_prose=commit_assessment_prose,
        view=view_assessment,
        view_prose=view_assessment_prose,
    ),
    AgenticStep(
        name="activities",
        identity="ActivityDesignerAgent",
        family="activity_designer",
        persona=("You are an expert learning-activity designer, responsible for how learners "
                 "spend their time practising toward the objectives."),
        intro=("Design how learners spend their time: the instructional approach, and a grouping "
               "of the objectives into activity blocks. You write the APPROACH here; the "
               "activities themselves are written one block at a time, after this. The grouping "
               "is YOUR call and it decides how many Developer calls follow — group objectives "
               "a shared progression genuinely serves, and do not split for the sake of it."),
        schema=_SCHEMA_ACTIVITIES_DISPATCH,
        rules=rules.rules_for("activities"),
        primary_type=NodeType.ACTIVITY,
        readable_types=(NodeType.OBJECTIVE, NodeType.ASSESSMENT),
        relations=("C2", "C3", "C4"),
        docket={"edges": ("C2",), "gaps": ("C3", "C4")},
        readable_docs=("objective", "assessment"),
        submit_fields=(
            ("instructional_strategies", "object", True),
            ("non_instructional_strategies", "object", False),
            ("dev_plan", "object", False),   # see the assessment step
        ),
        validate=validate_activities,
        commit=commit_activities,
        commit_prose=commit_activities_prose,
        view=view_activities,
        view_prose=view_activities_prose,
    ),
    AgenticStep(
        name="content",
        identity="ContentDesignerAgent",
        family="content_designer",
        persona=("You are an expert content designer, responsible for the modules, media and "
                 "materials the activities need."),
        intro=("Decide how the content is organised and what form it takes: the modules and the "
               "media that realise them. The materials themselves are produced one module at a "
               "time, after this."),
        schema=_SCHEMA_CONTENT_DISPATCH,
        rules=rules.rules_for("content"),
        primary_type=NodeType.MATERIAL,
        readable_types=(NodeType.ACTIVITY, NodeType.TOPIC, NodeType.CONSTRAINT),
        relations=("C5",),
        docket={"gaps": ("C5",)},
        readable_docs=("analysis", "activity"),
        submit_fields=(
            ("content_modules", "array", True), ("media_selections", "array", False),
        ),
        validate=validate_content,
        commit=commit_content,
        commit_prose=commit_content_prose,
        view=view_content,
        view_prose=view_content_prose,
    ),
    AgenticStep(
        name="implementation",
        identity="ImplementationPlannerAgent",
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
        readable_docs=("activity", "material"),
        submit_fields=tuple((key, "object", True) for key in _IMPLEMENTATION_ARTIFACTS),
        validate=validate_implementation,
        commit=commit_implementation,
        commit_prose=commit_implementation_prose,
        view=view_implementation,
        view_prose=view_implementation_prose,
    ),
)


#: The one persona the ``agent_mode="single"`` arm carries across every stage.
#: The multi arm's per-stage personas say the same thing scoped to one concern;
#: this says it once, unscoped. It is the ONLY prompt difference the axis
#: introduces — task text, rules, schema, tools and budgets are identical, and
#: ``test_ablation_flags`` pins that.
#: The one identity the ``agent_mode="single"`` arm reports for the whole run.
#: Identity names a ROLE, not a mechanism, so a trajectory consumer (the judge,
#: the webapp, the pooling scripts) reads one actor for the whole single-arm run
#: no matter how many loops it took.
SINGLE_IDENTITY = "SingleDesignerAgent"

SINGLE_PERSONA = (
    "You are an expert instructional designer responsible for this entire design, "
    "from analysis through implementation."
)


def parts_of(step: AgenticStep) -> tuple[str, ...]:
    """The artifacts that must ALL arrive before ``step`` is finished.

    Every stage is piecemeal now that each artifact has its own submit tool
    (``tools.submit_specs``), so this is the required subset of
    :attr:`AgenticStep.submit_fields` — with :attr:`submit_parts` as an
    explicit override for a step whose completeness is not what the tool
    schema marks required. ``analysis`` is that step: none of its five parts is
    ``required`` in the schema, because any ONE of them is a valid submit,
    while all five are needed before the step is done.
    """
    if not step.commits_to_state:
        # A fan-out work set: its commit is a no-op, the driver deposits every
        # set together once the loops close. "Has this part arrived" is a
        # question about the STATE, and this step writes none — so it has no
        # parts, and its loop ends on its first accepted submit.
        return ()
    if step.submit_parts:
        return step.submit_parts
    return tuple(key for key, _type, required in step.submit_fields if required)


def missing_parts(step: AgenticStep, state) -> tuple[str, ...]:
    """Parts of ``step``'s artifact the state does not hold yet."""
    parts = parts_of(step)
    if not parts:
        return ()
    landed = (step.view(state) if hasattr(state, "element_nodes")
              else step.view_prose(state))
    return tuple(part for part in parts if not landed.get(part))


def step_done(step: AgenticStep, state) -> bool:
    """Idempotence/produced guard. ``state`` is the AlignmentGraph in graph mode
    and the ProseStore in prose mode; the guard must mean the same thing in
    both, or a regen loop spins on one arm and not the other."""
    from ..outputs import _empty_required_fields

    if step.done is not None:
        return step.done(state)
    # Every stage submits one artifact per call, so a stage is finished when
    # every REQUIRED artifact has arrived — not when its primary element pool
    # is non-empty, which one artifact alone would satisfy.
    if parts_of(step):
        return not missing_parts(step, state)
    graph_mode = hasattr(state, "element_nodes")
    if step.primary_type is None:
        if graph_mode:
            node = state.get_node(state.section_id(NodeType.IMPLEMENTATION_PLAN))
            data = (node or {}).get("data") or {}
        else:
            data = state.get("implementation_plan") or {}
        return bool(data) and not _empty_required_fields(NodeType.IMPLEMENTATION_PLAN, data)
    if graph_mode:
        return bool(state.element_nodes(step.primary_type))
    from ..prose_store import primary_items

    return bool(primary_items(state, str(step.primary_type)))
