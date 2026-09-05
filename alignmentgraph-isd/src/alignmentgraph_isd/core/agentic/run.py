"""Entry point of the agentic arm: run a design brief as 7 tool-loop stages.

This is the executor. It honours both
ablation axes:

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
``loop._WORKFLOW_OVERVIEW``): the agents are autonomous in how they execute a
stage, never in what order the stages run.

Cross-artifact violations are reconciled ONCE after the last stage, bounded by
``SELF_VALIDATION_BUDGET`` rounds — see :func:`_reconcile`. The packaging
below IS the result contract: ``core/runner.py::MetaAgent.run`` returns it
unchanged, and the benchmark adapter reads it.
"""
from __future__ import annotations

import time
from contextlib import contextmanager

from .. import dev_plans, repairs
from ..aggregate import ADDIEOutputAggregator, aggregate_prose
from ..alignment_graph import AlignmentGraph
from ..memory import Memory, Plan
from ..alignment_graph.audit import GraphAuditor
from ..brief import DesignBrief
from ..prose_store import ProseStore
from ..trajectory import TrajectoryLogger, WORKFLOW_ORCHESTRATOR
from ..validation import validate_addie
from ..run_report import (
    _graph_attaching, _llm_metadata, _maybe_dump_graph, _safe_emit,
    _token_usage_metadata,
)
from ..outputs import (
    SELF_VALIDATION_BUDGET, _collect_violations, _collect_violations_prose, empty_addie,
)
from . import fanout, replan
from .loop import HISTORY_CHAR_BUDGET, AgenticLLM, ToolLoop
from . import react
from .specialists import SINGLE_IDENTITY, STEPS, step_done


@contextmanager
def _phase(trajectory: TrajectoryLogger, phase: str, index: int, total: int):
    """Phase boundaries for live consumers (the demo app's SSE stream). Was a
    hand-copy of the scripted pipeline's own phase bracket while it existed;
    since that went, this is the only definition."""
    trajectory.emit("phase_started", {"phase": phase, "index": index, "total": total})
    started = time.time()
    with trajectory.acting_as("", phase=phase):
        # Explicit agent: see the note on _phase above.
        trajectory.log_action("phase_started", agent=WORKFLOW_ORCHESTRATOR,
                              phase=phase, index=index, total=total)
        try:
            yield
        finally:
            duration_ms = (time.time() - started) * 1000
            trajectory.log_action(
                "phase_finished", agent=WORKFLOW_ORCHESTRATOR,
                phase=phase, index=index, total=total, duration_ms=duration_ms)
            trajectory.emit("phase_finished", {
                "phase": phase, "index": index, "total": total, "duration_ms": duration_ms})


#: Every stage reports the SAME keys, whatever path it took. Rubrics has no
#: dispatch hop, so without a zeroed template its record would simply lack the
#: dispatch counters — and a reader could not tell "this stage made no dispatch
#: call" from "this field was never written". Uniform shape is what makes the
#: series comparable across stages and across arms.
def empty_stage_stats() -> dict:
    return {"turns_used": 0, "submits_rejected": 0, "repeated_calls": 0,
            "history_dropped": 0, "gave_up": False, "reads": 0,
            "context_len": 0, "batched_calls": 0, "markup_recovered": 0,
            "args_salvaged": 0, "truncated_turns": 0, "dropped_args": 0,
            "n_sets": 0, "sets_gave_up": 0, "set_turns": 0,
            "set_submits_rejected": 0,
            # How often this stage's window filled, and how often the fold kept
            # something of what went. Reported per stage because the two arms
            # reach it at completely different rates, which is the mechanism
            # the decomposition axis is about rather than noise around it.
            "compactions": 0, "compaction_summaries": 0}


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


def _serialize(violations: list, owner: str) -> list[dict]:
    """The wire form of a violation.

    Carries all eight fields plus its identity. It used to carry four —
    ``edge_type``, ``repair_hint``, ``metadata`` and ``target_designer`` were
    dropped, the last one two lines after ``_reconcile`` had just stamped it —
    so nothing downstream could route, explain or re-find a violation it only
    had ``msg`` for. ``node_id``/``type``/``msg``/``severity``/``owner`` keep
    their names: ``audit.py`` and every archived run read them."""
    return [
        {"key": v.key, "node_id": v.node_id, "type": v.violation_type,
         "msg": v.message, "severity": v.severity, "owner": owner,
         "edge_type": v.edge_type, "repair_hint": v.repair_hint,
         "metadata": dict(v.metadata), "target_designer": v.target_designer}
        for v in violations
    ]


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

    Deterministic and model-free: every routine in ``repairs`` is structural
    (2026-09-03), so this pass rearranges what the design holds and writes no
    content. A violation needing WRITING was already handed to its agent as a
    repair turn inside that agent's own loop, which is where the ``agent_mode``
    axis lives; opening a second conversation out here to write it would have
    put a context boundary of its own on that axis.

    Bounded, and after the last stage rather than re-entering mid-pipeline: a
    route -> repair -> recheck -> route cycle is no longer bounded by the stage
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
        trajectory=trajectory, actor=WORKFLOW_ORCHESTRATOR)

    def collect(family: str) -> list:
        violations = (_collect_violations(family, state, design_brief) if graph_mode
                      else _collect_violations_prose(family, state))
        owned = [v for v in violations
                 if v.violation_type in repairs.OWNED_BY_FAMILY[family]]
        for violation in owned:
            violation.target_designer = repairs.OWNER_BY_VIOLATION[violation.violation_type]
        return owned

    residual: list[dict] = []
    # PER FAMILY, not a global loop over all six. The stop condition used to be
    # `if not pending` across every family at once, so a family that came back
    # clean in round 1 was re-collected in round 2 anyway because some OTHER
    # family still had work — which is why a measured run logged 12 reconcile
    # rounds for 6 families that each needed one.
    for family in repairs.OWNED_BY_FAMILY:
        identity = _IDENTITY_BY_FAMILY[family]
        found: list = []
        for _round in range(SELF_VALIDATION_BUDGET):
            found = collect(family)
            # Recorded even when empty, like every stage's own round: "the
            # pass looked and found nothing" and "the pass never ran" are
            # different facts, and an audit has to tell them apart.
            #
            # Credited to the ORCHESTRATOR, not to the family whose output is
            # being checked. Attribution answers WHO ACTED, and the check runs
            # outside every agent's tool loop — no agent chose it, saw it, or
            # could have done otherwise. WHICH family's work was inspected is
            # not lost: it is the `family` field on the record.
            with trajectory.acting_as(WORKFLOW_ORCHESTRATOR):
                round_no = trajectory.log_violations_result(
                    _serialize(found, identity), agent=WORKFLOW_ORCHESTRATOR)
            keys = memory.observe_violations(
                found, round=round_no, phase="reconcile", family=family)
            if not found:
                break
            with trajectory.acting_as(WORKFLOW_ORCHESTRATOR):
                # The ROUTING is the orchestrator's act; the structural repair
                # it dispatches is recorded under the owning family's identity.
                # No model call happens here — the pass is deterministic.
                trajectory.log_reconcile_result(
                    family, found, agent=WORKFLOW_ORCHESTRATOR)
                before = len(trajectory.repair_events)
                repairs.repair(family, found, ctx)
                repaired = len(trajectory.repair_events) - before
            if not repaired:
                # PROOF, not a guess: the checks are pure functions of state and
                # nothing else writes state in between, so a pass that repaired
                # nothing would find exactly this again. Stop before paying for
                # the second look.
                memory.mark_open_reason(keys, reason="converged", round=round_no)
                with trajectory.acting_as(WORKFLOW_ORCHESTRATOR):
                    trajectory.log_convergence(
                        family, sorted(keys), [v.violation_type for v in found],
                        round_number=round_no, agent=WORKFLOW_ORCHESTRATOR)
                break
            memory.credit_repair(
                keys - {v.key for v in collect(family)},
                by=identity, round=round_no, harness=True)
        else:
            # The budget ran out with a repair on the LAST pass, so state moved
            # after the last look. Look once more before calling anything
            # residual — reporting the pre-repair set was how a violation the
            # final repair had just closed still counted against the run.
            found = collect(family)
            with trajectory.acting_as(WORKFLOW_ORCHESTRATOR):
                round_no = trajectory.log_violations_result(
                    _serialize(found, identity), agent=WORKFLOW_ORCHESTRATOR)
            memory.observe_violations(
                found, round=round_no, phase="reconcile", family=family)
            memory.mark_open_reason({v.key for v in found}, reason="budget")
        residual += _serialize(found, identity)
    return residual


#: Which stage identity owns each artifact family, for reconciliation routing
#: in the ``multi`` arm. Derived from the step table so it cannot drift from it.
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

    Re-entrant on purpose: ``pending`` is recomputed from committed state on
    every call, so the OUTER
    regen loop retries only the sets that came back empty and each set gets
    ``1 + regen_budget`` attempts — not ``(1 + budget)^2``.
    """
    # Planning and committing read and write the design state, and every such
    # event is stamped with whoever is currently acting — outside a scope they
    # land with an EMPTY agent (the attribution class fixed on 2026-08-27).
    # They belong to the orchestrator: neither is any one Developer's work.
    orchestrator = WORKFLOW_ORCHESTRATOR
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
            source="fallback" if stats_dev["fallback_used"] else "llm",
            fallback_used=stats_dev["fallback_used"],
            dropped_refs=stats_dev["dropped_lo_refs"],
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
    payloads: list[dict] = []
    for work_set in pending:
        identity = spec.developer_identity
        llm = AgenticLLM(config, trajectory, identity)
        captured: dict = {}
        with trajectory.acting_as(identity):
            # Inside the scope: building the assignment now READS the state
            # (the objectives the set names), and a read outside a scope lands
            # with an empty agent.
            set_step = fanout.set_step(spec, work_set, step, state)
            for attempt in range(regen_budget + 1):
                if attempt > 0 and backoff:
                    time.sleep(backoff * attempt)
                loop = ToolLoop(
                    config, memory, trajectory, design_brief, set_step, llm,
                    identity=identity, capture=captured,
                    max_turns=fanout.DEVELOPER_MAX_TURNS, attempt=attempt + 1)
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
                                        loop.stats["history_dropped"])):
                        stats[key] = stats.get(key, 0) + value
                    stats["context_len"] = max(stats.get("context_len", 0),
                                               loop.stats["context_len"])
                if captured.get("section"):
                    break
                trajectory.log_recovery_event(
                    identity, "regen_empty_section", f"attempt {attempt + 1}", set_step.name)
        # COMMIT THIS SET NOW, not once the whole family has run.
        #
        # It used to be deferred to the end because the ids have to be
        # collision-free across sets, and the remapper only knew about the
        # batch in front of it. It now takes the ids the state already holds
        # (`_ids_already_held`), so a per-set commit bumps a colliding id
        # exactly as a batched one did — and the deferral bought nothing while
        # costing the thing this stage most needs: with the work in the graph,
        # the checks can see it while the family's DESIGNER still has its loop
        # open, so a gap can go back to the agent whose job is to plan around
        # it. Deferred, the family's output first became visible after every
        # loop that could act on it had closed.
        payload = {"set_id": work_set.set_id, **(captured.get("section") or {})}
        payloads.append(payload)
        with trajectory.acting_as(orchestrator):
            fanout.commit_sets(spec, state, trajectory, [work_set], [payload])
    return stats


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
    for round_index in range(1, replan.REPLAN_ROUNDS + 1):
        # The CHECK is the orchestrator's: it runs outside every agent's loop.
        with trajectory.acting_as(WORKFLOW_ORCHESTRATOR):
            violations = (_collect_violations(step.family, state, design_brief)
                          if graph_mode else _collect_violations_prose(step.family, state))
            gaps = replan.gaps_for(step.name, violations)
            if not gaps:
                return stats
            trajectory.log_reconcile_result(
                step.family, gaps, agent=WORKFLOW_ORCHESTRATOR)

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
                specs=loop._specs)
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
        with trajectory.acting_as(WORKFLOW_ORCHESTRATOR):
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
    else:
        objectives = replan.objectives_of(gaps)
        if not objectives:
            return []
        work_sets, _stats = dev_plans.normalize_activity_dev_plan(plan, list(objectives))
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
    return {}


def _section_data(state, key: str) -> dict:
    from ..alignment_graph import NodeType

    if not hasattr(state, "element_nodes"):
        return state.get(key) or {}
    if key in ("assessment_plan", "activity_plan"):
        section = (NodeType.ASSESSMENT_PLAN if key == "assessment_plan"
                   else NodeType.ACTIVITY_PLAN)
        node = state.get_node(state.section_id(section))
        return (node or {}).get("data") or {}
    modules = [n["data"] for n in state.element_nodes(NodeType.CONTENT)]
    media = [n["data"] for n in state.element_nodes(NodeType.MEDIA_SELECTION)]
    return {"content_modules": modules, "media_selections": media}


def _repair_all(state, graph, store, trajectory, design_brief, *,
                graph_mode: bool, identity: str) -> list[dict]:
    """The single arm's deterministic repair net, over every family at once.

    The multi arm runs this per stage, right after that stage's Developer. The
    single arm has no stage boundaries to hang it on, so it runs once at the
    end — same checks, same ``SELF_VALIDATION_BUDGET`` rounds, same toolbox.
    What differs is only WHEN, which is a consequence of the axis, not a second
    treatment: an agent that decides its own order has no per-stage moment."""
    ctx = repairs.RepairContext(graph=graph, store=store, trajectory=trajectory,
                                actor=WORKFLOW_ORCHESTRATOR)
    residual: list[dict] = []
    for family in repairs.OWNED_BY_FAMILY:
        found: list = []
        for _ in range(SELF_VALIDATION_BUDGET):
            violations = (_collect_violations(family, graph, design_brief) if graph_mode
                          else _collect_violations_prose(family, store))
            found = [v for v in violations
                     if v.violation_type in repairs.OWNED_BY_FAMILY[family]]
            trajectory.log_violations_result(
                _serialize(found, identity), agent=WORKFLOW_ORCHESTRATOR)
            if not found:
                break
            repairs.repair(family, found, ctx)
        residual += _serialize(found, identity)
    return residual


def _run_multi(config, memory, graph, store, trajectory, design_brief, *,
               graph_mode: bool, regen_budget: int, backoff: float,
               phase_total: int) -> tuple[dict, list, list, dict]:
    """The multi arm: the harness walks the stages, each in a fresh context
    under that stage's specialist, and hands list-valued families to their
    Developers (fanout.py). Contrast ``_run_single``, where the agent walks
    them itself."""
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

            # The ORCHESTRATOR's scope, not the specialist's: this runs after
            # the tool loop has returned, and the agent neither chose it nor
            # saw it. Crediting the agent for a check it never ran inflates
            # what the trace says it did. Nothing here calls the model: what
            # needed writing was already offered to the agent inside its loop.
            with trajectory.acting_as(WORKFLOW_ORCHESTRATOR):
                ctx = repairs.RepairContext(
                    graph=graph, store=store, trajectory=trajectory,
                    actor=WORKFLOW_ORCHESTRATOR)
                # `also_repairs` families run here too: their artifacts were
                # produced by THIS step's Developer, so this is where their
                # checks first have something to look at.
                # A family that owns no checks (needs_analyst) has nothing to
                # look for, and a round logged against it would report "looked,
                # found nothing" about a search that never happened.
                #
                # NO residual accumulator here any more. It used to do
                # `residual += _serialize(owned, identity)` OUTSIDE this loop,
                # so a step with `also_repairs` counted only its last family —
                # and `found` was not reset per family, so a family that hit
                # the `continue` leaked the previous one's. Both were invisible
                # because nothing tests a residual count. `_reconcile` walks
                # all six families through the same checks after the last
                # stage, which is a superset of this, so the run's residual is
                # its final look and this accumulator was two bugs guarding
                # nothing. What each stage found is not lost: it is
                # `Finding.first_phase` + `first_round` in the ledger.
                for family in (step.family, *step.also_repairs):
                    if family not in repairs.OWNED_BY_FAMILY:
                        continue
                    for _ in range(SELF_VALIDATION_BUDGET):
                        violations = (_collect_violations(family, graph, design_brief)
                                      if graph_mode
                                      else _collect_violations_prose(family, store))
                        owned_types = repairs.OWNED_BY_FAMILY.get(family, frozenset())
                        found = [v for v in violations if v.violation_type in owned_types]
                        round_no = trajectory.log_violations_result(
                            _serialize(found, identity), agent=WORKFLOW_ORCHESTRATOR)
                        keys = memory.observe_violations(
                            found, round=round_no, phase=step.name, family=family)
                        if not found:
                            break
                        before = len(trajectory.repair_events)
                        repairs.repair(family, found, ctx)
                        if len(trajectory.repair_events) == before:
                            # Repaired nothing, so the next look is provably
                            # identical — see _reconcile.
                            memory.mark_open_reason(
                                keys, reason="converged", round=round_no)
                            trajectory.log_convergence(
                                family, sorted(keys),
                                [v.violation_type for v in found],
                                round_number=round_no, agent=WORKFLOW_ORCHESTRATOR)
                            break
                        memory.credit_repair(
                            keys - {v.key for v in
                                    (_collect_violations(family, graph, design_brief)
                                     if graph_mode
                                     else _collect_violations_prose(family, store))},
                            by=identity, round=round_no, harness=True)
            autonomy[step.name] = stats
            task_attempts[step.name] = task_attempts.get(step.name, 0) + 1

    # No residual from here: `_reconcile` re-derives it over every family
    # after the last stage, so returning a per-stage guess as well was two
    # sources for one number.
    return autonomy, errors, [], task_attempts


def run_agentic_brief(config, design_brief: DesignBrief, *, on_event=None) -> dict:
    graph_mode = getattr(config, "context_mode", "graph") != "prose"
    single = getattr(config, "agent_mode", "multi") == "single"

    # ONE memory for the run: the live substrate, every agent's transcript,
    # and every plan a Designer made. `state` stays bound to the substrate so
    # the checks, commits and views that only touch nodes are unchanged.
    # ONE memory for the run: the live substrate, every agent's transcript,
    # and every plan a Designer made. `state` stays bound to the SUBSTRATE, not
    # to the memory — half this module asks `hasattr(state, "element_nodes")`
    # to tell the arms apart, and a wrapper that does not answer that question
    # would silently put every graph run down the prose branch.
    memory = Memory(graph=AlignmentGraph()) if graph_mode else Memory(store=ProseStore())
    graph, store, state = memory.graph, memory.store, memory.state

    attach_graph = on_event is not None and graph is not None
    trajectory = TrajectoryLogger(
        _graph_attaching(on_event, graph, design_brief) if attach_graph else on_event)
    if graph is not None:
        graph.set_observer(trajectory.graph_observer())

    # stages (or the single arm's one loop) + reconciliation + aggregate
    phase_total = (3 if single else len(STEPS) + 2)
    regen_budget = max(0, int(getattr(config, "regen_budget", 2)))
    backoff = max(0.0, float(getattr(config, "regen_backoff_seconds", 0.0)))

    #: The single arm's transcript, kept so its repairs run in the context it
    #: built — that is the axis expressed at repair time.
    if single:
        with _phase(trajectory, "design", 1, 2):
            loop = react.ReactLoop(config, memory, trajectory, design_brief)
            try:
                # Every read and write this loop makes is the one agent's, and
                # an event outside a scope lands with an EMPTY agent.
                with trajectory.acting_as(SINGLE_IDENTITY):
                    loop.run()
            except Exception as exc:  # noqa: BLE001 - same containment as the multi arm
                errors = [f"{SINGLE_IDENTITY}: {exc}"]
                trajectory.log_recovery_event(
                    SINGLE_IDENTITY, "agent_error", "", str(exc)[:400])
            else:
                errors = []
            autonomy = {"design": loop.stats}
            # Outside the ReAct loop, so the orchestrator's — same rule as the
            # multi arm's per-stage net.
            with trajectory.acting_as(WORKFLOW_ORCHESTRATOR):
                residual = _repair_all(
                    state, graph, store, trajectory, design_brief,
                    graph_mode=graph_mode, identity=SINGLE_IDENTITY)
        task_attempts = {"design": 1}
    else:
        autonomy, errors, residual, task_attempts = _run_multi(
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
            trajectory.acting_as(WORKFLOW_ORCHESTRATOR):
        # Assigned, not `or residual`. That fallback meant "reconcile found
        # nothing" silently reverted to the pre-reconciliation list — a stale
        # snapshot contradicted by the very check that ended the pass. The
        # reconciliation walks all six families and its final look IS the run's
        # residual, empty included.
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
                addie_output = (ADDIEOutputAggregator(config, graph, trajectory).aggregate()
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
            with trajectory.acting_as(WORKFLOW_ORCHESTRATOR):
                audit_result = GraphAuditor(graph).audit(residual)
                trajectory.log_audit_result(audit_result, agent=WORKFLOW_ORCHESTRATOR)
                audit = audit_result.to_dict()

    repair_metrics = trajectory.summary_metrics(len(residual))
    trajectory_payload = trajectory.finalize()
    metadata = {
        "llm": _llm_metadata(config),
        "token_usage": _token_usage_metadata(trajectory),
        "run_config": {
            "agent_mode": "single" if single else "multi",
            "context_mode": "graph" if graph_mode else "prose",
            "history_char_budget": HISTORY_CHAR_BUDGET,
            "max_turns": ToolLoop.MAX_TURNS,
            "submit_budget": ToolLoop.SUBMIT_BUDGET,
            "use_rag": config.use_rag,
            "regen_budget": regen_budget,
            "regen_backoff_seconds": backoff,
            # Serving posture: a results dir has to say how many requests
            # the run was allowed to keep in flight, because that is the
            # difference between a 429-throttled arm and a clean one.
            "llm_max_concurrency": config.llm_max_concurrency,
            "llm_min_interval_seconds": config.llm_min_interval_seconds,
        },
        "design_brief_id": design_brief.id,
        "errors": errors,
        "validation_errors": validation_errors,
        "audit": audit,
        "task_attempts": task_attempts,
        "repair_metrics": repair_metrics,
        "autonomy": autonomy,
    }
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
        # Every DISTINCT finding of the run, with what became of it. Not a
        # second copy of `metadata.audit.violations`: that is the graph arm's
        # residual only (the prose arm has no graph to audit), it is a snapshot
        # rather than a history, and it cannot say whether a violation was
        # repaired, converged, or simply ran out of budget.
        "violations": [f.as_dict() for f in memory.findings],
    }
    # Report writing — detach the observer so the deep trajectory ends with
    # the last thing an agent did.
    if graph is not None:
        graph.set_observer(None)
        _maybe_dump_graph(graph, design_brief, metadata)
        final_graph = graph.to_full_dict(design_brief_id=design_brief.id)
        _safe_emit(on_event, "graph_snapshot", final_graph)
        result["graph"] = final_graph
        result["graph_dot"] = graph.to_dot(title=design_brief.id or "alignment-graph")
    if store is not None:
        # The prose arm's counterpart artifact (saved as <agent_id>_prose.json
        # by the benchmark): the blackboard documents verbatim. Inspection
        # material only — it carries no relations and no coverage, so the "a
        # prose run ships no alignment audit" contrast is untouched.
        result["prose"] = store.to_full_dict(design_brief_id=design_brief.id)
    return result
