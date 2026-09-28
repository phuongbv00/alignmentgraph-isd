"""One tool call: its shape on the wire, what it costs, and what it means
before either arm decides what to do with it.

Everything here is TRANSPORT and ACCOUNTING, never policy. The two arms make
genuinely different decisions about a call — a stage loop judges it against one
stage's contract, the single arm against whichever stage is still open — and
that difference is the ``agent_mode`` treatment. What must not differ is the
price: which replies are refunded, how a batched reply is charged, when a
serving hiccup is recovered rather than billed, and what the record says
afterwards.

``via_budget_exhaustion`` is read off exactly this arithmetic, and the
decomposition claim rests on neither arm having been CUT by its ceiling. A
refund granted on one side and withheld on the other would put a ceiling
difference inside the treatment, which is the one confound that claim cannot
survive — so the arithmetic is written once and both arms call it.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import NamedTuple

from .. import dev_plans, llm_io
from . import budget, tools
from .protocol import (
    CONSTRAINED_PASS_REQUEST,
    INVALID_TURN_NUDGE,
    ITEM_RESTATES_OBJECTIVE,
    READ_ALREADY_SHOWN,
    REPEAT_UNCHANGED,
    turns_left_hint,
)
from .tools import unwrap_section
from .transcript import history_budget, message_size, trim_history


@dataclass
class ToolTurn:
    """One model turn under native tool calling.

    ``name`` empty means the model produced no tool call — either it answered
    with text (``text``), or the request failed. The loop treats those two the
    same way on purpose: both cost one turn and both get the same nudge, so a
    backend hiccup can never be cheaper than a protocol mistake."""

    name: str = ""
    #: As the parser handed them over — a dict, or a JSON string, or a dict
    #: whose structured values are still JSON strings. Both loops coerce it
    #: against the bound spec (:func:`coerce`) before anything reads it.
    args: object = None
    call_id: str = ""
    text: str = ""
    message: object = None
    #: The calls after this one in the same model turn, each a ToolTurn of its
    #: own with ``sibling=True``.
    calls: tuple = ()
    #: This call shares its assistant message with the call before it, so the
    #: message is already in the history and must not be appended again.
    sibling: bool = False
    #: The request never reached the model (a connection error or a 5xx,
    #: after the client's one retry): the endpoint's turn, not the model's,
    #: refunded by the loop (``TurnMeter.endpoint_failed``) instead of
    #: nudged for. An ordinary empty turn — the model answered with text —
    #: keeps ``failed`` False and is charged as before.
    failed: bool = False
    #: The backend refused ``bind_tools`` — not a model mistake, an endpoint
    #: one. Distinguished from an ordinary empty turn so the loop can stop
    #: immediately instead of spending its budget discovering it again.
    binding_failed: bool = False
    #: The generation hit the token cap. A native tool call that ran out of
    #: tokens arrives as a well-formed call with missing or partial arguments —
    #: no parse error, nothing to catch — so without this the loop reports
    #: "learner_analysis must be a non-empty object" for a field the model may
    #: well have been writing when it was cut off, and the model then rewrites
    #: the artifact from scratch and is cut off again.
    truncated: bool = False

    def __bool__(self) -> bool:
        return bool(self.name)


class TurnMeter:
    """What a loop has spent, and what it is given back.

    Two kinds of reply produce NO observation and NO artifact: an exact
    repeat of a call already answered, and a call that came back ERROR.
    Charging the ceiling for them spends the budget on the model's confusion
    and leaves less for its work — measured at 19 of A0's turns for repeats
    alone, and 13% of every tool result over runs 53042a0d and 2559b22d for
    errors. Each is therefore refunded, and each is BOUNDED by its allowance in
    :mod:`budget`, or a model that only ever repeats would never reach the
    ceiling at all.

    The allowances are read from :mod:`budget` here rather than carried as
    class attributes on the loops: two classes holding the same number is the
    shape a drift starts from, and these are never overridden per instance the
    way ``max_turns`` and ``repair_turns`` are.
    """

    def __init__(self, stats: dict, *, max_turns: int) -> None:
        self.stats = stats
        self.max_turns = max_turns
        #: Turns given back under the allowances above.
        self.refunded = 0
        #: Turns spent so far. ONE PER EXECUTED CALL, not per model reply: a
        #: reply carrying three calls costs three, which is what keeps the
        #: budget the honest unit of work now that every call runs — and what
        #: makes ``turns_used`` comparable across the decomposition axis.
        self.turn_no = 0
        #: Consecutive reads that bought nothing; see ``budget.FRUITLESS_READS``.
        self.fruitless = 0

    @property
    def reads_withheld(self) -> bool:
        """Whether the next binding should offer submits only."""
        return self.fruitless >= budget.FRUITLESS_READS

    def read_was(self, *, useful: bool) -> None:
        self.fruitless = 0 if useful else self.fruitless + 1

    def acted(self) -> None:
        """A submit arrived — accepted or not, the agent is working again."""
        self.fruitless = 0

    @property
    def ceiling(self) -> int:
        return self.max_turns + self.refunded

    @property
    def exhausted(self) -> bool:
        return self.turn_no >= self.ceiling

    def spend(self) -> None:
        self.turn_no += 1
        self.stats["turns_used"] = self.stats.get("turns_used", 0) + 1

    def _refund(self, key: str, allowance: int) -> None:
        self.stats[key] = self.stats.get(key, 0) + 1
        if self.stats[key] <= allowance:
            self.refunded += 1

    def repeated(self) -> None:
        """An exact repeat of a call already answered."""
        self._refund("repeated_calls", budget.REPEAT_ALLOWANCE)

    def tool_error(self) -> None:
        """A tool call whose observation came back ERROR."""
        self._refund("tool_errors", budget.ERROR_ALLOWANCE)

    def endpoint_failed(self) -> None:
        """A request the endpoint did not answer, after the retry. Bounded by
        the same allowance as a tool error, or an endpoint that is down would
        never let the ceiling close the stage."""
        self._refund("endpoint_failures", budget.ERROR_ALLOWANCE)

    def hint(self) -> str:
        """The countdown appended to an observation near the ceiling."""
        return turns_left_hint(self.ceiling - self.turn_no)


def spend_queue(turn: ToolTurn, *, meter: TurnMeter, handle, unexecuted,
                ended_why: str) -> str:
    """Execute every call the model's reply carried, in order, one turn each.

    Returns ``"done"`` when the handler ended the loop, ``"exhausted"`` when
    the ceiling was reached mid-queue, and ``""`` when the whole queue ran.

    Only the FIRST call used to run and the rest were counted and silently
    dropped, their ids left unanswered — measured on run e81b8108, five of six
    stages re-issued the dropped reads and the turn after a dropped batch came
    back empty.

    A call the budget cannot cover, or one after the call that ended the loop,
    is still ANSWERED with a stub saying it did not run: the chat API requires
    every call in an assistant message to be answered, and the single arm sends
    its whole conversation again on every request, so an id left open there is
    a malformed call from then on.
    """
    meter.stats["batched_calls"] = meter.stats.get("batched_calls", 0) + len(turn.calls)
    queue = [turn, *turn.calls]
    for index, call in enumerate(queue):
        if meter.exhausted:
            unexecuted(queue[index:], "the turn budget ran out first")
            return "exhausted"
        meter.spend()
        if handle(call) == "return":
            unexecuted(queue[index + 1:], ended_why)
            return "done"
    return ""


def recover_call(turn: ToolTurn, *, stats: dict, trajectory, identity: str) -> ToolTurn:
    """A correctly-formed call the server left as TEXT, recovered.

    Tried before the turn is treated as prose: otherwise a serving hiccup costs
    a turn and reads as a model mistake. Returns the turn unchanged when there
    was nothing to recover.
    """
    recovered = (tools.parse_tool_call_markup(turn.text)
                 or tools.parse_tool_call_json(turn.text))
    if recovered is None:
        return turn
    stats["markup_recovered"] = stats.get("markup_recovered", 0) + 1
    trajectory.log_recovery_event(
        identity, "tool_call_markup_recovered", recovered[0], (turn.text or "")[:100])
    return ToolTurn(name=recovered[0], args=recovered[1], call_id=turn.call_id,
                    text=turn.text, message=turn.message)


def nudge_for(turn: ToolTurn, *, trajectory, identity: str) -> str:
    """What an empty turn is answered with, and its entry in the record.

    ONE wording for both arms (``protocol.INVALID_TURN_NUDGE``): the nudge
    lands in the transcript the model reads, so a sentence worded differently
    on each side of the decomposition axis is a second variable sitting on the
    ``agent_mode`` axis.
    """
    trajectory.log_recovery_event(
        identity, "invalid_action", (turn.text or "")[:120], "")
    return INVALID_TURN_NUDGE


def coerce(turn: ToolTurn, params: dict, *, stats: dict,
           trajectory=None, identity: str = "") -> dict:
    """The call's arguments, parsed against the spec the tool was BOUND with.

    Before anything reads them: a structured value that arrived as text is a
    transport artifact, not a model mistake, and must not be charged to a
    submit budget — measured, it cost every stage of every arm its whole
    budget (see ``tools.coerce_args``). A scalar string in a field declared
    as a list of strings is then RESHAPED into a one-element list
    (``tools.reshape_args``); counted apart from salvage and logged as
    ``argument_reshaped`` so a reader sees what the harness re-containered.
    ONE implementation for both arms: a reshape granted on one side of the
    decomposition axis would be a validator difference inside the treatment.
    """
    salvaged: list[str] = []
    args = tools.coerce_args(params, turn.args, salvaged=salvaged)
    reshaped: list[str] = []
    args = tools.reshape_args(params, args, reshaped=reshaped, salvaged=salvaged)
    stats["args_salvaged"] = stats.get("args_salvaged", 0) + len(salvaged)
    stats["args_reshaped"] = stats.get("args_reshaped", 0) + len(reshaped)
    if reshaped and trajectory is not None:
        trajectory.log_recovery_event(
            identity, "argument_reshaped", "; ".join(reshaped)[:200],
            "container changed; content unchanged")
    if turn.truncated and not turn.sibling:
        stats["truncated_turns"] = stats.get("truncated_turns", 0) + 1
    return args


_EMPTY = (None, "", [], {})


def carry_over(kept: dict, args: dict) -> tuple[dict, list[str]]:
    """``args`` with the fields an EARLIER, rejected attempt at the same object
    artifact already carried and this attempt left out: ``(args, carried)``.

    A rejected artifact used to have to be written again WHOLE. MEASURED (runs
    40856c96, b8576814, 53a9cd1a): ``operator_manual`` arrived with a
    3,000-character ``system_setup`` and nothing else, was refused for the three
    fields it lacked, and the only way forward was to emit the 3,000 characters
    again plus the rest, under the same completion cap that had most likely
    ended the first attempt. What the model wrote and the validator did not
    object to is kept (:func:`keep_fields`), so the next submit may carry ONLY
    what was missing. The text is the model's own, from this same
    conversation; a field it sends again replaces the kept one."""
    out, carried = dict(args), []
    for name, value in args.items():
        earlier = kept.get(name)
        if isinstance(value, list) and isinstance(earlier, list) and earlier:
            # An instalment of a work set's list (``keep_items``): joined AFTER
            # what is kept. An item that REPEATS a kept one, or another of its
            # own instalment, adds nothing (``dev_plans.same_artifact_key`` —
            # the same test the commit's trim drops a repeat by, so a repeat
            # can never count towards the set's quota on the way there).
            out[name] = list(earlier) + dev_plans.without_repeats(name, value, beside=earlier)
            carried.append(f"{name}[:{len(earlier)}]")
            continue
        if not isinstance(value, dict) or not isinstance(earlier, dict):
            continue
        missing = {k: v for k, v in earlier.items()
                   if v not in _EMPTY and value.get(k) in _EMPTY}
        if missing:
            out[name] = {**value, **missing}
            carried += [f"{name}.{k}" for k in missing]
    return out, carried


def keep_fields(kept: dict, section: dict) -> str:
    """Remember a rejected submit's object artifacts, and say so: the sentence
    appended to the rejection, or ``""`` when there is nothing to keep."""
    lines = []
    for name, value in (section or {}).items():
        fields = [k for k, v in value.items() if v not in _EMPTY] if isinstance(value, dict) else []
        if not fields:
            continue
        kept[name] = {**(kept.get(name) or {}), **{k: value[k] for k in fields}}
        lines.append(f"{name}: {', '.join(sorted(kept[name]))}")
    if not lines:
        return ""
    return ("\nKEPT from what you sent — do not write these again: " + "; ".join(lines)
            + ". Your next submit of this artifact may carry ONLY the fields named above as "
              "missing; they are joined to what is kept.")


def keep_items(kept: dict, section: dict) -> int:
    """Remember the LISTS of an accepted-but-unfinished work-set submit, so the
    next one may carry only what is still owed. Returns how many items the
    pile gained — zero means the agent resent what was already kept."""
    gained = 0
    for name, value in (section or {}).items():
        if isinstance(value, list):
            # Repeats INSIDE one instalment go too: a model asked for two more
            # that sends one item twice has written one.
            unique = dev_plans.without_repeats(name, value)
            gained += len(unique) - len(kept.get(name) or [])
            kept[name] = unique
    return gained


def note_carried(carried: list[str], *, trajectory, identity: str) -> None:
    if carried and trajectory is not None:
        trajectory.log_recovery_event(
            identity, "argument_reshaped", "; ".join(carried)[:200],
            "carried from this agent's earlier attempt at the same artifact")


def judge_submit(params: dict, args: dict, validate) -> tuple[dict, list[str], list[str]]:
    """Drop what cannot be READ, then judge what is left. Returns the unwrapped
    section, the errors, and the keys that were dropped.

    An unreadable argument beside a valid artifact is a dropped argument, not a
    reason to refuse the artifact; an unreadable argument the artifact needed is
    the reason it failed, and then — and only then — the model is told about the
    shape, ahead of the validator's own complaint about the hole it left.

    The two arms must agree on when a submit is acceptable, or the axis
    measures acceptance policy instead of the context boundary.
    """
    unreadable = tools.shape_bad_keys(params, args)
    for key in unreadable:
        args.pop(key, None)
    section, errors = unwrap_section(args, validate)
    if errors and unreadable:
        shape = tools.shape_errors(params, args, unreadable)
        errors = shape + [e for e in errors if e not in shape]
    return section, errors, unreadable


#: Rejections a decoder cannot fix, as patterns built FROM the wording that
#: states them, so the two cannot drift apart. A grammar holds the shape of an
#: artifact — which ids exist, how many rows, which levels — and nothing about
#: what a question says; over one of these alone a pass is a second full
#: completion that writes the same thing again. MEASURED (2B tune run
#: 2026-09-26): 17 passes over a restated question, 3 accepted, 8 restated it
#: again and 6 ran to the completion cap.
_GRAMMAR_CANNOT_FIX = tuple(
    re.compile(".*".join(re.escape(part) for part in re.split(r"\{[a-z_]+\}", wording)))
    for wording in (ITEM_RESTATES_OBJECTIVE,))


def grammar_cannot_fix(errors: list[str]) -> bool:
    """Whether EVERY error is one no decoder can fix. A mixed list still gets
    the pass: the structural errors in it are what the pass is for."""
    return bool(errors) and all(
        any(p.fullmatch(e) for p in _GRAMMAR_CANNOT_FIX) for e in errors)


def _skip_pass(stats: dict, trajectory, identity: str, turn: ToolTurn,
               errors: list[str], why: str) -> None:
    stats["constrained_pass_skipped"] = stats.get("constrained_pass_skipped", 0) + 1
    trajectory.log_recovery_event(
        identity, "constrained_pass_skipped", f"{turn.name} | {'; '.join(errors)[:120]}", why)


def constrained_pass(llm, messages: list, turn: ToolTurn, *, artifact: str, schema: dict,
                     errors: list[str], params: dict, validate, stats: dict,
                     trajectory, identity: str) -> tuple[dict, dict, list[str]] | None:
    """A rejected submit, written again by the model under the artifact's
    per-run schema: ``(section, args, unreadable)`` when the pass is accepted,
    ``None`` when it is not or could not be made.

    Pass 1 is the tool call the agent chose to make; this is pass 2, made only
    when the validator refused it, and it is the TRANSPORT's recovery, not the
    agent's decision: the call the agent made is answered with what was wrong
    (``protocol.CONSTRAINED_PASS_REQUEST``) and the model writes the arguments
    again with no tools bound and the decoder holding the shape — the
    references as enums over the ids that exist, a fixed assignment's rows as
    constants, a stated count as bounds (:mod:`grammar`). The conversation the
    pass sees is the agent's own, and the artifact is committed as the agent's
    submit; nothing is published as a second context, and the pass is not a
    turn of the meter (``budget.CONSTRAINED_PASSES_PER_SUBMIT`` bounds it).

    ONE implementation, called identically by both loops. The alternative —
    answering the rejection and asking the model to try again — was measured
    to cost a turn and a share of the submit budget each time (2B run, 51
    rejections, 21 of them argument-less), and it charged the model for a
    failure that sits in the serving stack's tool-call parser (see
    ``client.AgenticLLM.call_structured``). A recovery granted on one side of
    the decomposition axis and withheld on the other would be a confound the
    claim cannot survive, which is why neither loop composes its own.

    What the pass returns is judged by the SAME validator the call was: a
    grammar fixes structure and not semantics, and an artifact the decoder
    shaped and the validator still refuses (a cross-field rule no schema can
    say) goes back to the agent as the rejection it always was, counted as
    ``constrained_pass_rejected``. Two cases are not sent at all, each logged
    ``constrained_pass_skipped``: a rejection no decoder can fix
    (:func:`grammar_cannot_fix`), and a prompt that does not fit the window.

    The pass's prompt is the agent's conversation PLUS the rejected call and
    the request, sent with the schema in place of the tools, so it is trimmed
    here to the history budget with the schema counted — a copy, never the
    agent's own messages. MEASURED (2B tune run 2026-09-26): a work set whose
    rejected call carried the whole item set sent three passes past a 16,384
    window, each refused with HTTP 400.
    """
    if llm is None or not schema or not llm.structured_outputs_available():
        return None
    if grammar_cannot_fix(errors):
        _skip_pass(stats, trajectory, identity, turn, errors, "grammar cannot fix")
        return None
    declared = list((params.get("properties") or {}).keys()) or [artifact]
    request = CONSTRAINED_PASS_REQUEST.format(
        tool=turn.name, keys=", ".join(f'"{k}"' for k in declared),
        errors="\n- ".join(errors))
    history = list(messages)
    if turn.message is not None or turn.call_id:
        history.append(turn.message if turn.message is not None
                       else {"role": "assistant", "content": turn.text or ""})
    if turn.call_id:
        history.append({"role": "tool", "tool_call_id": turn.call_id,
                        "name": turn.name, "content": request})
    else:
        history.append({"role": "user", "content": request})
    budget = history_budget(getattr(llm, "config", None), [schema])
    history, _dropped = trim_history(history, budget)
    if sum(message_size(m) for m in history) > budget:
        _skip_pass(stats, trajectory, identity, turn, errors, "prompt past window")
        return None
    stats["constrained_passes"] = stats.get("constrained_passes", 0) + 1
    raw = llm.call_structured(history, schema, turn.name)
    parsed = llm_io.parse_json_response(raw, warn=False) if raw else {}
    if not isinstance(parsed, dict) or not parsed:
        stats["constrained_pass_rejected"] = stats.get("constrained_pass_rejected", 0) + 1
        trajectory.log_recovery_event(
            identity, "constrained_pass", f"{turn.name} | {'; '.join(errors)[:120]}",
            "rejected: no artifact came back")
        return None
    if artifact in declared and not (set(parsed) & set(declared)):
        # The artifact without its envelope: the schema asked for the key and
        # a backend without a grammar may have answered with the value.
        parsed = {artifact: parsed}
    salvaged: list[str] = []
    args = tools.coerce_args(params, parsed, salvaged=salvaged)
    args = tools.reshape_args(params, args, reshaped=[], salvaged=salvaged)
    section, still, unreadable = judge_submit(params, args, validate)
    if still:
        stats["constrained_pass_rejected"] = stats.get("constrained_pass_rejected", 0) + 1
        trajectory.log_recovery_event(
            identity, "constrained_pass", f"{turn.name} | {'; '.join(errors)[:120]}",
            "rejected: " + "; ".join(still)[:160])
        return None
    trajectory.log_recovery_event(
        identity, "constrained_pass", f"{turn.name} | {'; '.join(errors)[:120]}",
        "accepted")
    return section, args, unreadable


#: What a tool result says when the artifact it answers was completed by the
#: constrained pass. The agent is told, because the committed arguments are not
#: the ones in its own call.
CONSTRAINED_PASS_NOTE = (" (your call was not accepted as sent — {errors} — and the artifact was "
                         "written again under its schema; what is committed is that version.)")


def constrained_note(errors: list[str]) -> str:
    return CONSTRAINED_PASS_NOTE.format(errors="; ".join(errors)[:160])


def note_submit_rejected(label: str, turn: ToolTurn, args: dict, errors: list[str], *,
                         stats: dict, trajectory, identity: str) -> None:
    """Record a rejected submit, with the argument SHAPE beside the errors.

    "expected dict, got str" has two very different causes — a parser that
    handed the value over as text, or a model that wrote prose where an object
    belongs — and only the shape tells them apart. BOTH the raw shape and the
    coerced one, because ``coerce_args`` answers an unparseable argument object
    with ``{}``: recording only the coerced shape made "the parser gave us
    nothing" and "the model sent nothing" the same empty string (measured: nine
    rejections reading ``args=`` on run single_20260901_205901, with no way to
    tell which had happened).
    """
    stats["submits_rejected"] = stats.get("submits_rejected", 0) + 1
    trajectory.log_recovery_event(
        identity, "submit_rejected",
        f"{label} | raw={tools.arg_shape(turn.args)} | args={tools.arg_shape(args)}"
        + (" | TRUNCATED" if turn.truncated else "") + reply_shape(turn.message),
        "; ".join(errors)[:200])


def reply_shape(message) -> str:
    """What the model's reply looked like, in numbers: how much content and
    reasoning it carried, why it stopped, and how many tool calls LangChain
    parsed or could not. Recorded beside a rejection so an argument-less call
    can be told apart across a whole run -- a router that dropped the
    arguments, a reply that put the artifact in its text, a cut-off -- without
    saving the transcript. Empty for a turn built without a reply."""
    if message is None:
        return ""
    content = getattr(message, "content", "") or ""
    if not isinstance(content, str):
        content = str(content)
    extra = getattr(message, "additional_kwargs", None) or {}
    reasoning = extra.get("reasoning_content") or ""
    calls = len(getattr(message, "tool_calls", None) or [])
    invalid = len(getattr(message, "invalid_tool_calls", None) or [])
    return (f" | content={len(content)} reasoning={len(reasoning)} "
            f"finish={llm_io.finish_reason(message) or '?'} calls={calls} invalid={invalid}")


def note_dropped_args(unreadable: list[str], *, stats: dict, trajectory,
                      identity: str) -> None:
    """Record the arguments dropped from a submit that was otherwise valid."""
    if not unreadable:
        return
    stats["dropped_args"] = stats.get("dropped_args", 0) + len(unreadable)
    trajectory.log_recovery_event(
        identity, "dropped_argument", ", ".join(unreadable),
        "arrived as text where a structure was declared; "
        "the rest of the submit was valid and was accepted")


def repeat_key(name: str, args: object) -> str:
    """The identity of a call, for the anti-loop guard.

    ONE composition for both arms: built differently, the same repeated call
    would be caught on one arm and missed on the other whenever an argument
    carried a non-ASCII character — which every scenario in this benchmark
    does.
    """
    return f"{name}:{json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)}"


class SeenCall(NamedTuple):
    """One answered read: the tool-call id its result sits under in the
    transcript (what ``transcript.forget_compacted_calls`` matches on) and a
    digest of that result (what a repeat is compared against)."""
    call_id: str
    digest: str
    #: For a ``read_node``: node id -> digest of the block rendered for it,
    #: what a later read of a SUBSET of those ids is compared against.
    blocks: dict = {}


def observation_digest(observation: str) -> str:
    """Identity of a read's RESULT. Taken before the turns-left countdown is
    appended, which changes every turn and is not part of the result."""
    return hashlib.sha1(observation.encode("utf-8", "replace")).hexdigest()


def answer_read(seen: dict, turn: ToolTurn, args: dict, execute, *, meter: TurnMeter,
                stats: dict, trajectory, identity: str, pure: bool = True,
                scope: str = "", on_answered=None, next_move: str = "") -> tuple[str, bool]:
    """One read, answered — or refused as a repeat ONLY when that is true.

    A call already made is one of three things. Its earlier result is no
    longer in the context (compaction took it, and ``forget_compacted_calls``
    has dropped it from ``seen``): answered as a first call. Its result is
    still there and the state has MOVED since: answered as a first call,
    because an agent that reads, submits and reads again is doing exactly
    what it should. Its result is still there and is IDENTICAL: refused, in
    ``protocol.REPEAT_UNCHANGED``, refunded up to ``budget.REPEAT_ALLOWANCE``
    and kept off the judge-visible trace.

    Telling the last two apart means re-deriving the result, which is why
    the executors are pure and model-free. The guard used to refuse every
    repeat with "its result has not changed" without looking — false after
    any commit, and a wall in front of the read → submit → re-read loop.
    MEASURED for the unchanged case it still answers: a 2B model burned its
    whole turn budget on six identical reads.

    ``pure=False`` (external retrieval) is never re-run: a repeat is refused
    on the call alone. ``on_answered`` runs only when the read is answered,
    so a caller's counters and events never fire for a refused repeat.
    Returns ``(observation, was_repeat)``. ONE implementation for both arms:
    a guard lenient on one side of the decomposition axis is a ceiling
    difference sitting inside the treatment.
    """
    key = repeat_key(turn.name, args)
    prior = seen.get(key)
    observation = "" if (prior is not None and not pure) else execute()
    digest = observation_digest(observation)
    if prior is not None and (not pure or digest == prior.digest):
        meter.repeated()
        meter.read_was(useful=False)
        trajectory.log_recovery_event(
            identity, "repeated_tool_call", turn.name, str(args)[:100])
        return (_do_next(REPEAT_UNCHANGED.format(name=turn.name), meter, next_move)
                + meter.hint(), True)
    blocks = _node_blocks(observation) if turn.name == "read_node" else {}
    covered = _ids_already_shown(seen, turn.name, args, blocks=blocks)
    if covered:
        # Not the same call, but nothing new: every id was answered by an
        # earlier read whose result is still in the context and unchanged.
        # MEASURED (2B run, 2026-09-24): 17 of 46 Designer `read_node` calls
        # re-read a subset of ids already shown, each a new call to the
        # exact-repeat guard and a judge-visible entry. Refunded and counted
        # fruitless like a repeat, so the binding withholds the reads after
        # `budget.FRUITLESS_READS` of them.
        meter.repeated()
        meter.read_was(useful=False)
        trajectory.log_recovery_event(
            identity, "repeated_tool_call", turn.name,
            f"ids already shown: {', '.join(covered)}"[:100])
        # The countdown rides on a refused read too: a model that only reads
        # is exactly the one that has to be told how many turns are left.
        return (_do_next(READ_ALREADY_SHOWN.format(ids=", ".join(covered)), meter, next_move)
                + meter.hint(), True)
    if prior is not None:
        stats["rereads_changed"] = stats.get("rereads_changed", 0) + 1
    seen[key] = SeenCall(turn.call_id, digest, blocks)
    stats["reads"] = stats.get("reads", 0) + 1
    failed = observation.startswith("ERROR")
    if failed:
        meter.tool_error()
    meter.read_was(useful=not failed)
    if on_answered is not None:
        on_answered()
    if failed:
        observation = _do_next(observation, meter, next_move)
    answered = observation + meter.hint()
    log_read(trajectory, identity, turn.name, args, answered, scope=scope)
    return answered, False


_BLOCK_HEADER = re.compile(r"^\[([A-Z_]+):([^\]]+)\]$", re.MULTILINE)


def _node_blocks(observation: str) -> dict[str, str]:
    """``node id -> digest of its block`` over a ``read_node`` observation
    (``tools.render_nodes``: one ``[TYPE:ID]`` header per node, the data
    under it). An ERROR observation has no blocks."""
    heads = list(_BLOCK_HEADER.finditer(observation))
    blocks: dict[str, str] = {}
    for index, head in enumerate(heads):
        end = heads[index + 1].start() if index + 1 < len(heads) else len(observation)
        blocks[head.group(2)] = observation_digest(observation[head.end():end].strip())
    return blocks


def _ids_already_shown(seen: dict, name: str, args: object, *, blocks: dict) -> list[str]:
    """The ids of a ``read_node`` call when EVERY one of them was rendered,
    byte for byte the same, by an earlier ``read_node`` still in ``seen``;
    ``[]`` otherwise. Compared on CONTENT, the way the exact-repeat guard is:
    a node a commit or a repair rewrote renders differently and the read is
    answered as new, as the read → submit → re-read loop requires; a read
    the compaction took is gone from ``seen`` and is answered as new too."""
    if name != "read_node" or not isinstance(args, dict) or not blocks:
        return []
    wanted = [str(i) for i in (args.get("ids") or []) if str(i).strip()]
    if not wanted or set(wanted) != set(blocks):
        return []
    shown: dict[str, str] = {}
    for key, prior in seen.items():
        if key.startswith("read_node:"):
            shown.update(getattr(prior, "blocks", None) or {})
    if all(shown.get(node_id) == blocks[node_id] for node_id in wanted):
        return wanted
    return []


def _do_next(observation: str, meter: TurnMeter, next_move: str) -> str:
    """A read that bought nothing, answered with the MOVE to make instead —
    named, because "use what you have" is the class of instruction a small
    model has been measured not to act on — and, once the allowance is spent,
    with the fact that reads are no longer on offer."""
    if next_move:
        observation += f" Do not read again: {next_move}."
    if meter.reads_withheld:
        observation += " The read tools are withheld until you submit."
    return observation


def withhold_reads(specs: list, meter: TurnMeter) -> list:
    """The binding with its read tools removed, while ``meter.reads_withheld``
    and a submit is on offer. ONE rule for both arms (``budget.FRUITLESS_READS``)."""
    if not meter.reads_withheld:
        return specs
    submits = [spec for spec in specs
               if str(spec.get("function", {}).get("name", "")).startswith("submit")]
    return submits or specs


def log_read(trajectory, identity: str, name: str, args: dict, observation: str, *,
             scope: str = "") -> None:
    """The judge-visible entry for one read.

    The tool name carries its scoping argument so the trace distinguishes
    ``read_nodes(objective)`` from ``read_nodes(assessment)`` — same-name
    entries with different targets otherwise read as redundant repeats to the
    BFCL judge.
    """
    scope = scope or str(args.get("node_type") or args.get("relation_id")
                         or args.get("key") or "").strip()
    trajectory.log_step(identity, f"tool_{name}" + (f"_{scope}" if scope else ""),
                        str(args)[:200], observation[:200])
