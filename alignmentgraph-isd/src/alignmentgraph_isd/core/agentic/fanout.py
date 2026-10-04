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

Equal call counts are NOT the parity requirement — an agent planning its own
batches cannot spend what a harness-walked plan does. What is shared is the
normalization, the renumbering, the establishers and the per-item rules.
"""
from __future__ import annotations

import re

import json
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from typing import Callable

from .. import dev_plans
from .. import rulebook as rules
from ..aggregate import _tasks_with_items as _join_tasks
from ..alignment_graph import NodeType, alignment
from ..checks import _ALL_BLOOM_VERBS, described_levels
from ..trajectory import ORCHESTRATOR
from . import tools
from .protocol import ITEM_RESTATES_OBJECTIVE
from .specialists import STEPS, AgenticStep, declared_required_errors, missing_parts


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
    #: When set, this output is a FIELD of a PARENT element node rather than
    #: a pool of nodes of its own: the item names its parent in this field and
    #: the commit files it there. The reason is the one that made a rubric
    #: criterion a field of its item — nothing but the parent owns it — and
    #: the payoff is that membership stops being an id a Developer can get
    #: wrong.
    parent_field: str = ""
    parent_list: str = "items"
    #: Per-ITEM errors for this output, or None for "a non-empty list is
    #: enough". Read by BOTH arms (``set_step``'s validator and the single
    #: arm's ``ReactLoop._validate``, through :func:`output_errors`): a rule
    #: enforced on the Developer tier alone would be a rejection one side of
    #: the decomposition axis gets and the other does not.
    validate_items: Callable[[list], list[str]] | None = None
    #: ``field -> element type`` for every field of this artifact that
    #: references ANOTHER family by id. Declarative, because the check is one
    #: rule over all of them: the id must name something that exists.
    ref_fields: tuple[tuple[str, str], ...] = ()
    #: The ``ref_fields`` every item must NAME something in, whenever the
    #: design holds anything of that type to name. Conditional rather than a
    #: schema ``required``, because a design with no such element leaves the
    #: field nothing it could hold.
    required_refs: tuple[str, ...] = ()


def _section_doc(state, node_type: str, doc_key: str) -> dict:
    """One section document, off the graph or off the blackboard."""
    if hasattr(state, "element_nodes"):
        return ((state.get_node(state.section_id(node_type)) or {}).get("data")) or {}
    return state.get(doc_key) or {}


def known_ids(state) -> dict[str, list[str]]:
    """``element type -> the ids that exist``, identically on either substrate.

    What a submit-time reference check compares against. Objectives and modules
    come from the element pool, which both substrates key by ``id``. The
    assessment pool comes from the PLAN that declares the tasks, not from the
    element pool: the graph arm's ``ASSESSMENT`` nodes ARE the tasks, but the
    blackboard keeps ``assessment_tools`` as a flat list of questions keyed by
    ``item_id``, so reading the pool would hand the two arms different facts
    and refuse in one arm what it accepts in the other.
    """
    plan = _section_doc(state, NodeType.ASSESSMENT_PLAN, "assessment_plan")
    pools = {
        NodeType.OBJECTIVE: _element_ids(
            state, NodeType.OBJECTIVE, ("objective", "learning_objectives")),
        NodeType.MODULE: _element_ids(
            state, NodeType.MODULE, ("module", "course_modules")),
        NodeType.ASSESSMENT: [t.get("id") for t in dev_plans.plan_tasks(plan)],
        NodeType.ACTIVITY: _element_ids(
            state, NodeType.ACTIVITY, ("activity", "learning_activities")),
        NodeType.MATERIAL: _element_ids(
            state, NodeType.MATERIAL, ("material", "learner_materials")),
    }
    # An id we could not read is not an id to measure against: where a pool is
    # empty the check stands down rather than refusing everything.
    return {kind: [str(one) for one in ids if str(one or "").strip()]
            for kind, ids in pools.items()}


def reference_errors(list_key: str, items: list, ref_fields, known) -> list[str]:
    """A reference must name something that EXISTS.

    ``_names_its`` refuses an item that names nothing; this refuses one that
    names nothing REAL, which is the same objection one step along and the
    same moment to raise it — while the author is still in the conversation.
    MEASURED (run 43c4ca5e): 12 of 18 activities wrote an ``aligned_objectives``
    that resolves to no objective — ``evaluate``, ``LO-003`` against
    ``ILO-003``, and one block that wrote the objective's whole statement as
    its id — so C3, a core relation, was established for 6 activities out of
    18 and all 14 findings died with ``shown_to_agent = 0``.

    What it does NOT do is choose the right id: a reference that resolves to
    two elements is left alone, and an artifact naming a real objective it has
    nothing to do with passes. C3 still fails for an objective nobody
    practises, which is what it is there to measure. Matching is
    ``alignment.matches_ref``, the same tolerance the establisher resolves
    with, so the validator cannot refuse a spelling the edge would accept.

    Refused only when NOTHING in the field resolves, which is exactly when the
    establisher reports a gap (``alignment.match_list``: one edge per resolved
    reference, "a violation only if NONE resolve"). A field of four ids two of
    which are real still builds its edges, so refusing it would make the
    contract shown stricter than the one the artifact is judged against — the
    same defect ``required_floor`` exists to prevent, in the other direction.
    An empty field is ``_names_its``'s question, not this one.
    """
    errors: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        for field, node_type in ref_fields:
            pool = (known or {}).get(node_type)
            if not pool:
                continue            # nothing to compare against: not our finding
            raw = item.get(field)
            refs = [one for one in (raw if isinstance(raw, list) else [raw])
                    if str(one or "").strip()]
            if not refs or any(alignment.matches_ref(pool, node_type, one) for one in refs):
                continue
            named = ", ".join(repr(str(one)[:40]) for one in refs[:3])
            errors.append(
                f"{list_key}[{index}].{field}: {named} "
                f"name{'s' if len(refs) == 1 else ''} no {node_type} that exists — "
                f"write one of these ids: {', '.join(sorted(pool)[:8])}")
    return errors


def missing_reference_errors(output: "SetOutput", items: list, known) -> list[str]:
    """An item that leaves a ``required_refs`` field EMPTY while the design
    holds something it could name.

    ``reference_errors`` judges a reference that is there; this is the one
    that is not. MEASURED (run t1 20261002_134550): the rule told every
    activity to list ``prepares_for_assessment`` and nothing held it to that —
    of the activity Developers' submits, 169 of 175 (graph) and 70 of 76
    (prose) arrived without the field, mostly under a fused key whose value
    was not a list, and C4 was then written by the deterministic net on one
    arm and not at all on the other."""
    errors: list[str] = []
    for field, node_type in output.ref_fields:
        pool = (known or {}).get(node_type)
        if field not in output.required_refs or not pool:
            continue
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            raw = item.get(field)
            if any(str(one or "").strip() for one in (raw if isinstance(raw, list) else [raw])):
                continue
            errors.append(
                f"{output.schema_key}[{index}].{field}: required — name at least one "
                f"{node_type} by id: {', '.join(sorted(pool)[:8])}")
    return errors


def output_errors(spec: "FanoutSpec", section: dict, known: dict | None = None, *,
                  levels: dict[str, str] | None = None,
                  committed_best: dict[str, int] | None = None,
                  statements: dict[str, str] | None = None) -> list[str]:
    """Errors for whatever fan-out output a submit carries, in either arm.

    One implementation because the two arms submit the same artifacts by
    different routes: a Developer's own submit in ``multi``, a batch inside the
    stage submit in ``single``. Two copies would drift, and a drifted item rule
    is a rejection on one side of the axis only.

    ``known`` is the id snapshot :func:`reference_errors` compares against
    (:func:`known_ids`). Both arms pass it, from the state each already holds:
    the rule has to be stated over the DESIGN rather than over an assignment,
    because the single arm has no assignment and a rule only one arm can break
    would be a second variable on the decomposition axis. ``levels`` and
    ``committed_best`` are the same kind of snapshot for
    :func:`item_level_errors` (:func:`objective_levels`,
    :func:`committed_item_levels`), and ``statements`` for
    :func:`item_restatement_errors` (:func:`objective_statements`).
    """
    errors: list[str] = []
    for output in spec.outputs:
        items = (section or {}).get(output.schema_key)
        if items is None:
            continue
        if not isinstance(items, list):
            errors.append(f"{output.schema_key}: expected a list of items")
            continue
        # The declared floor, per item — the fields the rubric reads (an
        # activity's duration and materials, a guide's objectives and prose)
        # were empty in half or more of the items while optional.
        for index, item in enumerate(items):
            errors += declared_required_errors(
                output.schema_key, item, f"{output.schema_key}[{index}]")
        if output.validate_items is not None:
            errors += output.validate_items(items)
        if output.ref_fields and known:
            errors += reference_errors(output.schema_key, items, output.ref_fields, known)
            errors += missing_reference_errors(output, items, known)
        if levels and output.element_type == NodeType.ASSESSMENT:
            errors += item_level_errors(items, levels, committed_best)
        if statements and output.element_type == NodeType.ASSESSMENT:
            errors += item_restatement_errors(items, statements)
    return errors


def _names_its(field_name: str, list_key: str, what: str) -> Callable[[list], list[str]]:
    """An item validator: every item must say which ``what`` it belongs to.

    Only that it SAYS so. Whether the id exists is a check's question
    (P13) — a validator has no state to ask — but an
    item that names nothing can be refused here, while its author is still in
    the conversation, instead of becoming a finding nobody can attribute."""
    def errors(items: list) -> list[str]:
        return [f"{list_key}[{index}].{field_name}: name the {what} this belongs to, "
                "by one of the ids you were given"
                for index, item in enumerate(items)
                if isinstance(item, dict) and not str(item.get(field_name) or "").strip()]
    return errors


def assessment_item_errors(items: list) -> list[str]:
    """An item names its set, and every criterion it carries says what
    each grade looks like.

    The second half is ``rubric_consistency`` asked while its author is still
    in the conversation. After the fan-out nobody is: a Developer's loop has
    closed and the Designer's next turn, if it gets one, is a plan. MEASURED
    (runs aef73e0a, 40856c96, b8576814, 53a9cd1a): 11, 2, 6 and 2
    ``rubric_consistency`` findings, 20 of the 21 with ``shown_to_agent = 0``
    and every one still open at the end of its run. Only MISSING levels are
    refused here — whether the words in them are good enough stays the
    check's."""
    errors = _names_its("task_id", "assessment_tools", "assessment task")(items)
    for index, item in enumerate(items):
        for position, criterion in enumerate((item or {}).get("rubric") or []
                                             if isinstance(item, dict) else []):
            if isinstance(criterion, dict) and len(described_levels(criterion)) < 2:
                errors.append(
                    f"assessment_tools[{index}].rubric[{position}].levels: say what an "
                    "excellent, a satisfactory and a needs_improvement answer each show, "
                    "one full sentence each")
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
    set_header: str = "=== YOUR ASSIGNMENT ==="
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


def course_modules(state) -> list[dict]:
    """The course's modules, in course order, from either substrate. They are
    written by the outcomes stage and are the key every family here divides
    its work by; the prose arm keeps them in the objective document, beside
    the objectives they group."""
    if hasattr(state, "element_nodes"):
        return [n["data"] for n in state.element_nodes(NodeType.MODULE)]
    return [m for m in state.items("objective", "course_modules") if isinstance(m, dict)]


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


def _derived_stats(stats: dict) -> dict:
    """The normalization record for a grouping NO MODEL PROPOSED.

    ``appended_sets`` and ``duplicate_pairs`` still count, because the
    normalizer still cuts the derived grouping at module boundaries and
    batches what one call cannot hold — but ``source`` is the honest label
    and ``fallback_used`` is false: there was no plan to fall back FROM."""
    return {**stats, "source": "deterministic", "fallback_used": False}


def cap_module_minutes(state, ceiling_minutes: float, trajectory) -> dict[str, int]:
    """Hold the modules' minutes together to the course's ceiling, on either
    substrate, right after the outcomes stage writes them.

    The Outcome Designer's own ``minutes`` are never rewritten: where the
    modules together exceed the ceiling each gains ``minutes_effective``
    (``dev_plans.effective_minutes``), which is what every time-bounded
    family reads (``dev_plans.module_minutes``). Returns what was written,
    empty when the modules fit."""
    modules = course_modules(state)
    capped = dev_plans.effective_minutes(modules, ceiling_minutes)
    if not capped:
        return {}
    if hasattr(state, "element_nodes"):
        for node in state.element_nodes(NodeType.MODULE):
            mid = dev_plans._bare(node["data"].get("id"))
            if mid in capped:
                state.update_node(node["id"], {"minutes_effective": capped[mid]})
    else:
        doc = dict(state.get("objective") or {})
        doc["course_modules"] = [
            ({**m, "minutes_effective": capped[dev_plans._bare(m.get("id"))]}
             if isinstance(m, dict) and dev_plans._bare(m.get("id")) in capped else m)
            for m in (doc.get("course_modules") or [])]
        state.put("objective", doc)
        trajectory.log_doc_write("objective", doc)
    written = sum(dev_plans._positive(m.get("minutes")) for m in modules)
    trajectory.log_recovery_event(
        ORCHESTRATOR, "module_minutes_capped",
        f"{len(capped)} modules, {written:g} minutes written against {ceiling_minutes:g}",
        ", ".join(f"{mid}={minutes}" for mid, minutes in capped.items()))
    return capped


def objective_levels(state) -> dict[str, str]:
    """``objective id -> its declared Bloom level``, identically on either
    substrate. What a light assignment reads to fix each item's and each
    activity's cognitive level: the objectives' OWN word, never the harness's."""
    return {
        str(one["id"]): str(one.get("level") or "").strip().lower()
        for one in _element_data(state, NodeType.OBJECTIVE, ("objective", "learning_objectives"))
        if one.get("id")
    }


def committed_item_levels(state) -> dict[str, int]:
    """``objective id -> the highest declared level of any committed item
    aligned to it``, on either substrate: the graph arm's tasks carry their
    items, the blackboard keeps the questions flat. What
    :func:`item_level_errors` counts beside a submit, so an objective already
    measured at its level is not refused another, lower item."""
    from ..alignment_graph import alignment  # noqa: PLC0415  (a leaf; no cycle)
    best: dict[str, int] = {}
    for entry in _element_data(state, NodeType.ASSESSMENT, ("assessment", "assessment_tools")):
        for item in (entry.get("items") or [entry]):
            if not isinstance(item, dict):
                continue
            lo = dev_plans._bare(str(item.get("aligned_objective") or ""))
            level = alignment.bloom_level_of(item.get("required_cognitive_process"))
            if lo and level is not None:
                best[lo] = max(best.get(lo, -1), level)
    return best


def item_level_errors(items: list, levels: dict[str, str],
                      committed_best: dict[str, int] | None = None) -> list[str]:
    """An objective whose items ALL sit below its own level is not measured.

    The rule ``bloom_mismatch_assessment`` applies after the fact — the highest
    declared ``required_cognitive_process`` of an objective's items against the
    objective's ``level`` — asked at submit, while the author is still in the
    conversation. Counts THIS submit together with what the design already
    holds for the objective, so a batch adding one more low item to an
    objective measured at its level is not refused. Stated over the DESIGN,
    never over an assignment, so both arms are held to it identically; an
    objective with no readable level, or one this submit does not align to,
    is not judged."""
    from ..alignment_graph import alignment  # noqa: PLC0415  (a leaf; no cycle)
    best: dict[str, int] = dict(committed_best or {})
    first_index: dict[str, int] = {}
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        lo = dev_plans._bare(str(item.get("aligned_objective") or ""))
        if not lo:
            continue
        first_index.setdefault(lo, index)
        level = alignment.bloom_level_of(item.get("required_cognitive_process"))
        if level is not None:
            best[lo] = max(best.get(lo, -1), level)
    errors: list[str] = []
    for lo, index in first_index.items():
        wanted = alignment.bloom_level_of(levels.get(lo))
        if wanted is None or best.get(lo, -1) >= wanted:
            continue
        name = alignment.bloom_level_name(wanted)
        formats = (", ".join(dev_plans.OPEN_RESPONSE_TYPES)
                   if wanted >= alignment.bloom_level_of("apply") else "any type")
        errors.append(
            f"assessment_tools[{index}].required_cognitive_process: {lo} states "
            f"{alignment.a_level(name)}-level performance and none of your item(s) for it "
            f"reaches {name} — set one item's "
            f"required_cognitive_process to '{name}' in a type that carries it ({formats}), "
            "or write one that does")
    return errors


def objective_statements(state) -> dict[str, str]:
    """``objective id -> its statement``, identically on either substrate.
    What :func:`item_restatement_errors` compares a question against."""
    return {
        str(one["id"]): str(one.get("statement") or "").strip()
        for one in _element_data(state, NodeType.OBJECTIVE, ("objective", "learning_objectives"))
        if one.get("id")
    }


#: The two shares that together say a question IS its objective's sentence:
#: the longest verbatim run of the objective's words inside the question, over
#: the objective's length, and the question's content words that come from the
#: objective, over the question's. Harness parameters, set on the tune slice
#: (runs train_10_*_20260923..0925, 1,674 items): at (0.5, 0.6) the rule takes
#: 70 of alignmentgraph-isd's 981 items and 1 of react-isd's 693, and every one
#: read by hand was the objective copied with a clause appended; either share
#: alone also took scenario-based questions that name the objective's topic.
RESTATEMENT_RUN = 0.5
RESTATEMENT_SHARE = 0.6
#: An objective this short is mostly its topic, and a question about the
#: topic would restate it by necessity.
RESTATEMENT_MIN_WORDS = 4

_LEARNER_LEAD = re.compile(
    r"^\s*(?:the\s+)?(?:learners?|participants?|students?|trainees?|teachers?)\s+"
    r"(?:will|can|should|are able to)\s+(?:be able to\s+)?", re.IGNORECASE)
_WORD = re.compile(r"[a-z0-9][a-z0-9'-]*")
_STOPWORDS = frozenset("""
    about above across after against along among and any are around based been before being
    between both but can could does each either every few following for from given has have
    how into its many may might more most much must not other our over own per same should
    some such than that the their them then there these they this those through toward under
    upon using very was were what when where which who whom whose why will with within without
    would your
""".split())


def _words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def _content_words(text: str) -> set[str]:
    return {word for word in _words(text)
            if len(word) >= 3 and word not in _STOPWORDS and word not in _ALL_BLOOM_VERBS}


def restatement_shares(question: str, statement: str) -> tuple[float, float]:
    """``(verbatim run over the objective, question words from the objective)``."""
    objective = _words(_LEARNER_LEAD.sub("", statement))
    asked = _words(question)
    if not objective or not asked:
        return 0.0, 0.0
    run = SequenceMatcher(None, objective, asked, autojunk=False).find_longest_match(
        0, len(objective), 0, len(asked)).size
    content = _content_words(question)
    shared = content & _content_words(" ".join(objective))
    return run / len(objective), (len(shared) / len(content) if content else 0.0)


def item_restatement_errors(items: list, statements: dict[str, str]) -> list[str]:
    """A question that is its objective's own sentence measures nothing.

    ``RULES_ASSESSMENT_ITEMS*`` already say never to restate an objective's
    wording; this holds the submit to it, while the author is still in the
    conversation. MEASURED on the tune slice: at 2B up to 26 of 58 objectives
    had a best-matching item copied from the statement, several at cosine 0.99,
    so the objective-assessment signal read the copy as correspondence. Refuses
    only both at once — a long verbatim run AND a question made mostly of the
    objective's words (see :data:`RESTATEMENT_RUN`) — so a case-based question
    naming the objective's topic passes. Stated over the DESIGN, never over an
    assignment, so both arms are held to it identically; an item naming no
    objective with a readable statement is not judged."""
    errors: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        lo = dev_plans._bare(str(item.get("aligned_objective") or ""))
        statement = statements.get(lo, "")
        if len(_words(_LEARNER_LEAD.sub("", statement))) < RESTATEMENT_MIN_WORDS:
            continue
        run, share = restatement_shares(str(item.get("question") or ""), statement)
        if run >= RESTATEMENT_RUN and share >= RESTATEMENT_SHARE:
            errors.append(ITEM_RESTATES_OBJECTIVE.format(index=index, lo=lo))
    return errors


def _assessment_sets(state, parsed: dict, mode: str = "full") -> tuple[list, dict]:
    """One work set per INSTRUMENT of the blueprint.

    The set is what an assessment designer actually divides by — a
    Developer writes the items of one quiz or one practical — and it is a
    real artifact of the design, so the grouping needs no separate plan to
    state it. Its ``item_counts`` already say how many items, and
    ``_item_batches`` splits a set too large for one call."""
    plan = parsed.get("assessment_plan") or {}
    blueprint = [one for one in dev_plans.plan_tasks(plan) if one.get("id")]
    derived = {"sets": [{"module_id": one.get("module_id"), "set_ids": [one["id"]]}
                        for one in blueprint]}
    sets, stats = dev_plans.assessment_work_sets(
        derived, _lo_ids(state), plan.get("lo_coverage_targets") or {},
        modules=parsed.get("modules"), blueprint=blueprint, mode=mode,
        levels=objective_levels(state))
    named = dev_plans.name_sets_after(
        sets, "AS", lambda ws: next((i["id"] for i in ws.payload.get("sets") or []
                                     if i.get("id")), ws.module_id))
    # How many tasks the blueprint planned against how many the course
    # carries at most: the ceiling is TOLD, so this is where its compliance is
    # measured (the tune slice reads it off the ``work_sets`` event).
    modules = course_modules(state)
    stats = {**stats, "tasks_planned": len(blueprint),
             "task_ceiling": dev_plans.task_ceiling(modules) if modules else None}
    return named, _derived_stats(stats)


def _activity_sets(state, parsed: dict, mode: str = "full") -> tuple[list, dict]:
    """One block per MODULE, holding the objectives that module serves.

    Unlike the other three families nothing in the design states how MANY
    activities a module needs, so the count comes from the module's own
    minutes (``fit_time_budget``) and, under ``light``, from the light
    quota."""
    modules = [m for m in (parsed.get("modules") or [])
               if isinstance(m, dict) and m.get("id")]
    derived = {"activity_blocks": [{"module_id": m["id"],
                                    "objectives": list(m.get("objectives") or []),
                                    "block_minutes": m.get("minutes")} for m in modules]}
    sets, stats = dev_plans.activity_work_sets(
        derived, _lo_ids(state), items_by_lo(state),
        modules=parsed.get("modules"), mode=mode, levels=objective_levels(state))
    return (dev_plans.name_sets_after(sets, "AB", lambda ws: ws.module_id),
            _derived_stats(stats))


def module_of_artifacts(state) -> dict[str, str]:
    """Which module each activity and each material was written for, by the
    field that artifact itself carries (``module_id`` / ``linked_module``).
    The delivery plan is divided by it."""
    out: dict[str, str] = {}
    for node_type, doc, field_name in (
            (NodeType.ACTIVITY, ("activity", "learning_activities"), "module_id"),
            (NodeType.MATERIAL, ("material", "learner_materials"), "linked_module")):
        for data in _element_data(state, node_type, doc):
            if data.get("id") and data.get(field_name):
                out[str(data["id"])] = str(data[field_name])
    return out


def _material_sets(state, parsed: dict, mode: str = "full") -> tuple[list, dict]:
    sets = dev_plans.material_work_units(
        parsed.get("modules") or [], parsed.get("media_selections") or [],
        _constraints(state), mode=mode)
    return sets, _deterministic_stats(sets)


def items_by_lo(state) -> dict[str, list[str]]:
    """Which committed assessment TASKS each objective is measured by.

    C4's far end is the task — the thing a learner sits — so an activity set
    names tasks, not questions: "prepare learners for the practical" is the
    claim an activity can make, and it is the one the relation records. Which
    objectives a task measures is read off the items inside it, so this is
    still the Developers' work rather than the plan's promise. A Developer
    told to prepare learners for AT-03 and not told what AT-03 asks has to go
    and read it — the read cost ``_resolved_references`` exists to remove."""
    by_lo: dict[str, list[str]] = {}
    for task in _element_data(state, NodeType.ASSESSMENT, ("assessment", "assessment_tools")):
        if "items" in task:
            task_id = str(task.get("id") or "")
        else:
            # The blackboard keeps the QUESTIONS flat, each naming its task;
            # the key is that task, never the question's own `item_id`, or the
            # prose arm's activity Developers are handed ids `known_ids`
            # refuses. MEASURED with question ids (run a1 20261001_101147):
            # 0 of 117 prose activities kept a C4 reference, 15 sets given up.
            task_id = str(task.get("task_id") or "").rsplit(":", 1)[-1]
        if not task_id:
            continue
        for one in (task.get("items") or [task]):
            lo_id = dev_plans._bare(str((one or {}).get("aligned_objective") or ""))
            if lo_id and task_id not in by_lo.setdefault(lo_id, []):
                by_lo[lo_id].append(task_id)
    return by_lo


def constraints(state) -> list[dict]:
    """The context constraints, which a material unit resolves for the media
    selections that declare ``respects_constraints``. Prose keeps them nested
    inside the analysis document rather than as their own element pool, which
    is why this does not go through :func:`_element_data`."""
    if hasattr(state, "element_nodes"):
        return [n["data"] for n in state.element_nodes(NodeType.CONSTRAINT)]
    context = (state.get("analysis") or {}).get("context_analysis") or {}
    return [c for c in (context.get("constraints") or []) if isinstance(c, dict)]


_constraints = constraints


def topics(state) -> list[dict]:
    """The task analysis's topics, from either substrate — nested inside the
    analysis document on the blackboard, like the constraints."""
    if hasattr(state, "element_nodes"):
        return [n["data"] for n in state.element_nodes(NodeType.TOPIC)]
    task = (state.get("analysis") or {}).get("task_analysis") or {}
    return [t for t in (task.get("topics") or []) if isinstance(t, dict)]


def media_selections(state) -> list[dict]:
    """The content stage's media selections, from either substrate."""
    return _element_data(state, NodeType.MEDIA_SELECTION, ("content", "media_selections"))


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


def _session_sets(state, parsed: dict, mode: str = "full") -> tuple[list, dict]:
    """One block per MODULE, holding what that module is taught with.

    Which activities and materials a module owns is already written on the
    artifacts themselves (``module_id`` / ``linked_module``), and the
    normalizer lands every id in exactly one block whatever the blocks are —
    so P10/P11 coverage is a property of a deterministic division rather than
    of a small model recalling ids. How many sessions a module takes comes
    from its minutes."""
    activity_ids = _element_ids(state, NodeType.ACTIVITY, ("activity", "learning_activities"))
    material_ids = _element_ids(state, NodeType.MATERIAL, ("material", "learner_materials"))
    module_of = module_of_artifacts(state)
    modules = [m for m in (parsed.get("modules") or [])
               if isinstance(m, dict) and m.get("id")]
    derived = {"session_blocks": [
        {"module_id": m["id"],
         "activity_ids": [a for a in activity_ids if module_of.get(a) == m["id"]],
         "material_ids": [x for x in material_ids if module_of.get(x) == m["id"]]}
        for m in modules]}
    sets, stats = dev_plans.session_work_sets(
        derived, activity_ids, material_ids,
        modules=parsed.get("modules"), module_of=module_of, mode=mode)
    return (dev_plans.name_sets_after(sets, "SB", lambda ws: ws.module_id),
            _derived_stats(stats))


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
    ``still_needed`` names what is already committed as not-to-resend."""
    step = next(s for s in STEPS if s.name == stage)
    return not missing_parts(step, state)


SPECS: dict[str, FanoutSpec] = {
    "assessment": FanoutSpec(
        stage="assessment",
        developer_identity="AssessmentDeveloperAgent",
        developer_persona=(
            "You are an expert instructional designer developing ONE assessment assessment set "
            "(ADDIE Development phase) — writing the actual items for exactly the objectives and "
            "plan categories your assigned set names, AND the scoring criteria that mark them. "
            "You are NOT responsible for any other objective or category; another Developer is "
            "handling those."),
        set_intro=("Write the actual items for the assessment sets in YOUR ASSIGNMENT below, each with "
                   "the scoring criteria that mark it, inside the item's own ``rubric`` list."),
        outputs=(
            SetOutput(
                schema_key="assessment_tools", id_field="item_id",
                rules=rules.RULES_ASSESSMENT_ITEMS_SET + "\n" + rules.RULES_RUBRICS_ITEM,
                element_type=NodeType.ASSESSMENT, id_prefix="ATI",
                doc_key=("assessment", "assessment_tools"),
                parent_field="task_id",
                ref_fields=(("task_id", NodeType.ASSESSMENT),
                            ("aligned_objective", NodeType.OBJECTIVE)),
                validate_items=assessment_item_errors),
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
                doc_key=("activity", "learning_activities"),
                validate_items=_names_its("module_id", "learning_activities", "module"),
                ref_fields=(("aligned_objectives", NodeType.OBJECTIVE),
                            ("prepares_for_assessment", NodeType.ASSESSMENT),
                            ("module_id", NodeType.MODULE)),
                required_refs=("prepares_for_assessment",)),
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
                doc_key=("material", "learner_materials"),
                ref_fields=(("linked_module", NodeType.MODULE),)),
        ),
        developer_reads=(NodeType.MODULE, NodeType.ACTIVITY),
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
                # No `ref_fields`. P10/P11 are secondary and report-only, and
                # `material_ids` is optional because a session that hands out
                # nothing is ordinary — but the deciding reason is that adding
                # them changed what `single`+`prose` produced while `multi`
                # passed unchanged, and a rule only one arm can break is a
                # second variable sitting on the decomposition axis. The ids a
                # guide may use are written out in its assignment, and
                # `dev_plans.session_work_sets` divides them deterministically,
                # so an unresolvable one is a P10/P11 gap that is reported
                # rather than refused.
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
_ASSIGNMENT_WRITTEN_OUT = (
    "Everything your assignment names is written out below — in full where you have to work "
    "from the artifact itself (the objectives, the items, the modules), and as one line per "
    "item where your job is to name ids (the activities and materials a session block "
    "schedules).")
#: A Developer whose assignment fits is bound NO read tool: what it needs is
#: in front of it, and a read is a turn. MEASURED (run 53a9cd1a): 31 of the 80
#: Developer calls were `read_node` for ids the assignment had already written
#: out (`read_of_assignment_id`) — a quarter of the run's model time, all of
#: it sequential, spent re-reading the prompt. Telling the Developer not to
#: ("You do not need to look them up") had been in this text throughout; under
#: a forced tool call a 2B model reaches for whatever is bound.
_ASSIGNMENT_IS_COMPLETE = (
    _ASSIGNMENT_WRITTEN_OUT + " It is all you need: write your artifacts from it and submit.")
#: Only an assignment that had to be CUT keeps the read tools, to reach what
#: the cut took.
_ASSIGNMENT_IS_TRUNCATED = (
    _ASSIGNMENT_WRITTEN_OUT + " It was too long to show whole: use the read tools for an "
    "artifact the cut took, and never for one that is written out.")

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
        # An activity set names the assessment TASKS its activities prepare for,
        # BY ID — C4's far end is the task, the thing a learner sits. A Developer
        # told to prepare learners for AT-03 and not told what AT-03 asks has no
        # choice but to go and read it.
        (NodeType.ASSESSMENT, "The assessment tasks your set prepares learners for",
         ("assessment", "assessment_tools"),
         tuple(work_set.payload.get("assessment_task_ids") or ()), "id", False),
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
        # The blackboard keeps ``assessment_tools`` as a flat list of QUESTIONS
        # keyed by ``item_id``, so the tasks an activity set names are the
        # plan's, each with the questions that name it — what the graph arm's
        # task node holds. Read as a flat pool, no task matched and the prose
        # arm's activity Developers were never shown what a task asks
        # (MEASURED, run t1 20261002_134550: the block was absent from every
        # prose assignment).
        pool = (_tasks_with_items(state) if node_type == NodeType.ASSESSMENT
                else state.items(*doc))
        nodes = [{"type": str(node_type), "id": f"{node_type}:{i.get(id_field)}", "data": i}
                 for i in pool
                 if isinstance(i, dict) and dev_plans._bare(i.get(id_field, "")) in wanted]
    if not nodes:
        return ""
    rendered = (tools.render_listing(nodes) if compact
                else tools.render_nodes(nodes) if hasattr(state, "element_nodes")
                else "\n".join(json.dumps(n["data"], ensure_ascii=False)[:tools.NODE_CHAR_CAP]
                                for n in nodes))
    return f"\n\n{label}:\n{rendered}" if rendered.strip() else ""


def _tasks_with_items(store) -> list[dict]:
    """The plan's assessment tasks off the blackboard, each carrying the
    questions that name it — the aggregator's join, so the assignment and the
    deliverable read the same document."""
    plan = _section_doc(store, NodeType.ASSESSMENT_PLAN, "assessment_plan")
    if not dev_plans.plan_tasks(plan):
        return []
    return _join_tasks(plan, [i for i in store.items("assessment", "assessment_tools")
                       if isinstance(i, dict)])


def set_step(spec: FanoutSpec, work_set: dev_plans.WorkSet, base: AgenticStep,
             state=None) -> AgenticStep:
    """An :class:`AgenticStep` for one work set, so the ordinary ToolLoop runs it.

    The assignment slice goes in the INTRO rather than as injected context: it
    is what this Developer was asked to do, not background it may consult. Read
    tools stay whatever the family's stage allows — a Developer still needs to
    see the objectives it is writing for."""
    primary = spec.outputs[0].schema_key
    # The reference pools, snapshotted once per set rather than per submit:
    # nothing this Developer writes adds to them, and the single arm reads the
    # same fact from its own state.
    known = known_ids(state) if state is not None else {}
    levels = objective_levels(state) if state is not None else {}
    committed_best = committed_item_levels(state) if state is not None else {}
    statements = objective_statements(state) if state is not None else {}
    whole = spec.render(work_set) + _resolved_references(work_set, state)
    assignment = _capped(whole)
    truncated = assignment != whole

    def validate(parsed: dict) -> list[str]:
        items = (parsed or {}).get(primary)
        if not isinstance(items, list) or not items:
            return [f"{primary} must be a non-empty list"]
        # Judged as it will be committed: a membership id the set itself
        # settles is filled in (``dev_plans.with_membership``), never refused.
        filled = {**parsed, primary: dev_plans.with_membership(work_set, primary, items)}
        return output_errors(spec, filled, known, levels=levels,
                             committed_best=committed_best, statements=statements)

    def owes(section: dict) -> str:
        # Counted without repeats: what the commit's trim would drop as a
        # repeat must not count towards the quota on the way there.
        written = dev_plans.without_repeats(primary, (section or {}).get(primary) or [])
        return dev_plans.short_of_quota(work_set, primary, written)

    return replace(
        base,
        name=f"{spec.stage}:{work_set.set_id}",
        identity=spec.developer_identity,
        persona=spec.developer_persona,
        intro=(f"{spec.set_intro}\n\n"
               f"{_ASSIGNMENT_IS_TRUNCATED if truncated else _ASSIGNMENT_IS_COMPLETE}"
               f"\n\n{spec.set_header}\n{assignment}"),
        rules="\n".join(o.rules for o in spec.outputs),
        submit_fields=tuple((o.schema_key, "array", i == 0)
                            for i, o in enumerate(spec.outputs)),
        # No docket and a narrowed read scope: coverage gaps belong to whoever
        # plans the sets, not to one Developer inside a set it did not choose.
        docket={},
        readable_types=spec.developer_reads if truncated else (),
        readable_docs=base.readable_docs if truncated else (),
        resolved_labels=resolved_labels(work_set),
        assignment_ids=assignment_ids(assignment),
        relations=(),
        state_tool=False,
        validate=validate,
        owes=owes,
        commit=lambda *_a, **_k: None,       # committing is the driver's job,
        commit_prose=lambda *_a, **_k: None,  # right after this loop returns
        commits_to_state=False,
        # THIS set's items, not the family's pool: siblings are committing into
        # the same pool as they finish, so the default guard would call this
        # set done before its Developer had spoken.
        done=lambda state, _sid=work_set.set_id: _sid in committed_set_ids(spec, state),
        work_set=work_set,
    )


_TAGGED_ID = re.compile(r"\[([A-Z_]+):([^\]\s]+)\]")
_BARE_ID = re.compile(r"(?<![A-Z0-9-])[A-Z]{1,5}-?\d{1,4}\b")


def assignment_ids(assignment: str) -> dict[str, str]:
    """``id -> heading`` for every artifact id the rendered assignment shows.

    MEASURED (run 14a6b4c7, content:MU-CM-01): the module's media selections
    (``MS-01``, ``MS-02``) and topics (``T1``) are written INTO the assignment
    and served by no read tool, so the Developer's reads for them were
    answered "no readable artifact ... use read_nodes to list their ids" —
    which it did, 18 times, then gave up on the turn ceiling without writing
    a material. The pointer that replaces that error needs to know which ids
    the assignment carries and under which heading.

    Ids are the ``[TYPE:ID]`` tags the renderers emit plus every bare token
    shaped like one (``T1``, ``MS-01``, ``AT-0103``); a heading is the last
    line above that ended in ``:`` (the renderers' block openers), or the
    assignment itself. Over-matching a stray token in prose is harmless: the
    pointer only fires when the model READS that token, and it is then true.
    Computed on the CAPPED text, so a truncated assignment never claims an
    id the model cannot see.
    """
    found: dict[str, str] = {}
    heading = "your assignment"
    for line in assignment.splitlines():
        text = line.strip()
        if text.startswith("===") and text.endswith("==="):
            heading = "your assignment"
        elif text.endswith(":") and " " in text and not text.startswith("["):
            heading = text[:-1]
        ids = [m.group(2) for m in _TAGGED_ID.finditer(text)] + _BARE_ID.findall(text)
        for one in ids:
            found.setdefault(one.upper(), heading)
    return found


def _capped(assignment: str) -> str:
    if len(assignment) <= ASSIGNMENT_CHAR_CAP:
        return assignment
    return assignment[:ASSIGNMENT_CHAR_CAP] + "\n… (assignment truncated)"


def committed_set_ids(spec: FanoutSpec, state) -> set[str]:
    """Set ids already present in the state — the re-entrancy guard that lets
    the outer regen loop retry ONLY the sets that came back empty."""
    primary = spec.outputs[0]
    if hasattr(state, "element_nodes"):
        return {one.get("plan_set")
                for one in _pool(state, primary) if one.get("plan_set")}
    key, field_name = primary.doc_key
    return {i.get("plan_set") for i in state.items(key, field_name)
            if isinstance(i, dict) and i.get("plan_set")}


def missing_outputs(stage: str, state) -> tuple[str, ...]:
    """The Developer-tier lists of ``stage`` the state holds none of yet.

    Empty for a stage that has no fan-out. The multi arm never asks: its
    Developers write these after the stage loop has closed. The single arm
    writes them itself, inside the stage, so a stage it walks is finished only
    when they exist — the plan alone leaves the work it plans unwritten."""
    spec = SPECS.get(stage)
    if spec is None:
        return ()
    graph = hasattr(state, "element_nodes")
    owed: list[str] = []
    for output in spec.outputs:
        pool = _pool(state, output) if graph else state.items(*output.doc_key)
        if not pool:
            owed.append(output.schema_key)
            continue
        uncovered = _units_without(stage, state, pool)
        if uncovered:
            owed.append(f"{output.schema_key} for {', '.join(uncovered)}")
    return tuple(owed)


def _units_without(stage: str, state, pool: list) -> list[str]:
    """The units of the design a stage's lists leave without any artifact:
    an assessment task no item sits in, a module no activity or material is
    written for. The multi arm writes one work set per such unit, so a single
    arm closed on the first artifact would write a fraction of what its plan
    asks for and be compared with one that wrote all of it."""
    if stage == "assessment":
        plan = _section_doc(state, NodeType.ASSESSMENT_PLAN, "assessment_plan")
        wanted = [dev_plans._bare(t.get("id")) for t in dev_plans.plan_tasks(plan)
                  if t.get("id")]
        if hasattr(state, "element_nodes"):
            held = {dev_plans._bare(n["data"].get("id") or n["id"])
                    for n in state.element_nodes(NodeType.ASSESSMENT)
                    if n["data"].get("items")}
        else:
            held = {dev_plans._bare(str(one.get("task_id") or "").rsplit(":", 1)[-1])
                    for one in pool if isinstance(one, dict)}
        return [t for t in wanted if t not in held]
    field_name = {"activities": "module_id", "content": "linked_module"}.get(stage)
    if field_name is None:
        return []
    held = {dev_plans._bare(one.get(field_name)) for one in pool if isinstance(one, dict)}
    return [str(m["id"]) for m in course_modules(state)
            if m.get("id") and dev_plans._bare(m["id"]) not in held]


def _pool(state, output: SetOutput) -> list[dict]:
    """The artifacts this output has already committed: the element nodes of
    its type, or — when it lives inside one — the items of those nodes."""
    nodes = state.element_nodes(output.element_type)
    if not output.parent_field:
        return [n["data"] for n in nodes]
    return [one for n in nodes for one in (n["data"].get(output.parent_list) or [])
            if isinstance(one, dict)]


def _ids_already_held(state, output: SetOutput) -> frozenset[str]:
    """The ids this output's pool already carries, so a per-set commit bumps a
    colliding id instead of overwriting the set that got there first."""
    if hasattr(state, "element_nodes"):
        return frozenset(str(one.get(output.id_field) or "")
                         for one in _pool(state, output))
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
    now, so each set is written against the ids its siblings already hold and
    the re-dispatch round sees the whole family rather than the last set. In
    the SINGLE arm the design loop is still open at this point and a gap can
    reach the agent; in the multi arm the Designer's loop has returned, and
    the route back to a writer is a second dispatch. The ids already in the
    state are handed to the remapper as ``taken``, or the second set's
    ``AT-01`` would overwrite the first's rather than being bumped.

    The whole deposit runs inside one graph transaction: reading the ids in
    play and then writing nodes chosen from what was read is only correct if
    nothing lands in between. Commits run one at a time on the driver's thread in plan order, so nothing does — the lock is what keeps that true while the Developers run on several (``fanout_workers``)."""
    with _deposit(state):
        _deposit_sets(spec, state, trajectory, work_sets, payloads)


def _deposit(state):
    from contextlib import nullcontext

    transaction = getattr(state, "transaction", None)
    return transaction() if callable(transaction) else nullcontext()


def _deposit_sets(spec: FanoutSpec, state, trajectory, work_sets: list,
                  payloads: list) -> None:
    committed: dict[str, list[str]] = {}
    set_of = {ws.set_id: ws for ws in work_sets}
    for output in spec.outputs:
        held: list[dict] = []
        for payload in payloads:
            items = payload.get(output.schema_key) or []
            work_set = set_of.get(payload.get("set_id", ""))
            if work_set is not None and isinstance(items, list):
                items = dev_plans.with_membership(work_set, output.schema_key, items)
                items, dropped = dev_plans.trim_to_quota(work_set, output.schema_key, items)
                if dropped:
                    trajectory.log_recovery_event(
                        ORCHESTRATOR, "excess_artifacts_trimmed", work_set.set_id,
                        f"{output.schema_key}: kept {len(items)} of {len(items) + dropped} "
                        "— the set's assignment stated the count")
            held.append({"set_id": payload.get("set_id", ""), "items": items})
        merged = dev_plans.remap_and_tag(
            work_sets, held,
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
        if output.parent_field:
            committed[output.schema_key] = _attach_to_parent(
                state, trajectory, output, merged)
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



def _attach_to_parent(state, trajectory, output: SetOutput, merged: list) -> list[str]:
    """File each item inside the element node it belongs to; say which nodes
    changed.

    An item naming no parent, or one that does not exist, is DROPPED rather
    than made a node of its own: the pool of this element type is the parents,
    and a stray there would be counted as one by every check and every
    coverage figure."""
    by_parent: dict[str, list[dict]] = {}
    for item in merged:
        parent = dev_plans._bare(item.get(output.parent_field))
        if parent:
            by_parent.setdefault(parent, []).append(
                {k: v for k, v in item.items() if k != output.parent_field})
    touched: list[str] = []
    homeless: list[str] = []
    for parent, items in by_parent.items():
        node_id = f"{output.element_type}{state.ELEMENT_SEP}{parent}"
        node = state.get_node(node_id)
        if node is None:
            homeless += [str(one.get(output.id_field) or "?") for one in items]
            continue
        data = node.get("data") or {}
        # The parent's own `timing` IS the item's plan category. Stamped here
        # it cannot disagree with it the way a copy the Developer wrote could,
        # and the check that policed that copy goes with it.
        timing = str(data.get("timing") or "").strip().lower()
        if timing:
            items = [{**one, "plan_category": timing} for one in items]
        state.update_node(node_id, {
            output.parent_list: list(data.get(output.parent_list) or []) + items})
        trajectory.log_node_edit("update", node_id, output.element_type)
        touched.append(node_id)
    if homeless:
        # Never silent: an item whose parent does not exist is the whole
        # artifact lost, and the likeliest cause is an order — the items
        # submitted before the plan that declares their task.
        trajectory.log_recovery_event(
            ORCHESTRATOR, "items_without_parent", ", ".join(homeless[:8]),
            f"{len(homeless)} {output.schema_key} named no {output.element_type} "
            "that exists and were dropped")
    return touched


def _establish(spec: FanoutSpec, state, committed: dict[str, list[str]]) -> None:
    """Alignment relations for a family's freshly committed artifacts."""
    if spec.stage == "assessment":
        alignment.match_from_items(state, "C2", field="aligned_objective")
        alignment.match_p3_realizes(state)
        alignment.match_module_assessed(state)
    elif spec.stage == "activities":
        alignment.match_id_reverse(state, "P13", field="module_id")
        alignment.match_list_reverse(state, "C3", field="aligned_objectives")
        alignment.match_list(state, "C4", field="prepares_for_assessment")
        plan_id = state.section_id(NodeType.ACTIVITY_PLAN)
        node_ids = committed.get("learning_activities", [])
        if state.get_node(plan_id):
            for node_id in node_ids:
                alignment.record_provenance(state, "P4", [plan_id], node_id)
        alignment.link_prerequisites(state, node_ids)
    elif spec.stage == "implementation":
        alignment.establish_delivery(state, committed.get("session_guides", []))
        # The plan section holds the guide's FRAMING and the guides are its
        # elements, which is exactly what `narrates` is for. Without it
        # `implementation_plan_0` is an edgeless island — the thing P10/P11
        # were added to stop, back when they hung off the section itself.
        alignment.link_section_narrative(state, NodeType.IMPLEMENTATION_PLAN,
                                         NodeType.SESSION_GUIDE)
    elif spec.stage == "content":
        for node_id in committed.get("learner_materials", []):
            data = state.get_node(node_id)["data"]
            module_id = alignment.resolve_element(
                state, NodeType.MODULE, data.get("linked_module", ""))
            if module_id:
                alignment.record_provenance(state, "P5", [module_id], node_id)
        alignment.match_p6_realizes(state)
