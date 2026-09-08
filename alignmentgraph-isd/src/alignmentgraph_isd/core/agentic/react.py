"""The single arm: ONE ReAct loop that runs the whole design brief.

WHY THIS IS SEPARATE FROM ``ToolLoop``. Until 2026-09-01 the ``single`` arm was
seven ``ToolLoop``s driven by a ``for step in STEPS`` in ``run.py``, sharing one
message list. The harness still decided when a stage was finished and what came
next — in BOTH arms — so "single agent" named a context-sharing trick, not an
agent. Here the agent decides: it is given the workflow, the schemas and the
rules, and it chooses what to work on, in what order, and when it is done.

``ToolLoop`` stays exactly as it is, for ``multi`` and its Developers. Every
guard that was paid for in measured 2B failures is shared as module-level
functions rather than copied: ``coerce_args`` and ``parse_tool_call_markup`` at
the transport boundary, ``protocol_leak_errors`` on the artifact,
``message_size``/``trim_history`` on the transcript.

WHAT THE AGENT IS GIVEN AND WHAT IT DECIDES:

  given    — the seven ADDIE stages in order, each stage's schema and rules,
             the scenario, the read tools, and a ``submit_<stage>`` for every
             stage not yet complete;
  decides  — which stage to work on next, how much to read first, how many
             items each artifact needs, and whether to write a family in one
             submit or several.

That last one matters and is why submits are ADDITIVE: a family of items has to
fit under an 8192-token completion, and the only way to produce more than that
is across several calls. The rule is in the prompt as well as in the tools —
an affordance the agent is not told about is not an option it has, and output
lost for want of it would be our design failing rather than the agent choosing.
"""
from __future__ import annotations

import copy
import json

from ..brief import _format_design_brief
from .. import dev_plans
from ..memory import Memory, new_agent_run_id
from ..trajectory import WORKFLOW_ORCHESTRATOR
from . import budget, fanout, tools
from .loop import (
    INVALID_TURN_NUDGE,
    brief_stages,
    respec,
    STAGE_BRIEF_HEADER,
    stage_brief_block,
    THINKING_ONLY_NUDGE,
    _merge_specs,
    compact,
    ToolLoop,
    _WORKFLOW_OVERVIEW,
    _repair_request,
    emit_context,
    history_budget,
    AgenticLLM,
    _arg_shape,
    _spec_parameters,
    message_size,
    protocol_leak_errors,
    forget_compacted_calls,
    trim_history,
)
from .specialists import (
    SINGLE_IDENTITY, SINGLE_PERSONA, STEPS, missing_parts, step_done,
)
from .tools import unwrap_section

#: Turn ceiling for the whole run. Deliberately NON-BINDING: `multi` spends a
#: number of turns that is a function of how many work sets it planned, which is
#: endogenous, so no constant makes the two arms "equal". What can be checked is
#: that the budget did not CUT either arm — `via_budget_exhaustion` is reported
#: for both, and a difference in outcome cannot be blamed on the ceiling while
#: it reads zero.
MAX_TURNS = budget.STAGE_MAX_TURNS * len(STEPS) * budget.SINGLE_ARM_TURN_FACTOR

_PROTOCOL = """\
You do this work by CALLING TOOLS. Every turn is a tool call — never prose.

The stages are listed above in the order they must be done. YOU decide which to
work on next, how much to read first, and when each one is finished.

Three rules that matter:
- The stage you are on is stated in a turn of its own, with its schema and its
  rules. The next stage arrives the same way when this one is done.
- A submit_<stage> tool appears only while that stage is still incomplete. When
  a stage's tool disappears, that stage is done. When none are left, so are you.
- A submit ADDS to what that stage already holds; it does not replace it. A
  stage needing many items is meant to be submitted across SEVERAL calls, a
  handful at a time. One call cannot hold them all — it will be cut off.

Tool names are protocol, never content: never mention them in what you write.

Tools available:
{menu}

You have {max_turns} turns in total; each tool call costs one."""


class ReactLoop:
    """One agent, one context, the whole brief."""

    MAX_TURNS = MAX_TURNS
    #: Held in :mod:`budget` with every other ceiling, ToolLoop's included:
    #: this one and ``SUBMIT_BUDGET`` are the pair a reader compares.
    SUBMIT_CAP = budget.SUBMIT_CAP

    def __init__(self, config, state, trajectory, design_brief) -> None:
        self.config = config
        # `state` may be the run's Memory or a bare substrate. Memory is what
        # production passes — it is where this loop's transcript is kept and
        # where its Designer's plans live — while a caller that only has a
        # graph (a test, a one-off) gets one wrapped around it. `self.state`
        # stays the substrate, because that is what every check, commit and
        # view already takes.
        self.memory = Memory.of(state)
        self.state = self.memory.state
        self.trajectory = trajectory
        self.design_brief = design_brief
        self.identity = SINGLE_IDENTITY
        self.agent_run_id = new_agent_run_id()
        #: What compaction has taken out of the live context — see
        #: ToolLoop.compacted. This arm carries ONE conversation for the
        #: whole brief, so it is the arm that actually hits the ceiling.
        self.compacted: list = []
        self.llm = AgenticLLM(config, trajectory, SINGLE_IDENTITY)
        #: The compaction HOOK's model caller, never this agent's. Compaction
        #: is something the harness does over the agent's head — it did not
        #: choose it and is not shown that conversation — so the call is
        #: attributed to the orchestrator and publishes no context. Reusing
        #: `self.llm` would book the orchestrator's completion in the agent's
        #: column and leave an `llm_call` under an agent name with no context
        #: to account for it, which is the shape
        #: `test_every_published_context_belongs_to_a_tool_loop` exists to
        #: forbid.
        self._summariser = AgenticLLM(config, trajectory, WORKFLOW_ORCHESTRATOR)
        self.messages: list = []
        self.stats: dict = {
            "turns_used": 0, "submits_rejected": 0, "repeated_calls": 0,
            "history_dropped": 0, "reads": 0, "context_len": 0, "batched_calls": 0,
            # See ToolLoop: how often the window filled. This is the arm
            # that fills it.
            "compactions": 0,
            # ...and how many of those folds the model actually delivered.
            # `compactions - compaction_summaries` is the hook's failure rate
            # on this model, which is the number that says whether the
            # completion it spends buys anything.
            "compaction_summaries": 0,
            "markup_recovered": 0, "args_salvaged": 0, "truncated_turns": 0,
            "dropped_args": 0, "repair_turns": 0, "thinking_only": 0,
            "via_budget_exhaustion": False,
            # The two numbers that separate "worked out of order" from "never
            # split the work" — different failures with identical output.
            "stage_order": [], "submits_per_stage": {},
        }
        #: Batch counter, so each additive submit's items get a distinct
        #: `plan_set` tag and `remap_and_tag` renames rather than overwrites
        #: when two batches propose the same id.
        self._batch = 0
        #: Rejected submits per stage. Reported only through the cap: what a
        #: stage COMMITTED stays the `submits_per_stage` series the axis reads,
        #: and folding failed attempts into it would make a stuck stage look
        #: like a productive one.
        self._rejected: dict[str, int] = {}
        #: Every tool schema bound during the run, first seen first. ACCUMULATED
        #: because this arm's binding SHRINKS: `react_specs` offers a
        #: `submit_<stage>` only for a stage still open, so by the end there are
        #: none — and publishing just the live binding made the context claim
        #: the agent never had a way to submit anything.
        self._specs: list[dict] = []
        #: Repair rounds spent per stage, so one stage cannot absorb them all.
        self._repairs: dict[str, int] = {}

    def _submit_attempts(self, stage: str) -> int:
        """Turns this stage has spent on submitting, accepted or not."""
        return (self.stats["submits_per_stage"].get(stage, 0)
                + self._rejected.get(stage, 0))

    @property
    def _history_budget(self) -> int:
        """Same derivation the multi arm uses — one budget for both arms, and
        re-read each turn so it tracks the measured token ratio."""
        return history_budget(self.config)

    @property
    def graph_mode(self) -> bool:
        return hasattr(self.state, "element_nodes")

    def _done(self) -> frozenset:
        return frozenset(s.name for s in STEPS if step_done(s, self.state))

    def _system_prompt(self) -> str:
        """Persona, the stage list, and the scenario. NOT every stage's schema.

        MEASURED FAILURE (run single_20260901_151738): with all six stages'
        schemas inlined the system turn was 23,668 characters against a 24,000
        history budget, so ``trim_history`` kept the system turn and dropped
        everything else — 189 drops in one run. The agent had no working memory
        at all: each turn it saw the whole specification and almost nothing of
        what it had just done, which is why it repeated reads 26-42 times, had
        21 submits rejected, and finished 96 turns with ZERO stages complete.

        A schema is needed when a stage is about to be written, not for the
        whole run. It was fetched (``stage_brief``) from 2026-09-03 to
        2026-09-06 and is now PUSHED one stage at a time, as each comes up —
        the same block, the same size, arriving when it is needed instead of
        being asked for. All six at once is what this docstring rules out and
        remains ruled out: measured, they are 27,193 characters."""
        stages = "\n".join(f"  {i}. {step.name} — {step.intro}"
                            for i, step in enumerate(STEPS, start=1))
        return (f"{SINGLE_PERSONA}\n\n{_WORKFLOW_OVERVIEW}\n\n"
                f"The stages, in order:\n{stages}\n\n"
                f"=== SCENARIO ===\n{_format_design_brief(self.design_brief)}")

    def stage_brief(self, name: str) -> str:
        """One stage's task, schema and rules — the same block the multi arm's
        specialist gets, composed here for the one stage that is current.

        Not a tool any more (2026-09-06): the harness pushes it when the stage
        comes up. What that costs this arm is the freedom to jump to a stage
        out of turn, which `react_specs` still allows; what it buys is that the
        contract can never be missing when the stage is being written."""
        step = {s.name: s for s in STEPS}.get(name)
        if step is None:
            return (f"ERROR: no stage named {name!r}. The stages are: "
                    + ", ".join(s.name for s in STEPS))
        block = stage_brief_block(step)
        # A fan-out family's stage block shows only the PLAN's rules, because
        # in the multi arm its items come from Developers who are shown
        # theirs separately. This agent writes both, so it has to see both
        # artifacts' rules — their SHAPE is already in the bound
        # ``submit_<stage>`` tool's own parameters (see ``react_specs``), not
        # restated here as text.
        spec = fanout.SPECS.get(step.name)
        if spec is not None:
            for output in spec.outputs:
                block += (f"\n\nAlso for this stage — {output.schema_key}:\n"
                          f"{output.rules}")
        return block

    def _own_violations(self, step) -> list:
        """The just-finished stage's own violations, structural fixes already
        applied. Identical to the multi arm's — one implementation, so the two
        arms are shown the same thing about the same artifact.

        Pairs the ledger write with a ``check`` trajectory event, attributed to
        the orchestrator like every other check round (see
        ``ToolLoop._own_violations`` in ``loop.py`` for why: without it, a
        violation whose only sighting was here never reaches
        ``expert_review.findings``, only the ledger)."""
        from .run import _serialize
        found = ToolLoop.own_violations(
            self.state, self.design_brief, step, self.trajectory, self.llm)
        if found:
            round_no = self.trajectory.log_violations_result(
                _serialize(found, self.identity), agent=WORKFLOW_ORCHESTRATOR)
            self.memory.observe_violations(
                found, round=round_no,
                phase=step.name, family=step.family, shown_to_agent=True)
        return found

    def _offer_contract(self) -> None:
        """Put the CURRENT stage's contract in front of the agent, if it is not
        already there.

        The current stage is the first not yet done, in the instructed ADDIE
        order — which both arms are given identically
        (``loop._WORKFLOW_OVERVIEW``), so this is the harness restating an order
        the agent was already told, not choosing one for it. What it does take
        away is submitting a stage out of turn without its schema;
        ``react_specs`` still offers every incomplete stage's submit, and the
        contract for one further down arrives when its turn comes.

        Called once before the first model turn and again after each commit, so
        exactly one stage's contract is live at a time. `_compact` releases a
        finished stage's contract the moment its artifact lands, which is what
        keeps that true over a six-stage conversation."""
        live = brief_stages(self.messages)
        for step in STEPS:
            if step.name in self._done_set:
                continue
            if step.name not in live:
                self.messages.append(
                    {"role": "user", "content": self.stage_brief(step.name)})
            return

    def _restore_brief(self, stage: str) -> str | None:
        """The contract to put back when a trim took it, or None.

        Only for a stage still being written. A FINISHED stage's brief is
        released on purpose (`_compact` replaces it with a stub the moment its
        artifact lands), and putting it back would undo that — this arm carries
        one conversation across all six stages, so the spec for work already
        written is exactly what crowds out the work still to do."""
        step = {s.name: s for s in STEPS}.get(stage)
        if step is None or not missing_parts(step, self.state):
            return None
        return self.stage_brief(stage)

    def _respec(self, step) -> str:
        """The stage's schema, re-attached to a rejection when it has fallen out
        of the transcript.

        MEASURED FAILURE (run single_20260901_162455): the graph arm was told
        "assessment_plan.lo_coverage_targets is missing" 15 times and the prose
        arm "needs_analysis.gaps must be a non-empty list" 48 times, each time
        submitting the same broken shape again. ``history_dropped`` was 170 and
        186: ``trim_history`` drops the oldest tool observations first, and the
        ``stage_brief`` answer is exactly that — early and large. So the agent
        was being corrected against a specification it could no longer see.

        Re-attached only when it is actually gone, because it is up to 7,400
        characters and pasting it onto every rejection would push out the very
        transcript it is meant to sit beside.

        ONE implementation, shared with `ToolLoop` since 2026-09-06 — which
        NARROWS the decomposition axis rather than widening it. Only this arm
        had it, so the multi arm was left arguing with a model that could not
        see the spec: that is what run 2b9e911a's implementation stage is. The
        brief differs (this one appends the fan-out output schemas, because
        this agent writes both halves); the rule for when to re-attach it does
        not."""
        return respec(self.messages, step, self.stage_brief(step.name))

    def _docket(self) -> str:
        """The alignment docket — which relations the design still leaves
        uncovered — recomputed where the state changed.

        Pushed, not merely available through ``coverage_gaps``, because the
        multi arm's stage message carries it: leaving it out here would make
        `context_mode` mean something different in each decomposition arm and
        confound the interaction between the two axes. The prose arm has no
        docket to compute, and gets nothing — that IS the axis."""
        if not self.graph_mode:
            return ""
        edges = tuple(dict.fromkeys(r for s in STEPS for r in s.relations))
        docket = tools.alignment_docket(self.state, edges=edges, gaps=edges)
        return f"\n\n{docket}" if docket else ""

    def _validate(self, step, section: dict) -> list[str]:
        """Permissive by design, because submits are ADDITIVE.

        A submit may carry the stage's plan, or a batch of its items, or both —
        the agent decides how to split the work, and rejecting a partial one
        would take that choice away. What is enforced: something must be there,
        whatever is there must be well-formed, and no tool names anywhere. The
        stage is finished when ``step_done`` says the artifacts exist, not when
        one call happens to contain everything."""
        errors = protocol_leak_errors(section)
        spec = fanout.SPECS.get(step.name)
        present = {k: v for k, v in (section or {}).items() if v not in (None, [], {})}
        if not present:
            return errors + ["the submit is empty; send the plan, or a batch of items"]
        # Dispatch keys go through the step's own validator, but only once the
        # submit actually claims to carry them.
        dispatch_keys = [k for k, _t, _r in step.submit_fields]
        if any(k in present for k in dispatch_keys):
            errors += list(step.validate(section))
        if spec is not None:
            # The SAME item rules a Developer's submit is held to
            # (`fanout.output_errors`), because this agent is writing exactly
            # what a Developer would.
            errors += fanout.output_errors(spec, present)
        return errors

    def run(self) -> None:
        """One ReAct loop over every stage, then publish the context it built.

        ONE snapshot for the whole run, where the multi arm publishes one per
        stage: that difference IS the decomposition axis, shown rather than
        described. The tool menu shrinks as stages complete, so the schemas
        reported are the ones in force when the loop ended."""
        try:
            self._run()
        finally:
            self._publish()

    def _publish(self, *, live: bool = False) -> None:
        """Publish this loop's context; ``live`` marks a mid-run snapshot,
        skipped when nobody is watching (see loop.emit_context)."""
        if live and not self.trajectory.is_observed:
            return
        emit_context(
            self.trajectory, agent_run_id=self.agent_run_id, agent=self.identity,
            phase="design", label="design", messages=self.messages,
            specs=self._specs, budget=self._history_budget, config=self.config,
            memory=self.memory, compacted=self.compacted)

    def _run(self) -> None:
        done = self._done()
        if len(done) == len(STEPS):
            return
        specs = tools.react_specs(STEPS, done, graph_mode=self.graph_mode)
        self._specs = _merge_specs(self._specs, specs)
        self.messages = [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user", "content": _PROTOCOL.format(
                menu=_menu(STEPS, done, graph_mode=self.graph_mode),
                max_turns=self.MAX_TURNS) + self._docket()},
        ]
        self._by_name = {s.name: s for s in STEPS}
        self._done_set = done
        self._offer_contract()
        self._live_specs = specs
        self._seen_calls: dict[str, str] = {}   # see loop.forget_compacted_calls
        # Turns spent so far. ONE PER EXECUTED CALL, not per model reply — the
        # same accounting as ToolLoop, or the arms would price a batched reply
        # differently.
        self._turn_no = 0
        #: Turns given back for a call that produced no observation and no
        #: artifact — a repeat, or a reasoning-only reply. `ToolLoop` has had
        #: this since the repeat guard landed and this loop had none, so the
        #: same failure cost the single arm turns the multi arm got back.
        self._refunded = 0
        # Before the first model call, then once per turn: this arm carries ONE
        # conversation for the whole brief, so a context that only appears at
        # the end appears once, at the end of the run.
        self._publish(live=True)

        # Turns spent after the LAST stage landed. What is left to do then is
        # answer repair requests, and the multi arm's stage loop bounds that
        # by its own ceiling (budget.STAGE_MAX_TURNS, repairs included). This arm has
        # no per-stage ceiling, so without a bound of its own an agent that
        # answers a repair request with reads runs to MAX_TURNS — measured on
        # the test fixture once P10/P11 became owned: 131 turns of the same
        # read after every stage was done. Same number as a stage gets, so the
        # arms are held to one allowance.
        closing = 0
        while self._turn_no < self.MAX_TURNS + self._refunded:
            if len(self._done_set) == len(STEPS):
                closing += 1
                if closing > budget.STAGE_MAX_TURNS:
                    self.trajectory.log_recovery_event(
                        self.identity, "repair_window_closed",
                        f"{budget.STAGE_MAX_TURNS} turn(s) after the last stage landed", "")
                    return
            self.messages, dropped = trim_history(self.messages, self._history_budget)
            self.compacted.extend(dropped)
            self.stats["history_dropped"] += len(dropped)
            forget_compacted_calls(self._seen_calls, dropped)
            if dropped:
                # The SAME call the stage loops make. This arm is the one that
                # actually hits the ceiling, and how much more often it does is
                # the decomposition axis showing its own mechanism — counted in
                # `compactions`, not smoothed away.
                self.messages = compact(
                    self.messages, dropped, len(self.compacted),
                    trajectory=self.trajectory, stats=self.stats,
                    restore=self._restore_brief, budget=self._history_budget,
                    llm=self._summariser)
            self._publish(live=True)
            self.stats["context_len"] = max(
                self.stats["context_len"], sum(message_size(m) for m in self.messages))

            turn = self.llm.call_tools(self.messages, self._live_specs)
            self.stats["batched_calls"] += turn.extra_calls
            # Every call the reply carried, in order — see ToolLoop._run.
            queue = [turn, *turn.calls]
            for index, call in enumerate(queue):
                if self._turn_no >= self.MAX_TURNS + self._refunded:
                    self._answer_unexecuted(queue[index:], "the turn budget ran out first")
                    break
                self._turn_no += 1
                self.stats["turns_used"] += 1
                if self._handle_call(call) == "return":
                    self._answer_unexecuted(queue[index + 1:], "the run ended first")
                    return
            else:
                continue
            break

        self.stats["via_budget_exhaustion"] = True
        self.trajectory.log_recovery_event(
            self.identity, "budget_exhausted", f"{len(self._done())}/{len(STEPS)} stages", "")

    def _handle_call(self, turn) -> str:
        """One tool call, judged and answered. ``"return"`` ends the run (every
        stage has landed), ``"continue"`` hands the loop the next call or the
        next model turn."""
        if not turn:
            recovered = (tools.parse_tool_call_markup(turn.text)
                         or tools.parse_tool_call_json(turn.text))
            if recovered is None:
                if turn.thinking_only:
                    self.stats["thinking_only"] += 1
                    if self.stats["thinking_only"] <= ToolLoop.THINKING_ALLOWANCE:
                        self._refunded += 1
                    self._nudge(turn, THINKING_ONLY_NUDGE)
                    return "continue"
                self.trajectory.log_recovery_event(
                    self.identity, "invalid_action", (turn.text or "")[:120], "")
                self._nudge(turn, INVALID_TURN_NUDGE)
                return "continue"
            self.stats["markup_recovered"] += 1
            self.trajectory.log_recovery_event(
                self.identity, "tool_call_markup_recovered", recovered[0],
                (turn.text or "")[:100])
            turn = turn.__class__(name=recovered[0], args=recovered[1],
                                  call_id=turn.call_id, text=turn.text,
                                  message=turn.message)

        salvaged: list[str] = []
        args = tools.coerce_args(
            _spec_parameters(self._live_specs, turn.name), turn.args, salvaged=salvaged)
        self.stats["args_salvaged"] += len(salvaged)
        if turn.truncated and not turn.sibling:
            self.stats["truncated_turns"] += 1

        if turn.name.startswith("submit_"):
            step = self._by_name.get(turn.name[len("submit_"):])
            if step is None:
                self._answer(turn, f"ERROR: no such stage in {turn.name!r}.")
                return "continue"
            # A submit to a stage that already has artifacts is ACCEPTED —
            # that is the agent adding a second batch, which is the whole
            # point of additive submits, and the menu drops a stage when it
            # no longer NEEDS work, not when it may no longer receive any.
            #
            # But it is bounded. MEASURED (run single_20260901_154303): the
            # prose arm submitted `analysis` 61 times, spending its entire
            # budget on one stage. Once the cap is reached the loop stops
            # accepting and says so, because a stage submitted over and over
            # without completing is a disagreement between the validator and
            # the self._done_set-guard, and accepting it forever turns that
            # disagreement into the whole run.
            if self._submit_attempts(step.name) >= self.SUBMIT_CAP:
                self._answer(turn, (
                    f"You have submitted {step.name} {self.SUBMIT_CAP} times and it is still "
                    "incomplete. Leave it and work on another stage; what is missing will be "
                    "repaired for you."))
                return "continue"
            # Drop what cannot be read, THEN judge what is left — see the
            # matching comment in ToolLoop. The two arms must agree on when
            # a submit is acceptable, or the axis measures acceptance
            # policy instead of the context boundary.
            params = _spec_parameters(self._live_specs, turn.name)
            unreadable = tools.shape_bad_keys(params, args)
            for key in unreadable:
                args.pop(key, None)
            section, errors = unwrap_section(
                args, lambda parsed, _s=step: self._validate(_s, parsed))
            if errors and unreadable:
                shape = tools.shape_errors(params, args, unreadable)
                errors = shape + [e for e in errors if e not in shape]
            if errors:
                self.stats["submits_rejected"] += 1
                self._rejected[step.name] = self._rejected.get(step.name, 0) + 1
                self.trajectory.log_recovery_event(
                    self.identity, "submit_rejected",
                    f"{step.name} | raw={_arg_shape(turn.args)} | args={_arg_shape(args)}"
                    + (" | TRUNCATED" if turn.truncated else ""),
                    "; ".join(errors)[:200])
                cut = ("YOUR ANSWER WAS CUT OFF at the length limit, so the arguments "
                       "below never arrived in full. Do not rewrite everything — send a "
                       "SHORTER submit: fewer items, shorter prose, required fields "
                       "first.\n" if turn.truncated else "")
                self._answer(turn, cut + "SUBMIT REJECTED — fix these and submit again:\n- "
                                   + "\n- ".join(errors)
                                   + self._respec(step))
                return "continue"
            if unreadable:
                self.stats["dropped_args"] += len(unreadable)
                self.trajectory.log_recovery_event(
                    self.identity, "dropped_argument", ", ".join(unreadable),
                    "arrived as text where a structure was declared; "
                    "the rest of the submit was valid and was accepted")
            self._commit(step, section)
            # Judge-visible, like the multi arm's `design_<stage>`: the
            # BFCL trajectory score reads `tool_calls`, so a submit that is
            # only a state change makes this arm look like it did nothing.
            # A submit answering a repair request is a different act and is
            # named so — four identical names read as redundancy.
            round_done = self._repairs.get(step.name, 0)
            self.trajectory.log_step(
                self.identity,
                f"design_{step.name}" + (f"_fix{round_done}" if round_done else ""),
                json.dumps(args, ensure_ascii=False)[:200],
                json.dumps(section, ensure_ascii=False)[:200])
            self._compact(turn, step, section)
            self.stats["submits_per_stage"][step.name] = (
                self.stats["submits_per_stage"].get(step.name, 0) + 1)
            if not self.stats["stage_order"] or self.stats["stage_order"][-1] != step.name:
                self.stats["stage_order"].append(step.name)
            self._done_set = self._done()
            self._offer_contract()
            self._live_specs = tools.react_specs(STEPS, self._done_set, graph_mode=self.graph_mode)
            self._specs = _merge_specs(self._specs, self._live_specs)
            # Same in-loop repair the multi arm's stages get. It has to be
            # the same or the axis grows a second variable: one arm would
            # see its own violations and the other would not, and the
            # quality difference would be that rather than the context
            # boundary.
            fixable = (self._own_violations(step)
                       if step.name in self._done_set and self._repairs.get(step.name, 0) < budget.REPAIR_TURNS
                       else [])
            if fixable:
                self._repairs[step.name] = self._repairs.get(step.name, 0) + 1
                self.stats["repair_turns"] += 1
                self._answer(turn, _repair_request(
                    step.name, fixable, self._repairs[step.name], budget.REPAIR_TURNS))
                return "continue"
            self._answer(turn, _committed_note(step, self._done_set, self.state) + self._docket())
            if len(self._done_set) == len(STEPS):
                return "return"
            return "continue"

        call_key = f"{turn.name}:{json.dumps(args, sort_keys=True, default=str)}"
        if call_key in self._seen_calls:
            self.stats["repeated_calls"] += 1
            # Refunded exactly as in `ToolLoop`. It was refunded on ONE side of
            # the decomposition axis and charged on the other, which is a
            # ceiling difference sitting inside the treatment — the same defect
            # the scripted fallback had before it was removed.
            if self.stats["repeated_calls"] <= ToolLoop.REPEAT_ALLOWANCE:
                self._refunded += 1
            self.trajectory.log_recovery_event(
                self.identity, "repeated_tool_call", turn.name, str(args)[:100])
            self._answer(turn, f"You already made this exact {turn.name} call and nothing "
                               "has changed. Use what you have, or work on another stage.")
            return "continue"
        self._seen_calls[call_key] = turn.call_id

        observation = self._read(turn.name, args)
        self.stats["reads"] += 1
        remaining = self.MAX_TURNS + self._refunded - self._turn_no
        if remaining <= 3:
            observation += (f"\n\n[{remaining} turn(s) left. Submit what you have for the "
                            "stages still open.]")
        scope = str(args.get("node_type") or args.get("relation_id")
                    or args.get("key") or "").strip()
        self.trajectory.log_step(
            self.identity, f"tool_{turn.name}" + (f"_{scope}" if scope else ""),
            str(args)[:200], observation[:200])
        self._answer(turn, observation)
        return "continue"

    # ── plumbing ────────────────────────────────────────────────────────────
    def _read(self, name: str, args: dict) -> str:
        executors = tools.executors_for(graph_mode=self.graph_mode)
        executor = executors.get(name)
        if executor is None:
            return f"ERROR: unknown tool {name!r}. Use one of the listed tools."
        # The union scope: this agent is not stage-bound, so a read is allowed
        # anywhere the workflow as a whole allows it.
        scope = tools._ReadScope(
            tuple(t for s in STEPS for t in s.readable_types),
            tuple(r for s in STEPS for r in s.relations),
            tuple(d for s in STEPS for d in s.readable_docs))
        return executor(self.state, scope, args)

    def _commit(self, step, section: dict) -> None:
        """Deposit one submit. ADDITIVE: a second submit for the same stage adds
        to what is there rather than replacing it, which is what lets the agent
        split a large family across calls."""
        section = copy.deepcopy(section)
        spec = fanout.SPECS.get(step.name)
        if self.graph_mode:
            # Element pools are additive by construction (`add_element_node`);
            # section nodes are single documents and a re-submit replaces them.
            step.commit(self.state, self.trajectory, section)
            if spec is not None:
                # The item lists a fan-out family's Developers would have
                # produced in the multi arm. One "set" because this agent chose
                # its own batching — that IS the batching.
                fanout.commit_sets(
                    spec, self.state, self.trajectory,
                    [dev_plans.WorkSet(set_id=f"S{self._batch}", source="agent")],
                    [{"set_id": f"S{self._batch}", **section}])
                self._batch += 1
            return
        before = {key: self.state.get(key) for key in _doc_keys(step)}
        step.commit_prose(self.state, self.trajectory, section)
        if spec is not None:
            fanout.commit_sets(
                spec, self.state, self.trajectory,
                [dev_plans.WorkSet(set_id=f"S{self._batch}", source="agent")],
                [{"set_id": f"S{self._batch}", **section}])
            self._batch += 1
        for key, old in before.items():
            if not isinstance(old, dict):
                continue
            new = self.state.get(key)
            if not isinstance(new, dict):
                continue
            merged = dict(new)
            for field, previous in old.items():
                if isinstance(previous, list) and isinstance(new.get(field), list):
                    merged[field] = previous + new[field]
            if merged != new:
                self.state.put(key, merged)
                self.trajectory.log_doc_write(key, merged)

    def _compact(self, turn, step, section: dict) -> None:
        """Replace a committed submit's payload with a record of what it was.

        MEASURED (run single_20260901_162455): ``context_len`` sat at the 23.9k
        trim ceiling for the whole run and ``history_dropped`` reached 186. Most
        of the transcript was the agent's OWN committed artifacts, carried
        verbatim in their tool-call arguments — roughly 5k each, and the design
        state already holds every one of them, readable with the tools.

        So this is what a single-agent design would really do, and it also makes
        the decomposition axis measure the right thing. The multi arm carries no
        payloads either — it starts each stage fresh — so before this, part of
        the measured gap was simply the single arm re-sending its own JSON. What
        it still accumulates is what it must actually hold in mind: every stage
        instruction, every observation, and a record of everything it has
        produced. That is the burden the axis is about."""
        summary = {}
        for key, value in (section or {}).items():
            if isinstance(value, list):
                ids = [str(i.get("id") or i.get("item_id") or "")
                       for i in value if isinstance(i, dict)]
                summary[key] = (f"{len(value)} committed"
                                + (f": {', '.join(i for i in ids if i)}" if any(ids) else ""))
            else:
                summary[key] = "committed"
        if getattr(turn, "sibling", False):
            # The assistant message is already in the transcript, shared with
            # the call before this one; it is not ours to replace here.
            return
        # Any OTHER call the same message carried keeps its id, so the tool
        # results that answer them still have a call to answer.
        others = [
            {"id": str(c.get("id") or ""), "type": "function",
             "function": {"name": str(c.get("name") or ""),
                          "arguments": json.dumps(c.get("args") or {}, ensure_ascii=False)}}
            for c in (getattr(turn.message, "tool_calls", None) or [])
            if isinstance(c, dict) and str(c.get("id") or "") != turn.call_id
        ]
        compacted = {
            "role": "assistant", "content": "",
            "tool_calls": [{
                "id": turn.call_id or "c", "type": "function",
                "function": {"name": turn.name,
                             "arguments": json.dumps(summary, ensure_ascii=False)}}] + others,
        }
        # `_answer` appends `turn.message`; hand it the compacted one instead.
        turn.message = compacted

        # And the stage's schema, now that the stage has been written from it.
        # These are the largest observations in the transcript (up to 7,400
        # characters); keeping the spec for finished work crowds out the work
        # still to do. If the agent adds another batch and gets it wrong,
        # `_respec` puts the schema back exactly where the error is.
        if missing_parts(step, self.state):
            # The stage is not finished — the agent still has parts to write
            # from this schema, and taking it away mid-artifact is the exact
            # failure `_respec` exists to undo.
            return
        # The contract is a USER turn since 2026-09-06 (it was a `stage_brief`
        # tool result before), so the release matches on the marker and not on
        # the role — and the marker is the only thing that identifies it either
        # way.
        marker = STAGE_BRIEF_HEADER.format(stage=step.name)
        for message in self.messages:
            if not isinstance(message, dict):
                continue
            if marker in str(message.get("content") or ""):
                message["content"] = (
                    f"(the {step.name} schema was here; that stage has been submitted. "
                    "Submit it again to add more — the schema comes back if anything is wrong.)")

    def _answer(self, turn, observation: str) -> None:
        if turn.call_id:
            self._ensure_assistant(turn)
            self.messages.append({"role": "tool", "tool_call_id": turn.call_id,
                                  "name": turn.name, "content": observation})
        else:
            self._nudge(turn, observation)

    def _nudge(self, turn, text: str) -> None:
        self._ensure_assistant(turn)
        self.messages.append({"role": "user", "content": text})

    def _ensure_assistant(self, turn) -> None:
        """The model's message, once per model turn — a sibling call shares it
        with the call before it (see ToolLoop._ensure_assistant)."""
        if getattr(turn, "sibling", False):
            return
        self.messages.append(turn.message if turn.message is not None else {
            "role": "assistant", "content": turn.text or ""})

    def _answer_unexecuted(self, calls: list, why: str) -> None:
        """Close the tool_call ids of calls that will not run (see ToolLoop)."""
        calls = [c for c in calls if c and c.call_id]
        if not calls:
            return
        self._ensure_assistant(calls[0])
        for call in calls:
            self.messages.append({"role": "tool", "tool_call_id": call.call_id,
                                  "name": call.name,
                                  "content": f"[not executed — {why}.]"})
        self.trajectory.log_recovery_event(
            self.identity, "calls_not_executed", ", ".join(c.name for c in calls), why)


def _doc_keys(step) -> tuple[str, ...]:
    """Blackboard documents this step writes — read back so a second submit
    ADDS to them rather than replacing them.

    Taken from the fan-out outputs and the step's primary type, NOT from
    ``step.family``: a family name ("outcome_designer") is not a document key
    ("objective"), so the merge was reading a key nothing ever wrote and every
    additive submit silently replaced its predecessor."""
    keys: list[str] = []
    spec = fanout.SPECS.get(step.name)
    if spec is not None:
        keys += [o.doc_key[0] for o in spec.outputs if o.doc_key[0]]
    if step.primary_type:
        keys.append(str(step.primary_type))
    return tuple(dict.fromkeys(keys))


def _committed_note(step, done: frozenset, state=None) -> str:
    # Name the PARTS a parts-based step is still missing, not just "more":
    # the multi arm's loop says exactly that after each instalment, and an
    # agent told less here would be running a different instruction.
    parts = missing_parts(step, state) if state is not None else ()
    if parts and step.name not in done:
        left = [s.name for s in STEPS if s.name not in done]
        return (f"COMMITTED to {step.name}, which still needs: {', '.join(parts)}. "
                "Submit the next part on its own — do not resend what you have "
                f"already committed. Still open after it: {', '.join(left)}.")
    left = [s.name for s in STEPS if s.name not in done]
    if not left:
        return f"COMMITTED to {step.name}. Every stage is now complete."
    if step.name in done:
        return (f"COMMITTED to {step.name}, which is now complete. "
                f"Still open: {', '.join(left)}.")
    return (f"COMMITTED to {step.name}, which still needs more. "
            f"Submit again to add to it. Still open: {', '.join(left)}.")


def _menu(steps, done: frozenset, *, graph_mode: bool) -> str:
    specs = tools.react_specs(steps, done, graph_mode=graph_mode)
    return "\n".join(f"- {spec['function']['name']} — {spec['function']['description']}"
                     for spec in specs)

