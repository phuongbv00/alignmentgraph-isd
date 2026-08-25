"""LangGraph node factories + the single graph builder.

A ``NodeFactory`` captures the per-run objects (config, graph, trajectory,
design brief) and exposes each ISD step as a node function. ``build_workflow``
wires those nodes into a StateGraph: 6 Designer agents in a fixed pipeline
order + aggregation, four of them expanded into their own dev-plan fan-out.

Topology (fixed edges + one conditional Send-fan-out edge per fan-out family,
no routing/revision):

    START -> outcome_designer
           -> assessment_designer --Send x N--> assessment_developer --> assessment_finalize
           -> activity_designer   --Send x N--> activity_developer   --> activity_finalize
           -> [fan-out] content_designer --Send x N--> content_developer --> content_finalize
                        rubric_designer  --Send x N--> rubric_developer  --> rubric_finalize
           -> implementation_planner -> aggregate -> END

assessment_designer/activity_designer/content_designer/rubric_designer are
DISPATCH nodes: they decide the artifact's strategy and group the work into
:class:`core.dev_plans.WorkSet`\\ s (an LLM decision for assessment/activity;
deterministic — no LLM call — for content/rubric, since a content module and
an assessment item are already-enumerated units, not a grouping choice). A
Send-based conditional edge fans out one Developer call per work set, in
parallel, on separate LangGraph worker threads; the matching ``*_finalize``
node commits the pooled result, runs per-set regen and the family's relation
matchers, then self-validates — see ``NodeFactory.dispatch_node`` /
``worker_node`` / ``finalize_node`` and each family's ``*_designer.py`` /
``*_developer.py`` pair. The dev plan itself is orchestration metadata,
recorded only in the trajectory's ``dev_plan`` event — never a graph node,
store document, or ADDIE output section (see ``core/dev_plans.py``).

Because ``implementation_planner``'s two predecessors (``content_finalize``,
``rubric_finalize``) are no longer guaranteed to complete in the same
superstep as their sibling now that both are fan-out families, it is wired
through ``NodeFactory.join_guarded`` rather than a plain multi-edge join
(LangGraph fires a plain join once per predecessor that arrives, not once
after ALL have — verified, and ``defer=True`` does not fix it once one
predecessor's lineage passes through a ``Send``-based edge).

This topology is identical across ``context_mode``: "graph" gives each
Designer/Developer an ``AlignmentGraph`` substrate (relation-scoped context
injection, the alignment-state docket, a residual ``GraphAuditor`` pass at
aggregation); "prose" gives it a graph-free ``ProseStore`` blackboard instead
(see ``core/prose_store.py``) — only the substrate an agent reads/writes
differs, not the wiring. Every family self-validates and repairs its own
owned violations inline before its node (or, for a fan-out family, its
finalize node) returns (``run_generation_step`` / ``_self_validate`` /
``SELF_VALIDATION_BUDGET``); nothing downstream re-checks another family's
work.

``AlignmentGraph`` is internally lock-guarded (see its own module) because
the multi-agent workflow genuinely runs specialists concurrently — this
predates the fan-out (content_designer/rubric_designer already shared a
superstep) but the fan-out's extra concurrent Developer calls widen the
window a lot further.

``agent_mode="single"`` builds a degenerate one-node graph instead
(``_build_single_agent_graph``): one ``SingleDesignerAgent`` whose
assessment/activities/content/rubrics states run the SAME dispatch-then-
per-set structure internally, but SEQUENTIALLY (parallelism is part of what
this axis measures) — see ``core/agents/single_designer.py``.

Removed 2026-08-28 (same date as the fan-out, unrelated to it): a set of 3
"validate" checkpoints + a deterministic router that could send a Designer
back for a narrow ``revise()`` when a downstream check found a cross-artifact
gap it traced to an earlier Designer's output. Measurement showed it was
structurally almost always a no-op: by the time a checkpoint ran, the
violation types it could route were either already self-repaired inline by
the exact owning Designer moments before (the checkpoint re-checked the same
types with nothing left to find), or excluded by the router's own
valid-targets list. Whatever a Designer's inline repair genuinely could not
fix still surfaces in the final ``GraphAuditor`` residual at aggregation —
removing the checkpoints costs no detection, only the topology and state
that never changed a run's outcome.
"""
from __future__ import annotations

import operator
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, TypedDict

from .alignment_graph import alignment
from . import checks
from . import repairs
from . import dev_plans
from . import prose_store as store_module
from .alignment_graph.audit import GraphAuditor
from .alignment_graph import NodeType
from .validation import PLACEHOLDER_FIELD_MARKER, validate_addie, validate_section
from .agents.outcome_designer import OutcomeDesignerAgent
from .agents.assessment_designer import AssessmentDesignerAgent
from .agents.assessment_developer import AssessmentDeveloperAgent
from .agents.activity_designer import ActivityDesignerAgent
from .agents.activity_developer import ActivityDeveloperAgent
from .agents.content_designer import ContentDesignerAgent
from .agents.material_developer import MaterialDeveloperAgent
from .agents.rubric_designer import RubricDesignerAgent
from .agents.rubric_developer import RubricDeveloperAgent
from .agents.implementation_planner import ImplementationPlannerAgent
from .agents.single_designer import SingleDesignerAgent
from .agents.addie_aggregator import ADDIEOutputAggregator, _merge_node_data, aggregate_prose
from .trajectory import WORKFLOW_ORCHESTRATOR

# ── LangGraph state ────────────────────────────────────────────────────────────
# Only plain JSON-serializable types live here so MemorySaver can checkpoint them.
# Non-serializable objects (config, graph, trajectory, brief) are captured by the
# NodeFactory and never placed in state.

def _merge_task_attempts(a: dict[str, int], b: dict[str, int]) -> dict[str, int]:
    """Additive merge for ``task_attempts``. Needed (not a plain dict) because
    Content Designer and Rubric Designer run in the SAME superstep (parallel
    fan-out) and each bumps its OWN key — LangGraph's default (last-value)
    channel can't reconcile two concurrent partial writes to one state field
    without a reducer, even when the keys they touch don't collide."""
    merged = dict(a)
    for key, value in b.items():
        merged[key] = merged.get(key, 0) + value
    return merged


def _merge_work_sets(a: dict[str, list[dict]], b: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Additive merge for ``work_sets``. content_designer and rubric_designer
    dispatch in the SAME superstep (the existing parallel fan-out before the
    implementation planner) and each writes its OWN family key — same reason
    ``task_attempts`` needs a reducer, not a plain last-value channel."""
    return {**a, **b}


class ISDState(TypedDict):
    violations: list[dict]          # serialized Violation dicts
    addie_output: dict
    errors: Annotated[list[str], operator.add]
    audit: dict
    task_attempts: Annotated[dict[str, int], _merge_task_attempts]
    validation_errors: list[str]
    #: Dev-plan fan-out state (2026-08-28). ``work_sets``: family -> the
    #: WorkSet dicts its dispatch node produced. ``pending_elements``: every
    #: Developer payload from every family's fan-out, tagged by "family" —
    #: an operator.add channel can't be cleared, so each finalize node
    #: filters to its own family and leaves the rest inert (harmless: no
    #: reader ever consumes an entry twice). See core/dev_plans.py.
    work_sets: Annotated[dict[str, list[dict]], _merge_work_sets]
    pending_elements: Annotated[list[dict], operator.add]


# Generation Designers in fixed pipeline order (node name -> agent class).
GENERATION_AGENTS: dict[str, type] = {
    "outcome_designer": OutcomeDesignerAgent,
    "assessment_designer": AssessmentDesignerAgent,
    "activity_designer": ActivityDesignerAgent,
    "content_designer": ContentDesignerAgent,
    "rubric_designer": RubricDesignerAgent,
    # A specialist like the rest, not a bolt-on. It was excluded while its only
    # justification held — "establishes no alignment edge" — but it now writes
    # P10/P11 (which activities it schedules, which materials it hands out), has
    # its own persona, checks and repairs, and had a hand-copied duplicate of
    # the generation scaffolding that was missing regen and exception
    # containment. Registering it removes the duplicate and, in the ablation's
    # single arm, removes the last leftover second persona.
    "implementation_planner": ImplementationPlannerAgent,
}

GENERATION_ORDER = [
    "outcome_designer", "assessment_designer", "activity_designer",
    "content_designer", "rubric_designer", "implementation_planner",
]

#: Families converted to the dev-plan fan-out (dispatch -> parallel Send
#: workers -> finalize) instead of the flat generation_node. The Designer
#: class (GENERATION_AGENTS) still owns dispatch + finalize; the Developer
#: class here owns exactly one LLM call per work set. See core/dev_plans.py
#: and each family's *_designer.py / *_developer.py module docstrings.
DEVELOPER_AGENTS: dict[str, type] = {
    "assessment_designer": AssessmentDeveloperAgent,
    "activity_designer": ActivityDeveloperAgent,
    "content_designer": MaterialDeveloperAgent,
    "rubric_designer": RubricDeveloperAgent,
}

#: Short node-name prefix per fan-out family: dispatch keeps the family's
#: existing node name (so upstream edges never change), the develop/finalize
#: nodes get "{prefix}_developer" / "{prefix}_finalize".
_FANOUT_NODE_PREFIX: dict[str, str] = {
    "assessment_designer": "assessment",
    "activity_designer": "activity",
    "content_designer": "content",
    "rubric_designer": "rubric",
}

FANOUT_FAMILIES: frozenset[str] = frozenset(DEVELOPER_AGENTS)

#: Steps whose artifact is a SECTION node with no element pool, so emptiness is
#: judged on the section's required fields instead. See NodeFactory._produced.
_SECTION_ONLY_STEPS: dict[str, str] = {
    "implementation_planner": NodeType.IMPLEMENTATION_PLAN,
}

# The one output each generation step must not come back empty for — the
# regen-empty check (see _generate) is scoped to "did this step's primary
# artifact type get created at all", not full field-level validation (that's
# validate_section's job, applied where a section node exists).
_PRIMARY_ELEMENT_TYPE: dict[str, str] = {
    "outcome_designer": NodeType.OBJECTIVE,
    "assessment_designer": NodeType.ASSESSMENT,
    "activity_designer": NodeType.ACTIVITY,
    "content_designer": NodeType.MATERIAL,
    "rubric_designer": NodeType.RUBRIC,
}

EMPTY_SECTION_REGEN_BUDGET = 2
SELF_VALIDATION_BUDGET = 2

_EMPTY_FIELD_MARKER = "required field is missing or empty"


def _empty_required_fields(section_type: str, data: dict) -> list[str]:
    """Required fields that came back unusable: missing/empty, or filled with
    schema placeholder text copied verbatim (equally absent to a reader, but
    invisible to a plain emptiness check)."""
    return [
        e for e in validate_section(section_type, data)
        if e.endswith(_EMPTY_FIELD_MARKER) or e.endswith(PLACEHOLDER_FIELD_MARKER)
    ]


class NodeFactory:
    """Builds node functions bound to one run's objects.

    Exactly one of ``graph``/``store`` is live per run (see config.py's
    ``context_mode``): the graph arm gets an AlignmentGraph and no store, the
    prose arm gets a ProseStore blackboard and ``graph=None``.
    """

    def __init__(self, config, graph, trajectory, design_brief, store=None) -> None:
        self.config = config
        self.graph = graph
        self.store = store
        self.trajectory = trajectory
        self.design_brief = design_brief
        #: Start time per open phase, keyed by phase name. Needed because a
        #: fan-out family's phase_started (dispatch node) and phase_finished
        #: (finalize node) fire from two SEPARATE LangGraph node
        #: invocations — possibly different threads — so the duration can't
        #: live on a local variable the way a single contextmanager scope
        #: could hold it (see _phase_open/_phase_close).
        self._phase_starts: dict[str, float] = {}

    @property
    def _graph_mode(self) -> bool:
        return getattr(self.config, "context_mode", "graph") == "graph"

    # ── shared helpers ──────────────────────────────────────────────────────
    def _args(self):
        return self.config, self.graph, self.trajectory, self.store

    @staticmethod
    def _bump_attempt(state: ISDState, task_name: str) -> dict:
        return {"task_attempts": {task_name: 1}}

    # ── progress signalling ─────────────────────────────────────────────────
    def _phase_open(self, phase: str, index: int, total: int) -> None:
        """The "started" half of a phase bracket, usable standalone (not just
        as a contextmanager) so a fan-out family can open its phase in the
        dispatch node and close it in the finalize node — two separate
        LangGraph node invocations. Ordinary (non-fan-out) nodes get the
        SAME bracket via ``_phase`` below, which just calls this then
        ``_phase_close`` around one node body."""
        self.trajectory.emit("phase_started", {"phase": phase, "index": index, "total": total})
        self._phase_starts[phase] = time.time()
        with self.trajectory.acting_as("", phase=phase):
            # Explicit agent: a phase boundary is the pipeline's own event, not
            # a specialist's — it fires before/after whichever agent is inside
            # this block sets its own identity, so falling back to "whoever
            # acted last" would misattribute it to a stale or unrelated agent.
            self.trajectory.log_action("phase_started", agent=WORKFLOW_ORCHESTRATOR,
                                       phase=phase, index=index, total=total)

    def _phase_close(self, phase: str, index: int, total: int) -> None:
        started = self._phase_starts.pop(phase, time.time())
        duration_ms = (time.time() - started) * 1000
        with self.trajectory.acting_as("", phase=phase):
            self.trajectory.log_action(
                "phase_finished", agent=WORKFLOW_ORCHESTRATOR,
                phase=phase, index=index, total=total, duration_ms=duration_ms,
            )
            self.trajectory.emit("phase_finished", {
                "phase": phase, "index": index, "total": total, "duration_ms": duration_ms,
            })

    @contextmanager
    def _phase(self, phase: str, index: int, total: int):
        """A single node's phase bracket — unlike ``_phase_open``/
        ``_phase_close`` used standalone (each opens its OWN narrow
        ``acting_as`` scope just for its one log line, because a fan-out
        family's dispatch and finalize are separate node invocations with a
        real ``acting_as(identity, phase=family)`` of their own in between —
        see ``dispatch_node``/``finalize_node``), this wraps OPEN + THE WHOLE
        YIELDED BODY + CLOSE in one continuous ``acting_as("", phase=phase)``
        scope. That continuity matters: ``run_generation_step``'s own
        ``acting_as(identity)`` call (deliberately no phase override, so it
        inherits whatever the caller already set) reads `self._phase` at
        that point — call this the ``_phase_open``/``_phase_close`` pair
        instead and the body runs with phase="" the whole time, since each
        of those closes its own scope immediately after logging.
        """
        self.trajectory.emit("phase_started", {"phase": phase, "index": index, "total": total})
        started = time.time()
        with self.trajectory.acting_as("", phase=phase):
            self.trajectory.log_action("phase_started", agent=WORKFLOW_ORCHESTRATOR,
                                       phase=phase, index=index, total=total)
            try:
                yield
            finally:
                duration_ms = (time.time() - started) * 1000
                self.trajectory.log_action(
                    "phase_finished", agent=WORKFLOW_ORCHESTRATOR,
                    phase=phase, index=index, total=total, duration_ms=duration_ms,
                )
                self.trajectory.emit("phase_finished", {
                    "phase": phase, "index": index, "total": total, "duration_ms": duration_ms,
                })

    # ── one generation step: regen + inline self-validation ─────────────────
    def _produced(self, node_name: str, primary_type: str | None) -> bool:
        """Did this step actually create its artifact?

        Element-pool emptiness for every artifact that HAS elements. The
        implementation planner is section-only — it never calls
        add_element_node — so an element-pool check would read empty on every
        attempt, burn the whole regen budget and still continue. For it the
        equivalent question is whether its section's required fields came back
        populated, which validate_section already answers.
        """
        section_type = _SECTION_ONLY_STEPS.get(node_name)
        if not self._graph_mode:
            if section_type is not None:
                data = self.store.get("implementation_plan") or {}
                return bool(data) and not _empty_required_fields(section_type, data)
            return bool(store_module.primary_items(
                self.store, str(primary_type or _PRIMARY_ELEMENT_TYPE[node_name])))
        if section_type is not None:
            node = self.graph.get_node(self.graph.section_id(section_type))
            data = (node or {}).get("data") or {}
            return bool(data) and not _empty_required_fields(section_type, data)
        return bool(self.graph.element_nodes(primary_type or _PRIMARY_ELEMENT_TYPE[node_name]))

    def _regen_loop(self, run_fn, produced_fn, identity: str, node_name: str) -> list[str]:
        """Attempt/backoff/regen-empty half of a generation step: call
        ``run_fn()`` up to ``config.regen_budget`` extra times until
        ``produced_fn()`` reports success.

        Extracted from ``run_generation_step`` (2026-08-28) so the dev-plan
        fan-out's ``dispatch_node`` can reuse the exact same retry story
        without duplicating it — the ablation's shared-scaffolding guarantee
        (see that method's docstring) has to keep holding for converted
        families too. Caller is responsible for the ``acting_as`` scope.
        """
        errors: list[str] = []
        budget = max(0, int(getattr(self.config, "regen_budget", EMPTY_SECTION_REGEN_BUDGET)))
        backoff = max(0.0, float(getattr(self.config, "regen_backoff_seconds", 0.0)))
        for attempt in range(budget + 1):
            if attempt > 0 and backoff:
                time.sleep(backoff * attempt)
            try:
                run_fn()
            except Exception as exc:
                errors.append(f"{identity}: {exc}")
                self.trajectory.log_recovery_event(identity, "agent_error", "", str(exc)[:400])
                continue
            if produced_fn():
                break
            self.trajectory.log_recovery_event(
                identity, "regen_empty_section", f"attempt {attempt + 1}", node_name,
            )
        return errors

    def _self_validate(self, agent, identity: str, node_name: str) -> None:
        """Inline self-validation + repair half of a generation step: run the
        node's owned checks up to ``SELF_VALIDATION_BUDGET`` rounds,
        repairing between rounds. Extracted alongside ``_regen_loop`` for the
        same reason — see its docstring. Caller is responsible for the
        ``acting_as`` scope (so events land under the right phase/actor)."""
        for _ in range(SELF_VALIDATION_BUDGET):
            violations = (
                _collect_violations(node_name, self.graph, self.design_brief)
                if self._graph_mode
                else _collect_violations_prose(node_name, self.store)
            )
            # Read off the INSTANCE: resolves to the class attribute for a
            # real Designer, and to the per-state family for
            # _SingleStateStep — both point at the same
            # repairs.OWNED_BY_FAMILY entry.
            owned = [v for v in violations if v.violation_type in agent.OWNED_VIOLATION_TYPES]
            self.trajectory.log_violations_result([
                {"node_id": v.node_id, "type": v.violation_type, "msg": v.message,
                 "severity": v.severity, "owner": identity}
                for v in owned
            ])
            if not owned:
                break
            agent.repair(owned)

    def run_generation_step(self, agent, identity: str, node_name: str,
                            primary_type: str | None = None, *,
                            self_validate: bool = True) -> list[str]:
        """Generate one artifact type, then self-validate and repair it.

        Shared verbatim by the multi-agent nodes and the single-agent arm's
        internal steps (the families NOT converted to the dev-plan fan-out —
        see ``dispatch_node``/``finalize_node`` for the converted ones, which
        call ``_regen_loop``/``_self_validate`` directly instead of through
        here). It has to be shared, not duplicated, because everything in
        here is scaffolding the ablation is NOT testing: empty-output regen,
        exception containment, and the self-validation budget. The single
        arm used to have none of the first two and a self-validation budget
        of 2 for ALL checks against multi's 2 per Designer, so `multi -
        single` was partly measuring robustness and repair effort rather
        than decomposition — with the gap widening on exactly the weak
        models the study is about.

        ``self_validate`` exists so the single arm can match the multi arm's
        verification EFFORT where its state machine packs more into one step
        (audit 2026-08-30): self-validation runs once per FAMILY in the multi
        arm (six family nodes, six passes), but the single arm's ``analysis``
        and ``outcomes`` are two states of the SAME family, so validating
        after both gave it seven passes and a spurious empty check event every
        scenario. That is verification effort, not decomposition, so it must
        not differ across the axis. The default keeps every multi-arm caller
        unchanged.

        The matching retry-ceiling fix lives on the other side, in
        ``SingleDesignerAgent._run_fanout_state``: that method is re-entrant,
        so this loop alone gives each work set ``1 + regen_budget`` attempts —
        the same ceiling ``finalize_node``'s ``_regen_missing_sets`` gives the
        multi arm. Doing both stacked the budgets to ``(1 + budget)^2``.

        Returns the errors to surface in state; violations are logged here.
        """
        # Default produced-check: pool-level emptiness (or, for a
        # section-only step, required-field emptiness). Wrong for a
        # RE-ENTRANT step whose "done" is finer-grained than "the pool has
        # >=1 item" -- the single arm's fan-out states define their own
        # produced() (see SingleDesignerAgent.produced /
        # _SingleStateStep.produced) so a state with some-but-not-all work
        # sets realised is correctly still "not produced", the same
        # distinction dispatch_node's dispatch_produced() draws for the
        # multi arm.
        produced = getattr(agent, "produced", None) or (
            lambda: self._produced(node_name, primary_type))
        # One scope for the whole method: `_produced`'s graph reads and the
        # self-validation loop below run after `agent.run()` returns, and a
        # narrower `acting_as` around just that call let every read/verify
        # after it fall back to whoever acted before this step (empty on the
        # very first step of a run) instead of `identity`.
        with self.trajectory.acting_as(identity):
            errors = self._regen_loop(
                lambda: agent.run(self.design_brief),
                produced,
                identity, node_name,
            )
            if self_validate:
                self._self_validate(agent, identity, node_name)
        return errors

    # ── generation nodes (first-pass OR revision-mode dispatch) ─────────────
    def generation_node(self, node_name: str, phase_index: int = 0, phase_total: int = 0):
        agent_cls = GENERATION_AGENTS[node_name]
        # .get, not []: a section-only step (the implementation planner) has no
        # element pool, and _produced answers emptiness from its section fields.
        primary_type = _PRIMARY_ELEMENT_TYPE.get(node_name)

        def _node(state: ISDState) -> dict:
            with self._phase(node_name, phase_index, phase_total):
                return _generate(state)

        def _generate(state: ISDState) -> dict:
            agent = agent_cls(*self._args())
            errors = self.run_generation_step(agent, agent_cls.__name__, node_name)

            result = self._bump_attempt(state, node_name)
            if errors:
                result["errors"] = errors
            return result
        return _node

    # ── dev-plan fan-out: dispatch -> [Send x N] -> develop -> finalize ─────
    # (2026-08-28) A converted family's node is three LangGraph nodes instead
    # of one: `dispatch_node` plans + groups the work into WorkSets and opens
    # the phase bracket; a Send-based conditional edge fans out one
    # `worker_node` instance per set (parallel, on separate LangGraph worker
    # threads — the same mechanism content_designer/rubric_designer already
    # use for their sibling fan-out); `finalize_node` commits the pooled
    # result, runs per-set regen + the family's self-validation, and closes
    # the phase bracket. See core/dev_plans.py for the WorkSet contract and
    # each family's *_designer.py/*_developer.py pair for the split itself.

    def dispatch_node(self, family: str, phase_index: int, phase_total: int):
        agent_cls = GENERATION_AGENTS[family]
        identity = agent_cls.__name__

        def _node(state: ISDState) -> dict:
            self._phase_open(family, phase_index, phase_total)
            agent = agent_cls(*self._args())
            # Default produced-check: did dispatch decide on >=1 unit of
            # work. Wrong for a family whose normalize function can't return
            # an empty list on its own (content_designer's material_work_units
            # degenerates to one MU-ALL unit rather than none) — such an
            # agent defines its own dispatch_produced() checking the real
            # artifact instead (see ContentDesignerAgent.dispatch_produced).
            produced = getattr(agent, "dispatch_produced", None) or (
                lambda: bool(agent.take_work_sets()))
            with self.trajectory.acting_as(identity, phase=family):
                errors = self._regen_loop(
                    lambda: agent.run_dispatch(self.design_brief),
                    produced,
                    identity, family,
                )
            result = {
                "work_sets": {family: [ws.as_dict() for ws in agent.take_work_sets()]},
                "task_attempts": {family: 1},
            }
            if errors:
                result["errors"] = errors
            return result
        return _node

    def fanout_edge(self, family: str, develop_name: str, finalize_name: str):
        """Conditional-edge callable: one ``Send`` per work set the dispatch
        node produced, all issued in the SAME superstep.

        Dispatch emits >=1 set whenever there is at least one ground-truth
        obligation to cover (dev-plan normalization falls back to one
        singleton set per obligation — see core/dev_plans.py). But a
        pathological upstream failure (e.g. zero learning objectives ever
        committed) leaves zero obligations, and thus zero sets, to fan out.
        ``finalize_name``'s ONLY inbound edge is from ``develop_name`` — if
        that edge never fires because zero Sends were issued, finalize (and
        everything after it: the rest of the pipeline, aggregation) never
        runs either, and the whole run silently stops right here with no
        exception. Routing straight to finalize with nothing to develop is
        the map-reduce escape hatch: it runs with an empty payload list,
        commits nothing, and the family's existing empty-output handling
        (repairs, the residual audit) takes it from there — exactly as an
        unconverted family behaves when its own regen budget exhausts on a
        persistently empty response.
        """
        def _edge(state: ISDState) -> list:
            from langgraph.types import Send
            work_sets = state.get("work_sets", {}).get(family, [])
            if not work_sets:
                return [finalize_name]
            return [Send(develop_name, {**ws, "family": family}) for ws in work_sets]
        return _edge

    def join_guarded(self, node_fn, required_keys: tuple[str, ...]):
        """Wrap a join node whose predecessors can complete in DIFFERENT
        supersteps.

        A plain multi-``add_edge`` join in LangGraph fires once per
        predecessor that arrives, not once after ALL of them have — and
        ``defer=True`` (the usual fix) does not help either once one
        predecessor's lineage passes through a ``Send``-based conditional
        edge: verified with a minimal reproduction, a deferred join node
        still fired before its Send-fanned branch had finished. Reading
        readiness from ``state`` instead of relying on LangGraph's edge
        scheduling sidesteps that entirely: every premature invocation sees
        at least one required ``task_attempts`` entry missing (that
        predecessor's write hasn't been merged into state yet) and returns
        no state update — no phase events, no LLM calls, nothing. The
        predecessor that finishes LAST naturally re-triggers this node with
        every entry now visible, and THAT invocation does the real work
        exactly once.
        """
        def _node(state: ISDState) -> dict:
            attempts = state.get("task_attempts", {})
            if not all(attempts.get(key) for key in required_keys):
                return {}
            return node_fn(state)
        return _node

    def worker_node(self, family: str):
        developer_cls = DEVELOPER_AGENTS[family]
        identity = developer_cls.__name__

        def _node(payload: dict) -> dict:
            developer = developer_cls(*self._args())
            work_set = dev_plans.work_set_from_dict(payload)
            with self.trajectory.acting_as(identity, phase=family):
                try:
                    item_payload = developer.run_worker(work_set, self.design_brief)
                except Exception as exc:
                    self.trajectory.log_recovery_event(identity, "agent_error", "", str(exc)[:400])
                    item_payload = {"family": family, "set_id": work_set.set_id, "items": []}
            return {"pending_elements": [item_payload]}
        return _node

    def finalize_node(self, family: str, phase_index: int, phase_total: int):
        agent_cls = GENERATION_AGENTS[family]
        identity = agent_cls.__name__

        def _node(state: ISDState) -> dict:
            agent = agent_cls(*self._args())
            work_sets = [
                dev_plans.work_set_from_dict(d)
                for d in state.get("work_sets", {}).get(family, [])
            ]
            payloads = [p for p in state.get("pending_elements", []) if p.get("family") == family]
            errors: list[str] = []
            with self.trajectory.acting_as(identity, phase=family):
                try:
                    agent.finalize(work_sets, payloads, self.design_brief)
                except Exception as exc:
                    errors.append(f"{identity}: {exc}")
                    self.trajectory.log_recovery_event(identity, "agent_error", "", str(exc)[:400])
                self._self_validate(agent, identity, family)
            self._phase_close(family, phase_index, phase_total)
            result = {"task_attempts": {f"{family}_finalize": 1}}
            if errors:
                result["errors"] = errors
            return result
        return _node

    # ── aggregation (+ silent residual audit) ───────────────────────────────
    def aggregate_node(self, phase_index: int = 0, phase_total: int = 0):
        def _node(state: ISDState) -> dict:
            with self._phase("aggregate", phase_index, phase_total):
                return _aggregate(state)

        def _aggregate(state: ISDState) -> dict:
            # One scope for assembly + its own validation, so log_validation_result
            # doesn't fall back to a stale actor once the aggregate() call returns.
            with self.trajectory.acting_as("ADDIEOutputAggregator"):
                try:
                    if self._graph_mode:
                        addie_output = ADDIEOutputAggregator(*self._args()).aggregate()
                    else:
                        addie_output = aggregate_prose(self.store, self.trajectory)
                except Exception:
                    addie_output = empty_addie()
                validation_errors = validate_addie(addie_output)
                self.trajectory.log_validation_result("addie_output", validation_errors)
            result: dict = {"addie_output": addie_output, "validation_errors": validation_errors}
            # The residual audit is a product of the graph; the prose arm has
            # nothing to audit — that absence is the auditability contrast.
            # It reads the final settled graph across every specialist's work,
            # not the aggregator's own — same WorkflowOrchestrator attribution
            # as the routing checkpoints.
            if self._graph_mode and not state.get("audit"):
                with self.trajectory.acting_as(WORKFLOW_ORCHESTRATOR):
                    residual = GraphAuditor(self.graph).audit(state.get("violations", []))
                    self.trajectory.log_audit_result(residual, agent=WORKFLOW_ORCHESTRATOR)
                result["audit"] = residual.to_dict()
            return result
        return _node


def _collect_violations(node_name: str, graph, design_brief) -> list:
    """The self-validation checks a Designer owns/inspects before committing
    — see each agent's own docstring for which checks it owns vs. only
    reads. Scoped narrowly per node so ``repair()``'s OWNED_VIOLATION_TYPES
    filter does meaningful work rather than every agent seeing everything."""
    if node_name == "outcome_designer":
        return checks.bloom_verbs(graph) + checks.measurability(graph)
    if node_name == "assessment_designer":
        coverage = [v for v in checks.relation_coverage(graph) if v.violation_type in ("C2", "P3")]
        bloom = [v for v in checks.bloom_mismatches(graph) if v.violation_type == "bloom_mismatch_assessment"]
        return (coverage + bloom + checks.evaluation_quality(graph) + checks.plan_coverage(graph)
                + checks.item_completeness(graph))
    if node_name == "activity_designer":
        coverage = [v for v in checks.relation_coverage(graph) if v.violation_type in ("C3", "C4", "P4")]
        bloom = [v for v in checks.bloom_mismatches(graph) if v.violation_type == "bloom_mismatch_activity"]
        return coverage + checks.activity_engagement(graph) + bloom
    if node_name == "content_designer":
        coverage = [v for v in checks.relation_coverage(graph) if v.violation_type in ("C5", "P5", "P6")]
        return coverage + checks.orphan_content(graph)
    if node_name == "rubric_designer":
        coverage = [v for v in checks.relation_coverage(graph) if v.violation_type in ("C6", "C7")]
        return (coverage + checks.rubric_consistency(graph) + checks.evidence_alignment(graph)
                + checks.orphan_rubric(graph))
    if node_name == "implementation_planner":
        return checks.feasibility(graph, design_brief) + checks.actionability(graph)
    return []


def _collect_violations_prose(node_name: str, store) -> list:
    """The prose arm's self-validation scope: the same WITHIN-ARTIFACT check
    cores the graph arm runs (see checks.py), fed from the blackboard. Every
    cross-artifact check — relation coverage, Bloom cross-checks,
    plan_coverage, engagement/orphan/evidence checks, feasibility — is part
    of the alignment machinery this arm ablates and does not run here."""
    if node_name == "outcome_designer":
        objectives = [
            (str(lo.get("id", "")), lo)
            for lo in store.items("objective", "learning_objectives")
            if isinstance(lo, dict)
        ]
        return checks.bloom_verbs_items(objectives) + checks.measurability_items(objectives)
    if node_name == "assessment_designer":
        plan = store.get("assessment_plan")
        quality = checks.evaluation_quality_data("assessment_plan", plan) if plan else []
        tools = [
            (str(t.get("item_id", "")), t)
            for t in store.items("assessment", "assessment_tools")
            if isinstance(t, dict)
        ]
        return quality + checks.item_completeness_items(tools)
    if node_name == "rubric_designer":
        criteria = [
            (str(rc.get("id", "")), rc)
            for rc in store.items("rubric", "rubric_criteria")
            if isinstance(rc, dict)
        ]
        return checks.rubric_consistency_items(criteria)
    if node_name == "implementation_planner":
        data = store.get("implementation_plan")
        return checks.actionability_data("implementation_plan", data) if data else []
    return []


def initial_state() -> ISDState:
    return {
        "violations": [], "addie_output": {}, "errors": [], "audit": {},
        "task_attempts": {}, "validation_errors": [],
        "work_sets": {}, "pending_elements": [],
    }


def build_workflow(config, graph, trajectory, design_brief, store=None):
    """Assemble the LangGraph StateGraph for this run.

    ``config.agent_mode == "single"`` builds a degenerate one-node graph
    running `SingleDesignerAgent` instead. Otherwise, both values of
    ``context_mode`` build the SAME linear multi-Designer topology
    (``_build_multi_graph``) — only the substrate ``NodeFactory`` hands each
    Designer (an ``AlignmentGraph`` vs. a graph-free ``ProseStore``
    blackboard) differs, not the wiring."""
    from langgraph.graph import StateGraph

    nf = NodeFactory(config, graph, trajectory, design_brief, store)
    wf = StateGraph(ISDState)

    if getattr(config, "agent_mode", "multi") == "single":
        return _build_single_agent_graph(wf, nf, config, graph, trajectory, design_brief)

    return _build_multi_graph(wf, nf)


def _build_multi_graph(wf, nf: NodeFactory):
    """The six generation nodes in fixed pipeline order, with content/rubric
    running as a parallel fan-out before the implementation planner.

    A family in ``FANOUT_FAMILIES`` is wired as three nodes instead of one
    (dispatch -> Send-fanned develop -> finalize — see
    ``NodeFactory.dispatch_node`` et al.), but the dispatch node keeps the
    family's ORIGINAL name, so every edge into/out of it below is written
    exactly as if it were still the flat node. Only ``_wire_family`` needs to
    know the difference.
    """
    from langgraph.graph import START, END

    phase_total = 6 + 1  # 6 designers + aggregate
    idx = 0

    def _next_idx():
        nonlocal idx
        idx += 1
        return idx

    def _wire_family(name: str) -> None:
        """Add one family's node(s), unconverted or fan-out, at the next
        phase index. Edges between families are added separately below, by
        the family's own (unchanged) node name either way."""
        phase_index = _next_idx()
        if name not in FANOUT_FAMILIES:
            wf.add_node(name, nf.generation_node(name, phase_index, phase_total))
            return
        prefix = _FANOUT_NODE_PREFIX[name]
        develop_name, finalize_name = f"{prefix}_developer", f"{prefix}_finalize"
        wf.add_node(name, nf.dispatch_node(name, phase_index, phase_total))
        wf.add_node(develop_name, nf.worker_node(name))
        wf.add_node(finalize_name, nf.finalize_node(name, phase_index, phase_total))
        wf.add_conditional_edges(
            name, nf.fanout_edge(name, develop_name, finalize_name), [develop_name, finalize_name])
        wf.add_edge(develop_name, finalize_name)

    def _family_out(name: str) -> str:
        """The node an edge FROM this family should originate at: the
        finalize node for a fan-out family (everything downstream must wait
        for the pooled, self-validated result), the flat node otherwise."""
        if name in FANOUT_FAMILIES:
            return f"{_FANOUT_NODE_PREFIX[name]}_finalize"
        return name

    def _readiness_key(name: str) -> str:
        """The ``task_attempts`` key that marks this family as genuinely
        DONE — the finalize node's key for a fan-out family (its dispatch
        node also bumps a key, but only finalize means "pooled and
        self-validated"), the flat node's own key otherwise."""
        if name in FANOUT_FAMILIES:
            return f"{name}_finalize"
        return name

    for family in ("outcome_designer", "assessment_designer", "activity_designer",
                    "content_designer", "rubric_designer"):
        _wire_family(family)
    # implementation_planner's two predecessors (content_designer's finalize,
    # rubric_designer) do NOT reliably complete in the same superstep once
    # content_designer is a fan-out family — a plain multi-edge join fires
    # once per predecessor, not once after both (see join_guarded's
    # docstring; ``defer=True`` does not fix this either, once one lineage
    # passes through a Send-based conditional edge). Wire it as a single
    # node wrapped in the state-readiness guard instead of two add_edges
    # racing to trigger a plain node.
    phase_index = _next_idx()
    wf.add_node("implementation_planner", nf.join_guarded(
        nf.generation_node("implementation_planner", phase_index, phase_total),
        required_keys=(_readiness_key("content_designer"), _readiness_key("rubric_designer")),
    ))
    # A guarded node's premature (no-op) pass still "completes" as far as
    # LangGraph is concerned, so its OWN downstream edge fires too -- the
    # guard has to cascade one more hop, or aggregate would run on a
    # premature call, and since `audit`/`addie_output` are plain (non-
    # reducer) channels, a genuinely-empty-but-real premature aggregate pass
    # would either get silently overwritten by the real one (best case,
    # wasted work) or -- what was actually observed -- have its OWN internal
    # `not state.get("audit")` guard read the state the premature pass just
    # wrote and skip recomputing it, leaving a stale, incomplete residual
    # audit as the final one. aggregate has no further downstream node, so
    # this is the last hop that needs guarding.
    wf.add_node("aggregate", nf.join_guarded(
        nf.aggregate_node(phase_index=phase_total, phase_total=phase_total),
        required_keys=("implementation_planner",),
    ))

    wf.add_edge(START, "outcome_designer")
    wf.add_edge(_family_out("outcome_designer"), "assessment_designer")
    wf.add_edge(_family_out("assessment_designer"), "activity_designer")
    wf.add_edge(_family_out("activity_designer"), "content_designer")
    wf.add_edge(_family_out("activity_designer"), "rubric_designer")
    # Fan-in: both parallel Designers must complete before the planner reads
    # (enforced by the readiness guard above, not by this edge pair alone).
    wf.add_edge(_family_out("content_designer"), "implementation_planner")
    wf.add_edge(_family_out("rubric_designer"), "implementation_planner")
    wf.add_edge("implementation_planner", "aggregate")
    wf.add_edge("aggregate", END)
    return wf.compile()


class _SingleStateStep:
    """Adapts one state of the single agent's state machine to the contract
    ``run_generation_step`` expects, so the shared scaffolding is literally the
    same code in both arms rather than a second copy that can drift.

    ``OWNED_VIOLATION_TYPES`` and ``repair`` come from the shared repair
    toolbox (``core/repairs.py``), addressed by the artifact family this state
    produced — the same functions the owning Designer's own ``repair()``
    dispatches to, run here under the single agent's own context and identity.
    No Designer class is instantiated: validation strength is a safeguard held
    constant across arms because both arms call the same substrate, not
    because one arm borrows the other's agents.
    """

    def __init__(self, agent, state: str, family: str) -> None:
        self._agent = agent
        self._state = state
        self._family = family
        self.OWNED_VIOLATION_TYPES = repairs.OWNED_BY_FAMILY[family]

    def run(self, design_brief) -> None:
        self._agent.run_state(self._state, design_brief)

    def produced(self) -> bool:
        """Delegates to the agent's own per-state predicate (see
        ``SingleDesignerAgent.produced``) — this wrapper has no state of its
        own, only ``self._state`` naming which one to ask about."""
        return self._agent.produced()

    def repair(self, violations: list) -> list:
        return repairs.repair(self._family, violations, repairs.context_for(self._agent))


def _build_single_agent_graph(wf, nf: NodeFactory, config, graph, trajectory, design_brief):
    """The `single` arm of the decomposition ablation axis: one
    `SingleDesignerAgent` node covering every artifact family the six
    specialists cover, and no routing (nothing else to route to)."""
    from langgraph.graph import START, END

    identity = SingleDesignerAgent.IDENTITY

    def _monolithic_node(state):
        with nf._phase("monolithic_designer", 1, 3):
            agent = SingleDesignerAgent(*nf._args())
            with trajectory.acting_as(identity, force_identity=True):
                # One agent, its own state machine — but the SAME scaffolding
                # every multi-agent node gets (regen, exception containment,
                # self-validation budget, the shared deterministic repairs in
                # core/repairs.py). Those are safeguards, not the manipulation:
                # an earlier version of this arm had none of them and `multi -
                # single` partly measured robustness instead of decomposition.
                errors: list[str] = []
                # Keep the retry ceiling and the self-validation COUNT
                # identical to the multi arm — see run_generation_step's
                # docstring for what each of the two guards below fixes.
                # Self-validation is per FAMILY there, so run it on each
                # family's LAST state here (only outcome_designer spans two).
                last_state_of_family = {
                    family: state for state, _t, _p, family in SingleDesignerAgent.STATES
                }
                for state_name, _task, primary, family in SingleDesignerAgent.STATES:
                    step = _SingleStateStep(agent, state_name, family)
                    errors += nf.run_generation_step(
                        step, identity, family, primary_type=primary,
                        self_validate=last_state_of_family[family] == state_name)
            result = {"task_attempts": {"monolithic_designer": 1}}
            if errors:
                result["errors"] = errors
            return result

    # No separate implementation node here: the implementation planner is a
    # specialist in the multi arm, so in this arm the single agent covers it as
    # its own state. Wiring it separately as well ran implementation TWICE and
    # left a second persona in the trajectory, which is exactly the leftover
    # this restructure removes.
    wf.add_node("monolithic_designer", _monolithic_node)
    wf.add_node("aggregate", nf.aggregate_node(phase_index=2, phase_total=2))
    wf.add_edge(START, "monolithic_designer")
    wf.add_edge("monolithic_designer", "aggregate")
    wf.add_edge("aggregate", END)
    return wf.compile()


def empty_addie() -> dict:
    return {
        "analysis": {"needs_analysis": {}, "learner_analysis": {}, "context_analysis": {}, "task_analysis": {}},
        "design": {"learning_objectives": [], "instructional_strategies": {}},
        "development": {"learner_materials": [], "assessment_tools": [], "expert_review": {}},
        "implementation": {"instructor_orientation": {}, "system_check": {}, "prototype_execution": {}, "monitoring": {}},
        "evaluation": {"formative": {}, "summative": {}, "improvement_plan": {}},
    }
