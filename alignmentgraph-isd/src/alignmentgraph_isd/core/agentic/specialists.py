"""Step definitions: 6 artifact-family steps, each run as
a tool loop by ``core/agentic/loop.py``.

Granularity is one step per artifact family, plan and execution together,
because the tool loop
subsumes the multi arm's plan/execute hop split: how much context to gather
and when the artifact is ready are the agent's own decisions inside the loop,
not separate pre-scripted calls. Personas stay specialist (one per family):
what the ``agent_mode`` axis varies is the CONTEXT BOUNDARY, not the roles.

Rules come from the shared rulebook (``core/rulebook.py``) and the artifact
shape from ``artifact_schemas.py``; both decomposition arms compose from the
same step table. Commits call only the shared establishers
(``alignment.record_provenance``/``match_*``/``establish_delivery``), so the
graph is shaped the same whichever arm wrote it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .. import dev_plans
from .. import rulebook as rules
from ..alignment_graph import NodeType, alignment
from ..trajectory import ORCHESTRATOR
from ..validation import validate_section
from .artifact_schemas import ARTIFACT_SCHEMAS


#: Blackboard documents whose ``commit_prose`` is ALREADY additive, so
#: ``ReactLoop._commit`` must not append them a second time. That re-merge
#: exists only because a prose commit replaces its key; a commit that appends
#: for itself has outgrown it.
ADDITIVE_PROSE_DOC_KEYS = frozenset({str(NodeType.OBJECTIVE)})


def _fold(item: dict, field: str) -> str:
    return str(item.get(field) or "").strip().casefold()


def _dedup_new(existing: list, incoming: list, dedup_field: str) -> tuple[list, int]:
    """Which of ``incoming`` are new by ``dedup_field``, and how many repeated.

    Pure, and shared by both substrates on purpose: the graph arm drops a
    repeated objective at :func:`_decompose` and the prose arm at
    :func:`commit_outcomes_prose`, and two implementations of "is this the same
    element" would be a difference sitting on the ``context_mode`` axis rather
    than on the machinery that axis ablates.
    """
    if not dedup_field:
        return [i for i in incoming if isinstance(i, dict)], 0
    seen = {_fold(i, dedup_field) for i in existing if isinstance(i, dict)} - {""}
    kept: list = []
    dropped = 0
    for item in incoming:
        if not isinstance(item, dict):
            continue
        key = _fold(item, dedup_field)
        if key and key in seen:
            dropped += 1
            continue
        seen.add(key)
        kept.append(item)
    return kept, dropped


def _log_duplicates(trajectory, what: str, dropped: int, kept: int, dedup_field: str) -> None:
    """One event shape for both substrates — see :func:`_dedup_new`."""
    if not dropped:
        return
    trajectory.log_recovery_event(
        "", "duplicate_element_dropped",
        f"{what}: {dropped} of {dropped + kept} duplicated by {dedup_field}",
        f"kept {kept}")


def _decompose(graph, trajectory, node_type: str, items: object, *,
               id_field: str = "id", dedup_field: str = "") -> list[str]:
    """Turn a just-generated list into element nodes AND log each one.

    The logging is IN here rather than at the call sites for a reason:
    ``node_edit`` events are judge-visible, so a call site that forgets one
    makes whichever arm reaches it look like it did less work — a difference
    the ablation would then read as an axis effect.

    ``dedup_field`` names the field that IDENTIFIES an element by content. Two
    items whose value for it is the same are the same element however many ids
    the model gave them, and only the first is committed. This is not a cap on
    what the model may produce — it writes as many as it likes and the drop is
    counted — it is a refusal to record one thing many times, the same rule
    ``dev_plans`` already applies to duplicate coverage pairs. Everything
    downstream sizes itself off these element counts, so a duplicate is not
    merely untidy: it multiplies work sets, calls and time."""
    node_ids: list[str] = []
    if not isinstance(items, list):
        return node_ids
    # An id-less item is skipped BEFORE the dedup, so it is never counted as a
    # duplicate of something it could not have been committed as anyway.
    candidates = [i for i in items if isinstance(i, dict) and i.get(id_field)]
    existing = ([(n.get("data") or {}) for n in graph.element_nodes(node_type)]
                if dedup_field else [])
    kept, dropped = _dedup_new(existing, candidates, dedup_field)
    for item in kept:
        node_id = graph.add_element_node(node_type, str(item[id_field]), dict(item))
        node_ids.append(node_id)
        trajectory.log_node_edit("add", node_id, node_type)
    _log_duplicates(trajectory, node_type, dropped, len(node_ids), dedup_field)
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
        alignment.link_section_narrative(graph, node_type)


# ── per-step commits ───────────────────────────────────────────────────────
# Signature: (graph, trajectory, parsed) -> None.

def _merge_section(graph, trajectory, node_type, updates: dict) -> str:
    """Write section fields WITHOUT dropping the ones already there.

    Each artifact of a stage arrives in its own submit call
    (``tools.submit_specs``), so a section node is built up over several
    commits; ``AlignmentGraph.add_node`` REPLACES a node's data, so a plain
    write of the dev plan would drop the assessment plan beside it.
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
        _merge_section(graph, trajectory, NodeType.LEARNER_PROFILE, learner)

    improvement = parsed.get("improvement_plan") or {}
    _decompose(graph, trajectory, NodeType.IMPROVEMENT, improvement.get("improvements"))
    _store_narrative(graph, trajectory, NodeType.IMPROVEMENT, improvement, "improvements")
    gap_by_id = {n["data"].get("id"): n["id"] for n in graph.element_nodes(NodeType.GAP)}
    for item in improvement.get("improvements") or []:
        if not isinstance(item, dict):
            continue
        source = gap_by_id.get(alignment.bare_ref(item.get("addresses_gap")))
        if source:
            alignment.record_provenance(
                graph, "P9", [source],
                f"{NodeType.IMPROVEMENT}{graph.ELEMENT_SEP}{item.get('id')}")


def commit_outcomes(graph, trajectory, parsed: dict) -> None:
    objectives = parsed.get("learning_objectives") or []
    objective_ids = _decompose(graph, trajectory, NodeType.OBJECTIVE, objectives,
                               dedup_field="statement")
    gap_ids = [n["id"] for n in graph.element_nodes(NodeType.GAP)]
    topic_ids = [n["id"] for n in graph.element_nodes(NodeType.TOPIC)]
    learner_id = graph.section_id(NodeType.LEARNER_PROFILE)
    for node_id in objective_ids:
        if gap_ids or topic_ids:
            alignment.record_provenance(graph, "P1", gap_ids + topic_ids, node_id)
        if graph.get_node(learner_id):
            alignment.record_provenance(graph, "P2", [learner_id], node_id)

    _decompose(graph, trajectory, NodeType.MODULE, parsed.get("course_modules"),
               dedup_field="title")
    _link_modules(graph)


def _link_modules(graph) -> None:
    """P7 and P12, from what every module names, over EVERY module.

    All of them rather than the ones this call added: the three outcomes
    artifacts arrive in separate submits and in no guaranteed order, so a
    module may land before the objectives it names. ``record_provenance`` is a
    no-op on a missing end and ``add_edge`` on a repeated edge, so running it
    again when the other end arrives is what makes the order not matter. Every
    reference is model-written and goes through ``alignment.bare_ref`` first
    (see :func:`commit_content`)."""
    for node in graph.element_nodes(NodeType.MODULE):
        data = node["data"]
        topics = [alignment.resolve_element(graph, NodeType.TOPIC, ref)
                  for ref in data.get("covers_topics") or []]
        alignment.record_provenance(graph, "P7", [t for t in topics if t], node["id"])
        for ref in data.get("objectives") or []:
            objective = alignment.resolve_element(graph, NodeType.OBJECTIVE, ref)
            if objective:
                alignment.record_provenance(graph, "P12", [node["id"]], objective)


def commit_assessment(graph, trajectory, parsed: dict) -> None:
    """Dispatch commit: the PLAN. The items are produced one work set at a
    time by the Developer tier (see ``fanout.py``) — a single submit cannot
    carry a whole family's item list under the 8192 completion cap, and the
    grouping is derived from the plan's own sets rather than stated.

    The assessment ELEMENT is the TASK — the thing a learner sits — not the
    question inside it. An item is a FIELD of its task for the reason a rubric
    criterion is a field of its item: nothing but the task owns it, and its
    membership is then structural instead of an id a Developer has to get
    right. The Developer tier fills each task's ``items`` one work set at a
    time (``fanout._attach_to_parent``)."""
    updates = _assessment_updates(parsed, trajectory)
    if updates:
        _merge_section(graph, trajectory, NodeType.ASSESSMENT_PLAN, updates)
        _decompose(graph, trajectory, NodeType.ASSESSMENT,
                   [{**task, "items": []} for task in dev_plans.plan_tasks(updates)])


def _assessment_updates(parsed: dict, trajectory=None) -> dict:
    """The plan as submitted, with a REPEATED task id renamed to the next free
    one (``dev_plans.dedupe_task_ids``) and each rename recorded. Settled at
    the commit, on either substrate, before any item exists to name a task:
    two tasks under one id are one element node and one ``task_id``, and the
    grammar cannot refuse a repeat. Never a rejection — the plan is the
    largest artifact of its stage and a refusal costs a whole re-emission."""
    plan = parsed.get("assessment_plan")
    if not isinstance(plan, dict):
        return {}
    plan, renamed = dev_plans.dedupe_task_ids(dict(plan))
    if renamed and trajectory is not None:
        # The actor is the scope's, as every commit-time event's is
        # (`_log_duplicates`): the commit runs inside the agent's scope.
        trajectory.log_recovery_event(
            "", "duplicate_task_id_renamed",
            "; ".join(f"{old} -> {new}" for old, new in renamed)[:200],
            f"{len(renamed)} task id(s) the plan repeated")
    return dict(plan)


def _activities_updates(parsed: dict) -> dict:
    return {key: parsed[key] for key in
            ("instructional_strategies", "non_instructional_strategies")
            if isinstance(parsed.get(key), dict) and parsed[key]}


def _implementation_updates(parsed: dict) -> dict:
    return {k: v for k, v in _guide_framing(parsed).items() if v}


def commit_activities(graph, trajectory, parsed: dict) -> None:
    updates = _activities_updates(parsed)
    if updates:
        _merge_section(graph, trajectory, NodeType.ACTIVITY_PLAN, updates)


def commit_content(graph, trajectory, parsed: dict) -> None:
    """Commit the media selections, and record P8.

    Every reference here is MODEL-WRITTEN and is normalized through
    ``alignment.bare_ref`` before a node id is composed from it. That is the
    rule everywhere a model's reference is read — ``alignment.py``'s
    id-matched establishers, ``fanout``'s P5, ``dev_plans.plan_category_pairs``.

    MEASURED (run 2559b22d): the model wrote a reference as
    ``"activity:TLA-0101"``, which is the node's own id and unambiguous. Bare
    composition made that ``activity:activity:TLA-0101``,
    ``record_provenance`` no-ops on a target that does not exist, and twelve
    correct references established no edge at all — a relation scoring 0.08 on
    a design that was right.
    """
    media_ids = _decompose(graph, trajectory, NodeType.MEDIA_SELECTION, parsed.get("media_selections"))
    for node_id in media_ids:
        data = graph.get_node(node_id)["data"]
        constraints = [alignment.resolve_element(graph, NodeType.CONSTRAINT, ref)
                       for ref in data.get("respects_constraints") or []]
        alignment.record_provenance(graph, "P8", [c for c in constraints if c], node_id)




def _guide_framing(parsed: dict) -> dict:
    """The dispatch payload with ``instructor_guide.session_guides`` removed.

    The guides are element nodes now (``NodeType.SESSION_GUIDE``), written one
    block at a time by the Developer tier and joined back under this key by the
    aggregator. A nested copy here would be a second source for the one list
    P10/P11 are established from, and the section node would then hold guides
    no establisher ever saw. The submit that carries one is rejected with the
    field named (:func:`validate_implementation`); this is the belt to that
    validator's braces, for a payload that reaches the commit another way (a
    salvaged truncation, a ``last_resort`` give-up).
    """
    out = dict(parsed or {})
    guide = out.get("instructor_guide")
    if isinstance(guide, dict) and "session_guides" in guide:
        out["instructor_guide"] = {k: v for k, v in guide.items() if k != "session_guides"}
    return out


def commit_implementation(graph, trajectory, parsed: dict) -> None:
    """Dispatch commit: the six framing artifacts and the DEV PLAN. The session
    guides are produced one block at a time by the Developer tier (fanout.py),
    and P10/P11 are established from those nodes (``alignment.establish_delivery``).

    The dev plan is kept on the section for the same reason the assessment one
    is (``commit_assessment``): ``_dispatch_payload`` reads the fan-out's input
    back out of the state, so a stripped plan means the deterministic fallback
    decides every division. It is stripped again at AGGREGATION
    so the graph dump shows how the
    delivery was divided while the judged output does not.
    """
    _merge_section(graph, trajectory, NodeType.IMPLEMENTATION_PLAN,
                   _implementation_updates(parsed))


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
    """ADDITIVE at the top level, because analysis arrives in parts and
    ``ProseStore.put`` overwrites — the graph arm writes each part to its own
    node, so a prose arm that lost earlier parts would put a data loss on the
    ``context_mode`` axis itself."""
    if not parsed:
        return
    existing = store.get("analysis") or {}
    merged = {**existing, **{k: v for k, v in parsed.items() if v}}
    _put(store, trajectory, "analysis", merged)


def commit_outcomes_prose(store, trajectory, parsed: dict) -> None:
    """ADDITIVE on the objective LIST, with the same dedup the graph arm runs.

    ``_merge_document`` REPLACES a key, and the graph arm's ``_decompose``
    appends each objective as its own element node — so a regen or a second
    accepted submit left the two substrates holding different designs, which
    is a data loss sitting on the ``context_mode`` axis itself rather than on
    the alignment machinery that axis exists to ablate. Both now append and
    both drop a repeated ``statement`` through :func:`_dedup_new`.

    ``course_modules`` is the same kind of list and gets the same treatment,
    deduplicated on ``title``.
    """
    updates = {k: v for k, v in (parsed or {}).items() if v}
    for list_key, dedup_field in (("learning_objectives", "statement"),
                                  ("course_modules", "title")):
        incoming = updates.get(list_key)
        if not isinstance(incoming, list):
            continue
        existing = [i for i in store.items(str(NodeType.OBJECTIVE), list_key)
                    if isinstance(i, dict)]
        kept, dropped = _dedup_new(existing, incoming, dedup_field)
        updates[list_key] = existing + kept
        _log_duplicates(trajectory, str(NodeType.OBJECTIVE), dropped, len(kept), dedup_field)
    _merge_document(store, trajectory, str(NodeType.OBJECTIVE), updates)


def commit_assessment_prose(store, trajectory, parsed: dict) -> None:
    updates = _assessment_updates(parsed, trajectory)
    if updates:
        _merge_document(store, trajectory, "assessment_plan", updates)


def commit_activities_prose(store, trajectory, parsed: dict) -> None:
    updates = _activities_updates(parsed)
    if updates:
        _merge_document(store, trajectory, "activity_plan", updates)


def commit_content_prose(store, trajectory, parsed: dict) -> None:
    updates = {key: parsed[key] for key in ("media_selections",)
               if isinstance(parsed.get(key), list) and parsed[key]}
    if updates:
        _merge_document(store, trajectory, "content", updates)


def commit_implementation_prose(store, trajectory, parsed: dict) -> None:
    _merge_document(store, trajectory, "implementation_plan",
                    _implementation_updates(parsed))


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
    return {"learning_objectives": graph.element_nodes(NodeType.OBJECTIVE),
            "course_modules": graph.element_nodes(NodeType.MODULE)}


def view_outcomes_prose(store) -> dict:
    return store.get("objective") or {}


def _assessment_view(plan: dict) -> dict:
    return {"assessment_plan": dict(plan or {})}


def view_assessment(graph) -> dict:
    return _assessment_view(_section(graph, NodeType.ASSESSMENT_PLAN))


def view_assessment_prose(store) -> dict:
    return _assessment_view(store.get("assessment_plan") or {})


def view_activities(graph) -> dict:
    return dict(_section(graph, NodeType.ACTIVITY_PLAN))


def view_activities_prose(store) -> dict:
    return store.get("activity_plan") or {}


def view_content(graph) -> dict:
    return {"media_selections": graph.element_nodes(NodeType.MEDIA_SELECTION)}


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

    An EMPTY container has not arrived either: ``{"assessment_plan": {}}`` accepted
    here is committed as nothing, found absent, and logged as the harness's
    ``commit_did_not_land`` for what is the model sending nothing. A
    rejection is the honest answer and gets the model its SUBMIT_BUDGET
    retries with the real reason.
    """
    if any(_arrived(parsed.get(key)) for key in keys):
        return []
    return [f"the submit is empty; send one of: {', '.join(keys)}"]


def _arrived(value) -> bool:
    return value not in (None, "", [], {})


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


#: The five top-level objects the Analysis artifact is made of, in the order
#: ``_ANALYSIS_PART_NODE`` declares them.
_ANALYSIS_PARTS = tuple(_ANALYSIS_PART_NODE)


#: Fields the HARNESS settles at commit rather than the model at submit, so a
#: declared-required check never refuses them: an item's ``task_id`` and an
#: activity's ``module_id`` are filled from the work set
#: (``dev_plans.with_membership``, and refused by ``_names_its`` only when
#: nothing can fill them), ``plan_category`` is stamped from the task's
#: ``timing``, and a session guide's ``activity_ids`` has its own rule
#: (``fanout.session_guide_errors``).
HARNESS_SETTLED_FIELDS = frozenset({"task_id", "module_id", "plan_category", "activity_ids"})


def declared_required_errors(key: str, artifact: object, where: str = "") -> list[str]:
    """Every field ``artifact_schemas.ARTIFACT_SCHEMAS[key]`` declares REQUIRED
    that ``artifact`` leaves out or empty — one error each, naming the field.

    The schema is the contract the model is shown; this is the same contract
    asked at the submit, so a field the rubric reads and the model skipped is
    refused while the author is in the conversation and the constrained pass
    can write it. ``required`` here means non-empty (``required_floor``)."""
    schema = ARTIFACT_SCHEMAS.get(key) or {}
    if not isinstance(artifact, dict):
        return []
    where = where or key
    return [f"{where}.{field}: required field is missing or empty"
            for field in schema.get("required", ())
            if field not in HARNESS_SETTLED_FIELDS and artifact.get(field) in (None, "", [], {})]


def validate_analysis(parsed: dict) -> list[str]:
    """Judge only the parts that ARRIVED.

    Analysis may be submitted piecemeal (see ``AgenticStep.submit_parts``), so
    demanding all five here would reject the first correct instalment. What is
    still missing is not an error, it is the reason the step is not finished
    yet, and the loop says so in those words. What is enforced: something must
    be there, and whatever is there must be well-formed.

    ``improvement_plan.improvements``, ``needs_analysis.gaps`` and
    ``task_analysis.topics`` are checked when their part is present — the
    first feeds P9 provenance and is the sole source the aggregator builds
    ``evaluation.improvement_plan`` from, so a part that arrives hollow zeroes
    the program-improvement rubric item. MEASURED (run aef73e0a): a
    ``task_analysis`` with seven keys and no ``topics`` was accepted, every
    module then named topic ids that did not exist, and P7 read 0.0.
    """
    errors: list[str] = []
    if not any(parsed.get(part) for part in _ANALYSIS_PARTS):
        return ["the submit is empty; send at least one part of the analysis"]
    if parsed.get("needs_analysis") is not None:
        _require_list(parsed, ("needs_analysis", "gaps"), errors)
    if parsed.get("improvement_plan") is not None:
        _require_list(parsed, ("improvement_plan", "improvements"), errors)
    if parsed.get("context_analysis") is not None:
        # The constraints are what every media selection is chosen in light of
        # (P8). MEASURED (run b8576814): a context analysis with no
        # ``constraints`` at all was accepted and P8 read 0.0.
        _require_list(parsed, ("context_analysis", "constraints"), errors)
    if parsed.get("task_analysis") is not None:
        # The topics are what the course's modules are clustered from (P7) and
        # one of the bounds on how many modules there are.
        _require_list(parsed, ("task_analysis", "topics"), errors)
    for key in ("learner_analysis", "context_analysis", "task_analysis"):
        value = parsed.get(key)
        if value is None:
            continue
        if not isinstance(value, dict) or not value:
            errors.append(f"{key} must be a non-empty object")
    # Every part is held to its declared floor: the ten analysis sub-items of
    # the rubric read exactly the prose fields a small model skips when they
    # are optional (see the note above ``ARTIFACT_SCHEMAS``).
    for key in _ANALYSIS_PARTS:
        if isinstance(parsed.get(key), dict) and parsed[key]:
            errors += [e for e in declared_required_errors(key, parsed[key]) if e not in errors]
    return errors


def validate_outcomes(parsed: dict) -> list[str]:
    """Judge only the artifacts that ARRIVED — see :func:`validate_analysis`.

    Every stage submits one artifact per call now (``tools.submit_specs``), so
    demanding the whole stage here would reject each correct instalment in
    turn. What is still missing is not an error, it is the reason the stage is
    not finished, and the loop says so in those words."""
    errors = _nothing_arrived(parsed, ("learning_objectives", "course_modules"))
    if errors:
        return errors
    if parsed.get("course_modules") is not None:
        errors += _module_errors(parsed["course_modules"])
    if parsed.get("learning_objectives") is not None:
        errors += validate_section("objective", {
            "learning_objectives": parsed.get("learning_objectives")})
    return errors


def _module_errors(modules) -> list[str]:
    """A module that names no objective or no time is not a unit anything can
    be divided by: every later family takes its share of the design from
    ``objectives`` and its ceiling from ``minutes``."""
    if not isinstance(modules, list) or not modules:
        return ["course_modules must be a non-empty list"]
    errors: list[str] = []
    for index, module in enumerate(modules):
        where = f"course_modules[{index}]"
        if not isinstance(module, dict):
            errors.append(f"{where} must be an object")
            continue
        for key in ("id", "title"):
            if not str(module.get(key) or "").strip():
                errors.append(f"{where}.{key} must be a non-empty string")
        for key, what in (("objectives", "objective id"),
                          ("covers_topics", "topic id")):
            value = module.get(key)
            if not isinstance(value, list) or not [v for v in value if str(v).strip()]:
                errors.append(f"{where}.{key} must list at least one {what}")
        minutes = module.get("minutes")
        if isinstance(minutes, bool) or not isinstance(minutes, (int, float)) or minutes <= 0:
            errors.append(f"{where}.minutes must be a positive number")
    return errors


def validate_assessment(parsed: dict) -> list[str]:
    """Dispatch validation: the PLAN. Items are validated per work set by the
    Developer tier, so requiring them here would reject a correct dispatch."""
    empty = _nothing_arrived(parsed, ("assessment_plan",))
    if empty:
        return empty
    errors = validate_section("assessment_plan", parsed["assessment_plan"])
    errors += [e for e in declared_required_errors("assessment_plan", parsed["assessment_plan"])
               if e not in errors]
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
        parsed, ("instructional_strategies", "non_instructional_strategies"))
    if empty:
        return empty
    errors: list[str] = []
    if not _arrived(parsed.get("instructional_strategies")):
        return errors
    return (errors + validate_section("activity_plan", {
        "instructional_strategies": parsed["instructional_strategies"],
    }) + declared_required_errors("instructional_strategies",
                                  parsed["instructional_strategies"]))


def validate_content(parsed: dict) -> list[str]:
    """Dispatch validation: the media. The materials that realise them are
    validated per work set by the Developer tier."""
    empty = _nothing_arrived(parsed, ("media_selections",))
    if empty:
        return empty
    errors: list[str] = []
    _require_list(parsed, ("media_selections",), errors)
    if not errors:
        errors += _media_selection_errors(parsed["media_selections"])
    return errors


def _media_selection_errors(selections) -> list[str]:
    """Every field the schema declares required, judged per selection.

    The four are each load-bearing, and three of them fail SILENTLY when
    absent, which is why the model is asked while it is still in the
    conversation rather than left to the checks: ``_decompose`` keeps only
    elements carrying an ``id``, so a selection without one is dropped without
    a word; ``for_modules`` is what hands a module its media, and a module left
    out gets materials of no chosen medium; ``media_type`` is the far end of
    P6, which a material's ``type`` has to match.

    ``respects_constraints`` is the one this function was added for. It is the
    whole source of P8, and it was declared OPTIONAL while the relation that
    measures it required it. MEASURED (run bd2531da): all 12 selections omitted
    it, P8 read 0.00 against a graph where every other relation read 1.00, and
    the 12 findings were stamped ``unseen`` -- the check runs after the stage's
    loop has closed, so nobody was ever in a position to fix it. Two parts of
    one system reading two different contracts, the same shape as the
    ``lo_coverage_targets`` defect.
    """
    if not isinstance(selections, list):
        return []
    errors: list[str] = []
    for index, selection in enumerate(selections):
        where = f"media_selections[{index}]"
        if not isinstance(selection, dict):
            errors.append(f"{where} must be an object")
            continue
        for key in ("id", "media_type"):
            if not str(selection.get(key) or "").strip():
                errors.append(f"{where}.{key} must be a non-empty string")
        for key, what in (("for_modules", "module id"),
                          ("respects_constraints", "constraint id")):
            value = selection.get(key)
            if not isinstance(value, list) or not [v for v in value if str(v).strip()]:
                errors.append(f"{where}.{key} must list at least one {what}")
    return errors


#: The six artifacts the implementation stage is made of, each with its own
#: submit tool. Declared once, read by the validator and the step table.
_IMPLEMENTATION_ARTIFACTS = ("instructor_orientation", "system_check",
                            "prototype_execution", "monitoring",
                            "instructor_guide", "operator_manual")


#: Error-path prefix of the one nested field the implementation stage does not own.
_SESSION_GUIDES_PATH = f"{NodeType.IMPLEMENTATION_PLAN}.instructor_guide.session_guides"


def validate_implementation(parsed: dict) -> list[str]:
    # instructor_guide / operator_manual are required in the shared section
    # schema (two rubric items score them directly), so the shared validator
    # already rejects a submit that ships a Development hole — but only once
    # that artifact is the one being submitted. Each of the six arrives in its
    # own call, so the validator judges the arrival, not the whole stage.
    # An artifact sent EMPTY has not arrived: a truncated completion leaves
    # the key with nothing under it, and rejecting five finished artifacts
    # over the sixth's empty envelope would cost the model the whole submit.
    # The five land, completion (`missing_parts`) keeps asking for the sixth.
    #
    # ``arrived`` is restricted to the artifacts this stage DECLARES: built
    # from any non-empty key, a payload of unrecognized names validated clean
    # and `unwrap_section` then stripped the artifact's own name off a
    # well-formed envelope whose inner fields were wrong (run 24343e4d: 43
    # top-level keys on the section, `operator_manual` submitted three times
    # and never landed).
    arrived = {k: v for k, v in (parsed or {}).items()
               if k in _IMPLEMENTATION_ARTIFACTS and _arrived(v)}
    if not arrived:
        return _nothing_arrived({}, _IMPLEMENTATION_ARTIFACTS)
    # Keep the errors about the artifacts that ARRIVED. Every error path is
    # rooted at the node type — ``implementation_plan.instructor_guide.overview``
    # — so the artifact is the SECOND dotted token. The first version tested
    # the first token against ``arrived`` and so kept nothing at all: any
    # non-empty dict was accepted, whatever its keys (measured on run
    # e81b8108, where a guide with no ``session_guides`` was COMMITTED and
    # every activity and material ended unscheduled).
    prefix = f"{NodeType.IMPLEMENTATION_PLAN}."
    errors = [e for e in validate_section("implementation_plan", arrived)
              if e.startswith(prefix)
              and _error_field(e[len(prefix):]) in arrived
              and not e.startswith(_SESSION_GUIDES_PATH)]
    # The one thing this stage's guide may NOT carry. `session_guides` is a
    # separate artifact with its own tool and its own Developer (fanout.py):
    # accepted here it would be a second source for the list P10/P11 are
    # established from, and it is the field a planner cannot in fact write —
    # naming every activity in the design is what the fan-out exists for. Named
    # explicitly rather than dropped silently, so the model is told where the
    # work goes instead of watching it disappear.
    guide = arrived.get("instructor_guide")
    if isinstance(guide, dict) and guide.get("session_guides"):
        errors.append(
            f"{_SESSION_GUIDES_PATH}: the session guides are not part of this artifact. "
            "Submit instructor_guide with its overview, facilitation_tips and "
            "troubleshooting only; the guides themselves are written one module at a "
            "time, by a Developer per module.")
    return errors


def _error_field(path: str) -> str:
    """The first field of a validator error path: ``instructor_guide`` from
    ``instructor_guide.session_guides[0].activity_ids: ...``."""
    for stop in (".", "[", ":"):
        path = path.split(stop, 1)[0]
    return path.strip()


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
    rules: str                    #: rulebook rules text
    primary_type: str | None      #: element type whose pool proves the step produced
    #: Extra families whose checks and repairs run after this step, because
    #: this step's Developer produced their artifacts too. Rubrics is the case:
    #: it has no stage of its own any more, but ``repairs.OWNED_BY_FAMILY``
    #: still assigns it `rubric_consistency`/`evidence_alignment`, and those
    #: must keep running somewhere.
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
    readable_types: tuple[str, ...] = ()   #: node types the state read lists and read_node serves
    relations: tuple[str, ...] = ()        #: relation ids this stage's artifacts take part in
    #: Whether ``read_alignment_state`` is bound. False for a fan-out work set
    #: and a re-dispatch round: their assignment IS their state, written into the
    #: turn, and the family's gaps belong to whoever planned the sets.
    state_tool: bool = True
    docket: dict = field(default_factory=dict)  #: what the state read reports as MISSING: which
                                                #: relations this step is shown
    #: TOP-LEVEL keys of the submit artifact, as ``(key, json_type, required)``.
    #: This is what the ``submit`` tool's parameter schema is built from
    #: (:func:`tools._parameters_from`, looking each key up in
    #: :mod:`artifact_schemas`), so the serving-side tool-call parser rejects a
    #: wrapped, key-less or wrongly-shaped artifact before it ever reaches
    #: :attr:`validate`. :attr:`validate` stays the authority on acceptance —
    #: this only rejects earlier what it would reject anyway.
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
    #: ``id -> heading`` for every artifact id a Developer's assignment shows
    #: (a module, a media selection, a topic, an item it prepares for). A read
    #: of one of these that no read tool serves is answered with where it
    #: already is instead of "no readable artifact" — see
    #: ``ToolLoop._execute``. Empty for a stage agent.
    assignment_ids: dict = field(default_factory=dict)
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
    #: What an ACCEPTED submit still owes before the step is finished: the
    #: sentence that asks for it, or ``""``. Only a fan-out work set declares
    #: one (its stated count). While it answers, the loop keeps what arrived,
    #: answers with this, and joins the next submit to it
    #: (``ToolLoop._handle_submit``) — an instalment, never a rejection.
    owes: Callable[[dict], str] | None = None
    #: The work set a fan-out Developer step was cut from, or None for a stage
    #: agent. What the per-run submit schema reads its fixed rows and stated
    #: counts from (``grammar.artifact_property``); it changes no wording.
    work_set: dev_plans.WorkSet | None = None

    def task_block(self) -> str:
        """Task + rules for the tool-loop prompt. No schema block: the
        artifact's field-level SHAPE (types, nesting, enums) lives in the
        bound ``submit_*`` tool's own ``parameters`` now
        (``artifact_schemas.ARTIFACT_SCHEMAS``, resolved through
        ``tools._parameters_from``), not restated here as text — see that
        module's docstring. This block still carries the RULES_* prose:
        cross-field, referential and judgment-call constraints (an
        objective's Bloom level driving what counts as achievable, an id
        that must exist in a sibling list, how many items a set
        genuinely needs) that no static JSON Schema can express.

        Deliberately does NOT end with an "output ONLY the JSON object"
        line: that instruction tells the model to emit the artifact
        directly, which contradicts the action protocol and (measured on a
        2B model) suppresses every tool call. The loop's protocol block
        already pins the output contract."""
        return f"{self.intro}\n\n{self.rules}{self.parts_block()}"

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
        # Its own role, not the Outcome Designer's second job: front-end
        # analysis and outcome design are different ADDIE phases, and a role
        # decomposition that spans two is the seam a reviewer pushes on.
        identity="NeedsAnalystAgent",
        family="needs_analyst",
        persona=("You are an expert instructional analyst performing the Analysis phase of "
                 "ADDIE. You do not design the course — you establish what the design will "
                 "have to answer to."),
        intro=("Analyse the situation: the performance gaps, who the learners are, what constrains "
               "delivery, what has to be taught, and what you would improve."),
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
                 "responsible for the learning objectives and the modules the course is "
                 "organised into."),
        intro=("State what learners will be able to do, and how the course divides into "
               "modules, grounded in the learning goals the brief states and in the analysis "
               "already in the design graph. Everything designed after this is divided by "
               "your modules."),
        rules=rules.rules_for("outcomes"),
        primary_type=NodeType.OBJECTIVE,
        readable_types=(NodeType.GAP, NodeType.TOPIC, NodeType.LEARNER_PROFILE, NodeType.CONSTRAINT),
        docket={"gaps": ("P12",), "module_ceiling": True},
        readable_docs=("analysis",),
        submit_fields=(
            ("learning_objectives", "array", True),
            # REQUIRED: the modules are the key all four fan-out families
            # divide their work by, and a run without them stops after this
            # stage (``core/runner.py``) rather than inventing a division.
            ("course_modules", "array", True),
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
        intro=("Decide how you will know learners met each objective. You write the "
               "STRATEGY here — the blueprint of sets each module's learners sit; "
               "the items themselves are written afterwards, one set at a time, by "
               "a Developer per set."),
        rules=rules.rules_for("assessment"),
        primary_type=NodeType.ASSESSMENT,
        readable_types=(NodeType.MODULE, NodeType.OBJECTIVE),
        relations=("C2",),
        docket={"edges": ("C2",), "gaps": ("C2", "P14"), "plan_pairs": True,
                "task_ceiling": True},
        readable_docs=("analysis", "objective"),
        # The blueprint alone. How its writing is divided is not a decision
        # an instructional designer makes: one Developer writes one
        # INSTRUMENT, which the plan already states, so `fanout._assessment_sets`
        # derives the grouping and the stage spends no call saying it.
        submit_fields=(("assessment_plan", "object", True),),
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
        intro=("Design how learners spend their time: the instructional approach the "
               "course takes. You write the APPROACH here; the activities themselves are "
               "written afterwards, one module at a time, by a Developer per module."),
        rules=rules.rules_for("activities"),
        primary_type=NodeType.ACTIVITY,
        readable_types=(NodeType.MODULE, NodeType.OBJECTIVE, NodeType.ASSESSMENT),
        relations=("C2", "C3", "C4"),
        docket={"edges": ("C2",), "gaps": ("C3", "C4", "P13")},
        readable_docs=("objective", "assessment"),
        submit_fields=(
            ("instructional_strategies", "object", True),
            ("non_instructional_strategies", "object", False),
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
        persona=("You are an expert content designer, responsible for the media and materials "
                 "each module's activities need."),
        intro=("Decide what form each module's content takes: the media that realise it. The "
               "materials themselves are produced one module at a time, after this."),
        rules=rules.rules_for("content"),
        primary_type=NodeType.MATERIAL,
        readable_types=(NodeType.MODULE, NodeType.ACTIVITY, NodeType.CONSTRAINT),
        readable_docs=("analysis", "objective", "activity"),
        submit_fields=(
            # REQUIRED, for the reason the two dev plans are (see the
            # assessment step) plus one of its own: an OPTIONAL artifact
            # gets at most ONE nudge, and a nudge is a turn the stage has to
            # REACH. MEASURED (run single_20260908_002508): the content stage
            # spent 9 of its 24 turns on repeated reads and gave up on "turn
            # budget exhausted" with `media_selections` never asked for. The media list is not decoration —
            # `dev_plans.render_material_set` derives BOTH the allowed "type"
            # values line AND the "each material's type is the media_type of
            # the selection it realizes" clause from it, and
            # `alignment.match_p6_realizes` builds its whole source set from
            # it. Empty, the Developer picks a type freely and EVERY material
            # violates P6 unconditionally: 0 media nodes, 15 materials, P6 30,
            # none of them repairable (P6 is `repairs.REPORT_ONLY`). Same on
            # runs single_20260901_151738/_154303/_162455/_205901 and
            # single_20260903_224852. The flag is half the fix — it changes
            # when the LOOP returns; `fanout._every_part_dispatch_done`
            # changes what SHIPS.
            ("media_selections", "array", True),
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
        intro=("Plan how this design is actually delivered: what instructors and operators "
               "need. You write the FRAMING here; the session-by-session guides are written "
               "afterwards, one module at a time, by a Developer per module."),
        rules=rules.rules_for("implementation"),
        primary_type=NodeType.SESSION_GUIDE,
        readable_types=(NodeType.MODULE, NodeType.ACTIVITY, NodeType.MATERIAL),
        relations=("P10", "P11"),
        docket={"gaps": ("P10", "P11")},
        readable_docs=("objective", "activity", "material"),
        # The framing artifacts alone. Which activities and materials a
        # session block delivers is already written on those artifacts
        # (`module_id` / `linked_module`), so `fanout._session_sets` derives
        # the division and every id lands in exactly one block whatever a
        # planner might have said.
        submit_fields=tuple((key, "object", True) for key in _IMPLEMENTATION_ARTIFACTS),
        validate=validate_implementation,
        commit=commit_implementation,
        commit_prose=commit_implementation_prose,
        view=view_implementation,
        view_prose=view_implementation_prose,
    ),
)


#: The one identity the ``agent_mode="single"`` arm reports for the whole run.
#: Identity names a ROLE, not a mechanism, so a trajectory consumer (the judge,
#: the webapp, the pooling scripts) reads one actor for the whole single-arm run
#: no matter how many loops it took.
SINGLE_IDENTITY = "SingleDesignerAgent"

#: The one persona the ``agent_mode="single"`` arm carries across every stage.
#: The multi arm's per-stage personas say the same thing scoped to one concern;
#: this says it once, unscoped. It is the ONLY prompt difference the axis
#: introduces — task text, rules, schema, tools and budgets are identical, and
#: ``test_ablation_flags`` pins that.
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
    landed = view_as_harness(step, state)
    return tuple(part for part in parts if not landed.get(part))


def commit_as_harness(commit, state, trajectory, section: dict) -> None:
    """Run a step's commit with its LOOKUPS booked to the orchestrator and its
    writes to whoever is acting: merging a submit into the section it belongs
    to reads that section first, and the graph observer would otherwise book
    the read to the agent whose submit it is — see
    ``AlignmentGraph.reads_as``."""
    reads_as = getattr(state, "reads_as", None)
    if reads_as is None:
        commit(state, trajectory, section)
        return
    with reads_as(ORCHESTRATOR):
        commit(state, trajectory, section)


def view_as_harness(step: AgenticStep, state) -> dict:
    """``step``'s view of the state, as a HARNESS probe: recorded as the
    orchestrator's read, not as one by whichever agent happens to be acting
    (``AlignmentGraph.reads_as``)."""
    if not hasattr(state, "element_nodes"):
        return step.view_prose(state)
    reads_as = getattr(state, "reads_as", None)
    if reads_as is None:
        return step.view(state)
    with reads_as(ORCHESTRATOR):
        return step.view(state)


def step_done(step: AgenticStep, state) -> bool:
    """Idempotence/produced guard. ``state`` is the AlignmentGraph in graph mode
    and the ProseStore in prose mode; the guard must mean the same thing in
    both, or a regen loop spins on one arm and not the other.

    A fan-out work set and a re-dispatch step declare ``done``; every stage submits
    one artifact per call, so a stage is finished when every REQUIRED artifact
    has arrived — not when its primary element pool is non-empty, which one
    artifact alone would satisfy."""
    if step.done is not None:
        return step.done(state)
    return not missing_parts(step, state)
