from __future__ import annotations
import threading
import time
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from enum import StrEnum
from typing import Callable


class TrajectoryAction(StrEnum):
    """The complete, stable vocabulary for one trajectory action.

    An action tells the reader what happened; action-specific operands and
    results belong in ``context``. New actions must be added here deliberately
    rather than introduced as ad-hoc strings at a call site.
    """

    PHASE_STARTED = "phase_started"
    PHASE_FINISHED = "phase_finished"
    NODE_READ = "node_read"
    NODE_WRITE = "node_write"
    NODE_ADD = "node_add"
    NODE_UPDATE = "node_update"
    EDGE_READ = "edge_read"
    EDGE_WRITE = "edge_write"
    #: No emitter since traversal was removed 2026-08-10 (measured: 0 of 1179
    #: graph reads were walks). Kept so an archived run still parses, and read
    #: by string from the webapp timelines.
    EDGE_WALK = "edge_walk"
    LLM_CALL = "llm_call"
    AGENT_STEP = "agent_step"
    VALIDATE = "validate"
    CHECK = "check"
    REPAIR = "repair"
    AUDIT = "audit"
    RETRIEVAL = "retrieval"
    RETRIEVAL_QUERY = "retrieval_query"
    RETRY = "retry"
    REGENERATE_EMPTY_SECTION = "regen_empty_section"
    AGENT_ERROR = "agent_error"
    LLM_ERROR = "llm_error"
    SALVAGE_TRUNCATED = "salvage_truncated"
    INVALID_ACTION = "invalid_action"
    SUBMIT_REJECTED = "submit_rejected"
    SUBMIT_INVALID_FINAL = "submit_invalid_final"
    REPEATED_TOOL_CALL = "repeated_tool_call"
    COMMIT_INVALID_SECTION = "commit_invalid_section"
    #: An accepted submit that re-sent what was already committed —
    #: how an agent answers "anything more for this stage?" with "no".
    #: A call was spent, so the trace has to show it; it is not a
    #: second design STEP, which the judge would score as redundancy.
    DUPLICATE_SUBMIT = "duplicate_submit"
    #: A submit the validator ACCEPTED whose artifact is absent from the design
    #: state afterwards. Always a harness failure, never the model's: the
    #: `unwrap_section` defect (run 24343e4d) stripped an artifact's own name
    #: off its envelope and committed the inside at the top level of the
    #: section, so the artifact was reported committed and never landed. The
    #: model was then told "COMMITTED. <stage> still needs: <that artifact>"
    #: beside a protocol saying never to resend what is committed, and each of
    #: the 11 resulting turns was recorded as its redundancy.
    COMMIT_DID_NOT_LAND = "commit_did_not_land"
    #: The reply carried the model's REASONING channel and nothing else — no
    #: content, no tool call — while `finish_reason` read "stop", so truncation
    #: salvage could not see it either. A serving posture (Qwen3 left in
    #: thinking mode), not the model refusing the protocol, and separated from
    #: `invalid_action` for exactly that reason: charging the two identically
    #: makes a serving artifact read as a finding about the model. The fix is
    #: `disable_thinking` on the factory; this is what makes its absence
    #: visible. MEASURED (run 24343e4d): 12 of 78 calls, 47-405 billed
    #: completion tokens each, one stage turn gone every time.
    THINKING_ONLY_REPLY = "thinking_only_reply"
    #: A submit whose payload was the artifact itself rather than the
    #: {key: artifact} envelope its tool declares — wrapped rather than
    #: rejected. See ToolLoop._wrap_bare_artifact.
    BARE_ARTIFACT_WRAPPED = "bare_artifact_wrapped"
    #: The window filled and the oldest turns were folded into a note. Says how
    #: many went and whether a model call kept anything of them. Recorded
    #: because it is a real model call that produces no design step — and
    #: because how OFTEN each arm reaches it is the decomposition mechanism
    #: measuring itself.
    CONTEXT_COMPACTED = "context_compacted"
    #: Tool calls in a batched reply that were answered with a stub instead of
    #: running: the turn budget ran out first, or the stage ended first. Every
    #: call the model makes is answered (the chat API requires it); this says
    #: which ones were answered without being done.
    CALLS_NOT_EXECUTED = "calls_not_executed"
    #: The single arm's allowance for answering repair requests after its last
    #: stage landed ran out — the same number of turns a stage gets.
    REPAIR_WINDOW_CLOSED = "repair_window_closed"
    #: A repair pass stopped early because it had proved it could not fix what
    #: was left: the same findings came back with nothing repaired in between.
    #: Recorded so a converged run does not read like a clean one.
    CONVERGE = "converge"
    #: An element the model submitted twice in ONE artifact, dropped on commit.
    #: MEASURED (run single_20260904_020259): a 2B model returned 50 learning
    #: objectives carrying 4 distinct statements, one of them 32 times, and
    #: every downstream family sizes itself off that count — 63 assessment work
    #: sets, 36 activity blocks, 347 model calls, 955s. Recorded rather than
    #: silently absorbed BECAUSE the padding rate is itself a finding about the
    #: model class this study is about.
    DUPLICATE_ELEMENT_DROPPED = "duplicate_element_dropped"
    AGENTIC_FALLBACK = "agentic_fallback"
    #: The backend accepted no tool binding, so the stage has no act->observe
    #: loop and gives up at once rather than spending MAX_TURNS discovering the
    #: same thing. On the ladder this must never fire (vLLM runs
    #: --enable-auto-tool-choice); it exists so that a misconfigured endpoint is
    #: visible in the trace instead of silently costing the run its artifacts.
    TOOL_BINDING_UNAVAILABLE = "tool_binding_unavailable"
    #: The serving-side tool-call parser left a correctly-formed call as plain
    #: text and the loop recovered it (``tools.parse_tool_call_markup``). Not a
    #: model mistake — recorded so the RATE is visible per size, because it
    #: bounds how much of the agentic arm's behaviour is really the serving
    #: stack's.
    TOOL_CALL_MARKUP_RECOVERED = "tool_call_markup_recovered"
    #: The single arm's ReAct loop ran out of turns with stages still open.
    #: Reported for BOTH arms (`autonomy.via_budget_exhaustion`) because the
    #: parity claim is not that the budgets are equal — `multi` spends a number
    #: of turns that is a function of how many work sets it planned — but that
    #: the budget CUT neither arm.
    BUDGET_EXHAUSTED = "budget_exhausted"
    #: A step ended without the agent producing a valid artifact. Until
    #: 2026-09-01 a scripted single-shot wrote one instead and this was called
    #: `agentic_fallback`; it was writing 26-35% of the full pipeline's
    #: artifacts, and only in the multi arm, so the decomposition axis was
    #: measuring who got rescued. The deterministic repair net catches what is
    #: left, for both arms.
    AGENTIC_GAVE_UP = "agentic_gave_up"
    #: One document written to the prose blackboard. The graph arm records
    #: every artifact it produces as ``node_add``; without this the prose arm
    #: recorded NOTHING it produced, so "what did this run make" was auditable
    #: in one context mode and blind in the other — an asymmetry in the AUDIT
    #: SURFACE, not in the treatment. (Judge input is unaffected: the judge
    #: reads tool_calls/reasoning_steps/agent_interactions, never ``events``.)
    DOC_WRITE = "doc_write"
    #: A residual cross-artifact violation handed to the family that owns it,
    #: after the last stage. See ``core/agentic/run.py::_reconcile``.
    RECONCILE = "reconcile"
    DEV_PLAN = "dev_plan"
    #: A repair that must SUPPLY a missing artifact asked the model to write it
    #: and got nothing usable back, so it wrote nothing. Recorded because the
    #: alternative — a template that filled the hole — was removed precisely
    #: for being invisible: the check passed, the artifact existed, and nothing
    #: in the trace said no design work had happened. This is a recovery event,
    #: so it never reaches the judge; it is how the RATE of unfilled repairs is
    #: read per size while tuning.
    REPAIR_UNFILLED = "repair_unfilled"
    #: An OPTIONAL submit argument arrived as text where a structure was
    #: declared, so it was removed and the rest of the submit accepted. The
    #: alternative — refusing the whole submit — threw away a Developer's
    #: complete set of assessment items because the criteria beside them were
    #: malformed. Recorded so the rate stays visible: if it is high, the
    #: secondary output is not really being produced and the repair that
    #: covers it is doing the work.
    DROPPED_ARGUMENT = "dropped_argument"


_RECOVERY_ACTIONS = frozenset({
    TrajectoryAction.RETRY,
    TrajectoryAction.REGENERATE_EMPTY_SECTION,
    TrajectoryAction.AGENT_ERROR,
    TrajectoryAction.LLM_ERROR,
    TrajectoryAction.SALVAGE_TRUNCATED,
    TrajectoryAction.INVALID_ACTION,
    TrajectoryAction.SUBMIT_REJECTED,
    TrajectoryAction.SUBMIT_INVALID_FINAL,
    TrajectoryAction.REPEATED_TOOL_CALL,
    TrajectoryAction.COMMIT_INVALID_SECTION,
    TrajectoryAction.DUPLICATE_SUBMIT,
    TrajectoryAction.BARE_ARTIFACT_WRAPPED,
    TrajectoryAction.COMMIT_DID_NOT_LAND,
    TrajectoryAction.THINKING_ONLY_REPLY,
    TrajectoryAction.CONTEXT_COMPACTED,
    TrajectoryAction.CALLS_NOT_EXECUTED,
    TrajectoryAction.REPAIR_WINDOW_CLOSED,
    TrajectoryAction.CONVERGE,
    TrajectoryAction.DUPLICATE_ELEMENT_DROPPED,
    TrajectoryAction.AGENTIC_FALLBACK,
    # Replaced AGENTIC_FALLBACK on 2026-09-01 and was never added here, so
    # every give-up was missing from `recovery_events` — the one view that is
    # supposed to answer "what went wrong in this run".
    TrajectoryAction.AGENTIC_GAVE_UP,
    TrajectoryAction.BUDGET_EXHAUSTED,
    TrajectoryAction.TOOL_BINDING_UNAVAILABLE,
    TrajectoryAction.TOOL_CALL_MARKUP_RECOVERED,
    TrajectoryAction.REPAIR_UNFILLED,
    TrajectoryAction.DROPPED_ARGUMENT,
    TrajectoryAction.REPAIR,
})

# Identity for events that belong to the pipeline itself, not any specialist —
# phase boundaries. Never leave ``agent`` to fall back to "whoever acted last"
# for these: a phase_started fires before its specialist has set an identity,
# and phase_finished fires after the stage's trailing self-validation
# loop has already exited that specialist's `acting_as` block, so the natural
# fallback is stale or empty, not this phase's owner.
WORKFLOW_ORCHESTRATOR = "WorkflowOrchestrator"


def _recovery_action(name: str) -> tuple[TrajectoryAction, dict]:
    """Map a recovery call site to the public taxonomy. An unknown name is a
    loud ValueError: no ``repair_*`` mapping exists here because the
    deterministic toolbox already records each repair as ONE structured
    ``log_repair_event`` (rule + narrative included), and a second mapping
    here would silently double-count it."""
    return TrajectoryAction(name), {}


class TrajectoryLogger:
    """Accumulates the run trace, and — optionally — mirrors it live.

    ``on_event`` is the one observation hook in the harness: it fires as each
    entry is recorded, so a consumer (the demo web app) can show progress while
    a run that takes minutes is still in flight. It is purely additive; with no
    consumer every emit is a no-op and the recorded trace is exactly what it
    was before. A consumer that raises is swallowed — observation must never be
    able to break a run — with one deliberate exception: ``HarnessCancelled``
    derives from ``BaseException`` and so passes through, which is how the app
    asks a run to stop.
    """

    def __init__(self, on_event: Callable[[str, dict], None] | None = None) -> None:
        self._on_event = on_event
        self._start = time.time()

        # ── the deep trajectory ──────────────────────────────────────────────
        # A single ordered log of what each agent actually did: read the graph,
        # write a node, draw an alignment edge, call the model, verify, repair.
        # It is the ONE full-fidelity record of a step (untruncated summaries);
        # the streams below are the benchmark contract — the judge trio
        # (tool_calls/reasoning_steps/agent_interactions, parsed by the
        # evaluator) plus structured audit events — and each fact appears in
        # exactly one of them, never in two.
        self.actions: list[dict] = []
        # Who/what phase is "currently acting". Plain instance state since
        # 2026-09-04: it was thread-local while the LangGraph pipeline ran
        # specialists on separate worker threads (content_designer and
        # rubric_designer fanned out from one join), where a shared attribute
        # let one thread's `acting_as` exit reset the actor out from under
        # another. The executor is sequential — no `ThreadPoolExecutor` in
        # `core/` outside RAG — so there is no longer a thread to isolate from,
        # and thread-local state would now be actively WRONG for the one place
        # concurrency remains: a retrieval worker thread would read an empty
        # actor instead of the agent that dispatched it. Restore it if any
        # concurrent fan-out comes back.
        self._actor: str = ""
        self._phase: str = ""
        self._identity: str = ""
        self.tool_calls: list[dict] = []
        self.reasoning_steps: list[str] = []
        self.agent_interactions: list[dict] = []
        # ── the unified event log ────────────────────────────────────────────
        # One chronological action log ("at time t, agent A did X"):
        # recovery / node_edit / validation / check / repair / retrieval.
        # Filter by their taxonomy action instead of keeping six parallel streams; the
        # ``*_events`` / ``node_edits`` properties below are those filters.
        self.events: list[dict] = []
        self.llm_calls: int = 0
        self.token_usage: dict = {"prompt_tokens": 0, "completion_tokens": 0}
        self.latency_ms: float = 0.0
        # Guards the read-modify-write increments in log_llm_call. KEPT even
        # though the pipeline is sequential: RAG's parallel retrieval plans run
        # on worker threads (`core/rag/sandbox.py`) and each is handed
        # ``log_llm_call`` directly.
        self._counter_lock = threading.Lock()

    # ── observation hook ────────────────────────────────────────────────────
    def _emit(self, kind: str, payload: dict) -> None:
        if self._on_event is None:
            return
        try:
            self._on_event(kind, payload)
        except Exception:  # noqa: BLE001 - observation is never load-bearing.
            # Deliberately Exception, not BaseException: HarnessCancelled must
            # propagate so a consumer can stop a run.
            pass

    @property
    def is_observed(self) -> bool:
        """Whether anyone is watching this run.

        Emitting is a no-op without a consumer, but BUILDING an emit's payload
        is not: a context snapshot serializes the whole transcript, and doing
        that once per turn for nobody would put a cost on every benchmark run
        to serve a viewer that is not there."""
        return self._on_event is not None

    def emit(self, kind: str, payload: dict) -> None:
        """Progress-only signal: records nothing, changes no state.

        Used for the "started" side of long operations (a phase, an LLM call),
        which the recorded streams cannot express because every ``log_*`` entry
        is written after the work it describes has already finished.
        """
        self._emit(kind, payload)

    # ── the deep trajectory: the action log ─────────────────────────────────

    @contextmanager
    def acting_as(self, actor: str, phase: str | None = None, *, force_identity: bool = False):
        """Attribute everything logged inside this block to one agent.

        Set around a specialist's work rather than passed to each call, because
        most actions are recorded deep inside the graph, which has no idea who
        is asking.

        ``force_identity`` also overrides the ``agent_name`` that ``log_step``,
        ``log_recovery_event`` and ``log_repair_event`` are given. Needed by
        the ablation's ``single`` arm: shared routines (the repair toolbox,
        the scaffolding around a stage loop) log under whoever calls
        them, and an earlier version of this arm ran the Designer classes as
        internal steps and emitted a trajectory naming six distinct agents —
        byte-identical in shape to the multi-agent arm, which left the
        decomposition axis unobservable to the trajectory judge. Off by
        default: in multi mode the actor already equals the name each step
        passes, so forcing would change nothing there.
        """
        previous_actor, previous_phase = self._actor, self._phase
        previous_identity = self._identity
        self._actor = actor or previous_actor
        if phase is not None:
            self._phase = phase
        if force_identity:
            self._identity = actor
        try:
            yield
        finally:
            self._actor, self._phase = previous_actor, previous_phase
            self._identity = previous_identity

    # ── the unified event log ───────────────────────────────────────────────

    def _record_event(
        self, action: TrajectoryAction, emit_kind: str, agent: str = "", **context,
    ) -> dict:
        """Append one canonical event to ``events`` and mirror it live.

        ``agent`` defaults to whoever is currently acting (``acting_as``), so
        every event answers "who did this" even when the call site cannot know.
        """
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent": agent or self._actor,
            "action": action.value,
            "context": {
                "phase": self._phase,
                **context,
            },
        }
        self.events.append(event)
        self._emit(emit_kind, event)
        return event

    def _events_of(self, actions: TrajectoryAction | frozenset[TrajectoryAction]) -> list[dict]:
        if isinstance(actions, TrajectoryAction):
            actions = frozenset({actions})
        return [event for event in self.events if event["action"] in actions]

    # Action views over ``events`` — internal consumers (aggregator, metrics,
    # tests) read these; the artifact carries only the one ``events`` list.
    @property
    def recovery_events(self) -> list[dict]:
        return self._events_of(_RECOVERY_ACTIONS)

    @property
    def node_edits(self) -> list[dict]:
        return self._events_of(frozenset({TrajectoryAction.NODE_ADD, TrajectoryAction.NODE_UPDATE}))

    @property
    def validation_events(self) -> list[dict]:
        return self._events_of(TrajectoryAction.VALIDATE)

    @property
    def check_events(self) -> list[dict]:
        return self._events_of(TrajectoryAction.CHECK)

    @property
    def repair_events(self) -> list[dict]:
        return self._events_of(TrajectoryAction.REPAIR)

    @property
    def retrieval_events(self) -> list[dict]:
        return self._events_of(TrajectoryAction.RETRIEVAL)

    def log_action(self, action: TrajectoryAction | str, *, agent: str = "", **context) -> dict:
        """Record one thing an agent did, and mirror it to any live consumer."""
        action = TrajectoryAction(action)
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent": agent or self._actor,
            "action": action.value,
            "context": {
                "phase": self._phase,
                "elapsed_ms": (time.time() - self._start) * 1000,
                **context,
            },
        }
        self.actions.append(entry)
        self._emit("action", entry)
        return entry

    def graph_observer(self):
        """Adapter for ``AlignmentGraph(observer=…)``.

        The graph reports operations without knowing who ran them; this stamps
        each one with whoever is currently acting.
        """
        def observe(kind: str, fields: dict) -> None:
            self.log_action(TrajectoryAction(kind), **fields)

        return observe

    def log_step(self, agent_name: str, action: str, input_summary: str, output_summary: str) -> None:
        """Record ONE real, successful, purposeful action — the judge-visible
        surface (``tool_calls``/``reasoning_steps``/``agent_interactions``).

        Since the pivot there are exactly TWO kinds, and both are acts of the
        tool loop: a tool call the loop answered with an observation, and a
        submit it accepted. Nothing else reaches these lists. (It used to be
        "one per hop" — Hop A/B, the Content Designer's three steps — which is
        machinery that no longer exists; the name ``agent_step`` is kept because
        an act->observe turn IS a step the agent took, and because the string is
        in every recorded run.)

        The fan-out is here too: a Developer's submit is its own step under its
        own identity, which is what makes the second tier visible to the judge
        at all.

        Do NOT call this for internal recovery plumbing (empty-output regen,
        truncation salvage, JSON-correction retries) — those go through
        ``log_recovery_event`` instead, which the judge never reads. Root
        cause this rule fixes: the benchmark's trajectory judge penalizes
        repeated tool names/args as redundancy, and the prior design put
        every retry attempt through this same method, tanking small-model
        scores (measured: AlignmentGraph-ISD lowest of 7 agents at
        Qwen3.5-0.8B, 83.85/100) purely because small models need more
        recovery attempts, not because their real tool use was worse.
        """
        agent_name = self._identity or agent_name
        timestamp = datetime.now(timezone.utc).isoformat()
        step_index = len(self.tool_calls) + 1
        self._emit("agent_step", {
            "agent_name": agent_name,
            "action": action,
            "input_summary": input_summary,
            "output_summary": output_summary,
            "timestamp": timestamp,
        })
        # The one full-fidelity (untruncated) copy of a step lives in the deep
        # action log; every list below is a judge-facing view of it.
        self.log_action(TrajectoryAction.AGENT_STEP, agent=agent_name, agent_action=action,
                        input_summary=input_summary, output_summary=output_summary)

        # The benchmark trajectory evaluator expects BFCL-style tool traces.
        # These three lists are exactly what its `_format_trajectory` reads
        # (tool/args/result; the reasoning strings; agent/action/iteration) —
        # their content is judge input and must not change shape or bytes.
        self.tool_calls.append({
            "step": step_index,
            "tool": f"{agent_name}.{action}",
            "args": {
                "agent": agent_name,
                "action": action,
                "input_summary": input_summary[:500],
            },
            "result": output_summary[:1000],
            "timestamp": timestamp,
        })
        self.reasoning_steps.append(
            f"Step {step_index}: {agent_name} performed {action}; "
            f"input={input_summary[:180]}; result={output_summary[:220]}"
        )
        self.agent_interactions.append({
            "iteration": step_index,
            "agent": agent_name,
            "action": action,
            "timestamp": timestamp,
        })

    def log_recovery_event(self, agent_name: str, action: str, input_summary: str, output_summary: str) -> None:
        """Record an internal recovery attempt (empty-output regen, truncation
        salvage, JSON-correction retry) — the SAME shape as ``log_step``, but
        written only to the deep action log + ``recovery_events``, never to
        ``tool_calls``/``reasoning_steps``/``agent_interactions``. The
        benchmark's trajectory judge only reads those three lists (confirmed:
        ``TrajectoryEvaluator._format_trajectory`` in the evaluator package),
        so recovery plumbing recorded here is fully honest for audit/debugging
        but invisible to the redundancy-avoidance check that used to penalize
        it. Call this instead of ``log_step`` for anything that is not the
        final, successful, judge-visible result of a Designer's turn."""
        agent_name = self._identity or agent_name
        taxonomy_action, action_context = _recovery_action(action)
        context = {**action_context, "input_summary": input_summary, "output_summary": output_summary}
        self._record_event(taxonomy_action, "recovery_event", agent=agent_name, **context)
        self.log_action(taxonomy_action, agent=agent_name, **context)

    def log_node_edit(self, op: str, node_id: str, node_type: str) -> None:
        action = TrajectoryAction.NODE_ADD if op == "add" else TrajectoryAction.NODE_UPDATE
        self._record_event(action, "node_edit", node_id=node_id,
                           node_type=node_type)

    def log_llm_call(self, prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
        # Concurrent specialists can each finish a model call at the same
        # moment; += is a read-modify-write and would silently lose counts
        # without this.
        with self._counter_lock:
            self.llm_calls += 1
            self.token_usage["prompt_tokens"] += prompt_tokens
            self.token_usage["completion_tokens"] += completion_tokens
            llm_calls, token_usage = self.llm_calls, dict(self.token_usage)
        self._emit("llm_call", {
            "llm_calls": llm_calls,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "token_usage": token_usage,
        })

    def log_validation_result(self, scope: str, errors: list[str], *, agent: str = "") -> None:
        """Record a schema-validation pass (scope = node type or 'addie_output').

        ``agent`` should be passed explicitly whenever the call happens after
        the owning specialist's ``acting_as`` block has already exited (e.g.
        the final ADDIE-output validation, which runs after the aggregator's
        own block closes) — otherwise this falls back to whoever last set the
        actor, which is stale, not "no one validated this".

        The event keeps scope + count only: the full error strings already
        travel as run-level ``metadata.validation_errors`` in the same artifact, and the
        deep action below keeps them for the ordered record."""
        self._record_event(TrajectoryAction.VALIDATE, "validation_event", agent=agent,
                           scope=scope, error_count=len(errors))
        self.log_action(TrajectoryAction.VALIDATE, agent=agent, scope=scope,
                        error_count=len(errors), errors=list(errors))

    def log_violations_result(self, violations: list[dict], *, agent: str = "") -> int:
        """Record one pedagogical-verification round.

        ``agent`` should be passed explicitly by callers whose self-validation
        loop runs after the specialist's own ``acting_as`` block has exited
        (a stage's trailing self-validation loop is exactly this case) —
        otherwise this falls back to whoever last set the actor, not the
        specialist actually being validated.

        The event keeps counts + the per-type breakdown; the full violation
        dicts live in the deep action log (per round), in the run's ledger
        (``core/memory.py``, which is what ``result["violations"]`` serves) and
        — for the residual set the paper reports — in
        ``metadata.audit.violations``.

        Returns the round number it recorded."""
        by_type: dict[str, int] = {}
        for violation in violations:
            vtype = violation.get("type", violation.get("violation_type", "unknown"))
            by_type[vtype] = by_type.get(vtype, 0) + 1
        round_number = len(self.check_events) + 1
        # The KEYS as well as the counts. Without them a reader can only sum
        # `by_type` across rounds, which counts one violation once per round it
        # survived: a measured run reported 28 for a set of 7.
        self._record_event(TrajectoryAction.CHECK, "check_event", agent=agent, round=round_number,
                           violation_count=len(violations), by_type=by_type,
                           keys=sorted({str(v.get("key") or f"{v.get('type', '?')}|{v.get('node_id', '?')}")
                                        for v in violations}))
        self.log_action(TrajectoryAction.CHECK, agent=agent, round=round_number, violation_count=len(violations),
                        by_type=by_type, violations=list(violations))
        # The round number is RETURNED rather than recomputed by the caller:
        # the ledger stamps every finding with it, and two places deriving
        # "which round is this" is how the two come to disagree.
        return round_number

    def log_convergence(self, family: str, keys: list[str], types: list[str], *,
                        round_number: int, agent: str = "") -> None:
        """The pass stopped: it looked, repaired nothing, and would have found
        the same thing again.

        Checks are pure functions of state and nothing else writes state
        between the repair and the next look, so "no repair event fired" is a
        PROOF that the next collect is identical — which is why the loop can
        stop before paying for it."""
        self._record_event(TrajectoryAction.CONVERGE, "converge_event", agent=agent,
                           family=family, round=round_number,
                           unfixable=len(keys), violation_types=sorted(types))
        self.log_action(TrajectoryAction.CONVERGE, agent=agent, family=family,
                        round=round_number, unfixable=len(keys),
                        violation_types=sorted(types), keys=sorted(keys))

    def log_repair_event(
        self,
        agent: str,
        violation_type: str,
        node_id: str,
        repaired_fields: list[str],
        *,
        rule: str = "",
        input_summary: str = "",
        output_summary: str = "",
    ) -> None:
        """ONE record per repair — structured fields plus, when the caller has
        them, the repair routine's own narrative (``rule``/summaries). Never
        pair this with a separate recovery event for the same repair: that was
        the pre-2026-08-27 shape and it double-counted every repair once both
        records landed in the unified event log."""
        # Same identity override as log_step/log_recovery_event: in the
        # ablation's `single` arm every repair belongs to the one agent,
        # whatever module the repair routine lives in.
        agent = self._identity or agent
        detail = {
            key: value
            for key, value in (("rule", rule), ("input_summary", input_summary),
                               ("output_summary", output_summary))
            if value
        }
        self._record_event(TrajectoryAction.REPAIR, "repair_event", agent=agent,
                           violation_type=violation_type, node_id=node_id,
                           repaired_fields=list(repaired_fields or []), **detail)
        self.log_action(TrajectoryAction.REPAIR, agent=agent, violation_type=violation_type,
                        node_id=node_id, repaired_fields=list(repaired_fields or []), **detail)

    def log_doc_write(self, key: str, document: object, *, agent: str = "") -> None:
        """One prose-blackboard document write — the prose counterpart of
        ``log_node_edit``. Counts only: the documents themselves ship in
        ``result["prose"]``; this records WHEN one was written and BY WHOM."""
        size = len(document) if isinstance(document, (list, dict)) else 0
        self._record_event(
            TrajectoryAction.DOC_WRITE, "doc_write_event", agent=agent,
            key=key, field_count=size)
        # Mirrored into the deep action log for the same reason ``log_dev_plan``
        # is: that log is what the live consumer streams and what the story view
        # replays, so an artifact recorded only in ``events`` is one the run
        # cannot be watched producing.
        self.log_action(TrajectoryAction.DOC_WRITE, agent=agent,
                        key=key, field_count=size)

    def log_reconcile_result(self, family: str, violations: list, *, agent: str = "") -> None:
        """One routed batch in the post-stage reconciliation pass.

        Recorded in ``events``, not only in the deep action log: routing is the
        decomposition axis expressed at repair time, so a results dir has to
        say which family a residual violation went to and how many went with
        it. Counts and types only — the violations themselves are already in
        ``metadata.audit``; this is a pointer, not a second copy."""
        context = {
            "family": family,
            "routed": len(violations),
            "violation_types": sorted({v.violation_type for v in violations}),
        }
        self._record_event(
            TrajectoryAction.RECONCILE, "reconcile_event", agent=agent, **context)
        self.log_action(TrajectoryAction.RECONCILE, agent=agent, **context)

    def log_audit_result(self, residual, *, agent: str = "") -> None:
        """The residual whole-graph audit (``GraphAuditor.audit()``), run once
        at aggregation over the final settled graph. Duck-typed on
        ``GraphAuditResult`` rather than importing it — ``core/alignment_graph``
        is a higher layer than this module.

        Before this, ``metadata.audit`` was the ONLY record of it: the ~300
        graph reads that compute it show up in the deep action log (correctly
        attributed to ``WORKFLOW_ORCHESTRATOR`` since 2026-08-27), but nothing
        in ``trajectory`` said what they found — a run with 5 uncovered
        relations and one with zero looked identical unless you went and read
        ``metadata.audit`` separately. Counts and the list of gapped relation
        ids only: the full per-relation coverage detail (labels, mechanism,
        uncovered node ids) stays exclusively in ``metadata.audit`` — this is
        a summary pointer to it, not a second copy."""
        gapped = sorted(
            relation_id for relation_id, info in residual.relation_coverage.items()
            if info["uncovered"]
        )
        self._record_event(
            TrajectoryAction.AUDIT, "audit_event", agent=agent,
            missing_node_type_count=len(residual.missing_node_types),
            schema_violation_count=len(residual.schema_violations),
            objective_count=residual.objective_count,
            unmeasured_count=len(residual.unmeasured_objectives),
            unsupported_count=len(residual.unsupported_objectives),
            residual_gap_count=residual.residual_gap_count,
            gapped_relations=gapped,
            ready_to_aggregate=residual.ready_to_aggregate,
        )
        self.log_action(
            TrajectoryAction.AUDIT, agent=agent,
            missing_node_type_count=len(residual.missing_node_types),
            schema_violation_count=len(residual.schema_violations),
            objective_count=residual.objective_count,
            unmeasured_count=len(residual.unmeasured_objectives),
            unsupported_count=len(residual.unsupported_objectives),
            residual_gap_count=residual.residual_gap_count,
            gapped_relations=gapped,
            ready_to_aggregate=residual.ready_to_aggregate,
        )

    def log_dev_plan(
        self,
        family: str,
        *,
        set_count: int,
        pair_count: int,
        sets: list[dict],
        source: str,
        fallback_used: bool,
        dropped_refs: int,
        appended_sets: int,
        oversized_splits: int = 0,
        dropped_pairs: int = 0,
        duplicate_pairs: int = 0,
        agent: str = "",
    ) -> None:
        """Record one family's dev-plan normalization result: how a fan-out's
        work was grouped, and whether the LLM's own proposal (if any) was
        usable. Orchestration metadata — never a graph node, store document,
        or ADDIE output section (see ``core/dev_plans.py``) — so the
        trajectory is its only record. ``agent`` is the acting family's own
        identity (a Designer, or ``SingleDesignerAgent``), not
        ``WORKFLOW_ORCHESTRATOR``: it answers "who fixed the work list", the
        same question every other family action answers. ``sets`` is a
        compact summary (id + objectives/categories per set) the caller
        caps; full WorkSet payloads are not logged here.

        ``oversized_splits`` is how many of the planner's own sets the harness
        had to cut because they were too large to answer. The planner is told
        the budget and asked to scope its sets itself; this is the only number
        that separates a plan doing that job from one the backstop is
        carrying.

        ``dropped_pairs`` counts obligations the plan named that its own
        coverage targets never promised (discarded), ``duplicate_pairs`` the
        ones it named in two sets (kept once). Both were computed and never
        logged until 2026-09-05, so a plan silently reshaped by the harness
        read as ``source: llm`` with nothing dropped."""
        self._record_event(
            TrajectoryAction.DEV_PLAN, "dev_plan_event", agent=agent,
            family=family, set_count=set_count, pair_count=pair_count, sets=sets,
            source=source, fallback_used=fallback_used, dropped_refs=dropped_refs,
            dropped_pairs=dropped_pairs, duplicate_pairs=duplicate_pairs,
            appended_sets=appended_sets, oversized_splits=oversized_splits,
        )
        self.log_action(
            TrajectoryAction.DEV_PLAN, agent=agent,
            family=family, set_count=set_count, pair_count=pair_count, sets=sets,
            source=source, fallback_used=fallback_used, dropped_refs=dropped_refs,
            dropped_pairs=dropped_pairs, duplicate_pairs=duplicate_pairs,
            appended_sets=appended_sets, oversized_splits=oversized_splits,
        )

    def log_retrieval_event(
        self,
        agent: str,
        task_name: str,
        decision: str,
        *,
        strategy: str = "",
        retrieval_agents: list[str] | None = None,
        executions: list[dict] | None = None,
        snippets: int = 0,
    ) -> None:
        """One on-demand retrieval decision by a specialist (agentic RAG).

        ``decision`` is "retrieve" / "skip" / "decision_error"; ``executions``
        carries the per-retrieval-agent sandbox events (status, tool_calls).
        """
        self._record_event(TrajectoryAction.RETRIEVAL, "retrieval_event", agent=agent,
                           task_name=task_name, decision=decision, strategy=strategy,
                           retrieval_agents=list(retrieval_agents or []),
                           executions=list(executions or []), snippets=snippets)
        self.log_action(TrajectoryAction.RETRIEVAL, agent=agent, task_name=task_name, decision=decision,
                        strategy=strategy, snippet_count=snippets,
                        retrieval_agents=list(retrieval_agents or []))
        # One action per corpus consulted, not just the decision. Retrieval
        # adapters are per-source by nature, so this is where a new one shows up
        # without any further plumbing: whatever the sandbox puts in an
        # execution record travels through unchanged.
        for execution in executions or []:
            self.log_action(
                TrajectoryAction.RETRIEVAL_QUERY,
                agent=agent,
                task_name=task_name,
                retrieval_agent=execution.get("agent", ""),
                status=execution.get("status", ""),
                tool_calls=execution.get("tool_calls", 0),
                detail=execution.get("detail", ""),
            )

    def summary_metrics(self, residual_violation_count: int) -> dict:
        """Aggregate structured events into headline metrics for metadata.

        ``repair_success_rate`` compares the peak check violation count with
        the residual count after all repair rounds, so an evaluator can read it
        directly without replaying the trajectory.
        """
        peak_violations = max(
            (event["context"]["violation_count"] for event in self.check_events), default=0
        )
        repaired = max(peak_violations - residual_violation_count, 0)
        repair_success_rate = (repaired / peak_violations) if peak_violations else None
        return {
            "repair_events": len(self.repair_events),
            "repair_success_rate": repair_success_rate,
            "validation_error_count": sum(
                event["context"]["error_count"] for event in self.validation_events
            ),
            "check_rounds": len(self.check_events),
            "peak_violation_count": peak_violations,
            "residual_violation_count": residual_violation_count,
        }

    def finalize(self) -> dict:
        self.latency_ms = (time.time() - self._start) * 1000
        return self.to_dict()

    def to_dict(self) -> dict:
        # The judge trio + the unified event log, nothing else: token/latency
        # accounting is operational metadata and travels in ``metadata`` (where
        # the benchmark's uniform accounter overwrites it anyway).
        return {
            "tool_calls": self.tool_calls,
            "reasoning_steps": self.reasoning_steps,
            "agent_interactions": self.agent_interactions,
            "events": self.events,
        }

    def to_dict_deep(self) -> dict:
        """The action log, plus enough summary to read it at a glance.

        Deliberately a separate document from ``to_dict``: that one is the
        artifact the benchmark and the evaluator parse, and its shape is a
        contract. This one is free to describe the run properly.
        """
        by_action = Counter(entry["action"] for entry in self.actions)
        by_agent: dict[str, Counter] = {}
        for entry in self.actions:
            by_agent.setdefault(entry["agent"] or "(none)", Counter())[entry["action"]] += 1

        return {
            "format": "deep",
            # A copy: the returned document is a snapshot, and anything appended
            # afterwards would otherwise grow the list while the counts beside it
            # stayed put.
            "actions": list(self.actions),
            "summary": {
                "action_count": len(self.actions),
                "by_action": dict(by_action),
                "by_agent": {agent: dict(actions) for agent, actions in by_agent.items()},
                "agents": [agent for agent in dict.fromkeys(x["agent"] for x in self.actions) if agent],
                "latency_ms": self.latency_ms,
            },
        }
