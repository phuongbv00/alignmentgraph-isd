"""The Developer tier: a family whose artifact is a LIST is produced one work
set at a time, not in one submit.

WHY THIS EXISTS. The artifact is the ``submit`` tool call's arguments, so one
call must carry the family's whole item list — and the ladder serves an 8192
completion cap. Measured on scenario IDLD-3226-V, the same arms with and
without this tier:

    learner_materials    38.5 -> 6.0      learning_activities  90.0 -> 6.0
    assessment_tools     15.0 -> 7.5      learner_materials    53.5 -> 4.0

Every arm, every family, down 50-93%: not a design choice, a token ceiling.

WHERE THE AXIS SITS. Both decomposition arms may split a family over several
calls; what differs is who divides the work and who writes each part:

  ``multi``  — the Designer's plan is normalized into work sets
               (``core/dev_plans.py``) and each set is a fresh context under
               that family's Developer identity. This arm spawns sub-agents.
  ``single`` — the one agent chooses its own batches and writes each itself,
               in the conversation it is already carrying; every batch goes
               through the same ``commit_sets`` and the same item rules
               (``output_errors``).

Equal call counts are NOT the parity requirement (an agent that plans its own
batches cannot spend the calls a harness-walked plan does); what is shared is
the normalization, the renumbering, the establishers and the per-item rules,
so the fan-out shape never depends on unvalidated SLM output.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Callable

from .. import dev_plans
from .. import rulebook as rules
from ..alignment_graph import NodeType
from . import tools
from .specialists import AgenticStep


@dataclass(frozen=True)
class SetOutput:
    """The one artifact list a Developer call produces. An assessment item
    carries its own scoring criteria as a field: splitting them cost one LLM
    call per item (measured: 32 calls per scenario, every arm) and asked a
    Developer to write criteria for an item it had not seen."""

    schema_key: str
    id_field: str
    rules: str
    element_type: str
    #: Id prefix this family's artifacts are numbered under ("AT", "TLA"),
    #: composed with the set ordinal by ``dev_plans._composite_id``.
    id_prefix: str
    #: (document key, list field) the prose arm writes this list under.
    doc_key: tuple[str, str]
    #: Fields holding references to OTHER artifacts of this same family, which
    #: the model writes as 1-based POSITIONS in the list it is submitting
    #: ([1] = the first artifact it wrote). The commit turns them into the ids
    #: it assigned — positional because the model does not write ids at all;
    #: see ``dev_plans.remap_and_tag`` for the measurement.
    self_ref_fields: tuple[str, ...] = ()
    #: Per-ITEM errors for this output, or None for "a non-empty list is
    #: enough". Read by BOTH arms (``set_step``'s validator and the single
    #: arm's ``ReactLoop._validate``, through :func:`output_errors`): a rule
    #: enforced on the Developer tier alone would be a rejection one side of
    #: the decomposition axis gets and the other does not.
    validate_items: Callable[[list], list[str]] | None = None


def output_errors(spec: "FanoutSpec", section: dict) -> list[str]:
    """Errors for whatever fan-out output a submit carries, in either arm.

    One implementation because the two arms submit the same artifacts by
    different routes: a Developer's own submit in ``multi``, a batch inside the
    stage submit in ``single``. Two copies would drift, and a drifted item rule
    is a rejection on one side of the axis only.
    """
    errors: list[str] = []
    for output in spec.outputs:
        items = (section or {}).get(output.schema_key)
        if items is None:
            continue
        if not isinstance(items, list):
            errors.append(f"{output.schema_key}: expected a list of items")
            continue
        if output.validate_items is not None:
            errors += output.validate_items(items)
    return errors


def session_guide_errors(guides: list) -> list[str]:
    """A session guide with prose but no ids schedules nothing.

    ``activity_ids`` is the field P10 is established from, and the rule the
    guides exist to satisfy is that between them they account for every
    activity in the design.
    """
    errors: list[str] = []
    for index, guide in enumerate(guides):
        if not isinstance(guide, dict):
            errors.append(f"session_guides[{index}]: expected an object")
            continue
        if not [r for r in (guide.get("activity_ids") or []) if str(r).strip()]:
            errors.append(
                f"session_guides[{index}].activity_ids: a session guide that names no "
                "activity ids schedules nothing — list the exact ids this session delivers")
    return errors


@dataclass(frozen=True)
class FanoutSpec:
    """How one family divides into work sets, and how each set is produced."""

    stage: str = ""
    #: Developer identity/persona for the ``multi`` arm. The ``single`` arm
    #: overrides both with its own, which is the whole axis.
    developer_identity: str = ""
    developer_persona: str = ""
    set_intro: str = ""
    #: Header the assignment slice is announced under. Verbatim the same four
    #: across families — a reader that keys on this header (the test
    #: fixture's per-set slicing) must see the same thing on either side of
    #: both ablation axes.
    set_header: str = "=== YOUR ASSIGNED SET ==="
    #: What one Developer call submits. More than one entry = one call
    #: produces several artifact lists at once.
    outputs: tuple[SetOutput, ...] = ()
    #: What a Developer of this family may READ, narrower than its stage's
    #: allowlist. A Developer is scoped: its assignment is rendered into its
    #: prompt, so the graph is background, not its working set.
    #:
    #: MEASURED (run single_20260901_151738): Developers were 95 of A0's 146
    #: calls, and MaterialDeveloper spent 54 calls on 10 work sets — only 10 of
    #: them submits. The other 44 were reads of topics, activities, objectives,
    #: edges and coverage gaps, none of which it was assigned to act on. A
    #: `coverage_gaps` answer in particular names gaps belonging to OTHER sets:
    #: it costs a turn to learn something this Developer cannot do anything
    #: about.
    developer_reads: tuple[str, ...] = ()
    #: Renders one work set into the assignment text its Developer reads.
    render: Callable[[dev_plans.WorkSet], str] = lambda ws: ""
    #: Derives the work sets from the state the dispatch stage just committed.
    plan_sets: Callable[..., tuple] = lambda state, parsed: ([], {})
    #: Has the DISPATCH hop produced? Distinct from ``step_done``, which asks
    #: whether the family's ITEMS exist — those now come from the Developer
    #: tier, so using the item pool as the dispatch guard would make the regen
    #: loop re-run the plan every time.
    dispatch_done: Callable[..., bool] = lambda state: True


def _lo_ids(state) -> list[str]:
    if hasattr(state, "element_nodes"):
        return [n["data"].get("id") for n in state.element_nodes(NodeType.OBJECTIVE)
                if n["data"].get("id")]
    return [lo.get("id") for lo in state.items("objective", "learning_objectives")
            if isinstance(lo, dict) and lo.get("id")]


#: Every ``plan_sets`` returns ``(work_sets, stats)``. ``stats`` is the
#: normalization record the ``dev_plan`` trajectory event carries; the
#: deterministic families report an equivalent one so the event shape does not
#: depend on which family produced it.
def _deterministic_stats(sets: list) -> dict:
    return {"set_count": len(sets), "pair_count": len(sets), "dropped_lo_refs": 0,
            "dropped_pairs": 0, "duplicate_pairs": 0, "appended_sets": 0,
            "fallback_used": False,
            # No model proposed this grouping.
            "source": "deterministic"}


def _assessment_sets(state, parsed: dict) -> tuple[list, dict]:
    plan = parsed.get("assessment_plan") or {}
    return dev_plans.normalize_assessment_dev_plan(
        parsed.get("dev_plan"), _lo_ids(state), plan.get("lo_coverage_targets") or {})


def _activity_sets(state, parsed: dict) -> tuple[list, dict]:
    return dev_plans.normalize_activity_dev_plan(
        parsed.get("dev_plan"), _lo_ids(state), items_by_lo(state))


def _material_sets(state, parsed: dict) -> tuple[list, dict]:
    sets = dev_plans.material_work_units(
        parsed.get("content_modules") or [], parsed.get("media_selections") or [],
        _constraints(state))
    return sets, _deterministic_stats(sets)


def items_by_lo(state) -> dict[str, list[str]]:
    """Which committed assessment items each objective already has.

    An activity set names the items its activities prepare for (``C4``), and a
    Developer told to prepare learners for AT-03 without being told what AT-03
    asks has to go and read it — the read cost ``_resolved_references`` exists
    to remove."""
    by_lo: dict[str, list[str]] = {}
    for item in _element_data(state, NodeType.ASSESSMENT, ("assessment", "assessment_tools")):
        lo_id = dev_plans._bare(str(item.get("aligned_objective") or ""))
        item_id = str(item.get("item_id") or "")
        if lo_id and item_id:
            by_lo.setdefault(lo_id, []).append(item_id)
    return by_lo


def _constraints(state) -> list[dict]:
    """The context constraints, which a material unit resolves for the media
    selections that declare ``respects_constraints``. Prose keeps them nested
    inside the analysis document rather than as their own element pool, which
    is why this does not go through :func:`_element_data`."""
    if hasattr(state, "element_nodes"):
        return [n["data"] for n in state.element_nodes(NodeType.CONSTRAINT)]
    context = (state.get("analysis") or {}).get("context_analysis") or {}
    return [c for c in (context.get("constraints") or []) if isinstance(c, dict)]


def _element_data(state, node_type: str, doc: tuple[str, str]) -> list[dict]:
    if hasattr(state, "element_nodes"):
        return [n["data"] for n in state.element_nodes(node_type)]
    return [i for i in state.items(*doc) if isinstance(i, dict)]


def _has_section(state, node_type: str, doc_key: str) -> bool:
    if hasattr(state, "element_nodes"):
        node = state.get_node(state.section_id(node_type))
        return bool((node or {}).get("data"))
    return bool(state.get(doc_key))


def _element_ids(state, node_type: str, doc: tuple[str, str], id_field: str = "id") -> list[str]:
    if hasattr(state, "element_nodes"):
        return [n["data"].get(id_field) for n in state.element_nodes(node_type)
                if n["data"].get(id_field)]
    return [i.get(id_field) for i in state.items(*doc)
            if isinstance(i, dict) and i.get(id_field)]


def _session_sets(state, parsed: dict) -> tuple[list, dict]:
    return dev_plans.normalize_implementation_dev_plan(
        parsed.get("dev_plan"),
        _element_ids(state, NodeType.ACTIVITY, ("activity", "learning_activities")),
        _element_ids(state, NodeType.MATERIAL, ("material", "learner_materials")))


def _every_part_dispatch_done(stage: str, state) -> bool:
    """Every artifact the stage DECLARES, not just its dispatch input.

    ``assessment`` and ``activities`` can afford a weaker gate ("the plan
    section exists") because their dispatch is one artifact plus its grouping.
    These two have more, so a gate that passes on one artifact lets a stage
    that lost another straight through.

    implementation: MEASURED on the partial-deposit fixture — ``monitoring``
    arrived as an empty dict five times, the dev plan landed on the sixth
    call, the regen loop broke on the plan alone, and the artifact shipped
    empty.

    content: MEASURED (run single_20260908_002508) — a gate that counted
    CONTENT nodes only let a stage that gave up on "turn budget exhausted"
    with MOD-01..08 and ZERO media selections through. ``dev_plans.material_work_units`` then built one unit per
    module with ``media_selections: []``, ``render_material_set`` dropped both
    of its media clauses, and ``alignment.match_p6_realizes`` had an empty
    source set: 15 materials, P6 30, every one of them unconditional. Making
    ``media_selections`` required fixes when the LOOP returns; only this fixes
    what SHIPS. The regen it triggers is narrow, not a second content stage —
    ``loop._run`` returns with zero LLM calls when the step is already done,
    the rebind offers only the missing artifact's submit, and
    ``_still_needed`` names what is already committed as not-to-resend."""
    from .specialists import STEPS, missing_parts

    step = next(s for s in STEPS if s.name == stage)
    return not missing_parts(step, state)


SPECS: dict[str, FanoutSpec] = {
    "assessment": FanoutSpec(
        stage="assessment",
        developer_identity="AssessmentDeveloperAgent",
        developer_persona=(
            "You are an expert instructional designer developing ONE assessment instrument set "
            "(ADDIE Development phase) — writing the actual items for exactly the objectives and "
            "plan categories your assigned set names, AND the scoring criteria that mark them. "
            "You are NOT responsible for any other objective or category; another Developer is "
            "handling those."),
        set_intro=("Write the actual items for YOUR ASSIGNED instrument set below, each with "
                   "the scoring criteria that mark it, inside the item's own ``rubric`` list."),
        outputs=(
            SetOutput(
                schema_key="assessment_tools", id_field="item_id",
                rules=rules.RULES_ASSESSMENT_ITEMS_SET + "\n" + rules.RULES_RUBRICS_ITEM,
                element_type=NodeType.ASSESSMENT, id_prefix="AT",
                doc_key=("assessment", "assessment_tools")),
        ),
        developer_reads=(NodeType.OBJECTIVE,),
        render=dev_plans.render_assessment_set, plan_sets=_assessment_sets,
        dispatch_done=lambda st: _has_section(st, NodeType.ASSESSMENT_PLAN, "assessment_plan")),
    "activities": FanoutSpec(
        stage="activities",
        developer_identity="ActivityDeveloperAgent",
        developer_persona=(
            "You are an expert instructional designer developing ONE block of learning activities "
            "(ADDIE Development phase) for exactly the objectives your assigned block names. You "
            "are NOT responsible for any other objective; another Developer is handling those."),
        set_intro="Write the actual learning activities for YOUR ASSIGNED block below.",
        set_header="=== YOUR ASSIGNED BLOCK ===",
        outputs=(
            SetOutput(
                schema_key="learning_activities", id_field="id",
                rules=rules.RULES_ACTIVITIES_SET,
                self_ref_fields=("prerequisite_activities",),
                element_type=NodeType.ACTIVITY, id_prefix="TLA",
                doc_key=("activity", "learning_activities")),
        ),
        developer_reads=(NodeType.OBJECTIVE, NodeType.ASSESSMENT),
        render=dev_plans.render_activity_set, plan_sets=_activity_sets,
        dispatch_done=lambda st: _has_section(st, NodeType.ACTIVITY_PLAN, "activity_plan")),
    "content": FanoutSpec(
        stage="content",
        developer_identity="MaterialDeveloperAgent",
        developer_persona=(
            "You are an expert instructional designer developing learner materials for ONE content "
            "module (ADDIE Development phase), realizing that module's media selections. You are "
            "NOT responsible for any other module; another Developer is handling those."),
        set_intro="Produce the actual materials for YOUR ASSIGNED module below.",
        set_header="=== YOUR ASSIGNED MODULE ===",
        outputs=(
            SetOutput(
                schema_key="learner_materials", id_field="id",
                rules=rules.RULES_MATERIALS_UNIT,
                element_type=NodeType.MATERIAL, id_prefix="MAT",
                doc_key=("material", "learner_materials")),
        ),
        developer_reads=(NodeType.CONTENT, NodeType.ACTIVITY),
        render=dev_plans.render_material_set, plan_sets=_material_sets,
        dispatch_done=lambda st: _every_part_dispatch_done("content", st)),
    "implementation": FanoutSpec(
        stage="implementation",
        developer_identity="SessionGuideDeveloper",
        developer_persona=(
            "You are an expert instructional designer writing the instructor's session guides "
            "for ONE block of the delivery (ADDIE Implementation phase) — the sessions your "
            "assigned block names, scheduling exactly the activities and materials it lists. "
            "You are NOT responsible for any other session; another Developer is handling "
            "those."),
        set_intro=("Write the session guides for YOUR ASSIGNED BLOCK below: what happens in each "
                   "session, and the exact ids it delivers and hands out."),
        set_header="=== YOUR ASSIGNED BLOCK ===",
        outputs=(
            SetOutput(
                schema_key="session_guides", id_field="id",
                rules=rules.RULES_SESSION_GUIDES_SET,
                validate_items=session_guide_errors,
                element_type=NodeType.SESSION_GUIDE, id_prefix="SG",
                doc_key=("implementation_plan", "session_guides")),
        ),
        developer_reads=(NodeType.ACTIVITY, NodeType.MATERIAL),
        render=dev_plans.render_session_set, plan_sets=_session_sets,
        dispatch_done=lambda st: _every_part_dispatch_done("implementation", st)),
}


#: Said once, in every Developer's own prompt. The read tools stay — a Developer
#: is an agent and may look at whatever it judges it needs — but the assignment
#: now resolves every artifact it names, and a Developer that does not know that
#: reads them anyway. MEASURED (run single_20260901_171408): 22 of 33 Developer
#: calls were reads, 11 of the 67 judge-visible calls were exact duplicates, and
#: the arm scored 18/25 on the judge's redundancy dimension against react-isd's
#: 25 with everything visible to it.
_ASSIGNMENT_IS_COMPLETE = (
    "Everything your assignment names is written out below — in full where you have to work "
    "from the artifact itself (the objectives, the items, the modules), and as one line per "
    "item where your job is to name ids (the activities and materials a session block "
    "schedules). You do not need to look them up. Use the read tools only for something your "
    "assignment does NOT name, or when one line is not enough.")

#: Cap on the rendered assignment a Developer is handed: an uncapped slice
#: over a family that committed many items can exceed the serving context on
#: its own (measured on the fixture: a 39k-character stage message against a
#: 16k-token window), and the protocol and rules blocks sit on top of it.
ASSIGNMENT_CHAR_CAP = 6000


def _resolved_references(work_set: dev_plans.WorkSet, state) -> str:
    """The artifacts a work set NAMES, rendered into its assignment.

    MEASURED (run single_20260901_162455): the assignment gave objective IDs
    only — "ILO-01 x formative" — so every Developer had to read the objectives
    to learn what ILO-01 actually says. Four AssessmentDevelopers therefore
    issued four identical `read_nodes(objective)` calls, and the BFCL judge,
    which sees a flat call list with no notion of WHO is calling, scored the
    arm 18.0 on redundancy_avoidance against react-isd's 23.0 — the whole of
    its trajectory deficit.

    Those reads were our design, not the model's: a Developer cannot be told to
    write items for ILO-01 and not be told what ILO-01 says. Resolving the
    references into the assignment is also exactly the scoped "context slice"
    the method section claims each specialist gets."""
    if state is None:
        return ""
    blocks = [
        _resolve(state, label, node_type, doc, ids, id_field, compact=compact)
        for node_type, label, doc, ids, id_field, compact in _reference_blocks(work_set)
    ]
    return "".join(b for b in blocks if b)


def _reference_blocks(work_set: dev_plans.WorkSet) -> tuple[tuple, ...]:
    """What a work set's assignment resolves, declared ONCE.

    Read twice: to render the block, and to answer a Developer that reads the
    same pool anyway with a pointer to where it already has it. Two lists would
    drift, and a pointer naming a heading the assignment does not carry is
    worse than no pointer.
    """
    return (
        (NodeType.OBJECTIVE, "The objectives your set names",
         ("objective", "learning_objectives"), work_set.objectives, "id", False),
        # An activity set names the assessment items its activities prepare for,
        # BY ID. A Developer told to prepare learners for AT-03 and not told what
        # AT-03 asks has no choice but to go and read it.
        (NodeType.ASSESSMENT, "The assessment items your set prepares learners for",
         ("assessment", "assessment_tools"),
         tuple(work_set.payload.get("assessment_items") or ()), "item_id", False),
        # A session block schedules activities and materials by id, and it
        # schedules MANY of them — that is the whole reason this family fans
        # out. So these two are rendered COMPACT: one line each, the same row
        # ``read_nodes`` answers with. Rendered whole they are also the two
        # longest artifacts the harness writes (a material's ``content`` is a
        # learner-facing script), and a block of 27 of them would blow through
        # ``ASSIGNMENT_CHAR_CAP`` and be truncated — which loses ids, and a
        # scheduled artifact whose id never reaches its Developer is a P10/P11
        # gap by construction. What a guide needs is which activity is which;
        # ``read_node`` is still bound for one that needs more.
        (NodeType.ACTIVITY, "The activities your block delivers",
         ("activity", "learning_activities"),
         tuple(work_set.payload.get("activity_ids") or ()), "id", True),
        (NodeType.MATERIAL, "The materials your block hands out",
         ("material", "learner_materials"),
         tuple(work_set.payload.get("material_ids") or ()), "id", True),
    )


def resolved_labels(work_set: dev_plans.WorkSet) -> dict[str, str]:
    """``node_type -> heading`` for the pools this assignment renders in full."""
    return {str(node_type): label
            for node_type, label, _doc, ids, _f, _c in _reference_blocks(work_set) if ids}


def _resolve(state, label: str, node_type: str, doc: tuple[str, str],
             ids: tuple, id_field: str, *, compact: bool = False) -> str:
    """Render the artifacts named by ``ids``, in whichever state this arm holds.

    ``compact`` renders one LINE per artifact instead of its whole JSON, for a
    pool a work set names by the dozen. Both substrates go through
    ``tools.render_listing``: the prose items are the same dicts the graph
    holds as ``data``, so wrapping them as nodes gives the two arms
    byte-identical assignment text rather than a listing on one side and a
    JSON dump on the other — a difference that would sit on the
    ``context_mode`` axis instead of on the substrate.
    """
    if not ids:
        return ""
    wanted = {dev_plans._bare(i) for i in ids}
    if hasattr(state, "element_nodes"):
        nodes = [n for n in state.element_nodes(node_type)
                 if dev_plans._bare(n["data"].get(id_field, "")) in wanted]
    else:
        nodes = [{"type": str(node_type), "id": f"{node_type}:{i.get(id_field)}", "data": i}
                 for i in state.items(*doc)
                 if isinstance(i, dict) and dev_plans._bare(i.get(id_field, "")) in wanted]
    if not nodes:
        return ""
    rendered = (tools.render_listing(nodes) if compact
                else tools.render_nodes(nodes) if hasattr(state, "element_nodes")
                else "\n".join(json.dumps(n["data"], ensure_ascii=False)[:tools.NODE_CHAR_CAP]
                                for n in nodes))
    return f"\n\n{label}:\n{rendered}" if rendered.strip() else ""


def set_step(spec: FanoutSpec, work_set: dev_plans.WorkSet, base: AgenticStep,
             state=None) -> AgenticStep:
    """An :class:`AgenticStep` for one work set, so the ordinary ToolLoop runs it.

    The assignment slice goes in the INTRO rather than as injected context: it
    is what this Developer was asked to do, not background it may consult. Read
    tools stay whatever the family's stage allows — a Developer still needs to
    see the objectives it is writing for."""
    primary = spec.outputs[0].schema_key

    def validate(parsed: dict) -> list[str]:
        items = (parsed or {}).get(primary)
        if not isinstance(items, list) or not items:
            return [f"{primary} must be a non-empty list"]
        return output_errors(spec, parsed)

    return replace(
        base,
        name=f"{spec.stage}:{work_set.set_id}",
        identity=spec.developer_identity,
        persona=spec.developer_persona,
        intro=(f"{spec.set_intro}\n\n{_ASSIGNMENT_IS_COMPLETE}\n\n{spec.set_header}\n"
               f"{_capped(spec.render(work_set) + _resolved_references(work_set, state))}"),
        rules="\n".join(o.rules for o in spec.outputs),
        submit_fields=tuple((o.schema_key, "array", i == 0)
                            for i, o in enumerate(spec.outputs)),
        # No docket and a narrowed read scope: coverage gaps belong to whoever
        # plans the sets, not to one Developer inside a set it did not choose.
        docket={},
        readable_types=spec.developer_reads,
        resolved_labels=resolved_labels(work_set),
        relations=(),
        validate=validate,
        commit=lambda *_a, **_k: None,       # committing is the driver's job,
        commit_prose=lambda *_a, **_k: None,  # right after this loop returns
        commits_to_state=False,
        # THIS set's items, not the family's pool: siblings are committing into
        # the same pool as they finish, so the default guard would call this
        # set done before its Developer had spoken.
        done=lambda state, _sid=work_set.set_id: _sid in committed_set_ids(spec, state),
    )


def _capped(assignment: str) -> str:
    if len(assignment) <= ASSIGNMENT_CHAR_CAP:
        return assignment
    return assignment[:ASSIGNMENT_CHAR_CAP] + "\n… (assignment truncated)"


def committed_set_ids(spec: FanoutSpec, state) -> set[str]:
    """Set ids already present in the state — the re-entrancy guard that lets
    the outer regen loop retry ONLY the sets that came back empty."""
    primary = spec.outputs[0]
    if hasattr(state, "element_nodes"):
        return {n["data"].get("plan_set") for n in state.element_nodes(primary.element_type)
                if n["data"].get("plan_set")}
    key, field_name = primary.doc_key
    return {i.get("plan_set") for i in state.items(key, field_name)
            if isinstance(i, dict) and i.get("plan_set")}


def _ids_already_held(state, output: SetOutput) -> frozenset[str]:
    """The ids this output's pool already carries, so a per-set commit bumps a
    colliding id instead of overwriting the set that got there first."""
    if hasattr(state, "element_nodes"):
        return frozenset(
            str(n["data"].get(output.id_field) or "")
            for n in state.element_nodes(output.element_type))
    key, field_name = output.doc_key
    return frozenset(
        str(item.get(output.id_field) or "")
        for item in ((state.get(key) or {}).get(field_name) or [])
        if isinstance(item, dict))


def commit_sets(spec: FanoutSpec, state, trajectory, work_sets: list, payloads: list) -> None:
    """Deposit one family's fanned-out artifacts, then establish their relations.

    The id remapping is ``dev_plans.remap_and_tag``, shared by both ablation
    arms, so identical payloads leave identical state. Each output list is
    remapped on its own — ids collide within a list, never across two different
    artifact types.

    Callable per set or for a whole batch. Per set is what the multi arm does
    now, so a Developer's work is in the design state — and therefore visible
    to the checks — while the family's Designer still has its loop open and
    can be asked to re-plan around what is missing. The ids already in the
    state are handed to the remapper as ``taken``, or the second set's
    ``AT-01`` would overwrite the first's rather than being bumped.

    The whole deposit runs inside one graph transaction: reading the ids in
    play and then writing nodes chosen from what was read is only correct if
    nothing lands in between. Sequential today, so nothing does — the lock is
    what keeps that true if the fan-out ever stops being sequential."""
    with _deposit(state):
        _deposit_sets(spec, state, trajectory, work_sets, payloads)


def _deposit(state):
    from contextlib import nullcontext

    transaction = getattr(state, "transaction", None)
    return transaction() if callable(transaction) else nullcontext()


def _deposit_sets(spec: FanoutSpec, state, trajectory, work_sets: list,
                  payloads: list) -> None:
    committed: dict[str, list[str]] = {}
    for output in spec.outputs:
        merged = dev_plans.remap_and_tag(
            work_sets, [{"set_id": p.get("set_id", ""),
                         "items": p.get(output.schema_key) or []} for p in payloads],
            id_field=output.id_field, self_ref_fields=output.self_ref_fields,
            id_prefix=output.id_prefix, taken=_ids_already_held(state, output))
        if not merged:
            continue
        if not hasattr(state, "element_nodes"):
            key, field_name = output.doc_key
            doc = state.get(key) or {}
            updated = {**doc, field_name: (doc.get(field_name) or []) + merged}
            state.put(key, updated)
            trajectory.log_doc_write(key, updated)
            continue
        node_ids = []
        for item in merged:
            raw_id = item.get(output.id_field)
            if not raw_id:
                continue
            node_id = state.add_element_node(output.element_type, str(raw_id), dict(item))
            node_ids.append(node_id)
            trajectory.log_node_edit("add", node_id, output.element_type)
        committed[output.schema_key] = node_ids

    if not hasattr(state, "element_nodes"):
        return
    _establish(spec, state, committed)



def _establish(spec: FanoutSpec, state, committed: dict[str, list[str]]) -> None:
    """Alignment relations for a family's freshly committed artifacts."""
    from ..alignment_graph import alignment

    if spec.stage == "assessment":
        alignment.match_id_reverse(state, "C2", field="aligned_objective")
        alignment.match_p3_realizes(state)
    elif spec.stage == "activities":
        alignment.match_list_reverse(state, "C3", field="aligned_objectives")
        alignment.match_list(state, "C4", field="prepares_for_assessment")
        plan_id = state.section_id(NodeType.ACTIVITY_PLAN)
        node_ids = committed.get("learning_activities", [])
        if state.get_node(plan_id):
            for node_id in node_ids:
                alignment.record_provenance(state, "P4", [plan_id], node_id)
        for node_id in node_ids:
            node = state.get_node(node_id)
            for prereq in (node or {}).get("data", {}).get("prerequisite_activities", []) or []:
                source = f"{NodeType.ACTIVITY}{state.ELEMENT_SEP}{prereq}"
                if state.get_node(source):
                    state.add_edge("precedes", source, node_id, relation_id="",
                                   established_by="id", evidence=str(prereq))
    elif spec.stage == "implementation":
        alignment.establish_delivery(state, committed.get("session_guides", []))
        # The plan section holds the guide's FRAMING and the guides are its
        # elements, which is exactly what `narrates` is for. Without it
        # `implementation_plan_0` is an edgeless island — the thing P10/P11
        # were added to stop, back when they hung off the section itself.
        state.link_section_narrative(NodeType.IMPLEMENTATION_PLAN,
                                     NodeType.SESSION_GUIDE)
    elif spec.stage == "content":
        for node_id in committed.get("learner_materials", []):
            data = state.get_node(node_id)["data"]
            ref = alignment.bare_ref(data.get("linked_module", ""))
            module_id = f"{NodeType.CONTENT}{state.ELEMENT_SEP}{ref}" if ref else ""
            if ref and state.get_node(module_id):
                alignment.record_provenance(state, "P5", [module_id], node_id)
        alignment.match_p6_realizes(state)
