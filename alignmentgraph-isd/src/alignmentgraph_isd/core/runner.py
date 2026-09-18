"""The package's entry point, and the executor behind it.

``MetaAgent.run`` is what every caller uses — the benchmark adapter,
``cli.py`` and the demo server — and it IS the run: six tool-loop stages, or
the single arm's one loop, over the helpers below. It lives here rather than
in ``core/agentic/`` because it orchestrates a dozen private helpers that
would each have to become public API for one caller if they were split
across the two modules. ``core/agentic/`` is therefore the executor's PARTS
(the loops, the tools, the stage table, the fan-out); this is the whole.

What a run reports about itself — provenance, tokens, dump, live emit — lives
in ``core/run_report.py``, a leaf, which is what lets these imports be
module-level.

It honours both ablation axes:

``agent_mode`` — the CONTEXT BOUNDARY, and nothing else. Stage order, stage
instructions, rules, schemas, tools, budgets and guards are identical either
way. ``"multi"`` starts each stage in a fresh context under that stage's
specialist identity; ``"single"`` carries ONE context across all six stages
under one identity. The hypothesis the axis tests is that instruction-following
decays with context length, so the single arm should degrade on later stages
while the multi arm does not — which is why ``metadata.autonomy`` reports
context length per stage as a first-class quantity, not a diagnostic.

``context_mode`` — the alignment machinery, as a bundle. ``"graph"`` writes and
reads the AlignmentGraph (relation reads, the coverage docket, cross-artifact
checks, the residual audit, the graph dump); ``"prose"`` writes and reads a
graph-free blackboard (``core/prose_store.py``) with the six within-artifact
checks only, and ships no graph artifact.

Stage ORDER stays deterministic and instructed in both arms (see
``loop.WORKFLOW_OVERVIEW``): the agents are autonomous in how they execute a
stage, never in what order the stages run.

Cross-artifact violations are reconciled ONCE after the last stage, bounded by
``SELF_VALIDATION_BUDGET`` rounds — see :func:`_reconcile`. What
:func:`_result_payload` assembles IS the result contract: ``MetaAgent.run``
returns it unchanged, and the benchmark adapter reads it.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

from . import dev_plans, repairs
from .aggregate import ADDIEOutputAggregator, aggregate_prose
from .alignment_graph import AlignmentGraph, NodeType
from .alignment_graph.audit import GraphAuditor
from ..config import HarnessRunConfig
from .brief import DesignBrief
from .checks import serialize_violations
from .memory import Memory, Plan
from .outputs import (
    _collect_violations,
    _collect_violations_prose,
    empty_addie,
)
from .prose_store import ProseStore
from .run_report import (
    _graph_attaching,
    _ledger_attaching,
    _llm_metadata,
    _maybe_dump_graph,
    _safe_emit,
    _token_usage_metadata,
)
from .trajectory import ORCHESTRATOR, TrajectoryLogger
from .validation import validate_addie
from .agentic import budget, fanout, react, replan
from .agentic.client import AgenticLLM
from .agentic.loop import ToolLoop
from .agentic.protocol import PROTOCOL_REV, empty_stage_stats
from .agentic.transcript import history_budget
from .agentic.specialists import SINGLE_IDENTITY, STEPS, step_done


@contextmanager
def _phase(trajectory: TrajectoryLogger, phase: str, index: int, total: int):
    """Phase boundaries for live consumers (the demo app's SSE stream)."""
    trajectory.emit("phase_started", {"phase": phase, "index": index, "total": total})
    started = time.time()
    with trajectory.acting_as("", phase=phase):
        trajectory.log_action("phase_started", agent=ORCHESTRATOR,
                              phase=phase, index=index, total=total)
        try:
            yield
        finally:
            duration_ms = (time.time() - started) * 1000
            trajectory.log_action(
                "phase_finished", agent=ORCHESTRATOR,
                phase=phase, index=index, total=total, duration_ms=duration_ms)
            trajectory.emit("phase_finished", {
                "phase": phase, "index": index, "total": total, "duration_ms": duration_ms})


def _merge_stats(carried: dict, fresh: dict) -> dict:
    """Accumulate one stage's loop stats across its regen attempts.

    Counters add; ``context_len`` takes the max (the peak the stage reached is
    what the context hypothesis is about, not the sum of retried prompts); the
    fallback flag is sticky."""
    if not carried:
        return dict(fresh)
    merged = dict(carried)
    for key, value in fresh.items():
        if key == "context_len":
            merged[key] = max(merged.get(key, 0), value)
        elif isinstance(value, bool):
            merged[key] = merged.get(key, False) or value
        else:
            merged[key] = merged.get(key, 0) + value
    return merged


def _verify_family(family: str, *, state, design_brief, graph_mode: bool, memory,
                   trajectory, ctx, identity: str, phase: str,
                   route: bool = False, final_look: bool = False) -> list:
    """One family's deterministic check -> repair -> credit loop, bounded by
    ``SELF_VALIDATION_BUDGET`` rounds. Returns the violations still standing.

    The ONE implementation behind the multi arm's per-stage net, the single
    arm's end-of-run net and the reconciliation pass, so the three cannot
    drift. Every round is recorded even when empty ("looked and found
    nothing" and "never looked" are different facts); a round that repaired
    nothing stops early (the checks are pure functions of state and nothing
    else writes state in between, so the next look would be identical);
    repair credit is a before/after key diff in the ledger. Everything here
    is the ORCHESTRATOR's act: the check runs outside every agent's tool loop
    and no model is called — what needed writing was already offered to the
    agent inside its loop.

    ``route`` stamps ``target_designer`` and logs the routing decision (the
    reconciliation pass). ``final_look`` re-checks once more when the budget
    ran out with a repair on the last pass, so a caller that USES the return
    value never gets a pre-repair snapshot.
    """
    owned_types = repairs.OWNED_BY_FAMILY.get(family, frozenset())

    def collect() -> tuple[list, list]:
        """What this family owns, and what it merely ran into.

        BOTH halves are returned. Filtering to the owned half and throwing the
        rest away makes the deterministic net the only thing a violation can
        reach: a type no family owns is computed on every round and then
        dropped, never becomes a Finding, and the ledger cannot say it
        existed.

        MEASURED (run 7ef3ed16): the run's own ``graph.json`` flagged 27 nodes
        — 3 ``measurability`` (ILO-02/03/06, "Students will know ...") and 24
        ``P8`` — while ``violations.json`` listed none of them, and the
        outcomes check round recorded ``violation_count: 0`` on a stage whose
        objectives were failing a check the same round had just run. The graph
        and the Violations tab were describing two different runs.

        Only the OWNED half drives repair, routing and convergence — that part
        is unchanged, and is what ``_verify_family`` returns. The other half is
        recorded and nothing more; ``Memory.observe_violations`` already stamps
        it ``open_reason: "unowned"``, and ``_REASON_PRECEDENCE`` already ranks
        that above ``converged`` so a later round cannot relabel it.
        """
        violations = (_collect_violations(family, state, design_brief) if graph_mode
                      else _collect_violations_prose(family, state))
        owned = [v for v in violations if v.violation_type in owned_types]
        unowned = [v for v in violations if v.violation_type not in owned_types]
        if route:
            for v in owned:
                v.target_designer = repairs.OWNER_BY_VIOLATION[v.violation_type]
        return owned, unowned

    def observe(found: list, unowned: list) -> tuple[int, set]:
        """One round, both halves — and only the owned keys handed back.

        ``credit_repair`` closes whatever is in the returned set and missing
        from the next ``collect()``; an unowned key is missing from it by
        construction, so returning one would credit the harness with a repair
        it is not even allowed to attempt.
        """
        round_no = trajectory.log_violations_result(
            serialize_violations(found + unowned, identity), agent=ORCHESTRATOR)
        keys = memory.observe_violations(found, round=round_no, phase=phase, family=family)
        memory.observe_violations(unowned, round=round_no, phase=phase, family=family)
        return round_no, keys

    found: list = []
    with trajectory.acting_as(ORCHESTRATOR):
        for _ in range(budget.SELF_VALIDATION_BUDGET):
            found, unowned = collect()
            round_no, keys = observe(found, unowned)
            if not found:
                break
            if route:
                trajectory.log_reconcile_result(family, found, agent=ORCHESTRATOR)
            before = len(trajectory.repair_events)
            repairs.repair(family, found, ctx)
            if len(trajectory.repair_events) == before:
                memory.mark_open_reason(keys, reason="converged", round=round_no)
                trajectory.log_convergence(
                    family, sorted(keys), [v.violation_type for v in found],
                    round_number=round_no, agent=ORCHESTRATOR)
                break
            memory.credit_repair(keys - {v.key for v in collect()[0]},
                                 by=identity, round=round_no, harness=True)
        else:
            if final_look:
                found, unowned = collect()
                observe(found, unowned)
                memory.mark_open_reason({v.key for v in found}, reason="budget")
    return found


def _reconcile(state, trajectory, design_brief, *, graph_mode: bool,
               memory=None) -> list[dict]:
    """Bounded reconciliation pass, once, after the last stage.

    The hole it closes: every stage runs the full check set but repairs only
    what its OWN family owns, and only while that stage is running. Anything
    still outstanding when the stage ends was dropped on the floor and
    reappeared only as a warning in the residual audit. Two things land here:
    a violation whose in-stage repair did not resolve it within
    ``SELF_VALIDATION_BUDGET``, and one that a LATER stage's own repair
    introduced upstream. That is the limitation the fixed-order design admitted
    (see the discussion of generation order in the paper); this pass answers it
    without giving up the bound that makes the order safe.

    Deterministic and model-free: every routine in ``repairs`` is structural,
    so this pass rearranges what the design holds and writes no content. A
    violation needing WRITING was already handed to its agent as a repair turn
    inside that agent's own loop, which is where the ``agent_mode`` axis lives;
    opening a second conversation out here to write it would put a context
    boundary of its own on that axis.

    Bounded, and after the last stage rather than re-entering mid-pipeline: a
    route -> repair -> recheck -> route cycle is not bounded by the stage
    order, and an unbounded one on a small model is a hang, not a fix.

    Prose runs it too and finds nothing by construction — the within-artifact
    checks it has are all owned by the family that just ran. That absence is
    the ``context_mode`` treatment, so the pass must still be entered (equal
    effort), not skipped.
    """
    memory = memory if memory is not None else Memory.of(state)
    ctx = repairs.RepairContext(
        graph=state if graph_mode else None,
        store=None if graph_mode else state,
        trajectory=trajectory, actor=ORCHESTRATOR)
    residual: list[dict] = []
    # PER FAMILY, not one loop over all six: a family clean in round 1 must
    # not be re-collected because another still has work (measured: 12
    # reconcile rounds for 6 families that each needed one).
    for family in repairs.OWNED_BY_FAMILY:
        identity = _IDENTITY_BY_FAMILY[family]
        found = _verify_family(
            family, state=state, design_brief=design_brief, graph_mode=graph_mode,
            memory=memory, trajectory=trajectory, ctx=ctx, identity=identity,
            phase="reconcile", route=True, final_look=True)
        residual += serialize_violations(found, identity)
    return residual


#: Which specialist answers for a family in the reconciliation pass. Includes
#: the `also_repairs` families — a family can own checks without owning a stage
#: (rubrics: its criteria are written by the assessment Developer as a field of
#: the item, but `repairs.OWNED_BY_FAMILY` still assigns it rubric_consistency
#: and evidence_alignment).
_IDENTITY_BY_FAMILY: dict[str, str] = {
    family: step.identity
    for step in STEPS
    for family in (step.family, *step.also_repairs)
}


def _run_fanout(config, memory, trajectory, design_brief, step, spec, *,
                regen_budget: int, backoff: float,
                work_sets: list | None = None, round_index: int = 0,
                answers: tuple[str, ...] = ()) -> dict:
    """Produce one family's items, one work set at a time.

    THE AXIS, at its second scale. Both arms plan the same work sets from the
    same ``dev_plans`` normalization and make the same number of calls; the
    difference is who runs each set:

      ``multi``  — a fresh ToolLoop per set under that family's DEVELOPER
                   identity and persona. This arm spawns sub-agents.
      ``single`` — no sub-agent: the one agent writes each set itself, inside
                   the conversation it is already carrying, and pays the
                   context for it.

    A set already in state is skipped, so a call that is handed sets the
    state holds (a replan round) does no work twice.
    """
    # Planning and committing read and write the design state, and every such
    # event is stamped with whoever is currently acting — outside a scope they
    # land with an EMPTY agent. They belong to the orchestrator: neither is any
    # one Developer's work.
    orchestrator = ORCHESTRATOR
    state = memory.state
    with trajectory.acting_as(orchestrator):
        if work_sets is None:
            parsed = _dispatch_payload(state, spec)
            work_sets, stats_dev = spec.plan_sets(state, parsed)
        else:
            # A REPLAN round: the sets were derived from the gaps, not from
            # re-normalizing the family (see agentic/replan.py).
            stats_dev = {"set_count": len(work_sets),
                         "pair_count": sum(len(ws.pairs) or 1 for ws in work_sets),
                         "dropped_lo_refs": 0, "dropped_pairs": 0,
                         "appended_sets": 0, "fallback_used": False}
        if not work_sets:
            return {}
        # KEPT, not only logged. The trajectory event carries a summary for the
        # judge; memory keeps the sets themselves, so "which Developer was
        # asked for what" is answerable after the run — the question a fan-out
        # failure always turns into, and the one the round-2 plan is scoped
        # against.
        memory.remember_plan(Plan(
            stage=step.name, family=step.family,
            source="fallback" if stats_dev["fallback_used"] else "llm",
            work_sets=tuple(work_sets), stats=dict(stats_dev),
            round=round_index, answers=answers))
        trajectory.log_dev_plan(
            step.family,
            set_count=stats_dev["set_count"], pair_count=stats_dev["pair_count"],
            sets=[{"set_id": ws.set_id, "objectives": list(ws.objectives)}
                  for ws in work_sets],
            source=("fallback" if stats_dev["fallback_used"]
                    else stats_dev.get("source", "llm")),
            fallback_used=stats_dev["fallback_used"],
            dropped_refs=stats_dev["dropped_lo_refs"],
            dropped_pairs=stats_dev.get("dropped_pairs", 0),
            duplicate_pairs=stats_dev.get("duplicate_pairs", 0),
            appended_sets=stats_dev["appended_sets"],
            oversized_splits=stats_dev.get("oversized_splits", 0),
            agent=orchestrator)
        committed = fanout.committed_set_ids(spec, state)
        pending = [ws for ws in work_sets if ws.set_id not in committed]
        if not pending:
            return {}

    # Per-set counters kept SEPARATE from the stage's own. Folded together,
    # a stage's ``via_fallback`` means "the dispatch OR any one of ten sets
    # gave up", which cannot be read: the Developer tier is the axis at its
    # second scale, so its outcomes have to be countable on their own.
    stats: dict = {"n_sets": len(pending)}
    phase = trajectory._phase

    def run_one(work_set) -> tuple[dict, dict]:
        return _run_one_set(config, memory, trajectory, design_brief, step, spec,
                            work_set, phase=phase, regen_budget=regen_budget,
                            backoff=backoff)

    def commit(work_set, captured: dict, set_stats: dict) -> None:
        for key, value in set_stats.items():
            if key == "context_len":
                stats[key] = max(stats.get(key, 0), value)
            else:
                stats[key] = stats.get(key, 0) + value
        # COMMIT THIS SET NOW, not once the whole family has run: with the
        # work in the graph, the checks can see it while the family's DESIGNER
        # still has its loop open, so a gap can go back to the agent whose job
        # is to plan around it. Ids stay collision-free because the remapper
        # reads the ids the state already holds (`_ids_already_held`).
        payload = {"set_id": work_set.set_id, **(captured.get("section") or {})}
        with trajectory.acting_as(orchestrator):
            fanout.commit_sets(spec, state, trajectory, [work_set], [payload])

    workers = _fanout_workers(config, len(pending))
    if workers <= 1:
        for work_set in pending:
            commit(work_set, *run_one(work_set))
        return stats
    # The Developers run at once; the COMMITS run in plan order, one at a
    # time, on this thread. Ids are order-independent already (the ordinal is
    # fixed when the plan is numbered), but the graph's INSERTION order is
    # not: it is the order every later `read_nodes` listing and the
    # aggregate's lists come out in, so committing as each worker finished
    # would make the deliverable depend on the worker count. Nothing waits
    # on any one set — the checks and the replan run after this returns.
    executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="agisd-fanout")
    try:
        futures = [executor.submit(run_one, work_set) for work_set in pending]
        for work_set, future in zip(pending, futures):
            commit(work_set, *future.result())
    finally:
        # Never `with`: on the error path that would wait for a worker in the
        # middle of a model call.
        executor.shutdown(wait=False, cancel_futures=True)
    return stats


def _fanout_workers(config, pending: int) -> int:
    """How many of ``pending`` sets to run at once: the configured count,
    capped by the sets there are and by the call gate where one is set."""
    workers = max(1, int(getattr(config, "fanout_workers", 1) or 1))
    cap = int(getattr(config, "llm_max_concurrency", 0) or 0)
    if cap > 0:
        workers = min(workers, cap)
    return max(1, min(workers, pending))


def _run_one_set(config, memory, trajectory, design_brief, step, spec, work_set, *,
                 phase: str, regen_budget: int, backoff: float) -> tuple[dict, dict]:
    """One Developer's work on one set: the loop, its regen attempts, and the
    counters — WITHOUT the commit, which is the driver's and is ordered.

    Runs on the calling thread or on a fan-out worker; either way it opens
    the Developer's own attribution scope, with the stage's phase carried in
    explicitly because a worker thread has no scope of its own to inherit
    one from."""
    identity = spec.developer_identity
    llm = AgenticLLM(config, trajectory, identity)
    captured: dict = {}
    set_stats: dict = {}
    with trajectory.acting_as(identity, phase=phase):
        # Inside the scope: building the assignment now READS the state
        # (the objectives the set names), and a read outside a scope lands
        # with an empty agent.
        set_step = fanout.set_step(spec, work_set, step, memory.state)
        for attempt in range(regen_budget + 1):
            if attempt > 0 and backoff:
                time.sleep(backoff * attempt)
            loop = ToolLoop(
                config, memory, trajectory, design_brief, set_step, llm,
                identity=identity, capture=captured,
                max_turns=budget.DEVELOPER_MAX_TURNS, attempt=attempt + 1)
            try:
                loop.run()
            except Exception as exc:  # noqa: BLE001 - one bad set must not lose the family
                trajectory.log_recovery_event(
                    identity, "agent_error", "", str(exc)[:400])
            finally:
                for key, value in (("set_turns", loop.stats["turns_used"]),
                                   ("set_submits_rejected",
                                    loop.stats["submits_rejected"]),
                                   ("sets_gave_up",
                                    int(loop.stats["gave_up"])),
                                   ("history_dropped",
                                    loop.stats["history_dropped"]),
                                   # Developer compactions count toward the
                                   # stage, or `compaction_summaries` would
                                   # be booked against a population that
                                   # does not contain them.
                                   ("compactions",
                                    loop.stats["compactions"]),
                                   ("compaction_summaries",
                                    loop.stats["compaction_summaries"]),
                                   ("args_reshaped",
                                    loop.stats["args_reshaped"]),
                                   ("assignment_reads",
                                    loop.stats["assignment_reads"])):
                    set_stats[key] = set_stats.get(key, 0) + value
                set_stats["context_len"] = max(set_stats.get("context_len", 0),
                                               loop.stats["context_len"])
            if captured.get("section"):
                break
            trajectory.log_recovery_event(
                identity, "regen_empty_section", f"attempt {attempt + 1}", set_step.name)
    return captured, set_stats


def _replan_rounds(config, memory, trajectory, design_brief, step, spec, loop, *,
                   llm, identity: str, graph_mode: bool,
                   regen_budget: int, backoff: float) -> dict:
    """Gaps -> the Designer -> a plan -> its Developers. Bounded, once.

    Runs INSIDE the Designer's own transcript: the replan loop is built over
    ``loop.messages``, so the gap list, the plan and the work that followed are
    consecutive turns of one conversation under one system prompt. The stage's
    first loop has already returned by now, which is exactly why its Developers
    could run — and why the message list is sitting here to be continued.
    """
    stats: dict = {}
    if step.name not in replan.REPLANNABLE or loop is None:
        return stats
    state = memory.state
    for round_index in range(1, budget.REPLAN_ROUNDS + 1):
        # The CHECK is the orchestrator's: it runs outside every agent's loop.
        with trajectory.acting_as(ORCHESTRATOR):
            violations = (_collect_violations(step.family, state, design_brief)
                          if graph_mode else _collect_violations_prose(step.family, state))
            gaps = replan.gaps_for(step.name, violations)
            if not gaps:
                return stats
            trajectory.log_reconcile_result(
                step.family, gaps, agent=ORCHESTRATOR)

        with trajectory.acting_as(identity):
            replan_loop = ToolLoop(
                config, memory, trajectory, design_brief,
                replan.step_for(step, step.name, gaps, round_index), llm,
                messages=loop.messages, identity=identity,
                # The Designer's OWN conversation, continued: everything that
                # describes the conversation rather than the task comes with the
                # message list. Its id and label, or the tab shows this agent
                # twice with the second row containing the first — the
                # split-block problem the in-loop repair exists to remove. Its
                # compaction record, or the part already trimmed away is lost.
                # And its ATTEMPT, which counts REGENS: a stage that came back
                # empty is run again from a fresh context, and a replan is not
                # that. Numbered from the round it would have read "retry #2"
                # on a conversation nothing had retried.
                agent_run_id=loop.agent_run_id, label=loop.label,
                compacted=loop.compacted, attempt=loop.attempt,
                specs=loop._specs,
                # Its OWN ceiling, not the stage's. The job here is one
                # artifact against gaps already listed in the request, so a
                # stage-sized budget is a round that can spend two dozen turns
                # re-reading a family it has just been handed the gaps for.
                # Turns are counted per loop, so this starts at zero even
                # though the message list is the stage's.
                max_turns=budget.REPLAN_TURNS)
            try:
                replan_loop.run()
            except Exception as exc:  # noqa: BLE001 - one failed replan must not lose the stage
                trajectory.log_recovery_event(identity, "agent_error", "", str(exc)[:400])
                return stats
            finally:
                stats = _merge_stats(stats, replan_loop.stats)

        # Deriving the round's sets reads the plan the Designer just committed
        # — the orchestrator's read, like the check above: an event outside an
        # `acting_as` scope lands with an empty agent.
        with trajectory.acting_as(ORCHESTRATOR):
            work_sets = _replan_sets(state, spec, step, gaps, round_index)
        if not work_sets:
            # The Designer had nothing to add, or named work the gaps do not
            # cover. Either way the gap stands and is counted as residual —
            # asking again is how a stage becomes a hang.
            return stats
        stats = _merge_stats(stats, _run_fanout(
            config, memory, trajectory, design_brief, step, spec,
            regen_budget=regen_budget, backoff=backoff, work_sets=work_sets,
            round_index=round_index,
            answers=tuple(sorted({v.violation_type for v in gaps}))))
    return stats


def _replan_sets(state, spec, step, gaps: list, round_index: int) -> list:
    """The work sets a replan round runs: the Designer's new plan, normalized
    against the GAPS as ground truth and tagged with the round.

    Both halves are load-bearing. Normalizing against the family would
    re-derive every set it already has; leaving the ids untagged would make
    every new set look like one ``committed_set_ids`` has already seen."""
    parsed = _dispatch_payload(state, spec)
    plan = parsed.get("dev_plan")
    if not isinstance(plan, dict) or not plan:
        return []
    if step.name == "assessment":
        promised = _section_data(state, "assessment_plan").get("lo_coverage_targets") or {}
        targets = replan.gap_targets(gaps, promised)
        if not targets:
            return []
        work_sets, _stats = dev_plans.normalize_assessment_dev_plan(
            plan, list(targets), targets)
    elif step.name == "implementation":
        activities, materials = replan.unscheduled_of(gaps)
        if not (activities or materials):
            return []
        work_sets, _stats = dev_plans.normalize_implementation_dev_plan(
            plan, activities, materials, first_session=replan.next_session(state))
    else:
        objectives = replan.objectives_of(gaps)
        if not objectives:
            return []
        work_sets, _stats = dev_plans.normalize_activity_dev_plan(
            plan, list(objectives), fanout.items_by_lo(state))
    return replan.tag_round(work_sets, round_index)


def _dispatch_payload(state, spec) -> dict:
    """What the dispatch hop left behind, in the shape ``plan_sets`` expects.

    Read back from committed state rather than passed through from the loop:
    the dispatch may have been regenerated or salvaged, so the sets must be
    derived from what actually landed either way."""
    if spec.stage == "assessment":
        plan = _section_data(state, "assessment_plan")
        return {"assessment_plan": plan, "dev_plan": plan.get("dev_plan")}
    if spec.stage == "activities":
        return {"dev_plan": _section_data(state, "activity_plan").get("dev_plan")}
    if spec.stage == "content":
        content = _section_data(state, "content")
        return {"content_modules": content.get("content_modules") or [],
                "media_selections": content.get("media_selections") or []}
    if spec.stage == "implementation":
        return {"dev_plan": _section_data(state, "implementation_plan").get("dev_plan")}
    return {}


def _section_data(state, key: str) -> dict:
    if not hasattr(state, "element_nodes"):
        return state.get(key) or {}
    sections = {"assessment_plan": NodeType.ASSESSMENT_PLAN,
                "activity_plan": NodeType.ACTIVITY_PLAN,
                "implementation_plan": NodeType.IMPLEMENTATION_PLAN}
    if key in sections:
        node = state.get_node(state.section_id(sections[key]))
        return (node or {}).get("data") or {}
    modules = [n["data"] for n in state.element_nodes(NodeType.CONTENT)]
    media = [n["data"] for n in state.element_nodes(NodeType.MEDIA_SELECTION)]
    return {"content_modules": modules, "media_selections": media}


def _repair_all(memory, trajectory, design_brief, *, graph_mode: bool,
                identity: str) -> None:
    """The single arm's deterministic repair net, over every family at once.

    The multi arm runs the same net per stage, right after that stage's
    Developer. The single arm has no stage boundaries to hang it on, so it
    runs once at the end — same checks, same rounds, same toolbox. What
    differs is only WHEN, which is a consequence of the axis, not a second
    treatment: an agent that decides its own order has no per-stage moment."""
    ctx = repairs.RepairContext(graph=memory.graph, store=memory.store,
                                trajectory=trajectory, actor=ORCHESTRATOR)
    for family in repairs.OWNED_BY_FAMILY:
        _verify_family(family, state=memory.state, design_brief=design_brief,
                       graph_mode=graph_mode, memory=memory, trajectory=trajectory,
                       ctx=ctx, identity=identity, phase="design")


def _run_single(config, memory, trajectory, design_brief, *,
                graph_mode: bool, phase_total: int) -> tuple[dict, list, dict]:
    """The single arm: ONE agent carries ONE context across all six stages and
    walks them itself (``react.ReactLoop``). Contrast the multi arm below,
    where the harness walks the stages and each starts in a fresh context.

    One phase, because there is one loop — the stage boundaries are the
    agent's, not the harness's, so there is nothing here to bracket per stage.
    """
    with _phase(trajectory, "design", 1, phase_total):
        # The loop is kept past its own scope so ``_repair_all`` runs in the
        # context it built — that is the axis expressed at repair time.
        loop = react.ReactLoop(config, memory, trajectory, design_brief)
        try:
            # Every read and write this loop makes is the one agent's, and an
            # event outside a scope lands with an EMPTY agent.
            with trajectory.acting_as(SINGLE_IDENTITY):
                loop.run()
        except Exception as exc:  # noqa: BLE001 - same containment as the multi arm
            errors = [f"{SINGLE_IDENTITY}: {exc}"]
            trajectory.log_recovery_event(
                SINGLE_IDENTITY, "agent_error", "", str(exc)[:400])
        else:
            errors = []
        # Outside the ReAct loop, so the orchestrator's — same rule as the
        # multi arm's per-stage net.
        _repair_all(memory, trajectory, design_brief,
                    graph_mode=graph_mode, identity=SINGLE_IDENTITY)
    return {"design": loop.stats}, errors, {"design": 1}


def _run_multi(config, memory, graph, store, trajectory, design_brief, *,
               graph_mode: bool, regen_budget: int, backoff: float,
               phase_total: int) -> tuple[dict, list, dict]:
    """The multi arm: the harness walks the stages, each in a fresh context
    under that stage's specialist, and hands list-valued families to their
    Developers (fanout.py). Contrast the single arm (``react.ReactLoop``),
    where the agent walks them itself."""
    errors: list[str] = []
    task_attempts: dict[str, int] = {}
    autonomy: dict[str, dict] = {}
    state = memory.state

    for index, step in enumerate(STEPS, start=1):
        identity = step.identity
        with _phase(trajectory, step.name, index, phase_total):
            llm = AgenticLLM(config, trajectory, identity)
            spec = fanout.SPECS.get(step.name)
            stats: dict = empty_stage_stats()
            with trajectory.acting_as(identity):
                # ── generation: the tool loop, with the shared regen posture ──
                for attempt in range(regen_budget + 1):
                    if attempt > 0 and backoff:
                        time.sleep(backoff * attempt)
                    loop = ToolLoop(
                        config, memory, trajectory, design_brief, step, llm,
                        attempt=attempt + 1, repair_turns=ToolLoop.REPAIR_TURNS,
                        identity=identity)
                    try:
                        loop.run()
                    except Exception as exc:  # noqa: BLE001 - contain a failing stage
                        errors.append(f"{identity}: {exc}")
                        trajectory.log_recovery_event(
                            identity, "agent_error", "", str(exc)[:400])
                        continue
                    finally:
                        stats = _merge_stats(stats, loop.stats)
                    if (spec.dispatch_done(state) if spec is not None
                            else step_done(step, state)):
                        break
                    trajectory.log_recovery_event(
                        identity, "regen_empty_section", f"attempt {attempt + 1}", step.name)

            # ── Developer tier: a list-valued family is produced one work set
            # at a time (see fanout.py). Outside the `acting_as(identity)`
            # scope above because in the multi arm each set runs under its own
            # DEVELOPER identity, which is the axis at its second scale.
            if spec is not None:
                set_stats = _run_fanout(
                    config, memory, trajectory, design_brief, step, spec,
                    regen_budget=regen_budget, backoff=backoff)
                stats = _merge_stats(stats, set_stats)
                # ── the gaps go back to the DESIGNER, which answers with a
                # plan (agentic/replan.py). Its Developers wrote into the graph
                # as they finished, so the checks can see the family while the
                # Designer's own loop is still there to be continued.
                stats = _merge_stats(stats, _replan_rounds(
                    config, memory, trajectory, design_brief, step, spec, loop,
                    llm=llm, identity=identity, graph_mode=graph_mode,
                    regen_budget=regen_budget, backoff=backoff))

            # The ORCHESTRATOR's, not the specialist's: this runs after the
            # tool loop has returned, and the agent neither chose it nor saw
            # it. `also_repairs` families run here too — their artifacts were
            # produced by THIS step's Developer, so this is where their checks
            # first have something to look at; a family that owns no checks
            # (needs_analyst) is skipped rather than logged as "looked, found
            # nothing" about a search that never happened. No residual is
            # kept from here: `_reconcile` re-derives it over every family
            # after the last stage.
            ctx = repairs.RepairContext(graph=graph, store=store, trajectory=trajectory,
                                        actor=ORCHESTRATOR)
            for family in (step.family, *step.also_repairs):
                if family not in repairs.OWNED_BY_FAMILY:
                    continue
                _verify_family(family, state=state, design_brief=design_brief,
                               graph_mode=graph_mode, memory=memory,
                               trajectory=trajectory, ctx=ctx, identity=identity,
                               phase=step.name)
            autonomy[step.name] = stats
            task_attempts[step.name] = task_attempts.get(step.name, 0) + 1

    return autonomy, errors, task_attempts


def _metadata(config, trajectory, design_brief, *, single: bool, graph_mode: bool,
              regen_budget: int, backoff: float, errors: list, validation_errors: list,
              audit: dict, task_attempts: dict, repair_metrics: dict,
              autonomy: dict) -> dict:
    """What the run reports about ITSELF, as opposed to what it produced."""
    return {
        "llm": _llm_metadata(config),
        "token_usage": _token_usage_metadata(trajectory),
        "run_config": {
            "agent_mode": "single" if single else "multi",
            "context_mode": "graph" if graph_mode else "prose",
            "history_char_budget": history_budget(config),
            "max_turns": react.MAX_TURNS if single else ToolLoop.MAX_TURNS,
            "submit_budget": ToolLoop.SUBMIT_BUDGET,
            "use_rag": config.use_rag,
            "regen_budget": regen_budget,
            "regen_backoff_seconds": backoff,
            # Serving posture: a results dir has to say how many requests
            # the run was allowed to keep in flight, because that is the
            # difference between a 429-throttled arm and a clean one.
            "llm_max_concurrency": config.llm_max_concurrency,
            "llm_min_interval_seconds": config.llm_min_interval_seconds,
            # 1 = the sequential fan-out. Above 1 the multi arm's Developers
            # ran at once, which changes wall time and nothing else.
            "fanout_workers": config.fanout_workers,
            "protocol_rev": PROTOCOL_REV,
        },
        "design_brief_id": design_brief.id,
        "errors": errors,
        "validation_errors": validation_errors,
        "audit": audit,
        "task_attempts": task_attempts,
        "repair_metrics": repair_metrics,
        "autonomy": autonomy,
    }


def _result_payload(memory, design_brief, *, addie_output: dict, metadata: dict,
                    trajectory, trajectory_payload: dict, on_event) -> dict:
    """The result contract, and the last writes of the run.

    Report writing happens here because it happens LAST: the observer is
    detached first, so the deep trajectory ends with the last thing an agent
    did rather than with the dump.
    """
    result = {
        "addie_output": addie_output,
        "trajectory": trajectory_payload,
        "trajectory_deep": trajectory.to_dict_deep(),
        "metadata": metadata,
        # What the run remembered, beside what it produced. Deliberately NOT
        # inside `trajectory`: the judge reads that and the benchmark compares
        # it across arms, and transcripts alone would multiply its size by the
        # number of turns. The benchmark runner writes named keys only, so
        # these reach the app and the CLI and nothing else.
        "contexts": [t.as_dict() for t in memory.transcripts],
        "plans": [p.as_dict() for p in memory.plans],
        # Every DISTINCT finding of the run, with what became of it — the sole
        # owner of that question. `metadata.audit` used to carry the residual
        # set beside this one; it was the same list (the `residual` that
        # `_reconcile` returns reaches `audit()` and `memory.settle()` in one
        # breath), the graph arm's only, a snapshot rather than a history, and
        # it could not say whether a violation was repaired, converged or ran
        # out of budget. It is gone; this is where a reader is sent.
        "violations": [f.as_dict() for f in memory.findings],
    }
    if memory.graph is not None:
        memory.graph.set_observer(None)
        _maybe_dump_graph(memory.graph, design_brief, metadata)
        final_graph = memory.graph.to_full_dict(design_brief_id=design_brief.id)
        _safe_emit(on_event, "graph_snapshot", final_graph)
        result["graph"] = final_graph
    if memory.store is not None:
        # The prose arm's counterpart artifact (saved as <agent_id>_prose.json
        # by the benchmark): the blackboard documents verbatim. Inspection
        # material only — it carries no relations and no coverage, so the "a
        # prose run ships no alignment audit" contrast is untouched.
        result["prose"] = memory.store.to_full_dict(design_brief_id=design_brief.id)
    return result


class MetaAgent:
    """Run one design brief through the harness — the package's entry point.

    ``run`` IS the run: there is no ``execute_brief`` under it to forward to.
    A method that holds the ``llm_factory`` guard and then delegates is a
    forwarder, and this package keeps none.
    """

    def __init__(self, config: HarnessRunConfig) -> None:
        self.config = config

    def run(self, design_brief: DesignBrief, *, on_event=None) -> dict:
        """Run the brief and return the result contract (see
        :func:`_result_payload`, which assembles it).

        ``on_event(kind, payload)`` is an optional consumer that observes the
        run as it happens (see ``TrajectoryLogger``). It changes nothing about
        the returned result; it exists so a UI can show progress during a run
        that takes minutes.

        The ``llm_factory`` guard lives HERE because the benchmark adapter
        calls ``MetaAgent`` directly and runs unattended for hours. What an
        unguarded run looks like is on record from the demo app: it starts,
        every specialist fails, and it "completes" in milliseconds with an
        empty graph under a ``succeeded`` label. Callers map their own
        scenario schema to ``DesignBrief`` outside the harness and pass a
        configured ``HarnessRunConfig``.
        """
        if self.config.llm_factory is None:
            raise RuntimeError(
                "MetaAgent.run requires HarnessRunConfig.llm_factory. "
                "Benchmark integrations should construct DesignBrief externally "
                "and pass a configured HarnessRunConfig."
            )
        config = self.config
        graph_mode = config.context_mode != "prose"
        single = config.agent_mode == "single"

        # ONE memory for the run: the live substrate, every agent's transcript,
        # and every plan a Designer made. `state` stays bound to the SUBSTRATE, not
        # to the memory — half this module asks `hasattr(state, "element_nodes")`
        # to tell the arms apart, and a wrapper that does not answer that question
        # would silently put every graph run down the prose branch.
        memory = Memory(graph=AlignmentGraph()) if graph_mode else Memory(store=ProseStore())
        graph, store, state = memory.graph, memory.store, memory.state

        # Both live views a watcher gets — the alignment graph and the ledger of
        # what the run found wrong — hang off the consumer, because neither is part
        # of a recorded stream. ORDER IS LOAD-BEARING: the ledger goes INSIDE, so
        # its `violations_snapshot` reaches the raw consumer and never passes back
        # down through `_graph_attaching`, which would answer it with an extra
        # ~95 KB `to_full_dict()` of its own. Nothing is gated on `is_observed`
        # either: with no consumer neither wrapper is built, so an unwatched run
        # pays one integer increment per finding and serializes nothing.
        emit = on_event
        if on_event is not None:
            emit = _ledger_attaching(emit, memory)
            if graph is not None:
                emit = _graph_attaching(emit, graph, design_brief)
        trajectory = TrajectoryLogger(emit)
        if graph is not None:
            graph.set_observer(trajectory.graph_observer())

        # stages (or the single arm's one loop) + reconciliation + aggregate
        phase_total = (3 if single else len(STEPS) + 2)
        # Clamped, not defaulted: the fields always exist (``HarnessRunConfig``
        # declares them), but nothing stops a caller setting a negative one.
        regen_budget = max(0, int(config.regen_budget))
        backoff = max(0.0, float(config.regen_backoff_seconds))

        if single:
            autonomy, errors, task_attempts = _run_single(
                config, memory, trajectory, design_brief,
                graph_mode=graph_mode, phase_total=phase_total)
        else:
            autonomy, errors, task_attempts = _run_multi(
                config, memory, graph, store, trajectory, design_brief,
                graph_mode=graph_mode, regen_budget=regen_budget, backoff=backoff,
                phase_total=phase_total)
        # ── reconciliation: the residual cross-family violations, routed once ────
        # Bracketed as its own phase: the pass runs AFTER the last stage and logs
        # a check round per family plus a route per owner, so without a bracket of
        # its own every one of those events folds into whichever stage happened to
        # close last — a live viewer then reads the implementation stage as having
        # re-checked artifacts it never touched.
        with _phase(trajectory, "reconcile", phase_total - 1, phase_total), \
                trajectory.acting_as(ORCHESTRATOR):
            # The reconciliation's final look IS the run's residual, empty included.
            residual = _reconcile(state, trajectory, design_brief,
                                  graph_mode=graph_mode, memory=memory)
            # Everything still standing is now explained: whatever nothing marked
            # is `unexplained`, which is a fact worth saying rather than defaulting
            # to "the model could not do it".
            memory.settle({str(v.get("key") or "") for v in residual})

        # ── aggregation + residual audit ────────────────────────────────────────
        with _phase(trajectory, "aggregate", phase_total, phase_total):
            # One scope for assembly + its own validation, so log_validation_result
            # doesn't fall back to a stale actor once aggregate() returns.
            with trajectory.acting_as(ADDIEOutputAggregator.__name__):
                try:
                    addie_output = (ADDIEOutputAggregator(graph, trajectory).aggregate()
                                    if graph_mode else aggregate_prose(store, trajectory))
                except Exception:  # noqa: BLE001 - aggregation failure must not lose the run
                    addie_output = empty_addie()
                validation_errors = validate_addie(addie_output)
                trajectory.log_validation_result("addie_output", validation_errors)
            # Reads the final settled graph across every step's work, not the
            # aggregator's own — the audit is a whole-pipeline operation, so it is
            # the orchestrator's, not any one stage's. A prose run has no graph and
            # therefore nothing to audit; that absence is the auditability
            # contrast, not an omission.
            audit: dict = {}
            if graph_mode:
                with trajectory.acting_as(ORCHESTRATOR):
                    audit_result = GraphAuditor(graph).audit(residual)
                    trajectory.log_audit_result(audit_result, agent=ORCHESTRATOR)
                    audit = audit_result.to_dict()

        metadata = _metadata(
            config, trajectory, design_brief, single=single, graph_mode=graph_mode,
            regen_budget=regen_budget, backoff=backoff, errors=errors,
            validation_errors=validation_errors, audit=audit,
            task_attempts=task_attempts,
            repair_metrics=trajectory.summary_metrics(len(residual)),
            autonomy=autonomy)
        return _result_payload(
            memory, design_brief, addie_output=addie_output, metadata=metadata,
            trajectory=trajectory, trajectory_payload=trajectory.finalize(),
            on_event=on_event)
