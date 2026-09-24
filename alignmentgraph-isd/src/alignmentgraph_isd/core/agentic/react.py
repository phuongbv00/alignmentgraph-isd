"""The single arm: ONE ReAct loop that runs the whole design brief.

WHY THIS IS SEPARATE FROM ``ToolLoop``. Six stage loops sharing one message
list would leave the harness deciding when a stage is finished and what comes
next, so "single agent" would name a context-sharing trick, not an agent.
Here the agent decides: it is given the workflow, the schemas and the rules,
and it chooses what to work on, in what order, and when it is done.

``ToolLoop`` stays exactly as it is, for ``multi`` and its Developers. Every
guard that was paid for in measured 2B failures is shared as module-level
functions rather than copied: ``coerce_args`` and ``parse_tool_call_markup`` at
the transport boundary, ``protocol_leak_errors`` on the artifact,
``message_size``/``trim_history`` on the transcript.

WHAT THE AGENT IS GIVEN AND WHAT IT DECIDES:

  given    — the six ADDIE stages in order, each stage's schema and rules,
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

from .. import dev_plans
from ..brief import _format_design_brief
from ..memory import Memory, new_agent_run_id
from ..checks import duration_hours, serialize_violations
from ..trajectory import ORCHESTRATOR
from . import alignment_state, budget, fanout, repair_turn, tools
from . import turn as turn_mod
from .client import AgenticLLM
from .compaction import compact
from .protocol import (
    STAGE_BRIEF_HEADER,
    WORKFLOW_OVERVIEW,
    brief_stages,
    empty_stage_stats,
    open_issues_pointer,
    protocol_leak_errors,
    respec,
    stage_brief_block,
    with_progress,
)
from .specialists import (
    ADDITIVE_PROSE_DOC_KEYS,
    SINGLE_IDENTITY,
    SINGLE_PERSONA,
    STEPS,
    missing_parts,
    step_done,
    commit_as_harness,
)
from .tools import merge_specs, spec_parameters
from .transcript import (
    answer_unexecuted,
    append_assistant,
    emit_context,
    forget_compacted_calls,
    history_budget,
    prompt_chars,
    supersede_earlier,
    trim_history,
)

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
{state_rule}
Tool names are protocol, never content: never mention them in what you write.

Tools available:
{menu}

You have {max_turns} turns in total; each tool call costs one."""


#: Graph arm only, where the tool exists; the prose arm's rules are unchanged.
_STATE_RULE = ("- Call read_alignment_state when a stage comes up and again after you submit "
               "to it:\n  it lists the artifacts that stage builds on with their real ids, "
               "what its output\n  must still close, and the open issues in what you "
               "committed.\n")

_STEP_BY_NAME = {s.name: s for s in STEPS}


class ReactLoop:
    """One agent, one context, the whole brief."""

    MAX_TURNS = MAX_TURNS
    #: Held in :mod:`budget` with every other ceiling, the stage loop's
    #: included: this one and ``SUBMIT_BUDGET`` are the pair a reader compares.
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
        self._summariser = AgenticLLM(config, trajectory, ORCHESTRATOR)
        self.messages: list = []
        self.stats: dict = {
            **empty_stage_stats(),
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
        #: Fields of rejected object artifacts, carried into the next attempt
        #: at the same artifact (``turn.carry_over``).
        self._kept: dict = {}
        #: Every tool schema bound during the run, first seen first. ACCUMULATED
        #: because this arm's binding SHRINKS: `react_specs` offers a
        #: `submit_<stage>` only for a stage still open, so by the end there are
        #: none — and publishing just the live binding made the context claim
        #: the agent never had a way to submit anything.
        self._specs: list[dict] = []
        #: Repair rounds spent per stage, so one stage cannot absorb them all.
        self._repairs: dict[str, int] = {}
        #: The stage whose open issues the agent has been pointed at, while
        #: that round is open: `read_alignment_state` stays on it rather than
        #: moving to the next incomplete stage. With it, whether the agent has
        #: read since the pointer, whether that read was this very call, and
        #: the idle calls since (``budget.REPAIR_IDLE_TURNS``).
        self._repairing: str | None = None
        self._read_since_pointer = self._just_read = False
        self._idle = 0
        self._state_view = None
        self._state_reads: dict[str, int] = {}

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
        whole run, so it is PUSHED one stage at a time as each comes up. All
        six at once is what this docstring rules out: measured, they are 27,193
        characters."""
        stages = "\n".join(f"  {i}. {step.name} — {step.intro}"
                            for i, step in enumerate(STEPS, start=1))
        return (f"{SINGLE_PERSONA}\n\n{WORKFLOW_OVERVIEW}\n\n"
                f"The stages, in order:\n{stages}\n\n"
                f"=== SCENARIO ===\n{_format_design_brief(self.design_brief)}")

    def stage_brief(self, name: str) -> str:
        """One stage's task, schema and rules — the same block the multi arm's
        specialist gets, composed here for the one stage that is current.

        Pushed by the harness when the stage comes up, not fetched by a tool.
        What that costs this arm is the freedom to jump to a stage out of
        turn, which `react_specs` still allows; what it buys is that the
        contract can never be missing when the stage is being written."""
        step = _STEP_BY_NAME.get(name)
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
                # The same sentence a Developer reads in its assignment. This
                # agent divides its own batches, so the rule is all it is given.
                note = dev_plans.development_note(
                    self.config.development_mode, str(output.element_type))
                if note:
                    block += f"\n{note}"
        return block

    def _own_violations(self, step) -> list:
        """The just-finished stage's own violations, structural fixes already
        applied. ONE implementation with the multi arm's, so the two arms are
        shown the same thing about the same artifact."""
        return repair_turn.violations_for_agent(
            self.state, self.design_brief, step, trajectory=self.trajectory,
            memory=self.memory, identity=self.identity, phase=step.name)

    def _offer_contract(self) -> None:
        """Put the CURRENT stage's contract in front of the agent, if it is not
        already there.

        The current stage is the first not yet done, in the instructed ADDIE
        order — which both arms are given identically
        (``loop.WORKFLOW_OVERVIEW``), so this is the harness restating an order
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
        step = _STEP_BY_NAME.get(stage)
        if step is None or not missing_parts(step, self.state):
            return None
        return with_progress(self.stage_brief(stage), step, self.state)

    def _respec(self, step) -> str:
        """The stage's schema, re-attached to a rejection when it has fallen out
        of the transcript.

        MEASURED FAILURE (run single_20260901_162455): the graph arm was told
        "assessment_plan.lo_coverage_targets is missing" 15 times and the prose
        arm "needs_analysis.gaps must be a non-empty list" 48 times, each time
        submitting the same broken shape again. ``history_dropped`` was 170 and
        186: ``trim_history`` drops the oldest tool observations first, and the
        stage turn is exactly that — early and large. So the agent was being
        corrected against a specification it could not see.

        Re-attached only when it is actually gone, because it is up to 7,400
        characters and pasting it onto every rejection would push out the very
        transcript it is meant to sit beside.

        ONE implementation, shared with `ToolLoop`: the brief differs (this
        one appends the fan-out output rules, because this agent writes both
        halves); the rule for when to re-attach it does not."""
        return respec(self.messages, step,
                      with_progress(self.stage_brief(step.name), step, self.state))

    def _state_step(self):
        """The stage `read_alignment_state` reports on: the one under repair
        while a repair round is open, else the first not yet complete in the
        instructed order — the same "current stage" `_offer_contract` uses, so
        the contract in the turn and the state in the tool describe one stage.
        The result's first line names it."""
        if self._repairing:
            return _STEP_BY_NAME[self._repairing]
        for step in STEPS:
            if step.name not in self._done_set:
                return step
        return STEPS[-1]

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
        if spec is not None and not fanout.course_modules(self.state):
            # The multi arm never reaches these stages without modules
            # (``core/runner.py`` stops the run after outcomes); this is the
            # same rule for an agent that walks the stages itself.
            return errors + [
                f"{step.name} is divided by the course's modules and there are none yet: "
                "submit course_modules with submit_outcomes first"]
        # Dispatch keys go through the step's own validator, but only once the
        # submit actually claims to carry them.
        dispatch_keys = [k for k, _t, _r in step.submit_fields]
        if any(k in present for k in dispatch_keys):
            errors += list(step.validate(section))
        if spec is not None:
            # The SAME item rules a Developer's submit is held to
            # (`fanout.output_errors`), because this agent is writing exactly
            # what a Developer would.
            errors += fanout.output_errors(
                spec, present, fanout.known_ids(self.state),
                levels=fanout.objective_levels(self.state),
                committed_best=fanout.committed_item_levels(self.state))
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
        self._specs = merge_specs(self._specs, specs)
        self.messages = [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user", "content": _PROTOCOL.format(
                menu=_menu(STEPS, done, graph_mode=self.graph_mode),
                max_turns=self.MAX_TURNS,
                state_rule=_STATE_RULE if self.graph_mode else "")},
        ]
        self._done_set = done
        self._offer_contract()
        self._live_specs = specs
        self._seen_calls: dict[str, turn_mod.SeenCall] = {}   # see forget_compacted_calls
        #: What this run has spent and what it has been given back. The stage
        #: loop keeps one of these too, and the arithmetic is the meter's, not
        #: either loop's — see :class:`turn.TurnMeter`.
        self._meter = turn_mod.TurnMeter(self.stats, max_turns=self.MAX_TURNS)
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
        while not self._meter.exhausted:
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
                self.stats["context_len"], prompt_chars(self.messages))

            turn = self.llm.call_tools(
                self.messages, turn_mod.withhold_reads(self._live_specs, self._meter))
            outcome = turn_mod.spend_queue(
                turn, meter=self._meter, handle=self._dispatch,
                unexecuted=self._answer_unexecuted,
                ended_why="the run ended first")
            if outcome == "done":
                return

        self.stats["via_budget_exhaustion"] = True
        self.trajectory.log_recovery_event(
            self.identity, "budget_exhausted", f"{len(self._done())}/{len(STEPS)} stages", "")

    def _handle_call(self, turn) -> str:
        """One tool call, judged and answered. ``"return"`` ends the run (every
        stage has landed), ``"continue"`` hands the loop the next call or the
        next model turn.

        Two branches: a submit to whichever stage the agent chose, and a read.
        Everything either branch does that the stage loop must do identically —
        recovery, coercion, refunds, the record — is in :mod:`turn`; what is
        left here is this arm's own policy, which is one conversation across
        six stages and a per-stage submit cap."""
        if not turn:
            recovered = turn_mod.recover_call(
                turn, stats=self.stats, trajectory=self.trajectory,
                identity=self.identity)
            if not recovered:
                self._nudge(turn, turn_mod.nudge_for(
                    turn, trajectory=self.trajectory, identity=self.identity))
                return "continue"
            turn = recovered

        if turn.name == "submit":
            # A bare `submit` is what every recovery path yields and what a
            # model says once it has stopped reading tool names carefully;
            # `ToolLoop` rescues it too. Here it means the one open stage whose
            # parameters declare the payload's keys — if that is ambiguous the
            # call falls through to the unknown-tool answer.
            turn = turn.__class__(name=_submit_for(self._live_specs, turn.args) or turn.name,
                                  args=turn.args, call_id=turn.call_id, text=turn.text,
                                  message=turn.message, truncated=turn.truncated)

        params = spec_parameters(self._live_specs, turn.name)
        args = turn_mod.coerce(turn, params, stats=self.stats,
                               trajectory=self.trajectory, identity=self.identity)

        if turn.name.startswith("submit_"):
            return self._handle_submit(turn, args, params)
        return self._handle_read(turn, args)

    def _handle_submit(self, turn, args: dict, params: dict) -> str:
        """One artifact offered to whichever stage the agent named."""
        self._meter.acted()
        step = _STEP_BY_NAME.get(turn.name[len("submit_"):])
        if step is None:
            self._answer(turn, f"ERROR: no such stage in {turn.name!r}.")
            return "continue"
        # A submit to a stage that already has artifacts is ACCEPTED —
        # that is the agent adding a second batch, which is the whole
        # point of additive submits, and the menu drops a stage when it
        # stops NEEDING work, not when it may stop receiving any.
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
        args, carried = turn_mod.carry_over(self._kept, args)
        turn_mod.note_carried(carried, trajectory=self.trajectory, identity=self.identity)
        section, errors, unreadable = turn_mod.judge_submit(
            params, args, lambda parsed, _s=step: self._validate(_s, parsed))
        if errors:
            self._rejected[step.name] = self._rejected.get(step.name, 0) + 1
            turn_mod.note_submit_rejected(
                step.name, turn, args, errors, stats=self.stats,
                trajectory=self.trajectory, identity=self.identity)
            cut = ("YOUR ANSWER WAS CUT OFF at the length limit, so the arguments "
                   "below never arrived in full. Do not rewrite everything — send a "
                   "SHORTER submit: fewer items, shorter prose, required fields "
                   "first.\n" if turn.truncated else "")
            self._answer(turn, cut + "SUBMIT REJECTED — fix these and submit again:\n- "
                               + "\n- ".join(errors)
                               + turn_mod.keep_fields(self._kept, section)
                               + self._respec(step))
            return "continue"
        turn_mod.note_dropped_args(
            unreadable, stats=self.stats, trajectory=self.trajectory,
            identity=self.identity)
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
        if self.graph_mode and not self._state_reads.get(step.name):
            self.stats["blind_submits"] += 1      # see ToolLoop._handle_submit
        self.stats["submits_per_stage"][step.name] = (
            self.stats["submits_per_stage"].get(step.name, 0) + 1)
        if not self.stats["stage_order"] or self.stats["stage_order"][-1] != step.name:
            self.stats["stage_order"].append(step.name)
        self._done_set = self._done()
        self._offer_contract()
        self._live_specs = tools.react_specs(STEPS, self._done_set, graph_mode=self.graph_mode)
        self._specs = merge_specs(self._specs, self._live_specs)
        # Same in-loop repair the multi arm's stages get. It has to be
        # the same or the axis grows a second variable: one arm would
        # see its own violations and the other would not, and the
        # quality difference would be that rather than the context
        # boundary.
        fixable: list = []
        if step.name in self._done_set:
            if self.graph_mode:
                # The free fixes first, then what is left FOR the agent —
                # counted here, shown by `read_alignment_state`.
                repair_turn.fix_structural(
                    self.state, self.design_brief, step, self.trajectory)
                fixable = repair_turn.collect_own(self.state, self.design_brief, step)
            elif self._repairs.get(step.name, 0) < budget.REPAIR_TURNS:
                fixable = self._own_violations(step)
        if fixable and self._repairs.get(step.name, 0) < budget.REPAIR_TURNS:
            self._repairs[step.name] = self._repairs.get(step.name, 0) + 1
            self.stats["repair_turns"] += 1
            self._repairing, self._read_since_pointer, self._idle = step.name, False, 0
            self._answer(turn, (
                open_issues_pointer(step.name, len(fixable), self._repairs[step.name],
                                    budget.REPAIR_TURNS)
                if self.graph_mode else repair_turn.repair_request(
                    step.name, fixable, self._repairs[step.name], budget.REPAIR_TURNS)))
            return "continue"
        if fixable:
            # Rounds spent with issues open: a parameter we chose, and said so.
            self._leave_open(step, fixable, reason="budget")
            self.trajectory.log_recovery_event(
                self.identity, "budget_exhausted",
                f"repair turns spent with {len(fixable)} violation(s) open",
                ", ".join(sorted({v.violation_type for v in fixable}))[:200])
        if self._repairing == step.name:
            self._repairing = None
        self._answer(turn, _committed_note(step, self._done_set, self.state))
        if len(self._done_set) == len(STEPS):
            return "return"
        return "continue"

    def _handle_read(self, turn, args: dict) -> str:
        """One read, through the guard both arms share (``turn.answer_read``)."""
        self._state_view = None
        scope = ""
        if turn.name == tools.STATE_TOOL:
            stage = self._state_step().name
            seen = self._state_reads.get(stage, 0)
            scope = stage if not seen else f"{stage}_r{seen + 1}"
        observation, repeat = turn_mod.answer_read(
            self._seen_calls, turn, args, lambda: self._read(turn.name, args),
            meter=self._meter, stats=self.stats, trajectory=self.trajectory,
            identity=self.identity, pure=turn.name != "retrieve", scope=scope,
            on_answered=self._note_answered,
            next_move=f"call submit_{self._state_step().name} now")
        self._answer(turn, observation)
        if not repeat and turn.name == tools.STATE_TOOL:
            supersede_earlier(self.messages, tools.STATE_TOOL, turn.call_id)
        return "continue"

    def _note_answered(self) -> None:
        """What an ANSWERED state read writes — never a refused repeat."""
        view, self._state_view = self._state_view, None
        if view is None:
            return
        step = self._state_step()
        self.stats["state_reads"] += 1
        self._state_reads[step.name] = self._state_reads.get(step.name, 0) + 1
        self._read_since_pointer = self._just_read = True
        repair_turn.stamp_shown(
            view.shown, view.unshown, trajectory=self.trajectory, memory=self.memory,
            identity=self.identity, phase=step.name, family=step.family)

    def _leave_open(self, step, outstanding: list, *, reason: str) -> None:
        """Write ``reason`` on violations a stage is left with. Observed first:
        ``mark_open_reason`` skips a key the ledger has never seen. NOT shown —
        nothing here was rendered to the agent."""
        if not outstanding:
            return
        round_no = self.trajectory.log_violations_result(
            serialize_violations(outstanding, self.identity), agent=ORCHESTRATOR)
        self.memory.observe_violations(outstanding, round=round_no, phase=step.name,
                                       family=step.family, shown_to_agent=False)
        self.memory.mark_open_reason({v.key for v in outstanding}, reason=reason)

    def _declined(self, why: str) -> None:
        """The agent saw a stage's open issues and moved on without a submit
        (``budget.REPAIR_IDLE_TURNS``, or a submit to another stage). Its
        decision, recorded as one — the same rule and the same event as the
        stage loop's, so neither arm turns a declined repair into a ceiling."""
        step = _STEP_BY_NAME[self._repairing]
        outstanding = repair_turn.collect_own(self.state, self.design_brief, step)
        self._leave_open(step, outstanding, reason="converged")
        self.trajectory.log_recovery_event(
            self.identity, "repair_declined",
            f"{len(outstanding)} issue(s) left open on {step.name}: {why}",
            ", ".join(sorted({v.violation_type for v in outstanding}))[:200])
        self._repairing = None

    def _dispatch(self, turn) -> str:
        """One call through `_handle_call`, then the idle rule of a repair
        round — see ``ToolLoop._dispatch``; one rule, one number."""
        name = turn.name or ""
        if self._repairing and name.startswith("submit_") \
                and name != f"submit_{self._repairing}":
            self._declined("the agent went on to another stage")
        outcome = self._handle_call(turn)
        if outcome != "continue" or not (self._repairing and self._read_since_pointer):
            return outcome
        if self._just_read:
            self._just_read = False
            return outcome
        if name.startswith("submit"):
            return outcome
        self._idle += 1
        if self._idle >= budget.REPAIR_IDLE_TURNS:
            self._declined("no submit after reading them")
            if len(self._done_set) == len(STEPS):
                return "return"
        return outcome

    # ── plumbing ────────────────────────────────────────────────────────────
    def _read(self, name: str, args: dict) -> str:
        if name == tools.STATE_TOOL and self.graph_mode:
            self._state_view = alignment_state.read(
                self.state, self.design_brief, self._state_step(),
                submit_tool=f"submit_{self._state_step().name}")
            return self._state_view.text
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
            commit_as_harness(step.commit, self.state, self.trajectory, section)
        else:
            before = {key: self.state.get(key) for key in _doc_keys(step)}
            step.commit_prose(self.state, self.trajectory, section)
        if step.name == "outcomes" and fanout.course_modules(self.state):
            # The same ceiling the multi arm applies after its outcomes stage:
            # a harness fact about the course, not a choice of either arm.
            fanout.cap_module_minutes(
                self.state, duration_hours(self.design_brief) * 60, self.trajectory)
        if spec is not None:
            # The item lists a fan-out family's Developers would have produced
            # in the multi arm. One "set" because this agent chose its own
            # batching — that IS the batching.
            fanout.commit_sets(
                spec, self.state, self.trajectory,
                [dev_plans.WorkSet(set_id=f"S{self._batch}", source="agent")],
                [{"set_id": f"S{self._batch}", **section}])
            self._batch += 1
        if self.graph_mode:
            return
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
        if getattr(turn, "sibling", False):
            # The assistant message is already in the transcript, shared with
            # the call before this one; it is not ours to replace here.
            return
        summary = {}
        for key, value in (section or {}).items():
            if isinstance(value, list):
                ids = [str(i.get("id") or i.get("item_id") or "")
                       for i in value if isinstance(i, dict)]
                summary[key] = (f"{len(value)} committed"
                                + (f": {', '.join(i for i in ids if i)}" if any(ids) else ""))
            else:
                summary[key] = "committed"
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
        # The release matches on the MARKER, not on the message role: the
        # marker is the only thing that identifies the contract.
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
        """The model's message, once per model turn. Shared with the stage loop
        (:func:`transcript.append_assistant`)."""
        append_assistant(self.messages, turn)

    def _answer_unexecuted(self, calls: list, why: str) -> None:
        """Close the tool_call ids of calls that will not run. Shared with the
        stage loop (:func:`transcript.answer_unexecuted`)."""
        answer_unexecuted(self.messages, calls, why,
                          trajectory=self.trajectory, identity=self.identity)


def _doc_keys(step) -> tuple[str, ...]:
    """Blackboard documents this step writes whose commit REPLACES its key —
    read back so a second submit ADDS to them instead.

    A commit that appends for itself is excluded
    (``specialists.ADDITIVE_PROSE_DOC_KEYS``): appending it here too would
    double it, and its own commit is the better place because it can dedup,
    which this cannot.

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
    # A document whose own commit already appends must NOT be appended again
    # here, or a second submit lands `previous + (previous + new)`. This
    # re-merge exists only for the commits that still replace their key.
    return tuple(k for k in dict.fromkeys(keys)
                 if k not in ADDITIVE_PROSE_DOC_KEYS)


def _committed_note(step, done: frozenset, state) -> str:
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


def _submit_for(specs: list, args) -> str | None:
    """Which open ``submit_<stage>`` a bare ``submit`` meant: the one whose
    parameters declare the payload's keys, when exactly one does."""
    keys = set(args) if isinstance(args, dict) else set()
    if not keys:
        return None
    matches = [name for name in tools.tool_names(specs)
               if name.startswith("submit_")
               and keys <= set(spec_parameters(specs, name).get("properties") or {})]
    return matches[0] if len(matches) == 1 else None


def _menu(steps, done: frozenset, *, graph_mode: bool) -> str:
    specs = tools.react_specs(steps, done, graph_mode=graph_mode)
    return "\n".join(f"- {spec['function']['name']} — {spec['function']['description']}"
                     for spec in specs)

