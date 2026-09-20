"""The act→observe tool loop that runs one agentic step.

This is the MULTI arm's loop and the Developer tier's: one conversation per
stage, opened under that stage's specialist identity and closed when its
artifact commits. The single arm's counterpart is ``react.py``, and the two are
deliberately different shapes rather than one loop with a flag — that
difference is what ``agent_mode`` measures.

What they nevertheless share is factored out and imported, never copied: the
transport and the model call (``client.py``), the transcript and its window
(``transcript.py``), the note that replaces what the window took
(``compaction.py``), and every word a stage is told or a turn is answered with
(``protocol.py``). A guard worded differently on each side of the axis would be
a second variable.

Deterministic scaffolding this loop keeps (the SLM-fit half of the design):

- the alignment state is one read away (``alignment_state.read``, the
  ``read_alignment_state`` tool) and the stage turn names it as the first
  move — an enumerated checklist of what exists and what is missing, which
  small models follow far more reliably than the quantified rules alone;
- every observation is a deterministic render of graph state with fixed caps;
- ``submit`` is validated deterministically; a rejected submit returns the
  exact errors as the next observation;
- hard budgets (``MAX_TURNS``, ``SUBMIT_BUDGET``). A step that exhausts them
  commits the best the MODEL managed and records ``gave_up``; nothing in this
  module writes an artifact on the model's behalf.

Where the agency actually lives: which tools to call, with what arguments,
in what order, and when to submit — none of which is scripted here.
"""
from __future__ import annotations

import copy
import json

from ..brief import _format_design_brief
from ..llm_io import parse_json_response
from ..memory import Memory, new_agent_run_id
from ..rag.planner import RetrievalPlanner
from ..trajectory import ORCHESTRATOR
from ..checks import serialize_violations
from . import alignment_state, budget, repair_turn, tools
from . import turn as turn_mod
from .client import AgenticLLM
from .compaction import compact
from .protocol import (
    WORKFLOW_OVERVIEW,
    empty_stage_stats,
    landed_parts,
    open_issues_pointer,
    protocol_leak_errors,
    respec,
    stage_brief_block,
    still_needed,
    with_progress,
)
from .specialists import AgenticStep, commit_as_harness, missing_parts, parts_of, step_done
from .tools import (
    merge_specs,
    spec_parameters,
    unwrap_section,
)
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
from .turn import ToolTurn

# The protocol block deliberately does NOT end the prompt: an SLM weights the
# last instruction heaviest, and v1 ended with the rulebook's "Output ONLY the
# JSON object" line right after the artifact schema — measured effect on a 2B
# model: it emitted the bare artifact on turn 1 of every step and never called
# a tool. The task block now ends on the action contract instead, and the
# schema is introduced as "what you will submit", not "what to output".
_PROTOCOL = """\
You work on a shared design state that already holds the artifacts earlier steps
produced. Do your work by CALLING TOOLS — never answer with prose or with a bare
artifact; when the artifact is ready, call submit.

Tools available:
{menu}
{grounding}
You have {max_turns} turns; each tool call costs one turn.
Tool names are protocol, never content: never mention them in the artifact you write."""


_GROUNDING = """
The scenario below is NOT the design state. Every id your artifact references must
match an artifact that already exists there, and the read tools are the only place
to see those artifacts' real ids and content — you have not seen them yet.
{first_move}"""

#: Named in the graph arm only, where the tool exists. An instruction and not
#: a push: the state is the agent's to read, but under a forced tool call a
#: small model's first move is otherwise a blind submit.
_FIRST_MOVE = ("Call read_alignment_state first: it lists those artifacts with their real "
               "ids and what your output must close. Call it again after you submit.\n")

# A fan-out work set gets its assignment resolved INTO its turn (`fanout.
# _ASSIGNMENT_IS_COMPLETE`), so the stage grounding above is false for it:
# told it had "not seen" the artifacts, a Developer reads them anyway, and
# reads for ids the assignment names but no read tool serves (a media
# selection, a topic). MEASURED (run 14a6b4c7, content:MU-CM-01): 18 reads,
# 0 submits, gave up on the turn ceiling, then a regen; 89 MaterialDeveloper
# calls for 8 modules against 2 per set for the AssessmentDeveloper, whose
# assignment names nothing it cannot read.
_GROUNDING_SET = """
Your assignment above IS the design state for this set: every artifact it names is
written out there under its real id, and those are the ids to reference. Use the read
tools only for an artifact your assignment does NOT name — never to look up one it
does. An id that is in neither your assignment nor a read result does not exist.
"""


class ToolLoop:
    """Run one :class:`AgenticStep` as an act→observe loop over native tool
    calls, and commit its artifact to the design state.

    ``state`` is the AlignmentGraph in ``context_mode="graph"`` and the
    ProseStore in ``"prose"``; which tools exist follows from that, and nothing
    else about the loop does.

    ``messages`` is how the ``agent_mode`` axis is expressed. Passing ``None``
    (the ``multi`` arm) starts a fresh context for this stage. Passing the list
    a previous stage left behind (the ``single`` arm) continues in it — same
    instructions, same tools, same budgets, one growing context.
    """

    #: Every ceiling this loop spends against. The numbers and the reasoning
    #: that fixed them live in :mod:`budget`, together with the ones `ReactLoop`
    #: and the Developer fan-out hold, because several of them are coupled
    #: across the decomposition axis and a pair that drifts apart is a ceiling
    #: difference sitting inside the treatment. They stay class attributes so a
    #: caller can still override one per instance — ``run.py`` passes a
    #: Developer loop its own ``max_turns`` and ``repair_turns=0``.
    MAX_TURNS = budget.STAGE_MAX_TURNS
    SUBMIT_BUDGET = budget.SUBMIT_BUDGET
    PART_SUBMIT_SLACK = budget.PART_SUBMIT_SLACK
    REPAIR_TURNS = budget.REPAIR_TURNS

    def __init__(self, config, state, trajectory, design_brief, step: AgenticStep,
                 llm: AgenticLLM, *, messages: list | None = None,
                 persona: str | None = None, identity: str | None = None,
                 capture: dict | None = None, max_turns: int | None = None,
                 attempt: int = 1, repair_turns: int = 0,
                 agent_run_id: str | None = None, label: str | None = None,
                 compacted: list | None = None, specs: list | None = None) -> None:
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
        self.step = step
        self.llm = llm
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
        self.persona = persona or step.persona
        #: Which regen attempt this is. A stage that comes back empty is run
        #: again from a FRESH context, so each attempt is a different context
        #: and the viewer must be able to tell them apart — three cards reading
        #: "analysis" with no way to order them says the stage ran three times
        #: without saying why there are three.
        self.attempt = attempt
        #: Turns this loop may spend on its OWN violations. Zero by default and
        #: switched on only for a STAGE loop: the checks are family-level, so a
        #: Developer working one work set would be shown the whole family's
        #: violations, most of them about artifacts it was never assigned.
        self.repair_turns = repair_turns
        #: One identity for the whole run in the ``single`` arm, the stage's
        #: specialist in ``multi`` — the trace has to show one actor or six.
        self.identity = identity or step.identity
        #: Where the committed section is handed back, for a caller that needs
        #: the payload rather than the side effect — the fan-out driver, which
        #: remaps and commits a whole family's sets together.
        self.capture = capture if capture is not None else {}
        #: Whether this stage has already spent its one turn asking for
        #: the optional artifacts it has not been given.
        self._nudged = False
        #: This conversation's id, and the name it is published under. Both are
        #: inherited when a loop CONTINUES someone else's message list — the
        #: replan round is that case (run.py) — because a conversation that
        #: gains turns under a new step name is still one conversation, and
        #: publishing it under a second id splits it into two rows of which the
        #: later contains the earlier.
        self.agent_run_id = agent_run_id or new_agent_run_id()
        self.label = label or step.name
        #: Messages compaction has taken OUT of the live context, oldest first.
        #: Kept rather than discarded because the Context tab answers "what was
        #: this agent shown", and a trimmed transcript answers that for the
        #: last call only — everything the earlier calls saw would be gone with
        #: no trace but a counter. They are published marked as compacted and
        #: are not counted toward the window meter, which measures what is
        #: actually being sent.
        self.compacted: list = compacted if compacted is not None else []
        #: Every tool schema bound during this CONVERSATION, first seen first,
        #: kept so the context snapshot can report them: under native tool
        #: calling they are half of what the model saw, and a context view
        #: without them shows half the context. Inherited, like the message
        #: list, by a loop that continues one.
        self._specs: list = list(specs or [])
        #: Per-instance so a Developer can be given a smaller budget than the
        #: stage that dispatched it — its job is smaller, and the class-level
        #: default stays what a stage gets.
        if max_turns is not None:
            self.MAX_TURNS = max_turns
        #: Carried out for the caller: the single arm hands this to the next
        #: stage, the multi arm throws it away.
        self.messages: list = list(messages) if messages else []
        #: Per-stage instrumentation, read by ``MetaAgent.run`` into
        #: ``metadata.autonomy`` — see ``empty_stage_stats`` for the keys.
        self.stats: dict = empty_stage_stats()
        #: ``node_type -> heading`` for artifact pools the assignment already
        #: renders in full. Empty for a stage agent, which reads real state.
        self._resolved_labels: dict[str, str] = dict(
            getattr(step, "resolved_labels", ()) or {})
        self._assignment_ids: dict[str, str] = dict(
            getattr(step, "assignment_ids", ()) or {})
        self._assignment_hit: tuple | None = None
        self._state_view = None
        #: A repair round is open / the agent has read its issues since the
        #: pointer / that read was this very call / idle calls since.
        self._repairing = self._read_since_pointer = self._just_read = False
        self._idle = 0
        self._submit_attempts: dict[str, int] = {}

    @property
    def graph_mode(self) -> bool:
        return hasattr(self.state, "element_nodes")

    def _validate(self, section: dict) -> list[str]:
        """The step's own deterministic checks, plus the transport gate that
        catches a model echoing a tool name into the artifact — a property of
        the TRANSPORT rather than of any one artifact's contract, so it is
        composed here and is the same for every step. A field the artifact
        does not declare is NOT a fault: it is kept (``artifact_schemas._obj``)."""
        return list(self.step.validate(section)) + protocol_leak_errors(section)

    # ── prompt assembly ─────────────────────────────────────────────────────
    def _retrieval_available(self) -> bool:
        return RetrievalPlanner(self.config).enabled()

    def _system_prompt(self) -> str:
        """Persona + the instructed stage order + the scenario.

        The scenario sits HERE, not in each stage turn, for two reasons that
        pull the same way. It is byte-identical for all six stages, so a
        per-stage copy is duplication: measured before this change, the single
        arm's carried transcript was one system turn plus N copies of the stage
        boilerplate — the axis was reading how many times we re-sent the
        instructions, not whether the agent carries its own work. And the
        system turn is the one thing ``trim_history`` never drops, so the brief
        cannot fall out of the window mid-run in either arm."""
        return (f"{self.persona}\n\n{WORKFLOW_OVERVIEW}\n\n"
                f"=== SCENARIO ===\n{_format_design_brief(self.design_brief)}")

    def _stage_message(self, retrieval_available: bool) -> str:
        """Everything the model needs for THIS stage, as one user turn.

        It lives in a user turn rather than the system prompt so that the two
        arms differ in exactly one thing. The single arm cannot rewrite its
        system prompt each stage without discarding the history that is the
        whole point of the axis; putting the stage here means both arms send
        byte-identical stage instructions and only the surrounding context
        differs."""
        readable = self.step.readable_types if self.graph_mode else self.step.readable_docs
        protocol_block = _PROTOCOL.format(
            menu=tools.tool_menu(self.step, retrieval_available=retrieval_available,
                                 graph_mode=self.graph_mode),
            max_turns=self.MAX_TURNS,
            grounding=((_GROUNDING.format(first_move=(
                            _FIRST_MOVE if self.graph_mode and self.step.state_tool else ""))
                        if self.step.commits_to_state else _GROUNDING_SET)
                       if readable else ""),
        )
        # The stage marker deliberately does NOT use the "=== HEADER ===" form:
        # that form means "injected prior-artifact context" everywhere else in
        # the package (the scenario and a Developer's assignment use it, and readers — the
        # test fixture included — strip on it). A stage boundary is neither.
        # The WHOLE task block in the stage turn, PUSHED rather than fetched
        # by a tool: fetched, the contract could be compacted away with
        # nothing to put it back (run 2b9e911a); pushed, `compact`'s
        # `restore` re-attaches it.
        parts = [stage_brief_block(self.step), protocol_block]
        resuming = still_needed(self.step, self.state)
        if resuming:
            parts.append(resuming)
        return "\n\n".join(parts)

    # ── the loop ────────────────────────────────────────────────────────────
    def run(self) -> None:
        """Run the step, and publish the context it built when it ends.

        The snapshot is taken in a ``finally`` because a step that gave up is
        the one whose context most needs reading: what the agent was shown is
        the first question about why it could not answer."""
        try:
            self._run()
        finally:
            self._publish()

    def _publish(self, *, live: bool = False) -> None:
        """Publish this loop's context. ``live`` marks a mid-run snapshot,
        which is skipped when nobody is watching — see :func:`emit_context`."""
        if live and not self.trajectory.is_observed:
            return
        emit_context(
            self.trajectory, agent_run_id=self.agent_run_id, agent=self.identity,
            phase=self.label, label=self.label, messages=self.messages,
            specs=self._specs, attempt=self.attempt,
            budget=self._history_budget, config=self.config, memory=self.memory,
            compacted=self.compacted)

    @property
    def _history_budget(self) -> int:
        return history_budget(self.config)

    def _run(self) -> None:
        if step_done(self.step, self.state):
            return
        retrieval_available = self._retrieval_available()
        stage_message = self._stage_message(retrieval_available)
        if not self.messages:
            self.messages = [{"role": "system", "content": self._system_prompt()}]
        self.messages.append({"role": "user", "content": stage_message})
        #: Rejected submits so far, PER ARTIFACT: a rejected artifact costs
        #: THAT artifact (`tools.submit_specs`), never the stage — one counter
        #: for the stage let three bad guesses at one `implementation`
        #: artifact abandon the five beside it and trigger a whole-stage regen
        #: (run 24343e4d: 55.6k prompt / 11.7k completion / 122 s).
        self._submit_attempts: dict[str, int] = {}
        self._bind(retrieval_available)
        # Before the first model call: a stage takes minutes, and what the
        # agent was ASKED is the thing a viewer wants first.
        self._publish(live=True)

        # Accepted submits, for a step whose artifact arrives in parts.
        self._accepted = 0
        #: The best REJECTED submit of each artifact, accumulated as ONE
        #: section (each rejected payload is already the `{artifact: {...}}`
        #: envelope, so merging them keeps the shape `_commit` wants).
        #: Committed only if the stage ends without a valid one. Deliberately
        #: not committed at rejection time: an invalid artifact under its own
        #: key is truthy to `landed`, so it would shrink `missing_parts`,
        #: satisfy `step_done` and skip the regen — which is how run 24343e4d
        #: shipped an unusable guide.
        self._best: dict = {}
        #: Fields of rejected object artifacts, carried into the next attempt
        #: at the same artifact (``turn.carry_over``).
        self._kept: dict = {}
        # call key -> the tool_call id it was answered under, so a result
        # compaction removes can be forgotten (forget_compacted_calls).
        self._seen_calls: dict[str, turn_mod.SeenCall] = {}
        #: What this stage has spent and what it has been given back. The
        #: single arm keeps one of these too, and the arithmetic is the
        #: meter's, not either loop's — see :class:`turn.TurnMeter`.
        self._meter = turn_mod.TurnMeter(self.stats, max_turns=self.MAX_TURNS)
        while not self._meter.exhausted:
            # Re-derived each turn: the ratio it converts through sharpens as
            # the run reports real prompt sizes, so freezing it at construction
            # would pin the whole run to the cold-start guess.
            self.messages, dropped = trim_history(self.messages, self._history_budget)
            self.compacted.extend(dropped)
            self.stats["history_dropped"] += len(dropped)
            forget_compacted_calls(self._seen_calls, dropped)
            if dropped:
                # Tell the agent, in the conversation, what went. It was being
                # taken away silently: the model simply stopped seeing turns it
                # had, with nothing to explain the gap and no reason to re-read
                # what it lost.
                self.messages = compact(
                    self.messages, dropped, len(self.compacted),
                    trajectory=self.trajectory, stats=self.stats,
                    restore=self._restore_brief, budget=self._history_budget,
                    llm=self._summariser)

            self.stats["context_len"] = max(
                self.stats["context_len"], prompt_chars(self.messages))
            # Re-bound every turn: a committed or closed artifact's schema
            # leaves the request the turn after it lands.
            self._bind(retrieval_available)
            self._live_specs = turn_mod.withhold_reads(self._live_specs, self._meter)
            turn = self.llm.call_tools(self.messages, self._live_specs)
            if turn.binding_failed:
                # No tool loop is possible against this endpoint. Going round
                # the budget would spend MAX_TURNS x 6 stages of requests to
                # learn the same thing, so give up at once.
                self._give_up("no valid submit")
                return

            outcome = turn_mod.spend_queue(
                turn, meter=self._meter,
                handle=lambda call: self._dispatch(call, stage_message),
                unexecuted=self._answer_unexecuted,
                ended_why="the stage ended first")
            if outcome == "done":
                return

        self.stats["via_budget_exhaustion"] = True
        # Whatever was rejected along the way is still the MODEL's work, and
        # with a per-artifact budget the ceiling — not the submit budget — is
        # now the usual way a struggling stage ends. Dropping `_best` here
        # would discard it exactly when it is most likely to be all there is.
        self._give_up("turn budget exhausted", last_resort=self._best or None)

    def _bind(self, retrieval_available: bool) -> None:
        """The tools this turn is offered: the reads, plus a submit for each
        artifact still OPEN — not yet landed and not closed by a spent submit
        budget.

        Recomputed before every model call. Bound once at the start, a stage
        kept sending the schema of every artifact it had already committed:
        measured on run 14a6b4c7, `implementation`'s seven submit tools rode
        every one of 49 turns at ~6.4k tokens a turn while six of the seven
        artifacts had landed by turn 10. A closed artifact is unbound for the
        same reason and one more: the loop has told the model not to submit
        it again, and a schema still offered says the opposite.

        On a first attempt nothing has landed, so `open_now` is the full set
        and the binding is byte-for-byte the one the golden fixture pins. An
        empty `open_now` binds NO submit tool — ``submit_specs`` reads `()` as
        none and `None` as all, and the two must not be conflated here.

        ``_specs`` — what is PUBLISHED — is accumulated across the
        conversation, never replaced. A loop that continues another's messages
        may bind a narrower set (the replan round binds only `submit_dev_plan`,
        because a plan is the one thing it is asking for), and publishing just
        the live binding made the merged row claim the agent never had
        `submit_assessment_plan`, which is how it wrote the plan in the first
        place. The row answers "what tools did this agent have", and the
        transcript beside it shows which were called when."""
        landed = set(landed_parts(self.step, self.state))
        closed = set(self._closed_parts())
        if not missing_parts(self.step, self.state):
            # Every required part has landed and the stage is still open:
            # it is on a repair turn or the optional-artifact nudge, either
            # of which is answered by RE-SENDING an artifact. Those need
            # their tools back, closed ones excepted.
            landed = set()
        open_now = tuple(key for key, _t, _r in self.step.submit_fields
                         if key not in landed and key not in closed)
        self._live_specs = tools.tool_specs(
            self.step, only=open_now, graph_mode=self.graph_mode,
            retrieval_available=retrieval_available)
        self._specs = merge_specs(self._specs, self._live_specs)

    def _handle_call(self, turn: ToolTurn, specs: list, stage_message: str) -> str:
        """One tool call, judged and answered. ``"return"`` ends the stage,
        ``"continue"`` hands the loop the next call or the next model turn.

        Three branches, in this order: a turn that carried no call, a submit,
        and a read. Everything each branch does that the single arm must do
        identically — recovery, coercion, refunds, the record — is in
        :mod:`turn`; what is left here is this arm's own policy, which is one
        stage's contract and one stage's budget."""
        if not turn:
            turn = turn_mod.recover_call(
                turn, stats=self.stats, trajectory=self.trajectory,
                identity=self.identity)

        if self._nudged and not (turn and (turn.name == "submit"
                                           or turn.name.startswith("submit_"))):
            # The optional-artifact nudge was answered with anything but a
            # submit: the agent has nothing more for this stage. End it
            # here rather than spending the rest of the budget asking
            # again — a turn on "no" is the whole cost of the nudge, and it
            # must not become a turn on "no" repeated.
            self._append_committed(turn, self.step.name)
            return "return"

        if not turn:
            return self._handle_empty(turn, stage_message)

        # A bare `submit` means the stage's submit, whichever artifact it
        # carries. No tool by that name is bound any more — each artifact
        # has its own (`tools.submit_specs`) — but "submit" is what the
        # model says when it has the artifact and has stopped reading tool
        # names carefully, and it arrives that way from every recovery path
        # too (markup, JSON-in-content). Refusing it as an unknown tool
        # would throw away a finished artifact over its envelope.
        if turn.name == "submit":
            turn = ToolTurn(
                name=self._submit_alias(specs, turn.args), args=turn.args,
                call_id=turn.call_id, text=turn.text, message=turn.message,
                truncated=turn.truncated)

        # A submit is coerced against the STAGE's whole artifact schema,
        # not only the one artifact its tool name claims. The tool name
        # says which artifact the model MEANT to send, and the schema of
        # that tool asks for exactly that one — but a model that puts a
        # second artifact in the same call has produced work, and dropping
        # it because it arrived under the neighbouring tool would be the
        # harness losing output the agent wrote. The split's job is to stop
        # the model having to fit six artifacts under one completion cap,
        # not to police which door they come through.
        params = (tools.submit_parameters(self.step)
                  if turn.name.startswith("submit_")
                  else spec_parameters(specs, turn.name))
        args = turn_mod.coerce(turn, params, stats=self.stats,
                               trajectory=self.trajectory, identity=self.identity)

        if turn.name.startswith("submit_"):
            return self._handle_submit(turn, args, params, stage_message)
        return self._handle_read(turn, args)

    def _handle_empty(self, turn: ToolTurn, stage_message: str) -> str:
        """A turn that carried no tool call, after recovery has failed.

        A model that answered with the bare artifact and got it right has done
        the work — accept it as an implicit submit rather than burning turns on
        protocol pedantry (SLM tolerance). Anything else is an invalid turn.
        """
        # warn=False: the model was not asked for JSON on this turn, it was
        # asked to call a tool. A failed parse here is the ordinary case, not
        # something to shout about in the run log.
        parsed = parse_json_response(turn.text, warn=False) if turn.text else {}
        if isinstance(parsed, dict) and parsed:
            section, errors = unwrap_section(parsed, self._validate)
            if not errors:
                self._commit(section, stage_message, turn.text,
                             note="implicit_submit")
                return "return"
        self._append_text_turn(turn, turn_mod.nudge_for(
            turn, trajectory=self.trajectory, identity=self.identity))
        return "continue"

    def _handle_submit(self, turn: ToolTurn, args: dict, params: dict,
                       stage_message: str) -> str:
        """One artifact offered to this stage: rejected with its errors, or
        committed and answered with what the stage still owes."""
        self._meter.acted()
        args = self._wrap_bare_artifact(turn.name, args)
        args = self._fill_single_key_object(args)
        args, carried = turn_mod.carry_over(self._kept, args)
        turn_mod.note_carried(carried, trajectory=self.trajectory, identity=self.identity)
        section, errors, unreadable = turn_mod.judge_submit(
            params, args, self._validate)
        artifact = self._artifact_of(turn.name, args)
        spent = self._submit_attempts.get(artifact, 0)
        if errors and spent < self.SUBMIT_BUDGET:
            self._submit_attempts[artifact] = spent = spent + 1
            # Kept from the FIRST rejection: the give-up commits `_best`, and
            # a payload rejected under one artifact's name may carry another
            # artifact that will never be offered again (its tool is unbound
            # once closed), so waiting for the final rejection loses it.
            self._best.update(section)
            turn_mod.note_submit_rejected(
                f"{artifact} attempt {spent}", turn, args, errors,
                stats=self.stats, trajectory=self.trajectory, identity=self.identity)
            self._append_tool_turn(
                turn, self._reject_message(errors, turn)
                + turn_mod.keep_fields(self._kept, section) + self._respec())
            return "continue"
        if errors:
            # Submit budget spent on a still-invalid artifact — measured
            # failure this answers: a truncated analysis submit kept
            # only needs_analysis, the gap pool satisfied the regen
            # guard, and the whole Analysis/Evaluation phases scored 0.
            self.trajectory.log_recovery_event(
                self.identity, "submit_invalid_final",
                "; ".join(errors)[:200], artifact)
            self._best.update(section)
            left = self._open_parts()
            if left:
                # One artifact that will not pass costs THAT artifact, not
                # the ones beside it. Exactly the single arm's existing
                # rule (`react.SUBMIT_CAP` is non-terminal), applied at the
                # granularity the per-artifact split already declares — so
                # this narrows a standing asymmetry rather than adding one.
                self._append_tool_turn(turn, (
                    f"{artifact} was rejected {self.SUBMIT_BUDGET} times and is "
                    f"still not accepted. Leave it and write the next one. "
                    f"{self.step.name} still needs: {', '.join(left)}."))
                return "continue"
            # Nothing open but the closed artifact(s): the stage ENDS, and the
            # answer says so. Listing the closed artifact as still needed put
            # "leave it" and "still needs it" in one message; a model that
            # obeyed the second half resubmitted it until the turn ceiling
            # (run 14a6b4c7, implementation: 15 resubmits per attempt, both
            # attempts, ~30 turns at ~5k prompt tokens each).
            self._append_tool_turn(turn, self._ends_without_closed(rejected=artifact))
            self._give_up("submit budget spent", last_resort=self._best)
            return "return"
        turn_mod.note_dropped_args(
            unreadable, stats=self.stats, trajectory=self.trajectory,
            identity=self.identity)
        owed = self.step.owes(section) if self.step.owes else ""
        if owed:
            # A valid INSTALMENT of a work set that states a count. Kept, and
            # the next submit is joined to it; refusing it made a model that
            # writes one item per call resend that one item until the set gave
            # up. An instalment that adds nothing is the one thing charged.
            if turn_mod.keep_items(self._kept, section) > 0:
                self._best.update(section)
                self._append_tool_turn(turn, owed)
                return "continue"
            self._submit_attempts[artifact] = spent + 1
            self._append_tool_turn(turn, (
                "NOTHING NEW: what you sent is already kept. " + owed))
            if spent + 1 >= self.SUBMIT_BUDGET:
                self._give_up("submit budget spent", last_resort=self._best)
                return "return"
            return "continue"
        # Commit FIRST, then answer once. The answer depends on what
        # the commit left missing, and a step declared in parts is not
        # necessarily finished by an accepted submit.
        #
        # One answer, not two. Appending the generic "move on to the
        # next stage" and then a second "still needs X" put the model's
        # own turn in the transcript TWICE with two contradictory tool
        # results for one call — which reads, in the context view, as
        # the model having submitted twice.
        # The label names the artifact, or the repair round: the judge
        # reads a flat list of tool names and scores repeats as
        # redundancy, so six `design_implementation` entries would report
        # a stage written one artifact at a time as pure repetition, and
        # four `design_assessment` entries would report iterative
        # correction the same way.
        note = (f"fix{self.stats['repair_turns']}"
                if self.stats["repair_turns"]
                else artifact)
        before = set(landed_parts(self.step, self.state))
        self._commit(section, stage_message,
                     json.dumps(args, ensure_ascii=False), note=note,
                     # Re-sending a landed artifact is a duplicate — except on
                     # a repair round, where re-sending it CHANGED is the fix
                     # the round exists for, and the judge-visible step it
                     # earns is `design_<stage>_fix<n>`.
                     duplicate=bool(self._accepted) and not self.stats["repair_turns"])
        landed = set(landed_parts(self.step, self.state))
        left = missing_parts(self.step, self.state)
        self._accepted += 1
        if tools.STATE_TOOL in tools.tool_names(self._live_specs) \
                and not self.stats["state_reads"]:
            # Written without ever looking at the state: how often a model
            # does that is what says whether the tool is being used at all.
            self.stats["blind_submits"] += 1
        if left and not self._open_parts():
            # Every part still missing is one whose submit budget is spent.
            # Continuing would answer "COMMITTED. <stage> still needs: <the
            # closed one>" and the stage would run to its turn ceiling on
            # resubmits of an artifact the loop no longer accepts.
            self._append_tool_turn(turn, self._ends_without_closed())
            self._give_up("submit budget spent", last_resort=self._best)
            return "return"
        if artifact in left and artifact not in landed:
            # The validator accepted this payload and the commit ran, yet
            # the artifact is not in the state. The answer must SAY so.
            # Saying "COMMITTED. <stage> still needs: <the artifact just
            # sent>" — while the protocol also says never resend what is
            # committed — is an instruction the model cannot satisfy, and
            # it is what hid the `unwrap_section` bug for a whole run
            # (24343e4d: 11 such turns, ~10.4k completion tokens, 107 s,
            # and `operator_manual` submitted three times and lost three
            # times). A commit that does not land is a harness failure;
            # the transcript must not report it as the model's redundancy.
            self.trajectory.log_recovery_event(
                self.identity, "commit_did_not_land", artifact,
                f"accepted by the validator, absent from {self.step.name} after commit")
            self._append_tool_turn(turn, (
                f"NOT COMMITTED: {artifact} was accepted but is not in the design "
                f"state, so it did not land. Send it again as "
                f"{{\"{artifact}\": {{...}}}}, using the field names from "
                f"the stage's schema exactly. {self.step.name} still needs: "
                f"{', '.join(left)}."))
            return "continue"
        open_optional = [key for key, _t, _r in self.step.submit_fields
                         if key not in landed]
        if not left and open_optional and landed > before and not self._nudged:
            # ONE nudge per stage, and one only. An OPTIONAL artifact is
            # not part of `missing_parts`, so the stage is complete
            # without it — but returning the instant the required ones
            # land means the agent never gets the turn to send it.
            # `non_instructional_strategies` (the activities stage) is
            # the only optional left, and a stage must never carry TWO:
            # one nudge names both, the model answers with one, the
            # stage ends (measured twice, on `dev_plan` and on
            # `media_selections`, both required since).
            #
            # Bounded at one because the cost is paid by the models that
            # can least afford it: a weak model with nothing more to say
            # answers a repeated ask with a repeated nothing, and the
            # stage burns to MAX_TURNS. The next turn either lands
            # something or ends the stage — see `_nudged` below.
            self._nudged = True
            self._append_tool_turn(turn, (
                f"COMMITTED: {', '.join(sorted(landed - before))}. "
                f"Still open for this stage: {', '.join(open_optional)}. "
                "Submit what you have for it now — this is the last turn "
                "for it, and the stage ends after your next call."))
            return "continue"
        if not left:
            # The artifact is complete — now let the agent see what is
            # wrong with it, in the context that wrote it.
            pulls = self.graph_mode and self.step.state_tool
            if pulls:
                # The free fixes first, then what is left FOR the agent —
                # counted here, shown by `read_alignment_state`.
                repair_turn.fix_structural(
                    self.state, self.design_brief, self.step, self.trajectory)
                fixable = repair_turn.collect_own(self.state, self.design_brief, self.step)
            else:
                fixable = self._own_violations()
            if fixable and self.stats["repair_turns"] < self.repair_turns:
                self.stats["repair_turns"] += 1
                self._repairing, self._read_since_pointer, self._idle = True, False, 0
                self._append_tool_turn(turn, (
                    open_issues_pointer(
                        self.step.name, len(fixable), self.stats["repair_turns"],
                        self.repair_turns)
                    if pulls else repair_turn.repair_request(
                        self.step.name, fixable, self.stats["repair_turns"],
                        self.repair_turns)))
                return "continue"
            if fixable:
                # Outstanding violations and no repair turn left: say
                # so, or "the model could not fix this" and "we did not
                # give it another turn" are indistinguishable — and the
                # second is a harness parameter, not a finding.
                self._observe_open(fixable)
                self._budget_stopped(fixable, "repair turns")
            self._append_committed(turn, self.step.name)
            return "return"
        if self._accepted >= len(parts_of(self.step)) + self.PART_SUBMIT_SLACK:
            # It has had a turn per part and more; a stage that keeps
            # submitting without completing is a disagreement between
            # the validator and the completeness probe, and letting it
            # run turns that disagreement into the whole stage.
            #
            # NOT `_append_committed`: this branch ends the stage while
            # `left` is non-empty, and that message says the stage's
            # artifact "is now part of the design state. Move on to the
            # next stage." Measured on run 46bd42a5's implementation
            # stage, which ended here owing `dev_plan`: the transcript
            # closed by telling the model the stage was finished, and the
            # give-up on the very next line recorded that it was not. The
            # tool call still has to be answered — that is all
            # `_append_committed` was ever for here — so it is answered
            # truthfully instead. It matters beyond the record in the
            # single arm, where this transcript is carried into every
            # later stage and can be handed back on a repair turn.
            self._append_tool_turn(turn, (
                f"COMMITTED. This stage ENDS here without "
                f"{', '.join(left)}: it has had a submit turn for every "
                f"artifact and more. Do not submit for {self.step.name} again."))
            self._give_up(f"parts still missing: {', '.join(left)}")
            return "return"
        owed = still_needed(self.step, self.state, self._closed_parts())
        if not (landed - before) and not self.stats["repair_turns"]:
            # A re-send of what the stage already held. Answering it
            # "COMMITTED" rewards the re-send — MEASURED (run 4bb81369,
            # analysis): `needs_analysis` was sent seven more times, each
            # answered "COMMITTED", until the stage ran out of submit turns
            # owing four artifacts. So it is called what it is, and the
            # artifact to write instead is named.
            move = self._next_submit()
            self._append_tool_turn(turn, (
                f"ALREADY COMMITTED: {artifact} was in the design state and nothing changed "
                f"— do not send it again. {owed}"
                + (f" Call {move} next." if move else "")))
            return "continue"
        self._append_tool_turn(turn, "COMMITTED. " + owed)
        return "continue"

    def _closed_parts(self) -> tuple[str, ...]:
        """Parts still missing whose submit budget is spent — the loop will
        not accept them again, so no sentence may list them as owed."""
        return tuple(p for p in missing_parts(self.step, self.state)
                     if self._submit_attempts.get(p, 0) >= self.SUBMIT_BUDGET)

    def _open_parts(self) -> tuple[str, ...]:
        """Parts still missing that a submit can still land."""
        closed = set(self._closed_parts())
        return tuple(p for p in missing_parts(self.step, self.state) if p not in closed)

    def _ends_without_closed(self, *, rejected: str = "") -> str:
        """The answer that ends a stage owing its closed artifacts.

        ``rejected`` names the artifact whose rejection is what ended it —
        the call being answered was then NOT committed, and a fan-out work
        set has no parts for `_closed_parts` to name, so the name has to come
        from the call."""
        closed = self._closed_parts() or ((rejected,) if rejected else ())
        lead = "NOT COMMITTED. " if rejected else "COMMITTED. "
        return (f"{lead}This stage ENDS here without {', '.join(closed)}: "
                f"rejected {self.SUBMIT_BUDGET} times and still not accepted. "
                f"Do not submit for {self.step.name} again.")

    def _handle_read(self, turn: ToolTurn, args: dict) -> str:
        """One read of the design state, answered with its observation — or
        refused as a repeat when its result is unchanged (``turn.answer_read``,
        shared with the single arm)."""
        self._assignment_hit = None
        self._state_view = None
        scope = ""
        if turn.name == tools.STATE_TOOL:
            # Named by stage and revision for the judge, which reads a flat
            # list of tool names and scores repeats as redundancy: every
            # ANSWERED state read is a different state (the guard refuses the
            # rest), so the ordinal is the truth and not a disguise.
            stage = self.label.replace(":", "_")
            scope = stage if not self.stats["state_reads"] \
                else f"{stage}_r{self.stats['state_reads'] + 1}"
        observation, repeat = turn_mod.answer_read(
            self._seen_calls, turn, args, lambda: self._execute(turn.name, args),
            meter=self._meter, stats=self.stats, trajectory=self.trajectory,
            identity=self.identity, pure=turn.name != "retrieve", scope=scope,
            on_answered=self._note_answered,
            next_move=(f"call {self._next_submit()} now" if self._next_submit() else ""))
        self._append_tool_turn(turn, observation)
        if not repeat and turn.name == tools.STATE_TOOL:
            supersede_earlier(self.messages, tools.STATE_TOOL, turn.call_id)
        return "continue"

    def _next_submit(self) -> str:
        """The submit tool the agent's next write goes through: the first
        artifact still open, else (a repair round) none in particular."""
        open_parts = self._open_parts()
        if open_parts:
            return f"submit_{open_parts[0]}"
        fields = [key for key, _t, _r in self.step.submit_fields]
        return f"submit_{fields[0]}" if len(fields) == 1 else ""

    def _note_answered(self) -> None:
        """What an ANSWERED read writes — never a refused repeat."""
        self._note_assignment_read()
        view = self._state_view
        if view is None:
            return
        self.stats["state_reads"] += 1
        self._read_since_pointer = True
        self._just_read = True
        repair_turn.stamp_shown(
            view.shown, view.unshown, trajectory=self.trajectory, memory=self.memory,
            identity=self.identity, phase=self.label, family=self.step.family)

    def _note_assignment_read(self) -> None:
        """Count and log a pointer answer — only once the read is ANSWERED, so
        a refused repeat of the same ids is not counted twice."""
        if not self._assignment_hit:
            return
        pointed, heading = self._assignment_hit
        self.stats["assignment_reads"] = self.stats.get("assignment_reads", 0) + 1
        self.trajectory.log_recovery_event(
            self.identity, "read_of_assignment_id", ", ".join(pointed), heading)

    # ── transcript ──────────────────────────────────────────────────────────
    def _append_tool_turn(self, turn: ToolTurn, observation: str) -> None:
        """Assistant turn + its tool result, in the shape the chat API expects.
        The assistant message is the model's own object when we have it, so the
        tool_call ids it generated survive the round trip. A turn with no call
        id is a TEXT reply (a recovered markup call, a prose answer to the
        nudge) and is answered as a user turn — a ``tool`` message with an
        empty id after an assistant message with no ``tool_calls`` is
        malformed, and the single arm sends the history again."""
        self._ensure_assistant(turn)
        if not turn.call_id:
            self.messages.append({"role": "user", "content": observation})
        else:
            self.messages.append({"role": "tool", "tool_call_id": turn.call_id,
                                  "name": turn.name, "content": observation})
        self._publish(live=True)

    def _ensure_assistant(self, turn: ToolTurn) -> None:
        """The model's message, appended once per model turn. Shared with the
        single arm (:func:`transcript.append_assistant`)."""
        append_assistant(self.messages, turn)

    def _answer_unexecuted(self, calls: list, why: str) -> None:
        """Close the tool_call ids of calls that will not run. Shared with the
        single arm; only the live republish is this arm's own."""
        if answer_unexecuted(self.messages, calls, why,
                             trajectory=self.trajectory, identity=self.identity):
            self._publish(live=True)

    def _observe_open(self, outstanding: list) -> None:
        """Put ``outstanding`` in the ledger before a reason is written on it:
        ``mark_open_reason`` skips a key it has never seen, and a violation
        the agent never read has been sighted by no one. NOT shown — nothing
        here was rendered to an agent."""
        if not outstanding:
            return
        round_no = self.trajectory.log_violations_result(
            serialize_violations(outstanding, self.identity), agent=ORCHESTRATOR)
        self.memory.observe_violations(outstanding, round=round_no, phase=self.label,
                                       family=self.step.family, shown_to_agent=False)

    def _declined(self) -> str:
        """The agent read its open issues and has not submitted since
        (``budget.REPAIR_IDLE_TURNS``): the stage closes with them open. Its
        decision, recorded as one — not a give-up and not a ceiling cut."""
        outstanding = repair_turn.collect_own(self.state, self.design_brief, self.step)
        self._observe_open(outstanding)
        self.memory.mark_open_reason({v.key for v in outstanding}, reason="converged")
        self.trajectory.log_recovery_event(
            self.identity, "repair_declined",
            f"{len(outstanding)} issue(s) left open after the agent read them",
            ", ".join(sorted({v.violation_type for v in outstanding}))[:200])
        return "return"

    def _dispatch(self, call: ToolTurn, stage_message: str) -> str:
        """One call through `_handle_call`, then the idle rule of a repair
        round: once the agent has READ its issues, a call that is not a submit
        counts toward closing the stage — the read itself excepted."""
        outcome = self._handle_call(call, self._live_specs, stage_message)
        if outcome != "continue" or not (self._repairing and self._read_since_pointer):
            return outcome
        if self._just_read:
            self._just_read = False
            return outcome
        if (call.name or "").startswith("submit"):
            return outcome
        self._idle += 1
        return self._declined() if self._idle >= budget.REPAIR_IDLE_TURNS else outcome

    def _budget_stopped(self, outstanding: list, budget: str) -> None:
        """Say which violations were still open when a budget ran out."""
        keys = {v.key for v in outstanding}
        self.memory.mark_open_reason(keys, reason="budget")
        self.trajectory.log_recovery_event(
            self.identity, "budget_exhausted",
            f"{budget} spent with {len(keys)} violation(s) open",
            ", ".join(sorted({v.violation_type for v in outstanding}))[:200])

    def _append_committed(self, turn: ToolTurn, stage: str) -> None:
        """The model's own submit turn, plus the tool result that closes it.

        The chat API requires every tool call to be answered; leaving the pair
        half-open would make the next request malformed for the single arm,
        which sends this transcript again."""
        self._append_tool_turn(turn, f"COMMITTED: the {stage} artifact is now part of "
                                     "the design state. Move on to the next stage.")

    def _append_text_turn(self, turn: ToolTurn, nudge: str) -> None:
        self._ensure_assistant(turn)
        self.messages.append({"role": "user", "content": nudge})
        self._publish(live=True)

    # ── tool dispatch ───────────────────────────────────────────────────────
    def _execute(self, action: str, args: dict) -> str:
        if action == "retrieve":
            return self._retrieve(args)
        if action == tools.STATE_TOOL and self.graph_mode and self.step.state_tool:
            self._state_view = alignment_state.read(
                self.state, self.design_brief, self.step, submit_tool=self._next_submit())
            return self._state_view.text
        already = self._already_in_assignment(action, args)
        if already:
            return already
        executor = tools.executors_for(graph_mode=self.graph_mode).get(action)
        if executor is None:
            return ("ERROR: unknown tool " + repr(action)
                    + ". Use one of the listed tools, or submit.")
        pointed, rest = self._ids_in_assignment(action, args)
        if not pointed:
            return executor(self.state, self.step, args)
        # A read for an id the assignment shows and no tool serves — a media
        # selection, a topic, the module itself. Answered with where it is
        # rather than "no readable artifact", which sent a Developer listing
        # and guessing for 18 turns (run 14a6b4c7, content:MU-CM-01). Not an
        # error, so not refunded: looking costs the turn, as a pool read does.
        self._assignment_hit = (pointed, self._assignment_ids[pointed[0].upper()])
        pointers = "\n".join(
            f"{one} is in your assignment above under '{self._assignment_ids[one.upper()]}'; "
            "it is not a separate artifact to read." for one in pointed)
        if not rest:
            return pointers + "\nUse what the assignment shows and submit."
        served = executor(self.state, self.step,
                          {**{k: v for k, v in args.items() if k not in ("id", "ids")},
                           "ids": rest})
        return f"{served}\n\n{pointers}"

    def _ids_in_assignment(self, action: str, args: dict) -> tuple[list[str], list[str]]:
        """Split a read's ids into those the assignment shows and no read tool
        serves, and the rest — which are served as usual, an unknown one
        keeping its ERROR (first in the observation, so the refund applies)."""
        if not self._assignment_ids or not self.graph_mode \
                or action != "read_node":
            return [], []
        wanted = args.get("ids") if args.get("ids") is not None else args.get("id")
        if wanted is None:
            return [], []
        ids = [str(one) for one in (wanted if isinstance(wanted, list) else [wanted])]
        pointed = [one for one in ids if one.upper() in self._assignment_ids
                   and tools._resolve_node(self.state, self.step, one) is None]
        return pointed, [one for one in ids if one not in pointed]

    def _own_violations(self) -> list:
        """This stage's outstanding violations, and a note in the ledger that
        they reached an agent. Shared with the single arm, which passes its own
        ``phase``."""
        return repair_turn.violations_for_agent(
            self.state, self.design_brief, self.step, trajectory=self.trajectory,
            memory=self.memory, identity=self.identity, phase=self.label)
    def _fill_single_key_object(self, args: dict) -> dict:
        """``course_goal: "Build a website"`` means
        ``course_goal: {"statement": "Build a website"}``.

        MEASURED FAILURE (run single_20260904_020259, Qwen3.5-2B on the pod):
        the model sent ``course_goal`` as a bare string. Its schema declares an
        object, so validation answered "course_goal.statement must be a
        non-empty string" three times, the submit budget ran out and the stage
        gave up — leaving ``design.course_goal`` null and C1, one of the five
        core construct-validity relations, at 0 of 50 objectives covered.

        The target field is DERIVED from the step's own deep tool schema
        (``artifact_schemas.ARTIFACT_SCHEMAS``), not declared in a table
        here: an artifact whose schema has exactly ONE property has only one
        thing a bare string could be. That derivation finds
        `course_goal -> statement` and, for the fan-out stages,
        `course_modules -> …`; it finds nothing for
        the multi-field artifacts, where a string would be a guess."""
        if not isinstance(args, dict):
            return args
        for key, field in self._single_key_fields().items():
            value = args.get(key)
            if isinstance(value, str) and value.strip():
                args = {**args, key: {field: value.strip()}}
                self.trajectory.log_recovery_event(
                    self.identity, "bare_artifact_wrapped",
                    f"{key}:str", f"{key}.{field}")
        return args

    def _single_key_fields(self) -> dict:
        """``{artifact key: its only field}`` read off this step's own deep
        tool schema."""
        cached = getattr(self.step, "_single_key_cache", None)
        if cached is None:
            cached = {}
            for key, json_type, _required in self.step.submit_fields:
                if json_type != "object":
                    continue
                properties = (tools.ARTIFACT_SCHEMAS.get(key) or {}).get("properties") or {}
                if len(properties) == 1:
                    cached[key] = next(iter(properties))
            object.__setattr__(self.step, "_single_key_cache", cached)
        return cached

    def _wrap_bare_artifact(self, tool: str, args: dict) -> dict:
        """``submit_course_goal({"statement": …})`` means
        ``{"course_goal": {"statement": …}}``.

        The mirror of ``unwrap_section``, and the same class of near-miss: the
        tool is named after the artifact, so a model that has just been shown
        that artifact's schema sends the INSIDE of the envelope and leaves the
        key off. Measured on the replan loop, where the tool has exactly one
        parameter and every submit was rejected for a key the model had been
        given no reason to write.

        Only for a step with ONE artifact, which is where it was measured and
        where the reading is unambiguous. A stage with several artifacts that
        receives a payload naming none of them is far more likely to have
        WRAPPED the artifact in a stray key — the 2B failure `unwrap_section`
        exists for — and guessing the other way would bury a good submit one
        level down instead of unwrapping it."""
        key = tool[len("submit_"):]
        declared = [name for name, _type, _required in self.step.submit_fields]
        if declared != [key]:
            return args
        if not isinstance(args, dict) or not args or key in args:
            return args
        self.trajectory.log_recovery_event(
            self.identity, "bare_artifact_wrapped", tool, ", ".join(sorted(args))[:100])
        return {key: args}

    def _artifact_of(self, tool_name: str, args) -> str:
        """The artifact a submit is FOR: the tool's own, unless the payload
        carries exactly one of the stage's declared artifacts and it is a
        different one — then that one.

        The tool name says which door the artifact came through; the payload
        says what it is. They part ways when a model re-sends an artifact
        whose own tool is no longer bound (`_bind` drops a landed artifact's
        tool) under whichever submit is still offered. Charging the door's
        artifact would answer a duplicate of X with "Y was accepted but did
        not land" and ask for Y again, forever."""
        named = tool_name[len("submit_"):]
        if isinstance(args, dict) and named not in args:
            carried = [key for key, _t, _r in self.step.submit_fields if key in args]
            if len(carried) == 1:
                return carried[0]
        return named

    def _submit_alias(self, specs: list, args) -> str:
        """Which submit tool a bare ``submit`` meant: the one whose artifact
        the payload actually carries — judged against the STAGE's declared
        artifacts, not only the ones still bound — else the first still bound.

        The binding shrinks as artifacts land (`_bind`), so matching against
        it alone would alias a re-sent, already-committed artifact to a
        neighbouring tool and charge that neighbour's submit budget for it."""
        declared = [key for key, _t, _r in self.step.submit_fields]
        if isinstance(args, dict):
            for key in declared:
                if key in args:
                    return f"submit_{key}"
        offered = [name for name in tools.tool_names(specs)
                   if name.startswith("submit_")]
        return offered[0] if offered else "submit"

    def _already_in_assignment(self, action: str, args: dict) -> str:
        """A pointer instead of a re-render, when the read asks for something
        the assignment already spells out in full.

        The instruction to not look it up exists and is placed as well as it can
        be — first line of the Developer's own intro, immediately above the data
        it describes. It was measured to help and measured not to be enough: on
        run 171408 reads were 22 of 33 Developer calls, and after the
        instruction (run f42dceff) 26 of 63 — with repeats making up the
        difference, so the total stayed at 67%.

        A second sentence would not do better. The harness KNOWS what it
        resolved into the assignment, so the redundant read stops being
        something the model must remember and becomes something it observes:
        the call is answered, honestly and cheaply, with where the answer
        already is. The tool stays bound — a Developer is an agent and may look
        at what it judges it needs — but looking costs the turn and returns no
        second copy.
        """
        if not self._resolved_labels or action not in ("read_node", "read_document"):
            return ""
        wanted = str(args.get("node_type") or args.get("key") or "").strip().lower()
        label = self._resolved_labels.get(wanted)
        if not label:
            return ""
        return (f"You already have every {wanted} your assignment names — under "
                f"\"{label}\" in your assignment above. Use them and submit; read one "
                "by id only if you need more than the assignment shows.")

    def _retrieve(self, args: dict) -> str:
        """External-corpus retrieval as a tool: the agent chose to call it and
        wrote the query itself (the classic arm's separate decision call is
        subsumed by that choice). Gated exactly like the classic path — on the
        benchmark the tool is not even offered."""
        planner = RetrievalPlanner(self.config)
        if not planner.enabled():
            return "ERROR: retrieval is not available in this run"
        menu = planner.build_menu(self.design_brief, self.step.name)
        if not menu:
            return "ERROR: no retrieval corpus is available for this task"
        query = str(args.get("query", "")).strip()
        agents = [entry["name"] for entry in menu][:1]
        plan = {"agents": agents, "strategy": "single",
                "queries": {agents[0]: query} if query else {}}
        results, events = planner.execute_plan(
            self.design_brief, self.step.name, plan,
            log_llm_call=self.trajectory.log_llm_call)
        snippets = sum(len(r.get("content", [])) for r in results)
        self.trajectory.log_retrieval_event(
            self.identity, self.step.name, "retrieve",
            strategy="single", retrieval_agents=agents, executions=events,
            snippets=snippets)
        if not results:
            return "(no material found)"
        lines = ["=== DOMAIN MATERIAL (retrieved on demand) ==="]
        for result in results:
            label = result.get("subagent") or result.get("source", "corpus")
            for snippet in result.get("content", []):
                lines.append(f"[{label}] {snippet}")
        return "\n".join(lines)

    # ── commit + fallback ───────────────────────────────────────────────────
    def _commit(self, section: dict, first_user: str, raw: str, *, note: str = "",
                valid: bool = True, duplicate: bool = False) -> None:
        """Deposit the section. Only a commit that passed validation is a
        judge-visible ``log_step`` — an invalid section committed on a spent
        budget is recovery plumbing (the outer regen loop will retry the whole
        step), and logging each such attempt as a design step is exactly the
        duplicate-trace noise the trajectory judge penalizes as redundancy."""
        # Deep-copy before committing. The submitted object is the model's own
        # tool-call arguments, and those stay in the transcript — the single arm
        # carries that transcript for the rest of the run. Without the copy the
        # design state ALIASES the message history, so a later repair that
        # appends to a list silently rewrites what the agent is shown to have
        # said. (It also let the test fixture's canned payload be mutated, which
        # is how this surfaced: run 1 repaired a C4, run 2 found none.)
        section = copy.deepcopy(section)
        landed_before = set(landed_parts(self.step, self.state))
        if valid:
            self.capture["section"] = section
        commit = self.step.commit if self.graph_mode else self.step.commit_prose
        commit_as_harness(commit, self.state, self.trajectory, section)
        action = f"design_{self.step.name}" + (f"_{note}" if note else "")
        if valid and duplicate and not (set(landed_parts(self.step, self.state)) - landed_before):
            # A re-send of what is already committed. It costs a call and the
            # trace has to show it, but it is not a second design STEP: the
            # judge reads a flat list of tool names and scores a repeated one
            # as redundancy, so logging it as a step would report the agent
            # answering "anything more?" with "no" as duplicated work.
            self.trajectory.log_recovery_event(
                self.identity, "duplicate_submit", action, (raw or "")[:200])
            return
        if valid:
            self.trajectory.log_step(
                self.identity, action, first_user[:200], (raw or "")[:200])
        else:
            self.trajectory.log_recovery_event(
                self.identity, "commit_invalid_section", action, (raw or "")[:200])

    def _reject_message(self, errors: list[str], turn) -> str:
        """The observation a rejected submit gets back.

        A truncated turn is told so FIRST, and told to submit less. Otherwise
        it reads a list of fields it was in the middle of writing when the cap
        cut it off, concludes they are wrong, rewrites the whole artifact, and
        is cut off at the same place — three times, then the stage gives up.
        That is the loop this branch exists to break; the errors still follow,
        because which fields did not arrive is still what it needs to know.
        """
        body = "SUBMIT REJECTED — fix these and submit again:\n- " + "\n- ".join(errors)
        if not turn.truncated:
            return body
        return (
            "YOUR ANSWER WAS CUT OFF at the length limit, so the arguments below "
            "never arrived in full. Do not rewrite everything — send a SHORTER "
            "submit: fewer items, shorter prose, and the required fields first.\n"
            + body)

    def _restore_brief(self, stage: str) -> str | None:
        """The stage turn to put back when a trim took it, or None.

        A stage loop is on ONE stage, so a turn it lost is always the live one.
        This is what makes pushing the contract safe: the turn is droppable
        like everything else, and it comes back when it goes."""
        if stage != self.step.name:
            return None
        return with_progress(stage_brief_block(self.step), self.step, self.state,
                             self._closed_parts())

    def _respec(self) -> str:
        """The contract, re-attached to a rejection when it is no longer in the
        transcript. Same rule and same function as the single arm's.

        The backstop to `compact`'s `restore`: a turn can be gone for reasons a
        trim did not report (a regen starting a fresh message list, a stage
        turn dropped before this loop's own restore could run)."""
        return respec(self.messages, self.step,
                      with_progress(stage_brief_block(self.step), self.step, self.state,
                                    self._closed_parts()))

    def _give_up(self, reason: str, *, last_resort: dict | None = None) -> None:
        """End a step with whatever the MODEL produced, and record that it did
        not finish. No scripted rescue, deliberately: a single-shot fallback
        once wrote up to 76% of the prose arm's artifacts, and existed on this
        loop but never on ``ReactLoop`` — one side of the decomposition axis
        caught, the other dropped. What still catches a failure catches it
        for BOTH arms (the regen loop in ``run.py``, the structural net in
        ``core/repairs.py``) and neither writes instructional content. A step
        that produces nothing says so; the count is the finding.
        """
        self.stats["gave_up"] = True
        self.trajectory.log_recovery_event(
            self.identity, "agentic_gave_up", reason, self.step.name)
        if last_resort is None:
            return
        # Only what never landed. `_best` holds every REJECTED payload, and a
        # model re-sends artifacts it has already committed; committing a
        # rejected re-send here would overwrite the accepted artifact with
        # the version the validator refused. MEASURED (run 9efc3cfa,
        # implementation): a valid `system_check` was replaced at give-up by
        # a rejected one under invented keys, and the run shipped three
        # "required field is missing" errors for an artifact it had accepted.
        landed = set(landed_parts(self.step, self.state))
        last_resort = {key: value for key, value in last_resort.items()
                       if key not in landed}
        if not last_resort:
            return
        # The best the MODEL managed, committed as-is rather than discarded: it
        # is the agent's own work, and the repair net can mend it.
        errors = self._validate(last_resort)
        self._commit(last_resort, "", "", note="incomplete", valid=not errors)
