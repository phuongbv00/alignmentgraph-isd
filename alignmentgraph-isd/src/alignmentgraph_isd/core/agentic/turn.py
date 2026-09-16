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

import json
from dataclasses import dataclass

from . import budget, tools
from .protocol import INVALID_TURN_NUDGE, THINKING_ONLY_NUDGE, turns_left_hint
from .tools import unwrap_section


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
    #: The model's REASONING channel, when the backend reports one separately
    #: (`additional_kwargs["reasoning_content"]` — vLLM's reasoning parser, and
    #: what LangChain does with it). Carried only so an empty turn can be told
    #: apart from a talkative one: a reply that is all reasoning and no answer
    #: is a serving posture, not the model refusing the protocol, and charging
    #: the two identically makes a serving artifact read as a finding about the
    #: model. `finish_reason` is "stop" for these, so `truncated` cannot see
    #: them either. Never sent back to the model and never in the transcript.
    reasoning: str = ""

    def __bool__(self) -> bool:
        return bool(self.name)

    @property
    def thinking_only(self) -> bool:
        """The reply carried reasoning and nothing else — no answer, no call."""
        return bool(self.reasoning) and not (self.text or "").strip() and not self.name


class TurnMeter:
    """What a loop has spent, and what it is given back.

    Three kinds of reply produce NO observation and NO artifact: an exact
    repeat of a call already answered, a call that came back ERROR, and a reply
    that was all reasoning. Charging the ceiling for them spends the budget on
    the model's confusion and leaves less for its work — measured at 19 of A0's
    turns for repeats alone, and 13% of every tool result over runs 53042a0d
    and 2559b22d for errors. Each is therefore refunded, and each is BOUNDED by
    its allowance in :mod:`budget`, or a model that only ever repeats would
    never reach the ceiling at all.

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

    def thinking_only(self) -> None:
        """A reply that was reasoning and nothing else. Not an invalid ACTION:
        no action was taken, and it was not the model choosing to talk — it is
        a property of the serving posture (the fix is ``disable_thinking`` on
        the factory), so charging it would make a serving artifact read as a
        finding about the model."""
        self._refund("thinking_only", budget.THINKING_ALLOWANCE)

    def repeated(self) -> None:
        """An exact repeat of a call already answered."""
        self._refund("repeated_calls", budget.REPEAT_ALLOWANCE)

    def tool_error(self) -> None:
        """A tool call whose observation came back ERROR."""
        self._refund("tool_errors", budget.ERROR_ALLOWANCE)

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


def nudge_for(turn: ToolTurn, *, meter: TurnMeter, trajectory, identity: str) -> str:
    """What an empty turn is answered with, and its entry in the record.

    A reasoning-only reply gets its own wording, because telling a model "not
    text" when it wrote none is an instruction it cannot act on.
    """
    if turn.thinking_only:
        meter.thinking_only()
        return THINKING_ONLY_NUDGE
    trajectory.log_recovery_event(
        identity, "invalid_action", (turn.text or "")[:120], "")
    return INVALID_TURN_NUDGE


def coerce(turn: ToolTurn, params: dict, *, stats: dict) -> dict:
    """The call's arguments, parsed against the spec the tool was BOUND with.

    Before anything reads them: a structured value that arrived as text is a
    transport artifact, not a model mistake, and must not be charged to a
    submit budget — measured, it cost every stage of every arm its whole
    budget (see ``tools.coerce_args``).
    """
    salvaged: list[str] = []
    args = tools.coerce_args(params, turn.args, salvaged=salvaged)
    stats["args_salvaged"] = stats.get("args_salvaged", 0) + len(salvaged)
    if turn.truncated and not turn.sibling:
        stats["truncated_turns"] = stats.get("truncated_turns", 0) + 1
    return args


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
        + (" | TRUNCATED" if turn.truncated else ""),
        "; ".join(errors)[:200])


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


def log_read(trajectory, identity: str, name: str, args: dict, observation: str) -> None:
    """The judge-visible entry for one read.

    The tool name carries its scoping argument so the trace distinguishes
    ``read_nodes(objective)`` from ``read_nodes(assessment)`` — same-name
    entries with different targets otherwise read as redundant repeats to the
    BFCL judge.
    """
    scope = str(args.get("node_type") or args.get("relation_id")
                or args.get("key") or "").strip()
    trajectory.log_step(identity, f"tool_{name}" + (f"_{scope}" if scope else ""),
                        str(args)[:200], observation[:200])
