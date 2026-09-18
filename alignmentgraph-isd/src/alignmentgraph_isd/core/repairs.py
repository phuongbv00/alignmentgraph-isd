"""Shared repair toolbox — the corrective half of the safeguard substrate
(``checks.py`` finds violations; this module fixes the fixable ones).

Free functions over the run's context substrate (graph or blackboard), owned
by neither decomposition arm: both arms dispatch into :func:`repair` with their
own :class:`RepairContext`, and neither instantiates the other's agent classes
to borrow its corrective machinery. Repair strength is a safeguard held
constant across the ablation (see ``config.py``).

**Every routine here is STRUCTURAL, and none of them calls the model.**
A repair rearranges what the design already holds — substitute
a Bloom verb from the taxonomy, prune a reference that resolves to nothing,
re-point a material at a module that exists, reformat a keyless choice item as
short_answer. Deterministic, exact, and free.

A violation that needs WRITING is not repaired here at all: it goes back to
the agent that owns it as a repair turn inside that agent's own tool loop
(:meth:`ToolLoop._own_violations`), where the request, the model's answer and
the artifact it produces are three consecutive turns of ONE transcript. A
generative routine HERE would open a second conversation under a second system
prompt with no tools bound, in the name of the same agent, so the recorded
context would show an agent producing text it was never shown asking for. The
context boundary is the whole ``agent_mode`` axis, and a repair path that
quietly crosses it is measuring something else.

Templated stand-ins are not an exception — a "Guided practice for ILO-01"
activity, a "Support module for TLA-01", a fixed rubric sentence, a canned list
of formative methods: a check a template can pass measures the template, which
is the objection that keeps P6 audit-only. They also pollute the signal a run
is tuned on; item text built from the objective's own statement reads to a
text-similarity measure as correspondence no design work produced.

So ``activity_engagement``, ``bloom_mismatch_activity``, ``rubric_consistency``,
``feasibility``, ``actionability`` and the C3/C5 "nothing exists yet" cases have
NO repair. They stay in :data:`OWNED_BY_FAMILY` so reconciliation routes them to
an owner, come back unrepaired, and are counted as residual. A repair that
changes nothing logs nothing: a repair event reporting no change is what makes
``repair_success_rate`` unreadable.

All logging goes through ``ctx.actor``, so a repair records whoever actually
ran it — a specialist in the multi arm, the single designer in the single arm.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from .alignment_graph import NodeType, alignment
from .checks import _VERB_LEVELS


@dataclass(frozen=True)
class RepairContext:
    """The slice of an agent a repair routine needs. Exactly one of
    ``graph``/``store`` is live per run (see config.py's ``context_mode``)."""

    graph: object | None
    store: object | None
    trajectory: object
    actor: str

    @property
    def graph_mode(self) -> bool:
        return self.graph is not None


def _log_repair(ctx: RepairContext, node_id: str, *, violation_type: str = "",
                repaired_fields: list[str] | None = None, rule: str = "",
                input_summary: str = "", output_summary: str = "") -> None:
    """ONE record per repair: the structured fields plus the rule's own
    narrative (which repair routine ran, what it saw, what it did). A second
    paired event would double-count every repair in ``repair_metrics``."""
    ctx.trajectory.log_repair_event(
        agent=ctx.actor, violation_type=violation_type,
        node_id=node_id, repaired_fields=repaired_fields or [],
        rule=rule, input_summary=input_summary, output_summary=output_summary,
    )


# ── ownership: which violation types each artifact family's repairs answer ──
# Both decomposition arms read this same map by family key: it is the one
# definition of who answers for what.
OWNED_BY_FAMILY: dict[str, frozenset[str]] = {
    "outcome_designer": frozenset({"bloom"}),
    "assessment_designer": frozenset(
        {"C2", "P3", "bloom_mismatch_assessment", "evaluation_quality", "plan_coverage",
         "item_completeness"}),
    "activity_designer": frozenset(
        {"C3", "C4", "P4", "activity_engagement", "bloom_mismatch_activity", "time_budget"}),
    # P8 must have an owner. Unowned, a media selection whose
    # `respects_constraints` names nothing real produces no finding at all:
    # `record_provenance` no-ops on an id that does not exist, and the gap
    # surfaces only in the final residual audit with nothing to explain it.
    # MEASURED (run 7ef3ed16): all 24 media selections wrote "low_bandwidth" /
    # "high_bandwidth" — copied from the rule's own parenthetical example —
    # against constraint nodes c1..c7; P8 scored 0.0, the ledger held zero P8
    # findings, and the Content Designer was never told.
    "content_designer": frozenset({"C5", "P5", "P6", "P8", "orphan_content"}),
    "rubric_designer": frozenset(
        {"rubric_consistency", "evidence_alignment"}),
    "implementation_planner": frozenset({"feasibility", "actionability", "P10", "P11"}),
}


#: Owned, but never repaired: routed to a family so the trace names an owner,
#: and handed straight back. Two reasons, and neither is an oversight.
#:
#: * Nothing exists yet to fix. C3 (no activity practices this objective) and
#:   C5 (no content supports this activity) are missing ARTIFACTS, and the
#:   only deterministic answer was a template — "Guided practice for ILO-01",
#:   "Support module for TLA-01". Each satisfied its own check by existing.
#: * The fix is not mechanical. ``activity_engagement`` /
#:   ``bloom_mismatch_activity`` need a different activity, ``rubric_consistency``
#:   a criterion that describes THIS item, ``feasibility`` / ``actionability`` a
#:   delivery decision. ``P4``/``P6`` are fuzzy type-matches, audit-only from
#:   the start — this list is that principle applied consistently.
#:
#: Everything else has a STRUCTURAL repair below.
#:
#: REPORT_ONLY is a statement about the HARNESS, not about the agent: these
#: types are shown to their owning agent as a repair turn like any other
#: violation (the agent can write what is missing), and are simply never
#: touched by the deterministic net. What survives the agent's repair budget
#: is counted as residual.
REPORT_ONLY: frozenset[str] = frozenset({
    # P8: which constraints a media selection was chosen in light of is a
    # design judgment, not a rearrangement of what the design already holds.
    # The net could only pick a constraint at random and make the check pass by
    # existing — the objection that has always kept P6 audit-only.
    "C3", "C5", "P4", "P6", "P8", "P10", "P11",
    "activity_engagement", "bloom_mismatch_activity", "time_budget",
    "rubric_consistency", "feasibility", "actionability",
})


#: Violation types with a free, exact, model-free fix: a Bloom verb looked up
#: in the taxonomy, a dangling reference pruned, a material pointed at a module
#: that exists, a criterion's evidence type loosened to what its own item can
#: produce.
#:
#: These run BEFORE the agent is shown anything (see
#: ``ToolLoop._own_violations``) — spending an agent turn on what a lookup does
#: perfectly is the waste the loop has been trimming everywhere else.
#:
#: NOT listed here, and deliberately: ``C2``/``P3`` and ``item_completeness``.
#: Each has a structural half (re-point a dangling item; reformat a keyless
#: choice item as short_answer) but that half is LOSSY — it settles for less
#: than the design asked for. The agent gets its repair turns first, and the
#: salvage runs only in the reconciliation pass, after every loop has closed.
STRUCTURAL: frozenset[str] = frozenset({
    "bloom", "C4", "P5", "orphan_content", "evidence_alignment",
})


#: Reverse index of :data:`OWNED_BY_FAMILY`: violation type -> owning family.
#: The reconciliation pass uses it to stamp ``Violation.target_designer`` and to
#: hand each residual violation to the family that can actually repair it. A
#: type absent here is owned by nobody and is audit-only (``measurability``).
OWNER_BY_VIOLATION: dict[str, str] = {
    violation_type: family
    for family, types in OWNED_BY_FAMILY.items()
    for violation_type in types
}
# A type owned by two families would make routing ambiguous and silently drop
# half the repairs, so the invariant is asserted at import time rather than
# discovered in a results dir.
assert len(OWNER_BY_VIOLATION) == sum(len(t) for t in OWNED_BY_FAMILY.values()), (
    "OWNED_BY_FAMILY entries overlap; each violation type must have one owner")


def repair(family: str, violations: list, ctx: RepairContext) -> list:
    """Dispatch ``violations`` to the ``family``'s repair routines; returns the
    violations no routine answers.

    :data:`REPORT_ONLY` types never reach a routine and are returned as-is.
    Filtered HERE rather than inside each family, because a per-family branch
    that sends C3/C5 to a routine with nothing to do drops them silently: the
    violation leaves ``remaining`` with nothing having been done about it,
    which is the exact failure mode a template has.
    """
    reported = [v for v in violations
                if getattr(v, "violation_type", "") in REPORT_ONLY]
    repairable = [v for v in violations
                  if getattr(v, "violation_type", "") not in REPORT_ONLY]
    remaining = _FAMILY_REPAIRERS[family](ctx, repairable) if repairable else []
    return list(remaining) + reported


# ── outcome family ──────────────────────────────────────────────────────────

BLOOM_VERB_BY_LEVEL = {
    "remember": "recall", "understand": "explain", "apply": "apply",
    "analyze": "analyze", "evaluate": "evaluate", "create": "design",
}
VERB_REPLACEMENTS = {
    "comprehend": "explain", "understand": "explain", "grasp": "explain",
    "learn": "identify", "know": "identify",
}


def _level_from_verb(verb: str) -> str:
    """The Bloom level a verb names. A verb that spans levels ("construct" is
    both Apply and Create) resolves to the lowest — a repair should not inflate
    the level an objective claims."""
    levels = _VERB_LEVELS.get(str(verb).lower().strip(".,;"), set())
    return alignment.BLOOM_LEVEL_NAME[min(levels)] if levels else "apply"


def _repair_outcome_family(ctx: RepairContext, violations: list) -> list:
    remaining = []
    for violation in violations:
        if getattr(violation, "violation_type", "") == "bloom":
            repair_bloom_verb(ctx, violation)
        else:
            remaining.append(violation)
    return remaining


def _fix_bloom_verb_in(objectives: list, lo_id: str, *, level_only: bool = False) -> bool:
    repaired = False
    for lo in objectives:
        if not isinstance(lo, dict) or (lo_id and lo.get("id") != lo_id):
            continue
        if level_only:
            # The verb is a real Bloom verb; only ``level`` names something
            # outside the six. Rewriting the verb (or the statement) here would
            # change what the objective asks for to fix a label.
            lo["level"] = _level_from_verb(str(lo.get("bloom_verb", "")))
            repaired = True
            continue
        old_verb = str(lo.get("bloom_verb", "")).strip()
        replacement = (
            VERB_REPLACEMENTS.get(old_verb.lower())
            or BLOOM_VERB_BY_LEVEL.get(str(lo.get("level", "")).lower(), "explain")
        )
        lo["bloom_verb"] = replacement
        if alignment.bloom_level_of(str(lo.get("level", ""))) is None:
            lo["level"] = _level_from_verb(replacement)
        statement = str(lo.get("statement", ""))
        # The verb is SUBSTITUTED where it appears. If it does not appear, the
        # statement is left exactly as written: appending "This is measured by
        # asking learners to apply the target skill in context." made the
        # objective longer and no more measurable, and it was the same sentence
        # in every design that tripped this check.
        if old_verb and re.search(re.escape(old_verb), statement, flags=re.IGNORECASE):
            lo["statement"] = re.sub(re.escape(old_verb), replacement, statement, count=1, flags=re.IGNORECASE)
        repaired = True
    return repaired


def repair_bloom_verb(ctx: RepairContext, violation) -> None:
    """bloom: a vague/non-measurable verb, or a ``level`` outside Bloom's six —
    deterministic substitution, same fix on either substrate. The check reports
    the out-of-taxonomy level with the declared value in ``metadata["level"]``,
    which is how the two cases are told apart here."""
    lo_id = str(violation.metadata.get("lo_id", "") or "")
    declared = violation.metadata.get("level")
    level_only = declared is not None and alignment.bloom_level_of(str(declared)) is None
    fields = ["learning_objectives", "level" if level_only else "bloom_verb"]
    what = "Bloom level" if level_only else "Bloom verb"
    if not ctx.graph_mode:
        document = ctx.store.get("objective")
        if not document:
            return
        objectives = [dict(lo) if isinstance(lo, dict) else lo
                      for lo in document.get("learning_objectives") or []]
        if not _fix_bloom_verb_in(objectives, lo_id, level_only=level_only):
            return
        ctx.store.put("objective", {**document, "learning_objectives": objectives})
        _log_repair(ctx, "objective", violation_type="bloom", repaired_fields=fields,
                rule="repair_objective", input_summary=violation.message,
                output_summary=f"Updated {what} for {lo_id or 'objective'}.")
        return
    objectives = [dict(n["data"]) for n in ctx.graph.element_nodes(NodeType.OBJECTIVE)]
    if not _fix_bloom_verb_in(objectives, lo_id, level_only=level_only):
        return
    for lo in objectives:
        if isinstance(lo, dict) and lo.get("id") and (not lo_id or lo["id"] == lo_id):
            ctx.graph.add_element_node(NodeType.OBJECTIVE, str(lo["id"]), dict(lo))
    if lo_id:
        ctx.trajectory.log_node_edit(
            "update", f"{NodeType.OBJECTIVE}{ctx.graph.ELEMENT_SEP}{lo_id}", NodeType.OBJECTIVE)
    _log_repair(ctx, lo_id or str(NodeType.OBJECTIVE), violation_type="bloom",
                repaired_fields=fields,
                rule="repair_objective", input_summary=violation.message,
                output_summary=f"Updated {what} for {lo_id or 'objectives'}.")


# ── assessment family ───────────────────────────────────────────────────────

def _element_lo_map(graph) -> dict[str, dict]:
    """LO lookup over element nodes, the single source of truth for every
    item list."""
    return {
        str(n["data"].get("id")): n["data"]
        for n in graph.element_nodes(NodeType.OBJECTIVE)
        if isinstance(n.get("data"), dict) and n["data"].get("id")
    }


def _repair_assessment_family(ctx: RepairContext, violations: list) -> list:
    # Everything else — bloom_mismatch_assessment, evaluation_quality (a thin
    # pilot plan, a plan with no formative method), plan_coverage (a planned
    # category with no item) — is MISSING WRITING and goes back to the
    # Designer as a repair turn in its own loop.
    coverage = [v for v in violations if v.violation_type in ("C2", "P3")]
    completeness = [v for v in violations if v.violation_type == "item_completeness"]
    if completeness:
        repair_item_completeness(ctx, completeness)
    if coverage:
        repair_assessment_coverage(ctx, coverage)
    return [v for v in violations if v not in coverage and v not in completeness]


def repair_assessment_coverage(ctx: RepairContext, violations: list) -> None:
    """C2 (assessed_by) / P3 (realizes-plan): repair the DANGLING REFERENCE only.

    An item pointing at an objective that does not exist, or carrying a
    plan_category outside the plan, is a bad pointer over ids the design
    already holds — a lookup fixes it exactly. An objective with no item at
    all is a MISSING ARTIFACT, and writing one is the agent's job: it comes
    back as a repair turn inside the Designer's own tool loop, where the
    request, the model's answer and the resulting artifact all sit in one
    transcript. Writing it here would mean a second conversation under a
    second system prompt, making the trace claim an agent said something it
    never saw.
    """
    graph = ctx.graph
    tools = [dict(n["data"]) for n in graph.element_nodes(NodeType.ASSESSMENT)]
    lo_map = _element_lo_map(graph)
    plan_node = graph.get_node(graph.section_id(NodeType.ASSESSMENT_PLAN))
    # The categories the plan PROMISED, read the one way every consumer of
    # `lo_coverage_targets` reads it. Scanning `diagnostic`/`formative`/
    # `summative` buckets instead is how this falls through to ["summative"]
    # and re-points every malformed item there: no rule asks for those buckets
    # and the schema does not declare them.
    plan_categories = sorted(
        alignment._promised_categories(plan_node["data"] if plan_node else {})
    ) or ["summative"]

    repaired_ids: list[str] = []
    for violation in violations:
        item_id = str(violation.metadata.get("item_id") or "")
        if not item_id:
            continue
        item = next((t for t in tools if isinstance(t, dict) and str(t.get("item_id")) == item_id), None)
        if not item:
            continue
        aligned = str(item.get("aligned_objective") or "")
        if lo_map and aligned not in lo_map:
            question = str(item.get("question", "")).lower()
            item["aligned_objective"] = next(
                (lo for lo in lo_map if lo.lower() in question), next(iter(lo_map), aligned))
        if str(item.get("plan_category", "")).lower() not in alignment._ASSESSMENT_PLAN_CATEGORIES:
            item["plan_category"] = plan_categories[0]
        item["repaired"] = True
        graph.add_element_node(NodeType.ASSESSMENT, item_id, dict(item))
        repaired_ids.append(item_id)

    if not repaired_ids:
        return
    alignment.match_id_reverse(graph, "C2", field="aligned_objective")
    alignment.match_p3_realizes(graph)
    _log_repair(ctx, str(NodeType.ASSESSMENT), violation_type=violations[0].violation_type,
                repaired_fields=["assessment_tools"], rule="repair_alignment_coverage",
                input_summary="; ".join(v.message for v in violations)[:200],
                output_summary=f"Re-pointed {', '.join(repaired_ids)}.")


def repair_item_completeness(ctx: RepairContext, violations: list) -> None:
    """item_completeness: a selectable-response item shipped without its
    response set (options/answer key).

    Deterministic and last-resort: the item is reformatted as ``short_answer``.
    Its question and scoring_criteria already carry the judgment, while a
    keyless choice item administers as nothing. Writing the options is the
    agent's job and it has already had its repair turns by the time this runs
    (:meth:`ToolLoop._own_violations` shows the violation first) — this only
    stops an unanswerable item reaching the output.
    """
    wanted = [str(v.metadata.get("item_id", "")) for v in violations if v.metadata.get("item_id")]
    if not wanted:
        return
    if ctx.graph_mode:
        pool = {str(n["data"].get("item_id", "")): dict(n["data"])
                for n in ctx.graph.element_nodes(NodeType.ASSESSMENT)}
    else:
        doc = ctx.store.get("assessment") or {}
        pool = {str(t.get("item_id", "")): dict(t)
                for t in (doc.get("assessment_tools") or []) if isinstance(t, dict)}
    updates_by_id = {iid: {"type": "short_answer", "repaired": True}
                     for iid in wanted if iid in pool}
    if not updates_by_id:
        return
    reformatted = list(updates_by_id)

    if ctx.graph_mode:
        for iid, updates in updates_by_id.items():
            node_id = f"{NodeType.ASSESSMENT}{ctx.graph.ELEMENT_SEP}{iid}"
            ctx.graph.update_node(node_id, updates)
            ctx.trajectory.log_node_edit("update", node_id, NodeType.ASSESSMENT)
    else:
        doc = ctx.store.get("assessment") or {}
        tools = [
            {**t, **updates_by_id[str(t.get("item_id", ""))]}
            if isinstance(t, dict) and str(t.get("item_id", "")) in updates_by_id else t
            for t in (doc.get("assessment_tools") or [])
        ]
        ctx.store.put("assessment", {**doc, "assessment_tools": tools})

    _log_repair(ctx, str(NodeType.ASSESSMENT), violation_type="item_completeness",
                repaired_fields=["assessment_tools"], rule="repair_item_completeness",
                input_summary="; ".join(v.message for v in violations)[:200],
                output_summary=f"reformatted {len(reformatted)} keyless item(s) as short_answer")


# ── activity family ─────────────────────────────────────────────────────────

def _repair_activity_family(ctx: RepairContext, violations: list) -> list:
    # C3, P4, `activity_engagement` and `bloom_mismatch_activity` never arrive:
    # `repair` filters REPORT_ONLY types out before dispatch.
    remaining = []
    coverage_violations = []
    for violation in violations:
        if getattr(violation, "violation_type", "") == "C4":
            coverage_violations.append(violation)
        else:
            remaining.append(violation)
    if coverage_violations:
        repair_activity_coverage(ctx, coverage_violations)
    return remaining


def repair_activity_coverage(ctx: RepairContext, violations: list) -> None:
    """C4 only: an assessment item with no preparing activity gets pointed at
    by one the design already has, and an activity whose item references do not
    resolve has them pruned and replaced with a real one.

    C3 — an objective with no practicing activity at all — is NOT repaired.
    Filling it meant writing "Guided practice for ILO-01 … on a realistic task
    with instructor feedback", which is an activity in shape only; it read as
    coverage to every downstream measure without any design behind it."""
    graph = ctx.graph
    activities = [dict(n["data"]) for n in graph.element_nodes(NodeType.ACTIVITY)]
    assessment_ids = [str(n["data"].get("item_id"))
                      for n in graph.element_nodes(NodeType.ASSESSMENT) if n["data"].get("item_id")]
    item_lo = {str(n["data"].get("item_id")): alignment.bare_ref(n["data"].get("aligned_objective"))
               for n in graph.element_nodes(NodeType.ASSESSMENT) if n["data"].get("item_id")}

    repaired_ids: list[str] = []
    touched: set[str] = set()
    for violation in violations:
        md = violation.metadata
        # Two distinct C4 findings arrive here and must not be conflated:
        # appending whatever node the violation named — including ACTIVITY
        # ids from establisher gaps — into the first activity's item list
        # shipped 'TLA-P-ILO-01' x5 inside prepares_for_assessment.
        ref = str(md.get("node_id") or getattr(violation, "node_id", "") or "")
        bare = ref.split(graph.ELEMENT_SEP, 1)[-1]
        sep = graph.ELEMENT_SEP
        if ref.startswith(f"{NodeType.ASSESSMENT}{sep}") and activities:
            # An item no activity prepares for: point one activity at it —
            # prefer an activity aligned to the item's own objective.
            host = next(
                (a for a in activities if isinstance(a, dict) and item_lo.get(bare)
                 and item_lo[bare] in [alignment.bare_ref(r) for r in (a.get("aligned_objectives") or [])]),
                activities[0],
            )
            prep = host.setdefault("prepares_for_assessment", [])
            if isinstance(prep, list) and bare in assessment_ids and bare not in prep:
                prep.append(bare)
                repaired_ids.append(ref)
                touched.add(str(host.get("id")))
        elif ref.startswith(f"{NodeType.ACTIVITY}{sep}"):
            # An activity with no resolvable item refs: prune the dangling
            # refs and give it one REAL item, preferring one that measures
            # an objective this activity practices.
            act = next((a for a in activities
                        if isinstance(a, dict) and str(a.get("id")) == bare), None)
            if act is not None and assessment_ids:
                prep = [alignment.bare_ref(r) for r in (act.get("prepares_for_assessment") or [])]
                prep = [r for r in prep if r in assessment_ids]
                if not prep:
                    act_los = [alignment.bare_ref(r) for r in (act.get("aligned_objectives") or [])]
                    pick = next((i for i in assessment_ids if item_lo.get(i) in act_los),
                                assessment_ids[0])
                    prep.append(pick)
                act["prepares_for_assessment"] = prep
                act["repaired"] = True
                repaired_ids.append(ref)
                touched.add(str(act.get("id")))

    if not touched:
        return
    for activity in activities:
        if isinstance(activity, dict) and str(activity.get("id")) in touched:
            graph.add_element_node(NodeType.ACTIVITY, str(activity["id"]), dict(activity))
    alignment.match_list_reverse(graph, "C3", field="aligned_objectives")
    alignment.match_list(graph, "C4", field="prepares_for_assessment")
    _log_repair(ctx, str(NodeType.ACTIVITY), violation_type=violations[0].violation_type, repaired_fields=["learning_activities"],
                rule="repair_alignment_coverage", input_summary="; ".join(v.message for v in violations)[:200],
                output_summary=f"Repointed activities: {', '.join(repaired_ids)}.")


def _repair_content_family(ctx: RepairContext, violations: list) -> list:
    remaining = []
    coverage_violations = []
    orphan_violations = []
    for violation in violations:
        vtype = getattr(violation, "violation_type", "")
        # C5 and P6 never arrive: `repair` filters REPORT_ONLY out first.
        if vtype == "P5":
            coverage_violations.append(violation)
        elif vtype == "orphan_content":
            orphan_violations.append(violation)
        else:
            remaining.append(violation)
    if coverage_violations:
        repair_content_coverage(ctx, coverage_violations)
    if orphan_violations:
        # RETURNED, not dropped: an orphaned MODULE is not repairable (see
        # `repair_content_orphans`), and a routine that silently swallows
        # what it cannot fix is the exact failure `repair`'s docstring names.
        remaining += repair_content_orphans(ctx, orphan_violations)
    return remaining


def repair_content_coverage(ctx: RepairContext, violations: list) -> None:
    """A material with no ``linked_module`` (``P5``, or ``orphan_content`` on
    a material) is pointed at a module the design already has. Both callers
    pre-filter to material violations; the type is not re-checked here, or an
    ``orphan_content`` material would be silently swallowed.

    C5 — an activity with no supporting content at all — is NOT repaired. The
    module a repair could add here is one titled "Support module for TLA-01"
    and described as "Content supporting activity TLA-01": a node that closes
    the relation and teaches nothing."""
    graph = ctx.graph
    module_nodes = graph.element_nodes(NodeType.CONTENT)
    repaired_ids: list[str] = []
    for violation in violations:
        if module_nodes:
            material_id = str(violation.metadata.get("node_id") or violation.node_id or "")
            material = graph.get_node(material_id) if material_id else None
            if material is not None:
                module_ref = module_nodes[0]["id"].split(graph.ELEMENT_SEP, 1)[-1]
                material["data"]["linked_module"] = module_ref
                alignment.record_provenance(graph, "P5", [module_nodes[0]["id"]], material_id)
                repaired_ids.append(material_id)
    if not repaired_ids:
        return
    _log_repair(
        ctx, repaired_ids[0],
        violation_type=violations[0].violation_type, repaired_fields=["learner_materials"],
                rule="repair_coverage", input_summary="; ".join(v.message for v in violations)[:200],
                output_summary=f"Linked materials to a module: {', '.join(repaired_ids)}.")


def repair_content_orphans(ctx: RepairContext, violations: list) -> list:
    """orphan_content on a MATERIAL is repaired; on a MODULE it is reported.

    The material case is structural — a material with no linked module is
    re-pointed at one the design already holds, the same shape as
    :func:`repair_content_coverage`'s P5 branch, which is reused directly
    because ``violation.node_id`` there is already a material id.

    THE MODULE CASE IS NOT REPAIRABLE: linking an orphaned module to some
    activity fabricates an ALIGNMENT EDGE (measured on run 2559b22d: twelve
    modules pointed at ``TLA-0101``, eleven activities still uncovered, and a
    graph asserting relations the modules' own data contradicts). Deciding
    which activity a module supports is authoring the alignment claim this
    package exists to make auditable, not rearranging what the design holds.
    So an orphaned module is a finding: it stays in the residual count and
    goes back to the Content Designer as a repair turn.
    """
    graph = ctx.graph
    modules, rest = [], []
    for violation in violations:
        node_id = str(violation.metadata.get("node_id") or violation.node_id or "")
        target = modules if node_id.startswith(
            f"{NodeType.CONTENT}{graph.ELEMENT_SEP}") else rest
        target.append(violation)
    if rest:
        repair_content_coverage(ctx, rest)
    return modules


# ── rubric family ───────────────────────────────────────────────────────────

def _repair_rubric_family(ctx: RepairContext, violations: list) -> list:
    """Rubric criteria are FIELDS of the item they mark, so the only repair
    is the one that reads a criterion against its own item;
    ``rubric_consistency`` is REPORT_ONLY."""
    remaining = []
    evidence_violations = []
    for violation in violations:
        if getattr(violation, "violation_type", "") == "evidence_alignment":
            evidence_violations.append(violation)
        else:
            remaining.append(violation)
    if evidence_violations:
        repair_evidence_alignment(ctx, evidence_violations)
    return remaining


def repair_evidence_alignment(ctx: RepairContext, violations: list) -> None:
    """evidence_alignment: a criterion expects evidence its own item cannot
    produce — loosen the criterion's ``evidence_type`` to what the item can
    actually give.

    STRUCTURAL, not generative: it rewrites one enum field to a value the
    design already holds. Keyed by ``(item_id, rc_id)``, never by ``rc_id``
    alone: criterion ids are model-written inside each item by independent
    Developers, so ``RC-01`` on several items is the normal case and a
    criterion on another item must not be rewritten.
    """
    graph = ctx.graph
    flagged = {(str(v.metadata.get("item_id") or ""), str(v.metadata.get("rc_id") or ""))
               for v in violations}
    repaired_ids: list[str] = []
    for item in graph.element_nodes(NodeType.ASSESSMENT):
        item_type = str(item["data"].get("type", "") or "")
        if not item_type:
            continue
        item_id = str(item["data"].get("item_id", ""))
        criteria = [dict(rc) if isinstance(rc, dict) else rc
                    for rc in (item["data"].get("rubric") or [])]
        touched = False
        for rc in criteria:
            if not isinstance(rc, dict) or (item_id, str(rc.get("id", ""))) not in flagged:
                continue
            rc["evidence_type"] = item_type
            rc["repaired"] = True
            repaired_ids.append(str(rc.get("id", "")))
            touched = True
        if touched:
            data = {**item["data"], "rubric": criteria}
            graph.add_element_node(
                NodeType.ASSESSMENT, str(item["data"].get("item_id", "")), data)
    if not repaired_ids:
        return
    _log_repair(ctx, str(NodeType.ASSESSMENT),
                violation_type="evidence_alignment", repaired_fields=["rubric"],
                rule="repair_evidence_alignment",
                input_summary="; ".join(v.message for v in violations)[:200],
                output_summary=f"Loosened evidence_type for {', '.join(repaired_ids)}.")


# ── implementation family ───────────────────────────────────────────────────

def _repair_implementation_family(ctx: RepairContext, violations: list) -> list:
    """No repair: everything this family owns (``feasibility``,
    ``actionability``, ``P10``, ``P11``) is REPORT_ONLY. A plan is not made
    feasible by a note recording that someone noticed it was not. The types
    stay in ``OWNED_BY_FAMILY`` so reconciliation names this planner as the
    owner; they come back unrepaired."""
    return list(violations)


_FAMILY_REPAIRERS: dict[str, Callable[[RepairContext, list], list]] = {
    "outcome_designer": _repair_outcome_family,
    "assessment_designer": _repair_assessment_family,
    "activity_designer": _repair_activity_family,
    "content_designer": _repair_content_family,
    "rubric_designer": _repair_rubric_family,
    "implementation_planner": _repair_implementation_family,
}
