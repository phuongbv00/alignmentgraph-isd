"""Shared repair toolbox — the corrective half of the safeguard substrate
(``checks.py`` finds violations; this module fixes the fixable ones).

Free functions over the run's context substrate (graph or blackboard), owned
by neither decomposition arm: each Designer's ``repair()`` is a thin dispatch
into :func:`repair`, and the single arm's state machine calls the same
dispatch with its own :class:`RepairContext` — no arm instantiates the other
arm's agent classes to borrow its corrective machinery. Repair strength is a
safeguard held constant across the ablation (see ``config.py``), which is why
these routines live on the shared substrate next to the checks they answer.

A repair that fixes a malformed field is deterministic. A repair that has to
supply a MISSING artifact hands the writing back to the model — one persona-free
call per batch, with a deterministic fallback so every routine still converges
when the call fails (:func:`_llm_repair_items`, :func:`repair_item_completeness`,
:func:`repair_formative_methods`, :func:`repair_pilot_data_plan`). Synthesising
that content from a template instead put the objective's own statement into the
assessment item, which reads to any text-similarity measure as perfect
objective-assessment correspondence that no design work produced.
All logging goes through ``ctx.actor``, so a repair records whoever actually
ran it — a specialist in the multi arm, the single designer in the single arm.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from .alignment_graph import NodeType, alignment


@dataclass(frozen=True)
class RepairContext:
    """The slice of an agent a repair routine needs. Exactly one of
    ``graph``/``store`` is live per run (see config.py's ``context_mode``)."""

    graph: object | None
    store: object | None
    trajectory: object
    call_llm: Callable[..., str]
    actor: str

    @property
    def graph_mode(self) -> bool:
        return self.graph is not None


def context_for(agent) -> RepairContext:
    """Build a :class:`RepairContext` from any agent exposing the BaseISDAgent
    surface (``graph``/``store``/``trajectory``/``_call_llm``)."""
    return RepairContext(
        graph=agent.graph, store=agent.store, trajectory=agent.trajectory,
        call_llm=agent._call_llm, actor=type(agent).__name__,
    )


def _log_repair(ctx: RepairContext, node_id: str, *, violation_type: str = "",
                repaired_fields: list[str] | None = None, rule: str = "",
                input_summary: str = "", output_summary: str = "") -> None:
    """ONE record per repair: the structured fields plus the rule's own
    narrative (which repair routine ran, what it saw, what it did). These used
    to be two separate log calls — a repair event and a paired ``repair_*``
    recovery event — which double-counted every repair in ``repair_events`` /
    ``repair_metrics`` the moment both landed in the unified event log."""
    ctx.trajectory.log_repair_event(
        agent=ctx.actor, violation_type=violation_type,
        node_id=node_id, repaired_fields=repaired_fields or [],
        rule=rule, input_summary=input_summary, output_summary=output_summary,
    )


# ── ownership: which violation types each artifact family's repairs answer ──
# Designer classes point their OWNED_VIOLATION_TYPES here; the single arm's
# per-state steps read the same map by family key. One definition, both arms.
OWNED_BY_FAMILY: dict[str, frozenset[str]] = {
    "outcome_designer": frozenset({"bloom"}),
    "assessment_designer": frozenset(
        {"C2", "P3", "bloom_mismatch_assessment", "evaluation_quality", "plan_coverage",
         "item_completeness"}),
    "activity_designer": frozenset(
        {"C3", "C4", "P4", "activity_engagement", "bloom_mismatch_activity"}),
    "content_designer": frozenset({"C5", "P5", "P6", "orphan_content"}),
    "rubric_designer": frozenset(
        {"C6", "C7", "rubric_consistency", "evidence_alignment", "orphan_rubric"}),
    "implementation_planner": frozenset({"feasibility", "actionability"}),
}


def repair(family: str, violations: list, ctx: RepairContext) -> list:
    """Dispatch ``violations`` to the ``family``'s repair routines; returns the
    violations no routine answers (mirroring each Designer's old ``repair()``
    contract)."""
    return _FAMILY_REPAIRERS[family](ctx, violations)


# ── outcome family ──────────────────────────────────────────────────────────

BLOOM_VERB_BY_LEVEL = {
    "remember": "recall", "understand": "explain", "apply": "apply",
    "analyze": "analyze", "evaluate": "evaluate", "create": "design",
}
VERB_REPLACEMENTS = {
    "comprehend": "explain", "understand": "explain", "grasp": "explain",
    "learn": "identify", "know": "identify",
}
_LEVEL_NAME_BY_INDEX = {1: "remember", 2: "understand", 3: "apply",
                        4: "analyze", 5: "evaluate", 6: "create"}


def _level_from_verb(verb: str) -> str:
    """The Bloom level a verb names. A verb that spans levels ("construct" is
    both Apply and Create) resolves to the lowest — a repair should not inflate
    the level an objective claims."""
    from .checks import _VERB_LEVELS

    levels = _VERB_LEVELS.get(str(verb).lower().strip(".,;"), set())
    return _LEVEL_NAME_BY_INDEX[min(levels)] if levels else "apply"


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
        if old_verb and re.search(re.escape(old_verb), statement, flags=re.IGNORECASE):
            lo["statement"] = re.sub(re.escape(old_verb), replacement, statement, count=1, flags=re.IGNORECASE)
        elif replacement not in statement.lower():
            lo["statement"] = f"{statement} This is measured by asking learners to {replacement} the target skill in context."
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
        if isinstance(lo, dict) and lo.get("id"):
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
    """LO lookup over element nodes — the single source of truth since the
    legacy full-list section nodes (objective_0/assessment_0/activity_0) were
    retired: sections now follow the analysis-narrative pattern and never
    carry an element list, so repairs read and write elements directly."""
    return {
        str(n["data"].get("id")): n["data"]
        for n in graph.element_nodes(NodeType.OBJECTIVE)
        if isinstance(n.get("data"), dict) and n["data"].get("id")
    }


OBSERVABLE_RUBRIC = (
    "Analytic rubric, 4 levels (0-3) per criterion: task completed with at least 80% "
    "accuracy; target concepts applied correctly; justification cites observable evidence."
)

FALLBACK_METHODS = [
    "Structured observation during activities using a facilitation checklist",
    "Exit tickets after each module scored against the objective criteria",
    "Rubric-scored formative checkpoints with instructor feedback",
]


def _repair_assessment_family(ctx: RepairContext, violations: list) -> list:
    remaining = []
    item_violations = []
    coverage_violations = []
    quality_violations = []
    plan_violations = []
    completeness_violations = []
    for violation in violations:
        vtype = getattr(violation, "violation_type", "")
        if vtype == "bloom_mismatch_assessment":
            item_violations.append(violation)
        elif vtype in ("C2", "P3"):
            coverage_violations.append(violation)
        elif vtype == "evaluation_quality":
            quality_violations.append(violation)
        elif vtype == "plan_coverage":
            plan_violations.append(violation)
        elif vtype == "item_completeness":
            completeness_violations.append(violation)
        else:
            remaining.append(violation)
    if item_violations:
        repair_assessment_items(ctx, item_violations)
    if completeness_violations:
        repair_item_completeness(ctx, completeness_violations)
    if coverage_violations:
        repair_assessment_coverage(ctx, coverage_violations)
    for violation in quality_violations:
        if (getattr(violation, "metadata", None) or {}).get("section") == "pilot_data_plan":
            repair_pilot_data_plan(ctx, violation)
        else:
            repair_formative_methods(ctx, violation)
    if plan_violations:
        repair_plan_coverage(ctx, plan_violations)
    return remaining


def _fallback_item_text(spec: dict) -> dict:
    """Deterministic stand-in when the model writes nothing. It only names the
    objective, so the item's text is close to the objective's own statement —
    which is exactly why it is the fallback and not the repair."""
    return {
        "question": (f"Demonstrate the performance described by {spec['objective_id']}: "
                     f"{spec['objective']}"),
        "scoring_criteria": OBSERVABLE_RUBRIC,
    }


def _llm_repair_items(ctx: RepairContext, specs: list[dict]) -> dict[str, dict]:
    """Ask the model to WRITE the assessment items a coverage repair needs,
    one call for the whole batch, keyed by ``item_id``.

    A coverage gap is a missing artifact, not a malformed field, so the fix is
    a generation the model owns. Synthesising the question deterministically
    put the objective's own statement in the item text, which then measured as
    near-perfect objective-assessment correspondence without any design work
    having happened. Ids the model omits fall back to :func:`_fallback_item_text`,
    so the repair still converges on a call that fails or returns nothing."""
    import json

    from .agents.base import parse_json_response

    system = (
        "Write the missing assessment items for a course design. For each spec write a "
        "``question`` that makes the learner PERFORM the named cognitive level on that "
        "objective's subject matter, and ``scoring_criteria`` naming observable evidence "
        "a scorer can check. The question must be a task in its own words — never restate "
        "the objective back as the question. Match ``type``: a performance_task sets a "
        "realistic task to carry out, a short_answer asks for a written response. "
        'Return ONLY valid JSON: {"items": [{"item_id": "<id>", "question": "<question>", '
        '"scoring_criteria": "<criteria>"}, ...]}'
    )
    user = json.dumps({"items": specs}, ensure_ascii=False)[:4000]
    response = ctx.call_llm(
        [{"role": "system", "content": system}, {"role": "user", "content": user}], max_retries=0,
    )
    parsed = parse_json_response(response, warn=False) or {}
    out: dict[str, dict] = {}
    for entry in parsed.get("items") or []:
        if not isinstance(entry, dict):
            continue
        item_id = str(entry.get("item_id") or "").strip()
        question = str(entry.get("question") or "").strip()
        if not item_id or not question:
            continue
        out[item_id] = {
            "question": question,
            "scoring_criteria": str(entry.get("scoring_criteria") or "").strip() or OBSERVABLE_RUBRIC,
        }
    return out


def repair_plan_coverage(ctx: RepairContext, violations: list) -> None:
    """The plan promised a (objective, category) pair no item realises — the
    model writes the missing item. Format follows the objective's cognitive
    level, so a repaired summative item for an Apply+ objective is a
    performance task rather than a recognition item that would then trip
    the Bloom cross-check."""
    graph = ctx.graph
    specs: list[dict] = []
    for violation in violations:
        lo_id = str(violation.metadata.get("lo_id", "") or "")
        category = str(violation.metadata.get("plan_category", "") or "")
        if not lo_id or not category:
            continue
        lo_node = graph.get_node(f"{NodeType.OBJECTIVE}{graph.ELEMENT_SEP}{lo_id}")
        lo_data = lo_node["data"] if lo_node else {}
        level_name = str(lo_data.get("level", "apply"))
        level = alignment.bloom_level_of(level_name) or 1
        specs.append({
            "item_id": f"AT-{category[:1].upper()}-{lo_id}",
            "objective_id": lo_id,
            "objective": str(lo_data.get("statement", "")),
            "level": level_name,
            "type": "performance_task" if level >= 3 else "short_answer",
            "plan_category": category,
        })
    if not specs:
        return

    written = _llm_repair_items(ctx, specs)
    repaired: list[str] = []
    for spec in specs:
        item_id = spec["item_id"]
        drafted = written.get(item_id) or _fallback_item_text(spec)
        graph.add_element_node(NodeType.ASSESSMENT, item_id, {
            "item_id": item_id,
            "type": spec["type"],
            "question": drafted["question"],
            "aligned_objective": spec["objective_id"],
            "plan_category": spec["plan_category"],
            "required_cognitive_process": spec["level"],
            "scoring_criteria": drafted["scoring_criteria"],
            "repaired": True,
        })
        repaired.append(item_id)

    alignment.match_id_reverse(graph, "C2", field="aligned_objective")
    alignment.match_p3_realizes(graph)
    _log_repair(ctx, str(NodeType.ASSESSMENT), violation_type="plan_coverage", repaired_fields=["assessment_tools"],
                rule="repair_plan_coverage", input_summary="; ".join(v.message for v in violations)[:200],
                output_summary=f"Added {', '.join(repaired) or 'no'} item(s) the plan promised.")


def repair_assessment_coverage(ctx: RepairContext, violations: list) -> None:
    """C2 (assessed_by) / P3 (realizes-plan) gaps: either a dangling item
    reference (fix it deterministically) or an uncovered objective (the model
    writes the item, with a deterministic stub as fallback)."""
    graph = ctx.graph
    tools = [dict(n["data"]) for n in graph.element_nodes(NodeType.ASSESSMENT)]
    lo_map = _element_lo_map(graph)
    plan_node = graph.get_node(graph.section_id(NodeType.ASSESSMENT_PLAN))
    plan_categories = [
        cat for cat in alignment._ASSESSMENT_PLAN_CATEGORIES if plan_node and plan_node["data"].get(cat)
    ] or ["summative"]

    # Objectives with no item at all need one WRITTEN; collect them first so the
    # whole batch costs one generation call.
    specs = [
        {"item_id": f"AT-R-{lo}", "objective_id": lo,
         "objective": str(lo_map.get(lo, {}).get("statement", "")),
         "level": str(lo_map.get(lo, {}).get("level", "apply")),
         "type": "performance_task", "plan_category": plan_categories[0]}
        for lo in dict.fromkeys(
            str(v.metadata.get("lo_id") or "") for v in violations if v.metadata.get("lo_id")
        )
    ]
    written = _llm_repair_items(ctx, specs) if specs else {}
    drafts = {spec["item_id"]: (written.get(spec["item_id"]) or _fallback_item_text(spec))
              for spec in specs}

    repaired_ids: list[str] = []
    for violation in violations:
        md = violation.metadata
        lo_id = str(md.get("lo_id") or "")
        item_id = str(md.get("item_id") or "")
        if lo_id:
            new_item_id = f"AT-R-{lo_id}"
            drafted = drafts.get(new_item_id) or _fallback_item_text(
                {"objective_id": lo_id, "objective": str(lo_map.get(lo_id, {}).get("statement", ""))})
            graph.add_element_node(NodeType.ASSESSMENT, new_item_id, {
                "item_id": new_item_id, "type": "performance_task",
                "question": drafted["question"],
                "aligned_objective": lo_id, "plan_category": plan_categories[0],
                "required_cognitive_process": str(lo_map.get(lo_id, {}).get("level", "apply")),
                "scoring_criteria": drafted["scoring_criteria"], "repaired": True,
            })
            repaired_ids.append(new_item_id)
        elif item_id:
            item = next((t for t in tools if isinstance(t, dict) and str(t.get("item_id")) == item_id), None)
            if not item:
                continue
            aligned = str(item.get("aligned_objective") or "")
            if lo_map and aligned not in lo_map:
                question = str(item.get("question", "")).lower()
                item["aligned_objective"] = next((lo for lo in lo_map if lo.lower() in question), next(iter(lo_map), aligned))
            if str(item.get("plan_category", "")).lower() not in alignment._ASSESSMENT_PLAN_CATEGORIES:
                item["plan_category"] = plan_categories[0]
            item["repaired"] = True
            graph.add_element_node(NodeType.ASSESSMENT, item_id, dict(item))
            repaired_ids.append(item_id)

    alignment.match_id_reverse(graph, "C2", field="aligned_objective")
    alignment.match_p3_realizes(graph)
    _log_repair(ctx, str(NodeType.ASSESSMENT), violation_type=violations[0].violation_type, repaired_fields=["assessment_tools"],
                rule="repair_alignment_coverage", input_summary="; ".join(v.message for v in violations)[:200],
                output_summary=f"Fixed/added items for {', '.join(repaired_ids) or 'existing coverage'}.")


def repair_item_completeness(ctx: RepairContext, violations: list) -> None:
    """item_completeness: a selectable-response item shipped without its
    response set (options/answer key). Same repair on either substrate: one
    persona-free LLM attempt writes the missing options and answer; an item
    the LLM cannot complete is reformatted as short_answer (deterministic —
    the question and scoring_criteria already carry the judgment, while a
    keyless choice item administers as nothing)."""
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
    flagged = {iid: pool[iid] for iid in wanted if iid in pool}
    if not flagged:
        return

    attempt = _llm_item_options(ctx, list(flagged.values()))
    completed: list[str] = []
    reformatted: list[str] = []
    updates_by_id: dict[str, dict] = {}
    for iid, item in flagged.items():
        fix = attempt.get(iid) or {}
        options = fix.get("options")
        answer = str(fix.get("correct_answer", "") or "").strip()
        has_options = isinstance(options, list) and len([o for o in options if str(o).strip()]) >= 2
        if answer and (has_options or str(item.get("type", "")).lower() == "true_false"):
            updates: dict = {"correct_answer": answer, "repaired": True}
            if has_options:
                updates["options"] = [str(o).strip() for o in options if str(o).strip()][:6]
            completed.append(iid)
        else:
            updates = {"type": "short_answer", "repaired": True}
            reformatted.append(iid)
        updates_by_id[iid] = updates

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

    summary_bits = []
    if completed:
        summary_bits.append(f"added options/answer key to {len(completed)} item(s)")
    if reformatted:
        summary_bits.append(f"reformatted {len(reformatted)} keyless item(s) as short_answer")
    _log_repair(ctx, str(NodeType.ASSESSMENT), violation_type="item_completeness",
                repaired_fields=["assessment_tools"], rule="repair_item_completeness",
                input_summary="; ".join(v.message for v in violations)[:200],
                output_summary="; ".join(summary_bits) or "no matching items found")


def _llm_item_options(ctx: RepairContext, items: list[dict]) -> dict[str, dict]:
    import json

    from .agents.base import parse_json_response

    system = (
        "Complete selectable-response assessment items that are missing their answer options "
        "and/or answer key. For each item write 3-5 options — plausible distractors a partially "
        "informed learner might pick — and set correct_answer to the right option verbatim; for "
        "a true_false item return only correct_answer. Return ONLY valid JSON: "
        '{"items": [{"item_id": "<id>", "options": ["<option>", ...], '
        '"correct_answer": "<the correct option>"}, ...]}'
    )
    user = json.dumps(
        {"items": [{"item_id": t.get("item_id"), "type": t.get("type"),
                    "question": t.get("question"),
                    "scoring_criteria": t.get("scoring_criteria")} for t in items]},
        ensure_ascii=False)[:4000]
    response = ctx.call_llm(
        [{"role": "system", "content": system}, {"role": "user", "content": user}], max_retries=0,
    )
    parsed = parse_json_response(response, warn=False) or {}
    out: dict[str, dict] = {}
    for entry in parsed.get("items") or []:
        if isinstance(entry, dict) and entry.get("item_id"):
            out[str(entry["item_id"])] = entry
    return out


def repair_assessment_items(ctx: RepairContext, violations: list) -> None:
    """bloom_mismatch_assessment: no item measuring an objective can elicit
    its Bloom level — the model writes a performance_task that can, falling
    back to a deterministic stub so convergence stays guaranteed."""
    graph = ctx.graph
    tools = [dict(n["data"]) for n in graph.element_nodes(NodeType.ASSESSMENT)]
    lo_map = _element_lo_map(graph)

    specs: list[dict] = []
    for lo_id in dict.fromkeys(
        str(v.metadata.get("lo_id") or "") for v in violations if v.metadata.get("lo_id")
    ):
        capability = max(
            (alignment._item_capability(t) for t in tools if isinstance(t, dict) and str(t.get("aligned_objective")) == lo_id),
            default=0,
        )
        level = str(lo_map.get(lo_id, {}).get("level", "apply"))
        # Ask the SAME predicate the check asks. This used to re-implement
        # the old binary gate (capability > recognition ceiling), so once
        # format_valid_for_capability became a real level comparison the
        # repair skipped exactly the cases the check had just flagged —
        # a Create objective measured by an Apply item was reported every
        # round and fixed in none, burning the self-validation budget.
        if alignment.format_valid_for_capability(capability, alignment.bloom_level_of(level)):
            continue
        specs.append({
            "item_id": f"AT-P-{lo_id}", "objective_id": lo_id,
            "objective": str(lo_map.get(lo_id, {}).get("statement", "")),
            "level": level, "type": "performance_task", "plan_category": "summative",
        })

    written = _llm_repair_items(ctx, specs) if specs else {}
    for spec in specs:
        item_id = spec["item_id"]
        drafted = written.get(item_id) or _fallback_item_text(spec)
        graph.add_element_node(NodeType.ASSESSMENT, item_id, {
            "item_id": item_id, "type": "performance_task",
            "question": drafted["question"],
            "aligned_objective": spec["objective_id"], "plan_category": "summative",
            "required_cognitive_process": spec["level"],
            "scoring_criteria": drafted["scoring_criteria"], "repaired": True,
        })

    alignment.match_id_reverse(graph, "C2", field="aligned_objective")
    alignment.match_p3_realizes(graph)
    _log_repair(ctx, str(NodeType.ASSESSMENT), violation_type="bloom_mismatch_assessment", repaired_fields=["assessment_tools"],
                rule="repair_assessment_items", input_summary="; ".join(v.message for v in violations)[:200],
                output_summary=f"Added performance evidence for {len(violations)} objective(s).")


def repair_formative_methods(ctx: RepairContext, violation) -> None:
    """evaluation_quality: assessment_plan declares formative intent but
    names no concrete data-collection method. Same repair on either
    substrate; one persona-free LLM attempt, deterministic fallback."""
    if not ctx.graph_mode:
        plan = ctx.store.get("assessment_plan")
        if not plan:
            return
        methods = _llm_formative_methods(ctx, plan) or list(FALLBACK_METHODS)
        ctx.store.put("assessment_plan", {**plan, "formative_methods": methods, "repaired": True})
        _log_repair(ctx, "assessment_plan", violation_type="evaluation_quality", repaired_fields=["formative_methods"],
                rule="repair_formative_methods", input_summary=violation.message,
                output_summary=f"Set {len(methods)} formative data-collection method(s).")
        return
    graph = ctx.graph
    node_id = graph.section_id(NodeType.ASSESSMENT_PLAN)
    node = graph.get_node(node_id)
    if not node:
        return
    methods = _llm_formative_methods(ctx, node["data"])
    if not methods:
        methods = list(FALLBACK_METHODS)
    graph.update_node(node_id, {"formative_methods": methods, "repaired": True})
    _log_repair(ctx, node_id, violation_type="evaluation_quality", repaired_fields=["formative_methods"],
                rule="repair_formative_methods", input_summary=violation.message,
                output_summary=f"Set {len(methods)} formative data-collection method(s).")
    ctx.trajectory.log_node_edit("update", node_id, NodeType.ASSESSMENT_PLAN)


def _render_method(method: object) -> str:
    """A formative method as one readable string. A dict entry (a model that
    emitted {"instrument": ..., "cadence": ...} instead of a string) renders
    as "instrument — cadence"; the previous str() coercion shipped literal
    Python-dict text ("{'instrument': ...}") into the judged output."""
    if isinstance(method, dict):
        parts = [str(v).strip() for v in method.values() if str(v).strip()]
        return " — ".join(parts)
    return str(method).strip()


def repair_pilot_data_plan(ctx: RepairContext, violation) -> None:
    """evaluation_quality (section=pilot_data_plan): the plan's pilot data —
    collection points plus anticipated difficulties with first revisions — is
    missing or thin. The aggregator builds the whole formative half of ADDIE
    Evaluation from these fields, so the hole zeroes two rubric items. Same
    repair on either substrate; one persona-free LLM attempt, then a
    deterministic fallback grounded in the design's own objectives."""
    if not ctx.graph_mode:
        plan = ctx.store.get("assessment_plan")
        if not plan:
            return
        objectives = [o for o in ctx.store.items("objective", "learning_objectives")
                      if isinstance(o, dict)]
        analysis = ctx.store.get("analysis") or {}
        topics = [t for t in ((analysis.get("task_analysis") or {}).get("topics") or [])
                  if isinstance(t, dict)]
        pilot = _repaired_pilot(ctx, plan, objectives, topics)
        ctx.store.put("assessment_plan", {**plan, "pilot_data_plan": pilot, "repaired": True})
        _log_repair(ctx, "assessment_plan", violation_type="evaluation_quality",
                    repaired_fields=["pilot_data_plan"],
                rule="repair_pilot_data_plan", input_summary=violation.message,
                output_summary=f"Set pilot data plan with {len(pilot.get('anticipated_difficulties', []))} difficulties.")
        return
    graph = ctx.graph
    node_id = graph.section_id(NodeType.ASSESSMENT_PLAN)
    node = graph.get_node(node_id)
    if not node:
        return
    objectives = [n["data"] for n in graph.element_nodes(NodeType.OBJECTIVE)]
    topics = [n["data"] for n in graph.element_nodes(NodeType.TOPIC)]
    pilot = _repaired_pilot(ctx, node["data"], objectives, topics)
    graph.update_node(node_id, {"pilot_data_plan": pilot, "repaired": True})
    _log_repair(ctx, node_id, violation_type="evaluation_quality",
                repaired_fields=["pilot_data_plan"],
                rule="repair_pilot_data_plan", input_summary=violation.message,
                output_summary=f"Set pilot data plan with {len(pilot.get('anticipated_difficulties', []))} difficulties.")
    ctx.trajectory.log_node_edit("update", node_id, NodeType.ASSESSMENT_PLAN)


def _valid_difficulties(pilot: dict) -> list[dict]:
    return [
        entry for entry in (pilot.get("anticipated_difficulties") or [])
        if isinstance(entry, dict)
        and str(entry.get("area", "")).strip()
        and str(entry.get("first_revision", "")).strip()
    ]


def _repaired_pilot(ctx: RepairContext, plan_data: dict, objectives: list[dict],
                    topics: list[dict] | None = None) -> dict:
    """The repaired pilot_data_plan: existing fields preserved, holes filled —
    by the LLM when it cooperates, deterministically otherwise."""
    existing = plan_data.get("pilot_data_plan")
    existing = dict(existing) if isinstance(existing, dict) else {}
    attempt = _llm_pilot_data_plan(ctx, plan_data, objectives, topics or [])
    if attempt:
        merged = {**existing, **attempt}
        if len(_valid_difficulties(merged)) >= 2 and merged.get("collection_points"):
            return merged
    return _fallback_pilot_data_plan(existing, plan_data, objectives, topics or [])


def _llm_pilot_data_plan(ctx: RepairContext, plan_data: dict, objectives: list[dict],
                         topics: list[dict]) -> dict:
    import json

    from .agents.base import parse_json_response

    system = (
        "Fix an assessment plan whose pilot data plan is missing or thin. "
        "Return ONLY valid JSON: "
        '{"collection_points": ["<when during the pilot data is captured>", ...], '
        '"anticipated_difficulties": [{"area": "<the topic/module where learners will '
        "struggle> \u2014 <objective id>\", "
        '"rationale": "<why, for these learners>", "detected_by": "<which formative method '
        'surfaces it>", "first_revision": "<the concrete fix>"}, ...]}\n'
        "Name at least two SPECIFIC areas, each anchored to BOTH a real topic/module given "
        "AND the objective id affected (e.g. \"Topic 'Interactive content design' \u2014 "
        "ILO-02\") \u2014 never a bare objective id, never \"general comprehension\"."
    )
    user = json.dumps(
        {"assessment_plan": plan_data,
         "objectives": [{"id": o.get("id"), "statement": o.get("statement"),
                         "level": o.get("level")} for o in objectives],
         "topics": [{"id": t.get("id"), "topic": t.get("topic")} for t in topics]},
        ensure_ascii=False)[:4000]
    response = ctx.call_llm(
        [{"role": "system", "content": system}, {"role": "user", "content": user}], max_retries=0,
    )
    parsed = parse_json_response(response, warn=False) or {}
    result: dict = {}
    if isinstance(parsed.get("collection_points"), list):
        result["collection_points"] = [str(p).strip() for p in parsed["collection_points"]
                                       if str(p).strip()][:5]
    if isinstance(parsed.get("anticipated_difficulties"), list):
        result["anticipated_difficulties"] = [
            e for e in parsed["anticipated_difficulties"] if isinstance(e, dict)][:5]
    return result


def _fallback_pilot_data_plan(existing: dict, plan_data: dict, objectives: list[dict],
                              topics: list[dict] | None = None) -> dict:
    """Deterministic pilot data grounded in the design's own artifacts: the
    highest-demand objectives are the areas first pilot data must watch, and
    the plan's own formative methods are the detectors. Generic wording, real
    ids — the same posture as FALLBACK_METHODS."""
    methods = [_render_method(m) for m in (plan_data.get("formative_methods") or [])]
    methods = [m for m in methods if m]
    detector = methods[0] if methods else "formative checkpoint review"
    pilot = dict(existing)
    if not pilot.get("collection_points"):
        pilot["collection_points"] = ([f"During: {m}" for m in methods[:3]]
                                      or ["After the first module", "Mid-course checkpoint"])
    if len(_valid_difficulties(pilot)) < 2:
        ranked = sorted(
            (o for o in objectives if isinstance(o, dict) and o.get("id")),
            key=lambda o: alignment.bloom_level_of(str(o.get("level", ""))) or 0,
            reverse=True,
        )[:2]
        # anchor each area to a topic AND the objective id (the rubric grades
        # pilot data by the module learners struggled in, not by bare LO ids)
        titles = [str(t.get("topic") or t.get("title") or "").strip()
                  for t in (topics or []) if isinstance(t, dict)]
        titles = [t for t in titles if t]

        def _area(index: int, lo_id: str) -> str:
            if titles:
                return f"Topic '{titles[index % len(titles)]}' \u2014 {lo_id}"
            return f"Module covering {lo_id} \u2014 {lo_id}"

        pilot["anticipated_difficulties"] = [
            {
                "area": _area(i, str(obj.get("id"))),
                "rationale": ("Highest cognitive-demand objective in this design; "
                              "first pilot data should confirm learners can reach it."),
                "detected_by": detector,
                "first_revision": ("Insert a guided worked example and scaffolded practice "
                                   "before the task assessing this objective."),
            }
            for i, obj in enumerate(ranked)
        ] or [
            {"area": "first content module",
             "rationale": "Entry point of the design; pilot data verifies the on-ramp.",
             "detected_by": detector,
             "first_revision": "Slow the first module down and add a checkpoint."},
            {"area": "final assessed task",
             "rationale": "Highest-stakes moment of the design.",
             "detected_by": detector,
             "first_revision": "Add a rehearsal round before the assessed attempt."},
        ]
    return pilot


def _llm_formative_methods(ctx: RepairContext, plan_data: dict) -> list[str]:
    import json

    from .agents.base import parse_json_response

    # Task-only instruction, no persona: this is a shared tool, and whichever
    # agent runs it already carries its own persona in its generation prompts.
    system = (
        "Fix an assessment plan that names no formative data-collection method. "
        'Return ONLY valid JSON: '
        '{"methods": ["<concrete method 1>", "<concrete method 2>", "<concrete method 3>"]}\n'
        "Each method must name an instrument and a cadence, consistent with the plan given."
    )
    user = json.dumps({"assessment_plan": plan_data}, ensure_ascii=False)[:4000]
    response = ctx.call_llm(
        [{"role": "system", "content": system}, {"role": "user", "content": user}], max_retries=0,
    )
    parsed = parse_json_response(response, warn=False) or {}
    methods = parsed.get("methods")
    if isinstance(methods, list):
        return [_render_method(m) for m in methods if _render_method(m)][:5]
    return []


# ── activity family ─────────────────────────────────────────────────────────

def _repair_activity_family(ctx: RepairContext, violations: list) -> list:
    remaining = []
    coverage_violations = []
    engagement_violations = []
    bloom_violations = []
    for violation in violations:
        vtype = getattr(violation, "violation_type", "")
        if vtype in ("C3", "C4", "P4"):
            coverage_violations.append(violation)
        elif vtype == "activity_engagement":
            engagement_violations.append(violation)
        elif vtype == "bloom_mismatch_activity":
            bloom_violations.append(violation)
        else:
            remaining.append(violation)
    if coverage_violations:
        repair_activity_coverage(ctx, coverage_violations)
    if engagement_violations or bloom_violations:
        repair_active_practice(ctx, engagement_violations + bloom_violations)
    return remaining


def repair_activity_coverage(ctx: RepairContext, violations: list) -> None:
    """C3: an LO has no practicing activity — add one. C4: an assessment item
    has no preparing activity — point an existing activity at it."""
    graph = ctx.graph
    activities = [dict(n["data"]) for n in graph.element_nodes(NodeType.ACTIVITY)]
    lo_map = _element_lo_map(graph)
    assessment_ids = [str(n["data"].get("item_id"))
                      for n in graph.element_nodes(NodeType.ASSESSMENT) if n["data"].get("item_id")]
    item_lo = {str(n["data"].get("item_id")): alignment.bare_ref(n["data"].get("aligned_objective"))
               for n in graph.element_nodes(NodeType.ASSESSMENT) if n["data"].get("item_id")}

    repaired_ids: list[str] = []
    touched: set[str] = set()
    for violation in violations:
        md = violation.metadata
        if violation.violation_type == "C3":
            lo_id = str(md.get("lo_id") or "")
            if not lo_id:
                continue
            new_id = f"TLA-R-{lo_id}"
            activities.append({
                "id": new_id, "activity_name": f"Guided practice for {lo_id}",
                "duration": "45m",
                "description": f"Learners practice the skill behind {lo_id} on a realistic task with instructor feedback.",
                "materials_needed": "A practice task sheet and worked example.",
                "aligned_objectives": [lo_id],
                "prepares_for_assessment": assessment_ids[:1],
                "learner_cognitive_process": str(lo_map.get(lo_id, {}).get("level", "apply")),
                "repaired": True,
            })
            repaired_ids.append(new_id)
            touched.add(new_id)
        elif violation.violation_type == "C4":
            # Two distinct C4 findings arrive here and the old branch conflated
            # them: it appended whatever node the violation named — including
            # ACTIVITY ids from establisher gaps — into the first activity's
            # item list, unchecked and without dedup, once per validation
            # round (measured: 'TLA-P-ILO-01' x5 inside prepares_for_assessment
            # shipped to the judge).
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

    for activity in activities:
        if isinstance(activity, dict) and str(activity.get("id")) in touched:
            graph.add_element_node(NodeType.ACTIVITY, str(activity["id"]), dict(activity))
    alignment.match_list_reverse(graph, "C3", field="aligned_objectives")
    alignment.match_list(graph, "C4", field="prepares_for_assessment")
    _log_repair(ctx, str(NodeType.ACTIVITY), violation_type=violations[0].violation_type, repaired_fields=["learning_activities"],
                rule="repair_alignment_coverage", input_summary="; ".join(v.message for v in violations)[:200],
                output_summary=f"Fixed/added activities for {', '.join(repaired_ids) or 'existing coverage'}.")


def repair_active_practice(ctx: RepairContext, violations: list) -> None:
    """A higher-order objective practiced only passively, or with a
    learner_cognitive_process below what the objective needs, gets a
    hands-on activity added."""
    graph = ctx.graph
    lo_map = _element_lo_map(graph)
    repaired_ids: list[str] = []
    for violation in violations:
        lo_id = str(violation.metadata.get("lo_id") or "")
        if not lo_id:
            continue
        new_id = f"TLA-P-{lo_id}"
        graph.add_element_node(NodeType.ACTIVITY, new_id, {
            "id": new_id, "activity_name": f"Hands-on practice for {lo_id}",
            "duration": "45m",
            "description": f"Learners actively practice {lo_id} on a realistic task with feedback.",
            "materials_needed": "A hands-on practice exercise or lab guide.",
            "aligned_objectives": [lo_id],
            "learner_cognitive_process": str(lo_map.get(lo_id, {}).get("level", "apply")),
            "repaired": True,
        })
        repaired_ids.append(new_id)

    alignment.match_list_reverse(graph, "C3", field="aligned_objectives")
    _log_repair(ctx, str(NodeType.ACTIVITY), violation_type="activity_engagement", repaired_fields=["learning_activities"],
                rule="repair_active_practice", input_summary="; ".join(v.message for v in violations)[:200],
                output_summary=f"Added active-practice activities for {', '.join(repaired_ids) or 'existing objectives'}.")


# ── content family ──────────────────────────────────────────────────────────

def _repair_content_family(ctx: RepairContext, violations: list) -> list:
    remaining = []
    coverage_violations = []
    orphan_violations = []
    for violation in violations:
        vtype = getattr(violation, "violation_type", "")
        if vtype in ("C5", "P5"):
            coverage_violations.append(violation)
        elif vtype == "orphan_content":
            orphan_violations.append(violation)
        elif vtype == "P6":
            # P6 (media<->material type-match on a fuzzy alias table) is
            # audit-only, same rationale as the old R9: no deterministic
            # fix wouldn't risk gaming the metric by inventing a fake
            # media entry just to pass.
            continue
        else:
            remaining.append(violation)
    if coverage_violations:
        repair_content_coverage(ctx, coverage_violations)
    if orphan_violations:
        repair_content_orphans(ctx, orphan_violations)
    return remaining


def repair_content_coverage(ctx: RepairContext, violations: list) -> None:
    """C5: an activity has no supporting content module — add one. P5: a
    material has no linked_module — point it at an existing module."""
    graph = ctx.graph
    module_nodes = graph.element_nodes(NodeType.CONTENT)
    repaired_ids: list[str] = []
    for violation in violations:
        if violation.violation_type == "C5":
            activity_id = str(violation.metadata.get("node_id") or violation.node_id or "")
            if not activity_id:
                continue
            activity_ref = activity_id.split(graph.ELEMENT_SEP, 1)[-1]
            new_module_id = f"MOD-R-{activity_ref}"
            data = {
                "id": new_module_id,
                "title": f"Support module for {activity_ref}",
                "description": f"Content supporting activity {activity_ref}.",
                "repaired": True,
            }
            full_id = graph.add_element_node(NodeType.CONTENT, new_module_id, data)
            ctx.trajectory.log_node_edit("add", full_id, NodeType.CONTENT)
            alignment.record_provenance(graph, "C5", [full_id], activity_id)
            repaired_ids.append(new_module_id)
        elif violation.violation_type == "P5" and module_nodes:
            material_id = str(violation.metadata.get("node_id") or violation.node_id or "")
            material = graph.get_node(material_id) if material_id else None
            if material is not None:
                module_ref = module_nodes[0]["id"].split(graph.ELEMENT_SEP, 1)[-1]
                material["data"]["linked_module"] = module_ref
                alignment.record_provenance(graph, "P5", [module_nodes[0]["id"]], material_id)
                repaired_ids.append(material_id)
    _log_repair(
        ctx, repaired_ids[0] if repaired_ids else "content_designer",
        violation_type=violations[0].violation_type, repaired_fields=["content_modules", "learner_materials"],
                rule="repair_coverage", input_summary="; ".join(v.message for v in violations)[:200],
                output_summary=f"Fixed/added coverage for {', '.join(repaired_ids) or 'existing links'}.")


def repair_content_orphans(ctx: RepairContext, violations: list) -> None:
    """orphan_content flags either a Content module with no outgoing C5
    (link it to an existing Activity) or a Material with no linked
    module (P5, same shape as :func:`repair_content_coverage`'s P5 branch —
    reused directly since ``violation.node_id`` there is already a material
    id). A module orphan needs its own branch: unlike the C5 case (which
    starts from an under-supported Activity and invents a new module), here
    the violation already names the orphan MODULE itself, so the fix is to
    link it to an existing Activity rather than manufacture a redundant
    one."""
    graph = ctx.graph
    module_violations = []
    rest = []
    activity_nodes = graph.element_nodes(NodeType.ACTIVITY)
    for violation in violations:
        node_id = str(violation.metadata.get("node_id") or violation.node_id or "")
        if node_id.startswith(f"{NodeType.CONTENT}{graph.ELEMENT_SEP}"):
            module_violations.append((violation, node_id))
        else:
            rest.append(violation)
    repaired_ids: list[str] = []
    if module_violations and activity_nodes:
        target_activity = activity_nodes[0]["id"]
        for _violation, module_id in module_violations:
            alignment.record_provenance(graph, "C5", [module_id], target_activity)
            repaired_ids.append(module_id)
        _log_repair(
            ctx, repaired_ids[0], violation_type="orphan_content", repaired_fields=["content_modules"],
                rule="repair_orphan_content", input_summary="; ".join(v.message for v, _ in module_violations)[:200],
                output_summary=f"Linked {', '.join(repaired_ids)} to {target_activity}.")
    if rest:
        repair_content_coverage(ctx, rest)


# ── rubric family ───────────────────────────────────────────────────────────

OBSERVABLE_DESCRIPTION = (
    "Full marks require correct application of the target concept, with justification citing "
    "at least one concrete piece of evidence, scored 0-3 against this rubric."
)


def _repair_rubric_family(ctx: RepairContext, violations: list) -> list:
    remaining = []
    coverage_violations = []
    consistency_violations = []
    evidence_violations = []
    orphan_violations = []
    for violation in violations:
        vtype = getattr(violation, "violation_type", "")
        if vtype in ("C6", "C7"):
            coverage_violations.append(violation)
        elif vtype == "rubric_consistency":
            consistency_violations.append(violation)
        elif vtype == "evidence_alignment":
            evidence_violations.append(violation)
        elif vtype == "orphan_rubric":
            orphan_violations.append(violation)
        else:
            remaining.append(violation)
    if coverage_violations:
        repair_rubric_coverage(ctx, coverage_violations)
    if consistency_violations:
        repair_rubric_consistency(ctx, consistency_violations)
    if evidence_violations:
        repair_evidence_alignment(ctx, evidence_violations)
    if orphan_violations:
        repair_orphan_rubrics(ctx, orphan_violations)
    return remaining


def repair_orphan_rubrics(ctx: RepairContext, violations: list) -> None:
    """orphan_rubric: a criterion that names no item and no objective.
    Attach it to an assessment item — preferring items that have no
    criterion yet, so the repair closes a real C6 gap instead of piling a
    second criterion onto a covered item — and inherit that item's own
    objective, exactly as a first-pass criterion would have declared."""
    graph = ctx.graph
    items = graph.element_nodes(NodeType.ASSESSMENT)
    if not items:
        return  # nothing to attach to; the island stays reported by the check
    covered = {e["source"] for e in graph.get_edges(relation_id="C6")}
    uncovered = [i for i in items if i["id"] not in covered]
    repaired: list[str] = []
    for index, violation in enumerate(violations):
        rc = graph.get_node(violation.node_id)
        if not rc:
            continue
        pool = uncovered or items
        item = pool[index % len(pool)]
        item_ref = item["id"].split(graph.ELEMENT_SEP, 1)[-1]
        data = dict(rc["data"])
        data["aligned_assessment"] = item_ref
        data["aligned_objective"] = str(item["data"].get("aligned_objective", "") or "")
        data["repaired"] = True
        rc_ref = violation.node_id.split(graph.ELEMENT_SEP, 1)[-1]
        graph.add_element_node(NodeType.RUBRIC, rc_ref, data)
        alignment.record_provenance(graph, "C6", [item["id"]], violation.node_id)
        repaired.append(rc_ref)
    alignment.match_id(graph, "C7", field="aligned_objective")
    _log_repair(ctx, repaired[0] if repaired else "rubric_designer",
                violation_type="orphan_rubric", repaired_fields=["aligned_assessment", "aligned_objective"],
                rule="repair_orphan_rubric", input_summary="; ".join(v.message for v in violations)[:200],
                output_summary=f"Attached {', '.join(repaired) or 'no'} criterion(s) to assessment items.")


def repair_rubric_coverage(ctx: RepairContext, violations: list) -> None:
    """C6: an assessment item has no evaluating criterion — add one.
    C7: a criterion has no resolvable aligned_objective — point it at
    the criterion's linked assessment item's own objective."""
    graph = ctx.graph
    assessment_by_id = {n["id"]: n for n in graph.element_nodes(NodeType.ASSESSMENT)}
    repaired_ids: list[str] = []
    for violation in violations:
        if violation.violation_type == "C6":
            item_id = str(violation.metadata.get("node_id") or violation.node_id or "")
            item = assessment_by_id.get(item_id)
            if not item:
                continue
            item_ref = item_id.split(graph.ELEMENT_SEP, 1)[-1]
            new_id = f"RC-R-{item_ref}"
            data = {
                "id": new_id, "aligned_assessment": item_ref,
                "aligned_objective": str(item["data"].get("aligned_objective", "")),
                "description": OBSERVABLE_DESCRIPTION,
                "evidence_type": str(item["data"].get("type", "short_answer")),
                "repaired": True,
            }
            full_id = graph.add_element_node(NodeType.RUBRIC, new_id, data)
            ctx.trajectory.log_node_edit("add", full_id, NodeType.RUBRIC)
            alignment.record_provenance(graph, "C6", [item_id], full_id)
            repaired_ids.append(new_id)
        elif violation.violation_type == "C7":
            rc_id = str(violation.metadata.get("node_id") or violation.node_id or "")
            rc = graph.get_node(rc_id)
            if not rc:
                continue
            assessment_ref = alignment.bare_ref(rc["data"].get("aligned_assessment", ""))
            assessment_id = f"{NodeType.ASSESSMENT}{graph.ELEMENT_SEP}{assessment_ref}" if assessment_ref else ""
            linked = assessment_by_id.get(assessment_id)
            if linked and linked["data"].get("aligned_objective"):
                rc["data"]["aligned_objective"] = str(linked["data"]["aligned_objective"])
                graph.add_element_node(NodeType.RUBRIC, rc_id.split(graph.ELEMENT_SEP, 1)[-1], dict(rc["data"]))
                repaired_ids.append(rc_id)
    alignment.match_id(graph, "C7", field="aligned_objective")
    _log_repair(ctx, repaired_ids[0] if repaired_ids else "rubric_designer",
                violation_type=violations[0].violation_type, repaired_fields=["rubric_criteria"],
                rule="repair_coverage", input_summary="; ".join(v.message for v in violations)[:200],
                output_summary=f"Fixed/added coverage for {', '.join(repaired_ids) or 'existing criteria'}.")


def repair_rubric_consistency(ctx: RepairContext, violations: list) -> None:
    """rubric_consistency: a criterion has no/vague scoring description.
    Same repair on either substrate; only where the criteria live differs."""
    if not ctx.graph_mode:
        document = ctx.store.get("rubric") or {}
        criteria = [dict(rc) if isinstance(rc, dict) else rc
                    for rc in document.get("rubric_criteria") or []]
        flagged = {str(v.metadata.get("rc_id") or v.node_id) for v in violations}
        repaired: list[str] = []
        for rc in criteria:
            if isinstance(rc, dict) and str(rc.get("id")) in flagged:
                rc["description"] = OBSERVABLE_DESCRIPTION
                rc["repaired"] = True
                repaired.append(str(rc.get("id")))
        if repaired:
            ctx.store.put("rubric", {**document, "rubric_criteria": criteria})
        _log_repair(ctx, repaired[0] if repaired else "rubric_designer",
                    violation_type="rubric_consistency", repaired_fields=["description"],
                rule="repair_consistency", input_summary="; ".join(v.message for v in violations)[:200],
                output_summary=f"Rewrote description for {', '.join(repaired) or 'flagged criteria'}.")
        return
    graph = ctx.graph
    repaired_ids: list[str] = []
    for violation in violations:
        rc = graph.get_node(violation.node_id)
        if not rc:
            continue
        rc["data"]["description"] = OBSERVABLE_DESCRIPTION
        rc["data"]["repaired"] = True
        graph.add_element_node(NodeType.RUBRIC, violation.node_id.split(graph.ELEMENT_SEP, 1)[-1], dict(rc["data"]))
        repaired_ids.append(violation.node_id)
    _log_repair(ctx, repaired_ids[0] if repaired_ids else "rubric_designer",
                violation_type="rubric_consistency", repaired_fields=["description"],
                rule="repair_consistency", input_summary="; ".join(v.message for v in violations)[:200],
                output_summary=f"Rewrote description for {', '.join(repaired_ids) or 'flagged criteria'}.")


def repair_evidence_alignment(ctx: RepairContext, violations: list) -> None:
    """evidence_alignment: a criterion expects evidence its linked item
    can't produce — loosen the criterion's own evidence_type down to
    what the item can actually give (deterministic, converges without
    needing to change the already-committed assessment item)."""
    graph = ctx.graph
    repaired_ids: list[str] = []
    for violation in violations:
        rc = graph.get_node(violation.node_id)
        if not rc:
            continue
        evaluated_edges = graph.get_edges(relation_id="C6", target=violation.node_id)
        item_types = [
            str((graph.get_node(e["source"]) or {"data": {}})["data"].get("type", ""))
            for e in evaluated_edges
        ]
        if item_types:
            rc["data"]["evidence_type"] = item_types[0]
            rc["data"]["repaired"] = True
            graph.add_element_node(NodeType.RUBRIC, violation.node_id.split(graph.ELEMENT_SEP, 1)[-1], dict(rc["data"]))
            repaired_ids.append(violation.node_id)
    _log_repair(ctx, repaired_ids[0] if repaired_ids else "rubric_designer",
                violation_type="evidence_alignment", repaired_fields=["evidence_type"],
                rule="repair_evidence_alignment", input_summary="; ".join(v.message for v in violations)[:200],
                output_summary=f"Loosened evidence_type for {', '.join(repaired_ids) or 'flagged criteria'}.")


# ── implementation family ───────────────────────────────────────────────────

def _repair_implementation_family(ctx: RepairContext, violations: list) -> list:
    remaining = []
    owned = []
    for violation in violations:
        is_owner = (
            getattr(violation, "violation_type", "") == "feasibility"
            or getattr(violation, "edge_type", "") == "constrains"
        )
        if is_owner:
            owned.append(violation)
        else:
            remaining.append(violation)

    if not owned:
        return remaining

    if not ctx.graph_mode:
        # Same deterministic monitoring-note repair, on the blackboard.
        data = dict(ctx.store.get("implementation_plan") or {})
        monitoring = data.setdefault("monitoring", {})
        if isinstance(monitoring, dict):
            adjustments = monitoring.setdefault("real_time_adjustments", [])
            if isinstance(adjustments, list):
                adjustments.append("Re-scope delivery constraints after verifier feasibility warning.")
        data["repaired"] = True
        ctx.store.put("implementation_plan", data)
        _log_repair(
            ctx, "implementation_plan",
            violation_type=(owned[0].violation_type if owned else "actionability"),
            repaired_fields=["monitoring", "delivery_constraints"],
        )
        ctx.trajectory.log_step(
            ctx.actor,
            "repair_feasibility",
            "; ".join(v.message for v in owned),
            "Updated implementation monitoring and contingency adjustment notes.",
        )
        return remaining

    graph = ctx.graph
    node = graph.get_node(graph.section_id(NodeType.IMPLEMENTATION_PLAN))
    if not node:
        graph.add_node(NodeType.IMPLEMENTATION_PLAN, graph.section_id(NodeType.IMPLEMENTATION_PLAN), {
            "instructor_orientation": {},
            "system_check": {},
            "prototype_execution": {},
            "monitoring": {},
            "instructor_guide": {},
            "operator_manual": {},
            "repaired": True,
        })
        ctx.trajectory.log_node_edit("add", graph.section_id(NodeType.IMPLEMENTATION_PLAN), NodeType.IMPLEMENTATION_PLAN)
    constraint = graph.get_node(graph.section_id(NodeType.IMPLEMENTATION_PLAN))
    data = constraint["data"] if constraint else {}
    monitoring = data.setdefault("monitoring", {})
    if isinstance(monitoring, dict):
        adjustments = monitoring.setdefault("real_time_adjustments", [])
        if isinstance(adjustments, list):
            adjustments.append("Re-scope delivery constraints after verifier feasibility warning.")
    impl_id = graph.section_id(NodeType.IMPLEMENTATION_PLAN)
    graph.update_node(impl_id, {"monitoring": monitoring, "repaired": True})
    _log_repair(
        ctx, impl_id,
        violation_type=(owned[0].violation_type if owned else "feasibility"),
        repaired_fields=["monitoring", "delivery_constraints"],
    )
    ctx.trajectory.log_step(
        ctx.actor,
        "repair_feasibility",
        "; ".join(v.message for v in owned),
        "Updated implementation monitoring and contingency adjustment notes.",
    )
    return remaining


_FAMILY_REPAIRERS: dict[str, Callable[[RepairContext, list], list]] = {
    "outcome_designer": _repair_outcome_family,
    "assessment_designer": _repair_assessment_family,
    "activity_designer": _repair_activity_family,
    "content_designer": _repair_content_family,
    "rubric_designer": _repair_rubric_family,
    "implementation_planner": _repair_implementation_family,
}
