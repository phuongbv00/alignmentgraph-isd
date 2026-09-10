"""The act→observe tool loop that runs one agentic step.

Transport is NATIVE tool calling: tools are bound with ``bind_tools`` and each
model turn comes back as ``.tool_calls``. The ladder serves this — vLLM with
``--enable-auto-tool-choice --tool-call-parser qwen3_coder`` (see
docs/benchmark_guides.md §3.2) — so the serving-side parser enforces the
argument shape before the text ever reaches us. That removes ONE measured
failure mode at the small end (a wrapped or bare artifact instead of a call);
it removes none of the others, so every guard below stays exactly as it was.

Deterministic scaffolding the loop keeps (the SLM-fit half of the design):

- the alignment docket is injected up front (``tools.alignment_docket``) —
  an enumerated checklist, which small models follow far more reliably than
  the quantified rules alone;
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
import re
import threading
import time
from dataclasses import dataclass

from .. import repairs
from ..brief import _format_design_brief
from ..checks import serialize_violations
from ..llm_io import (
    _extract_token_usage,
    _is_truncation_error,
    finish_reason,
    parse_json_response,
    was_truncated,
)
from ..memory import Memory, new_agent_run_id
from ..ratelimit import gate_for
from ..trajectory import WORKFLOW_ORCHESTRATOR
from . import budget, compaction, tools
from .specialists import STEPS, AgenticStep, missing_parts, parts_of, step_done
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
    #: whose structured values are still JSON strings. ``ToolLoop`` coerces it
    #: against the bound spec before anything reads it.
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


#: Every tool name the arm can ever bind. Protocol vocabulary, and therefore
#: words that must never appear in a design artifact.
#: NOT "submit": it is ordinary English ("learners submit their project"), and
#: including it made the gate fire on legitimate content — measured in run
#: single_20260831_160530, where the model then burned two turns arguing with
#: an error it could not act on ("I see the issue. The artifact is rejected
#: because it mentions `submit`..."). Every name here is underscored and has no
#: ordinary-English reading.
_PROTOCOL_WORDS = (
    "read_nodes", "read_node", "read_edges", "coverage_gaps",
    "list_documents", "read_document",
)


def protocol_leak_errors(section: object) -> list[str]:
    """Deterministic gate: tool names must not appear in the artifact.

    MEASURED FAILURE (run single_20260831_152628): all four arms leaked protocol
    vocabulary into judge-scored content — 33 occurrences in the full pipeline
    alone, including an assessment item that asked learners to map SDLC phases
    to "read_nodes" and "read_edges". react-isd, which has no such protocol,
    was clean. Development scored 28.9/100 on that arm.

    Same shape as the placeholder gate: a violation the model can fix if it is
    told, so it is returned as a rejected-submit error rather than silently
    repaired. Underscored names only — "list documents" as ordinary English is
    not a match, and only exact protocol tokens are.
    """
    if not isinstance(section, (dict, list)):
        return []
    blob = json.dumps(section, ensure_ascii=False)
    found = sorted({word for word in _PROTOCOL_WORDS
                    if re.search(rf"\b{re.escape(word)}\b", blob)})
    if not found:
        return []
    return [f"the artifact mentions tool names ({', '.join(found)}); tool names are "
            "protocol, never content — rewrite those parts in the language of the "
            "design itself"]


def _arg_shape(args: object) -> str:
    """``key:type`` for each argument, for the rejection record."""
    if not isinstance(args, dict):
        return type(args).__name__
    return ",".join(f"{k}:{type(v).__name__}" for k, v in sorted(args.items()))[:160]


def _spec_parameters(specs: list[dict], name: str) -> dict:
    """The declared parameter schema for one bound tool, or ``{}`` for a name we
    never offered (which the dispatcher answers with an ERROR observation)."""
    for spec in specs:
        function = spec.get("function") or {}
        if function.get("name") == name:
            return function.get("parameters") or {}
    return {}


def message_size(message: object) -> int:
    """Characters one message contributes to the next request.

    Counts ``tool_calls`` as well as ``content``, because that is where the
    payload actually is. An assistant turn that submits an artifact carries an
    EMPTY content and the whole artifact in its tool call — measured: the
    reported context_len was ~24k chars while the same run burned 744k tokens,
    because the one thing the single arm accumulates was the one thing the size
    function could not see. Undercounting here is not cosmetic: it is the
    headline quantity of the decomposition hypothesis, and it also decides when
    ``trim_history`` fires.
    """
    if isinstance(message, dict):
        content = message.get("content", "")
        calls = message.get("tool_calls")
    else:
        content = getattr(message, "content", "")
        calls = getattr(message, "tool_calls", None)
    total = len(str(content or ""))
    if calls:
        try:
            total += len(json.dumps(calls, ensure_ascii=False, default=str))
        except (TypeError, ValueError):
            total += len(str(calls))
    return total


def serialize_messages(messages: list) -> list[dict]:
    """The transcript as plain JSON-safe dicts.

    Needed because the transcript is MIXED: the tool-call round trip leaves the
    model's own message objects in it (that is how the tool_call ids survive),
    and those are not serializable. Their content and tool calls are read off
    with getattr, exactly as ``message_size`` counts them.

    Copies, always. The live list is appended to, trimmed, and — in the single
    arm — rewritten in place by ``_compact``, so a consumer handed the objects
    would be reading something that changes underneath it.
    """
    out: list[dict] = []
    for message in messages:
        if isinstance(message, dict):
            role = str(message.get("role") or "")
            content = message.get("content", "")
            calls = message.get("tool_calls")
            name = message.get("name") or ""
        else:
            role = "assistant"
            content = getattr(message, "content", "")
            calls = getattr(message, "tool_calls", None)
            name = ""
        entry: dict = {"role": role, "content": str(content or "")}
        if name:
            entry["name"] = str(name)
        if calls:
            try:
                entry["tool_calls"] = json.loads(
                    json.dumps(calls, ensure_ascii=False, default=str))
            except (TypeError, ValueError):
                entry["tool_calls"] = [{"raw": str(calls)}]
        out.append(entry)
    return out


def context_parts(messages: list) -> dict[str, int]:
    """The transcript split into what a reader can act on, in characters.

    A true PARTITION — the three sum to the transcript, so a bar drawn from
    them cannot lie about what filled the window:

      ``system``    the system turn: instructions and rules for the model.
      ``messages``  the conversation proper — user and assistant TEXT.
      ``tools``     tool calls and their results: the function names and
                    arguments the model asked for, and the data that came
                    back. On this harness that is most of the context, which
                    is exactly the thing worth seeing.

    The bound tool SCHEMAS are real context too but are not in the message
    list, so they are reported beside this rather than inside it — folding
    them in would make these three stop summing to the transcript.
    """
    parts = {"system": 0, "messages": 0, "tools": 0}
    for index, message in enumerate(messages):
        if isinstance(message, dict):
            role = str(message.get("role") or "")
            content = str(message.get("content") or "")
            calls = message.get("tool_calls")
        else:
            role = "assistant"
            content = str(getattr(message, "content", "") or "")
            calls = getattr(message, "tool_calls", None)
        if role == "system" or (index == 0 and not role):
            parts["system"] += len(content)
            continue
        if role == "tool":
            parts["tools"] += len(content)      # a tool RESULT
        else:
            parts["messages"] += len(content)
        if calls:
            # A submit's artifact lives HERE, not in content: an assistant turn
            # that submits carries empty content and the whole artifact in its
            # tool call.
            try:
                parts["tools"] += len(json.dumps(calls, ensure_ascii=False, default=str))
            except (TypeError, ValueError):
                parts["tools"] += len(str(calls))
    return parts




def _landed(step, state) -> tuple[str, ...]:
    """Which of ``step``'s declared artifacts the state now holds."""
    view = step.view(state) if hasattr(state, "element_nodes") else step.view_prose(state)
    return tuple(key for key, _type, _required in step.submit_fields if view.get(key))


def _still_needed(step, state) -> str:
    """What this stage already holds and what it still owes, from the STATE.

    ONE renderer, so the sentence cannot drift between the place a stage OPENS
    and the place a submit is answered. Computed from the state and never from
    `attempt` or any loop counter — the rule `missing_parts` already carries,
    because a regen resets a counter and the arms would then disagree.

    The gap it closes: a stage that gave up is re-run from a fresh context, and
    its opening turn was byte-identical to the first attempt's. It listed all
    six of `implementation`'s artifacts however many were already committed, so
    the retry re-issued every read and re-sent work
    that was done — on run 24343e4d, three such attempts at 55.6k prompt /
    11.7k completion tokens / 122 s. The single arm never had this hole: it
    never restarts a stage, and `_committed_note` tells it the same thing after
    every submit.
    """
    landed, left = _landed(step, state), missing_parts(step, state)
    if not landed or not left:
        return ""
    return (f"{step.name} still needs: {', '.join(left)}. "
            f"Already committed: {', '.join(landed)} — submit the next part on "
            "its own and do not resend those.")


def with_progress(brief: str, step, state) -> str:
    """A stage's contract, RE-attached, plus what the state says it still owes.

    The first issue of a brief needs nothing appended: the stage has committed
    nothing yet, `_still_needed` returns "", and this is the identity function
    — which is what keeps the opening turn byte-identical for the golden
    fixture, and what makes it correct to route every re-attachment through
    here without a flag.

    MEASURED FAILURE (run 46bd42a5, implementation): compaction dropped 20
    turns of a stage that had committed six of its seven artifacts, and
    `compact`'s `restore` put the contract back VERBATIM — ending, as every
    brief for a stage declared in parts does, "This stage has 7 of them:
    instructor_orientation, system_check, ...". Nothing in the re-attached turn
    said six of those were already committed, and the tool results that had
    said so were exactly what the trim took. The model read it as the stage
    starting and re-submitted the committed six, one per turn, until the ceiling
    ended the stage — nine turns, and `dev_plan`, the one artifact still
    genuinely missing and the whole point of the stage, was never written. The
    fan-out then divided the delivery deterministically, so what the
    `agent_mode` axis is supposed to measure — the agent's own grouping — came
    from the backstop instead.

    The sentence itself is `_still_needed`'s, not a second wording: the place a
    stage OPENS, the place a submit is answered and the place a contract comes
    BACK now say the same thing, computed from the same state.
    """
    resuming = _still_needed(step, state)
    return f"{brief}\n\n{resuming}" if resuming else brief


def _repair_request(stage: str, violations: list, round_index: int, rounds: int) -> str:
    """The user turn that hands a stage its own violations back.

    Deliberately concrete: each line is the check's own message plus its repair
    hint, because "fix the alignment" is the class of instruction this codebase
    has twice measured a small model failing to act on. The stage is named and
    the round is counted so the agent knows it is not starting over.
    """
    lines = []
    for violation in violations[:budget.REPAIR_REQUEST_CAP]:
        hint = getattr(violation, "repair_hint", "")
        lines.append(f"- {getattr(violation, 'message', violation)}"
                     + (f"\n  Fix: {hint}" if hint else ""))
    more = len(violations) - budget.REPAIR_REQUEST_CAP
    if more > 0:
        lines.append(f"- (+{more} more of the same kind)")
    return (
        f"COMMITTED, but {stage} does not check out yet "
        f"(round {round_index} of {rounds}):\n"
        + "\n".join(lines)
        + "\n\nFix these and submit the corrected artifact. Submit only what "
          "changes — what you have already committed stays committed. If a "
          "point is wrong or you cannot act on it, submit nothing and say why."
    )


def _merge_specs(seen: list, bound: list) -> list:
    """Tool schemas in first-seen order, deduped by name."""
    by_name = {(spec.get("function") or {}).get("name"): spec for spec in seen}
    merged = list(seen)
    for spec in bound:
        name = (spec.get("function") or {}).get("name")
        if name not in by_name:
            by_name[name] = spec
            merged.append(spec)
    return merged


def compacted_transcript(messages: list, compacted: list) -> list[dict]:
    """The WHOLE conversation, with the compacted part marked and in place.

    ``trim_history`` drops a contiguous run starting right after the system
    message, so the original order is exactly ``[system] + everything dropped
    so far + what is left``. Nothing has to record positions.

    Marked rather than merged away, and kept rather than counted: the Context
    tab answers "what was this agent shown", and a trimmed transcript answers
    that for the LAST call only. Everything the earlier calls saw would
    otherwise be gone but for a number in ``history_dropped`` — which says how
    much was lost and nothing about what.

    The marked messages are NOT part of the token figures: those measure what
    is being sent now, which is the thing the window constrains.
    """
    if not compacted:
        return serialize_messages(messages)
    head, tail = messages[:1], messages[1:]
    return (serialize_messages(head)
            + [{**message, "compacted": True} for message in serialize_messages(compacted)]
            + serialize_messages(tail))


def emit_context(trajectory, *, agent_run_id: str, agent: str, phase: str,
                 label: str, messages: list, specs: list[dict], attempt: int = 1,
                 budget: int = 0, config=None, memory=None,
                 compacted: list | None = None) -> None:
    """Publish one agent's WHOLE context — system turn, transcript, bound tool
    schemas — to the live consumer AND to the run's memory.

    Purely additive, like every other ``on_event`` emit: with no consumer this
    is a no-op and the recorded trajectory is byte-for-byte what it was. It is
    deliberately NOT written into ``trajectory``/``trajectory_deep``: the judge
    reads those, the benchmark compares them across arms, and doubling their
    size with a second copy of every artifact would change what is measured to
    serve a viewer.

    Published PER TURN while a run is being watched, and once more when the
    loop ends. A stage takes minutes and a context that only appears after its
    agent has finished shows the viewer nothing about the part it most wants to
    see — what the agent is doing right now. The per-turn emits are skipped
    entirely when nobody is watching (``TrajectoryLogger.is_observed``): the
    emit itself is a no-op without a consumer, but SERIALIZING the transcript
    to build one is not, and a benchmark run must not pay it.

    Under native tool calling the SCHEMAS are half of what the model sees, so a
    context view without them shows half the context. ``tests/fixtures/
    golden_prompts.json`` pins both for the same reason.

    ``memory`` is where it is KEPT, as opposed to broadcast. The live consumer
    is optional and only the app supplies one, so before this the CLI and the
    benchmark ran whole ladders whose contexts existed nowhere afterwards —
    the one record that answers "what was this agent shown" was available only
    to a viewer that happened to be watching. ``core.memory`` keeps it for
    every caller, and still never touches ``trajectory``.
    """
    parts = context_parts(messages)
    token_ratio = ratio_for(config)
    ratio = token_ratio.chars_per_token
    token_budget = prompt_token_budget(config) or int(
        (budget or HISTORY_CHAR_BUDGET) / ratio)
    payload = {
        # The AGENT RUN this belongs to, minted where the conversation started
        # (core.memory.new_agent_run_id). Everything downstream — the run's
        # memory, the server's live state, the browser merging live rows
        # against fetched transcripts — keys on it and none of them has to
        # know what a context's identity is made of.
        "id": agent_run_id,
        "agent": agent,
        "phase": phase,
        "label": label,
        "attempt": attempt,
        "messages": compacted_transcript(messages, compacted or []),
        # How much of that transcript is no longer being sent.
        "compacted": len(compacted or []),
        "tools": json.loads(json.dumps(specs, ensure_ascii=False, default=str)),
        "chars": _prompt_chars_any(messages),
        # The ceiling `chars` is measured against, sent with it so a viewer
        # never has to know the harness's constant to draw the bar — and so a
        # run recorded under a different budget still renders truthfully.
        "budget": budget or HISTORY_CHAR_BUDGET,
        # TOKENS, because tokens are what the window is measured in and what
        # actually runs out; characters are only what this code counts. The
        # conversion goes through the ratio measured on this run's own traffic,
        # so the viewer is shown the unit the constraint is expressed in rather
        # than the unit the implementation happens to use.
        "tokens": {name: int(count / ratio) for name, count in parts.items()},
        "total_tokens": int(sum(parts.values()) / ratio),
        "token_budget": token_budget,
        # What the budget is DERIVED from, carried so a viewer can explain the
        # number instead of just showing it: a budget of 8.2k under a 16.4k
        # window looks wrong until the 8.2k reserved for the reply is on screen
        # beside it. 0 = not configured, and then the budget is the historical
        # character constant converted at the measured ratio.
        "token_window": int(getattr(config, "llm_context_window", 0) or 0),
        "token_reserve": int(getattr(config, "llm_completion_reserve", 0) or 0),
        # The bound schemas: real context, but not in the message list, so
        # reported BESIDE the partition rather than folded into it.
        "schema_tokens": int(
            len(json.dumps(specs, ensure_ascii=False, default=str)) / ratio),
        "ratio_measured": token_ratio.measured,
    }
    trajectory.emit("context_snapshot", payload)
    if memory is not None:
        from ..memory import Transcript

        memory.remember_context(Transcript(
            id=payload["id"], agent=agent, phase=phase, label=label, attempt=attempt,
            messages=payload["messages"], tools=payload["tools"],
            tokens={key: payload[key] for key in
                    ("chars", "budget", "tokens", "total_tokens", "token_budget",
                     "token_window", "token_reserve",
                     "schema_tokens", "ratio_measured", "compacted")}))


def _prompt_chars_any(messages: list) -> int:
    """Prompt size over a mixed transcript: plain dicts AND the model's own
    message objects, which the tool-call round trip puts in the history.

    The ONLY prompt-size function: it counts ``tool_calls`` too, which is
    where a submit's artifact lives."""
    return sum(message_size(m) for m in messages)


class AgenticLLM:
    """Model caller for the agentic arm: native tool calling, truncation
    salvage, trajectory accounting.

    Tool calls are the ONLY way an AGENT reaches the model. That invariant is
    unchanged and load-bearing; what changed 2026-09-08 is that it is now
    stated about the agent rather than about this class, because the class also
    carries ``call_prose`` — the HARNESS's own call, made by the compaction
    hook under ``WORKFLOW_ORCHESTRATOR``, binding no tools and publishing no
    context. An agent never chooses to compact, so compaction is not an action
    in its protocol and must not be dressed as one; and the accounting both
    paths share (``_begin``/``_account``) is what keeps the hook's price on the
    books. Repairs never call the model at all (2026-09-03).

    The JSON-mode ``__call__`` this class used to carry stays gone and must not
    come back in any form: a summary written under
    ``response_format=json_object`` came back as JSON, was rejected as
    non-prose, and cost a full completion every time the window filled —
    measured on run e81b8108: three calls, 11.8k completion tokens, nothing
    kept. ``call_prose`` is that call with the one field that broke it removed.
    """

    def __init__(self, config, trajectory, identity: str) -> None:
        self.config = config
        self.trajectory = trajectory
        self.identity = identity

    def call_tools(self, messages: list[dict], tool_specs: list[dict]) -> ToolTurn:
        """One act turn with tools bound. Returns the model's tool call, or an
        empty :class:`ToolTurn` carrying whatever text it produced instead.

        No JSON retry here, deliberately: with native calling a non-call reply
        is not a parse failure to correct, it is the model choosing to talk.
        The loop answers that with a protocol nudge (and, when the text happens
        to BE a valid artifact, accepts it) — which is one turn either way, but
        without a wasted extra request. Truncation salvage stays: the 8192
        completion cap is what truncates a large ``submit``, and that is the
        same failure whatever the transport."""
        if self.config.llm_factory is None:
            self.trajectory.log_llm_call(0, 0)
            self.trajectory.log_recovery_event(
                self.identity, "llm_error", "", "llm_factory not set — cannot call LLM")
            return ToolTurn()
        raw_llm = self.config.llm_factory()
        try:
            # tool_choice="auto" is sent EXPLICITLY. LangChain's bind_tools
            # omits it, and vLLM's --enable-auto-tool-choice is what engages
            # the tool-call parser: without the field the server can hand the
            # call back as raw markup in `content` instead of parsing it into
            # `tool_calls`. Traced 2026-08-31 by diffing the harness's outgoing
            # payload against a probe that scored 100% well-formed in all four
            # transport x turn-shape cells — tool_choice was the only field
            # that differed.
            bound = raw_llm.bind_tools(tool_specs, tool_choice="auto")
        except TypeError:
            # A backend whose bind_tools does not take tool_choice.
            bound = raw_llm.bind_tools(tool_specs)
        except Exception as exc:  # noqa: BLE001 - a backend without tool support
            self.trajectory.log_recovery_event(
                self.identity, "tool_binding_unavailable", str(exc)[:120], "")
            return ToolTurn(binding_failed=True)
        try:
            return self._invoke_tools(bound, messages)
        except Exception as exc:
            if _is_truncation_error(exc):
                self.trajectory.log_recovery_event(
                    self.identity, "salvage_truncated", str(exc)[:80], "")
            self.trajectory.log_llm_call(0, 0)
            self.trajectory.log_recovery_event(self.identity, "llm_error", "", str(exc))
            return ToolTurn()

    def call_prose(self, messages: list[dict]) -> str:
        """One model call with NO tools bound and NO ``response_format``.

        Not an agent's turn: the ONLY caller is the compaction hook
        (``core/agentic/compaction.py``), which runs under
        ``WORKFLOW_ORCHESTRATOR`` and whose conversation is never published as
        any agent's context — ``tests/test_compaction.py`` enforces the
        one-caller rule. See the class docstring for why ``response_format``
        must never return on this path.
        """
        if self.config.llm_factory is None:
            self.trajectory.log_llm_call(0, 0)
            self.trajectory.log_recovery_event(
                self.identity, "llm_error", "", "llm_factory not set — cannot call LLM")
            return ""
        try:
            raw_llm = self.config.llm_factory()
            started = self._begin(messages)
            with gate_for(self.config).hold():
                result = raw_llm.invoke(messages)
        except Exception as exc:  # noqa: BLE001 - a summary is never load-bearing
            self.trajectory.log_llm_call(0, 0)
            self.trajectory.log_recovery_event(self.identity, "llm_error", "", str(exc))
            return ""
        content, _calls, _cut, _reasoning = self._account(result, messages, started)
        return content

    def _begin(self, messages: list[dict]) -> float:
        """Announce the call and start its clock.

        ``llm_started``/``llm_finished`` bracket every model call the package
        makes and are the only signal during the ~50 s one takes, so a new call
        path has to open with this or a watcher goes quiet for its duration."""
        self.trajectory.emit("llm_started", {
            "agent": self.identity,
            "prompt_chars": _prompt_chars_any(messages),
            "message_count": len(messages),
            "retries_left": 0,
        })
        return time.time()

    def _account(self, result, messages: list[dict],
                 started: float) -> tuple[str, list, bool, str]:
        """Everything a model call must leave behind: its flattened content, its
        tool calls, whether it was cut and its reasoning channel — plus
        ``llm_finished``, the chars-per-token measurement, the ``llm_call``
        action, the token totals and the thinking-only reply.

        ONE copy, so that a second way into the model (the compaction hook)
        cannot quietly leave the cost table."""
        content = getattr(result, "content", "") or ""
        if not isinstance(content, str):
            # Some backends return content as a list of blocks; the loop only
            # ever uses it as fallback text, so flatten rather than branch.
            content = " ".join(
                str(block.get("text", "")) if isinstance(block, dict) else str(block)
                for block in content)
        calls = list(getattr(result, "tool_calls", None) or [])
        prompt_tokens, completion_tokens = _extract_token_usage(result)
        duration_ms = (time.time() - started) * 1000
        self.trajectory.emit("llm_finished", {
            "agent": self.identity, "duration_ms": duration_ms,
            "response_chars": len(content), "tool_calls": len(calls),
            "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
        })
        stopped = finish_reason(result)
        # The tokenizer's own verdict on a prompt whose size we know: this is
        # what calibrates the transcript budget, and it arrives free with every
        # response.
        ratio_for(self.config).observe(_prompt_chars_any(messages), prompt_tokens)
        self.trajectory.log_action(
            "llm_call", agent=self.identity, duration_ms=duration_ms,
            prompt_chars=_prompt_chars_any(messages), response_chars=len(content),
            prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
            tool_calls=len(calls), finish_reason=stopped, attempt_of_retries_left=0)
        self.trajectory.log_llm_call(prompt_tokens, completion_tokens)
        extra = getattr(result, "additional_kwargs", None) or {}
        reasoning = str(extra.get("reasoning_content") or "") if isinstance(extra, dict) else ""
        if reasoning and not content.strip():
            # MEASURED (run 24343e4d): 12 of 78 calls, 47-405 billed completion
            # tokens each, every one charged a full stage turn as
            # `invalid_action`. Recorded HERE, at the one path EVERY model call
            # goes through — both arms and the compaction hook — so the rate is comparable across the axis and is
            # attributable to the serving posture rather than to the model. The
            # fix is `disable_thinking` on the factory; this is what makes its
            # absence visible when it is not set.
            self.trajectory.log_recovery_event(
                self.identity, "thinking_only_reply",
                f"{completion_tokens} completion tokens, no content, no tool call",
                reasoning[:200])
        return content, calls, was_truncated(result), reasoning

    def _invoke_tools(self, llm, messages: list[dict]) -> ToolTurn:
        started = self._begin(messages)
        with gate_for(self.config).hold():
            result = llm.invoke(messages)
        content, calls, cut, reasoning = self._account(result, messages, started)
        if not calls:
            return ToolTurn(text=content, message=result, truncated=cut,
                            reasoning=reasoning)
        # Raw here; the loop coerces against the SPEC it bound (only it knows
        # which tool this name refers to and what types that tool declares).
        # One ToolTurn per call, all sharing the model's message: the first
        # carries the rest as `calls`, and `truncated` rides on every one
        # because it is the LAST call of a cut batch that is incomplete and
        # only the caller knows which that is.
        turns = [ToolTurn(name=str(call.get("name") or "").strip(), args=call.get("args"),
                          call_id=str(call.get("id") or ""), text=content if i == 0 else "",
                          message=result, sibling=i > 0, truncated=cut)
                 for i, call in enumerate(calls)]
        turns[0].calls = tuple(turns[1:])
        return turns[0]


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
"""




#: How much prompt history the loop will carry, in characters. The ladder serves
#: ``--max-model-len 16384`` against an 8192 completion cap, so the input budget
#: is ~8k tokens; at the pessimistic ``COLD_CHARS_PER_TOKEN`` below this leaves
#: headroom for the completion.
#: It is a CHARACTER budget on purpose — a token count would need the tokenizer
#: of whichever model is serving, and this has to be identical across the ladder
#: or the ``agent_mode`` axis would be trimmed differently at each size.
HISTORY_CHAR_BUDGET = 24000

#: Cold-start chars-per-token, used only until the first real call reports its
#: prompt size. Deliberately PESSIMISTIC: under-estimating shrinks the budget
#: and costs some retained history, while over-estimating builds a prompt that
#: does not fit and the request fails outright.
COLD_CHARS_PER_TOKEN = 3.0


class TokenRatio:
    """Characters per token, MEASURED on this run's own traffic.

    Not a tokenizer library, and not a constant. A library would be the wrong
    tokenizer: ``tiktoken`` is OpenAI's vocabulary and the ladder serves Qwen,
    so it would be a different estimate rather than a correct one, and loading
    the model's real tokenizer means pulling ``transformers`` plus the vocab
    files into a package that the benchmark installs plain (see
    ``tests/test_import_isolation.py``).

    The exact answer is already arriving: every response reports
    ``prompt_tokens`` for a prompt whose character count we know. Dividing them
    gives this model's real ratio on this run's real content — the tokenizer's
    own verdict, observed rather than approximated, at no cost and with no
    dependency. It self-corrects per model and per artifact shape, which no
    fixed number and no foreign vocabulary can.

    Kept per RUN, not per agent, so both arms calibrate off the same traffic.
    """

    def __init__(self) -> None:
        self._chars = 0
        self._tokens = 0
        self._lock = threading.Lock()

    def observe(self, chars: int, prompt_tokens: int) -> None:
        # Both must be real: a provider that reports no usage leaves the ratio
        # where it is rather than driving it to zero.
        if chars <= 0 or prompt_tokens <= 0:
            return
        with self._lock:
            self._chars += chars
            self._tokens += prompt_tokens

    @property
    def chars_per_token(self) -> float:
        with self._lock:
            if self._tokens <= 0:
                return COLD_CHARS_PER_TOKEN
            # Never let a measurement RAISE the estimate above the cold value:
            # the budget it feeds is a safety limit, and a ratio measured on
            # prose-heavy turns would license a prompt that a JSON-heavy turn
            # then overflows.
            return min(self._chars / self._tokens, COLD_CHARS_PER_TOKEN)

    @property
    def measured(self) -> bool:
        return self._tokens > 0


_RATIO_LOCK = threading.Lock()


def ratio_for(config) -> TokenRatio:
    """The run's token ratio, built once per config object and cached on it —
    the same per-run caching ``ratelimit.gate_for`` uses, and for the same
    reason: every agent in a run is handed the SAME config instance."""
    if config is None:
        return TokenRatio()
    ratio = getattr(config, "_token_ratio", None)
    if isinstance(ratio, TokenRatio):
        return ratio
    with _RATIO_LOCK:
        ratio = getattr(config, "_token_ratio", None)
        if isinstance(ratio, TokenRatio):
            return ratio
        ratio = TokenRatio()
        try:
            config._token_ratio = ratio
        except Exception:  # noqa: BLE001 - a stub config just gets a fresh one
            pass
        return ratio


def prompt_token_budget(config) -> int:
    """Tokens the transcript may occupy, or 0 when the window is unknown."""
    window = int(getattr(config, "llm_context_window", 0) or 0)
    if window <= 0:
        return 0
    reserve = int(getattr(config, "llm_completion_reserve", 0) or 0)
    # A floor, so a misconfigured window cannot leave a budget too small to
    # hold the system turn — which trim never drops, and which would then be
    # the whole prompt with nothing else able to survive beside it.
    return max(1024, window - reserve)


def history_budget(config) -> int:
    """The transcript budget in CHARACTERS, from the serving window when it is
    known and the historical constant otherwise.

    Characters because that is what ``trim_history`` and ``message_size``
    count; the conversion uses the ratio measured on this run's own traffic, so
    it sharpens as the run proceeds instead of staying an assumption.

    One number for BOTH arms. The ``agent_mode`` axis is the context BOUNDARY;
    a budget that varied by arm would make them spend different effort and mix
    "saw less" with "did less".
    """
    tokens = prompt_token_budget(config)
    if tokens <= 0:
        return HISTORY_CHAR_BUDGET
    return int(tokens * ratio_for(config).chars_per_token)

#: The instructed workflow. Both arms get this, verbatim: the pivot makes the
#: agents autonomous in HOW they execute a stage, never in WHAT ORDER the stages
#: run. Stating it once here (and nowhere else) is what keeps that true.
def _workflow_overview() -> str:
    """The instructed stage order, GENERATED from the step table.

    It was a hand-written list, and it drifted: it still named a "rubrics"
    stage months after that stage was removed, so every agent in every run was
    told to expect a seventh step that does not exist. A list beside the table
    that defines the thing is a list that will disagree with it — the same
    lesson as the planner's per-block budget, which is interpolated from
    ``max_units`` rather than typed out.

    The ORDER itself is instructed in both arms deliberately: it is the
    workflow, and the axis is who holds the context, not who decides the
    sequence.
    """
    names = [step.name for step in STEPS]
    numbered = "  ".join(f"{i}. {name}" for i, name in enumerate(names, start=1))
    return (
        "You are working through the ADDIE instructional-design process in "
        f"this fixed order:\n{numbered}\n"
        "Each stage is given to you in turn. Work only on the stage you are given."
    )


_WORKFLOW_OVERVIEW = _workflow_overview()


#: Marks the note compaction leaves in the conversation. A flag rather than a
#: string match, so the note's wording can change without changing what is
#: protected from the next trim.
COMPACTION_NOTE = "compaction_note"

#: The header a stage's turn carries, and the regex that finds it again. ONE
#: marker: the turn IS the brief.
#:
#: Reading the stage name back OUT of the text is what lets one implementation
#: serve both arms — the multi arm builds this turn per stage loop and the
#: single arm has it injected into its one conversation as each stage comes up,
#: and neither difference reaches `brief_stages`/`lost_briefs`/`respec`.
STAGE_BRIEF_HEADER = "--- STAGE: {stage} ---"
_BRIEF_HEADER_RE = re.compile(
    re.escape(STAGE_BRIEF_HEADER).replace(re.escape("{stage}"), r"(\S+)"))


def stage_brief_block(step) -> str:
    """One stage's turn: the header, then its task, schema and rules.

    The stage marker deliberately does NOT use the "=== HEADER ===" form: that
    form means "injected prior-artifact context" everywhere else in the package
    (the docket and the scenario use it, and readers — the test fixture
    included — strip on it). A stage boundary is neither."""
    return f"{STAGE_BRIEF_HEADER.format(stage=step.name)}\n{step.task_block()}"


def brief_stages(messages: list) -> set[str]:
    """Which stages' briefs are still in this transcript."""
    found: set[str] = set()
    for message in messages:
        content = message.get("content", "") if isinstance(message, dict) else ""
        found.update(_BRIEF_HEADER_RE.findall(str(content or "")))
    return found


def lost_briefs(kept: list, dropped: list) -> list[str]:
    """Stages whose brief went with this trim and is not still live elsewhere.

    Subtracting what survived is what makes the note stage-precise instead of a
    blanket nudge: in the single arm, stage X's brief can be gone while stage
    Y's is intact, and telling that agent to re-fetch everything spends the
    shared budget it is already short of."""
    return sorted(brief_stages(dropped) - brief_stages(kept))


def respec(messages: list, step, brief: str) -> str:
    """The stage's contract, re-attached to a rejection when it has fallen out
    of the transcript.

    MEASURED FAILURE (run single_20260901_162455): the graph arm was told
    "assessment_plan.lo_coverage_targets is missing" 15 times and the prose arm
    "needs_analysis.gaps must be a non-empty list" 48 times, each time
    submitting the same broken shape again — corrected against a specification
    it could no longer see. And from the other arm (run 2b9e911a,
    implementation): once compaction took the brief, the model invented
    ``instructor_guidance`` and ``session_guides`` as a dict, was rejected
    eight times across three regens, and the artifact never committed.

    Re-attached only when it is actually gone, because it is up to 7,400
    characters and pasting it onto every rejection would push out the very
    transcript it is meant to sit beside. Pasted rather than merely asked for:
    a paste costs no turn and is certain to arrive, and that run is three
    regens of evidence that a small model does not act on general advice.
    """
    if step.name in brief_stages(messages):
        return ""
    return "\n\nThe contract for this stage, again:\n" + brief


#: What replaces what was taken away. The bracketed part is always true and
#: costs nothing — only observations are dropped, and their findings are in the
#: design state — so it stands whatever the summariser does. A model-written
#: summary of the dropped turns is folded in AFTER it by ``compaction_note``
#: when the compaction hook delivered one (``core/agentic/compaction.py``); a
#: run where it never does reads exactly as this note has always read. Keeping
#: the two separable is the point: the count is a fact about the trim, the
#: summary is a claim by a model, and a reader of the transcript can tell them
#: apart.
_COMPACTED_NOTE = (
    "[{count} earlier turn(s) of this conversation were removed to stay inside "
    "the context window — the oldest tool results, nothing you were told to do. "
    "Their findings are in the design state: read them again with the tools "
    "above if you need them. Everything since is intact.]"
)


#: Appended to the note when the trim took a stage's CONTRACT with it. The
#: standing note says the dropped findings are in the design state, which is
#: true of tool results and false of the brief — the schema is not in the
#: design state at all. MEASURED (run 2b9e911a): the brief went on turn 9 of
#: the implementation stage, the model was told its findings were recoverable,
#: and it invented field names for the rest of the stage. `forget_compacted_calls`
#: already clears the repeat guard for the dropped result, so the re-fetch this
#: asks for is permitted — the permission existed and the instruction did not.
_BRIEF_LOST_NOTE = (
    " The stage turn for {stages} went with them, so you no longer have the "
    "schema or the field names — submit only what you are certain of, and the "
    "contract comes back with any rejection."
)


def compaction_note(count: int, lost: tuple | list = (), *,
                    summary: str = "") -> dict:
    """The note itself, as a turn the model actually sees.

    The bracket closes before the summary begins: the count and the brief-lost
    sentence are harness facts, the summary is a model's account of turns the
    model can no longer see, and running them together would let the second
    borrow the authority of the first.

    The summary rides as a key on the dict as well as in the text, so the next
    fold reads it back with ``running_summary`` instead of parsing its own
    prose out of the note. ``serialize_messages`` drops unknown keys before
    anything is sent, exactly as it already does for ``COMPACTION_NOTE``.
    """
    content = _COMPACTED_NOTE.format(count=count)
    if lost:
        content = content.rstrip("]") + _BRIEF_LOST_NOTE.format(
            stages=", ".join(lost)) + "]"
    if summary.strip():
        content += f"\n\nWhat those turns established:\n{summary.strip()}"
    return {"role": "user", "content": content,
            COMPACTION_NOTE: True, "summary": summary}


def running_summary(messages: list) -> str:
    """The summary the current note carries, for the next fold to build on."""
    for message in messages:
        if isinstance(message, dict) and message.get(COMPACTION_NOTE):
            return str(message.get("summary") or "")
    return ""


def _with_note(messages: list, count: int, lost: tuple | list = (), *,
               summary: str = "") -> list:
    """The transcript with its compaction note current — one note, rewritten,
    never a second one. It sits where the dropped turns were: after the system
    turn (the only one `trim_history` protects) and before what survived."""
    head = messages[:1]
    body = [m for m in messages[1:]
            if not (isinstance(m, dict) and m.get(COMPACTION_NOTE))]
    return head + [compaction_note(count, lost, summary=summary)] + body


def compact(messages: list, dropped: list, total: int, *, trajectory,
            stats: dict, restore=None, budget: int = 0, llm=None) -> list:
    """Record what just went, in the conversation and in the trace.

    ONE implementation, called identically by both arms — which is what makes
    the difference between them a measurement. ``single`` carries one
    conversation all run and reaches this often; ``multi`` starts each stage
    fresh and barely reaches it at all. That gap is the decomposition axis
    showing its own mechanism, and ``stats`` counts it so the cost can be
    stated rather than implied.

    ``llm`` is the compaction HOOK's model caller — an ``AgenticLLM`` built
    with the ``WORKFLOW_ORCHESTRATOR`` identity, never the agent's own. Given
    one, the turns being dropped are folded into a rolling summary that rides
    in the note (``core/agentic/compaction.py``); given ``None``, the note is
    the count alone and nothing else changes. That fallback is not only for
    tests: every failure mode of the hook lands on it, so a compaction always
    succeeds whatever the model does.

    The hook is the harness's call, not the agent's — the agent did not choose
    to compact and is never shown that conversation, so nothing is bound for it
    and no context is published in the agent's name. ``stats`` carries both
    ``compactions`` and ``compaction_summaries``, and the difference is the
    hook's failure rate on this model.
    """
    stats["compactions"] = stats.get("compactions", 0) + 1

    # A dropped stage BRIEF is not like a dropped observation. The note's
    # standing promise — the findings are in the design state, read them again —
    # is true of a tool result and false of the contract, which is not in the
    # design state at all. So the contract is put BACK, at the tail, where it is
    # newest and the next trim (oldest first) will not take it.
    #
    # Re-attaching beats asking: it costs no turn and is certain to arrive,
    # where a note asking the model to re-fetch costs a turn and depends on it
    # complying — and run 2b9e911a is three regens of a model that did not.
    # It is not PROTECTED in place, which is a different thing and was rejected:
    # a `role: "tool"` message cannot be hoisted the way the note is (the
    # assistant turn that made the call has to precede it), and pinning it would
    # fix a block at the front of the very window it has to make room in.
    lost = lost_briefs(messages, dropped)
    restored: list[tuple[str, str]] = []
    still_lost: list[str] = []
    for stage in lost:
        brief = restore(stage) if restore is not None else None
        # Only if it FITS in what the trim just freed. Draining to the
        # low-water mark leaves room by construction, but a brief is up to
        # 7,400 characters and a small budget could put the transcript straight
        # back over the line and trim again on the next turn.
        if brief and (not budget or _prompt_chars_any(messages) + len(brief) <= budget):
            restored.append((stage, brief))
        else:
            still_lost.append(stage)

    previous = running_summary(messages)
    summary, outcome = previous, "count only"
    if llm is not None:
        with trajectory.acting_as(WORKFLOW_ORCHESTRATOR):
            summary, outcome = compaction.summarize(llm, previous, dropped)
        if outcome == "summarised":
            stats["compaction_summaries"] = stats.get("compaction_summaries", 0) + 1

    # The note names only what could not be put back, so a model whose contract
    # is sitting right there is not sent to fetch it again.
    kept = _with_note(messages, total, still_lost, summary=summary)
    for _stage, brief in restored:
        kept.append({"role": "user", "content": brief})

    trajectory.log_recovery_event(
        WORKFLOW_ORCHESTRATOR, "context_compacted",
        f"{len(dropped)} turn(s), {total} total"
        + (f", stage brief re-attached: {', '.join(s for s, _ in restored)}" if restored else "")
        + (f", stage brief lost: {', '.join(still_lost)}" if still_lost else ""),
        # Both facts — the outcome and the resulting size — because the paper
        # reports the hook's failure rate against what it was spent on.
        f"{outcome}; live context now {_prompt_chars_any(kept)} chars")
    return kept


def empty_stage_stats() -> dict:
    """The per-stage instrumentation record, SAME keys whatever path a stage
    took: both loops start from it and ``run.py`` zero-fills from it, so a
    reader can tell "this stage made no dispatch call" from "this field was
    never written". Without these the context hypothesis cannot be tested and
    the low end of the ladder cannot be read at all.

    ``via_budget_exhaustion``: whether the TURN CEILING is what ended the
    stage. Reported for BOTH arms because the ``agent_mode`` claim rests on
    neither arm having been CUT by its budget.
    ``compactions`` / ``compaction_summaries``: how often the window filled
    (``single`` reaches this constantly, ``multi`` barely — the axis showing
    its own mechanism) and how many of those folds the model delivered; the
    difference is the compaction hook's failure rate on this model.
    ``repair_turns``: turns spent fixing the stage's OWN violations, kept
    apart so the decomposition axis is not read off a mixed turn count.
    ``thinking_only``: replies carrying reasoning and nothing else — a
    property of the SERVING posture, not of the axis.
    ``tool_errors``: tool calls that came back ERROR (13% of every tool
    result over runs 53042a0d/2559b22d), so the ceiling is read against
    turns that DID something.
    ``n_sets``..``set_submits_rejected``: the Developer tier's own counters,
    kept separate so "the dispatch OR any one of ten sets gave up" is not one
    number."""
    return {"turns_used": 0, "submits_rejected": 0, "repeated_calls": 0,
            "history_dropped": 0, "gave_up": False, "reads": 0,
            "via_budget_exhaustion": False,
            "compactions": 0, "compaction_summaries": 0,
            "context_len": 0, "batched_calls": 0, "markup_recovered": 0,
            "args_salvaged": 0, "truncated_turns": 0, "dropped_args": 0,
            "repair_turns": 0, "thinking_only": 0, "tool_errors": 0,
            "n_sets": 0, "sets_gave_up": 0, "set_turns": 0,
            "set_submits_rejected": 0}


def turns_left_hint(remaining: int) -> str:
    """The countdown a loop appends to a tool observation near its ceiling.

    ONE implementation and one wording for both arms — see
    ``budget.TURNS_LEFT_WARNING`` for why, and why the countdown exists at
    all. Empty until the ceiling is close, so an ordinary turn is unchanged.
    """
    if remaining > budget.TURNS_LEFT_WARNING:
        return ""
    if remaining <= 0:
        return "\n\n[No turns left. This was your last observation.]"
    return (f"\n\n[{remaining} turn(s) left. Submit what you have now — "
            "an incomplete submit is better than none.]")


#: What an empty turn is answered with. ONE constant, used by both loops: it
#: lands in the transcript, the transcript is what the model sees, and a nudge
#: worded differently on each side of the decomposition axis is a second
#: variable.
INVALID_TURN_NUDGE = (
    "Invalid turn: you must CALL A TOOL, not answer with text. Call one of "
    "the listed tools, or call submit with the complete artifact.")
#: What a reasoning-only turn is answered with. Separate from the above because
#: the model did not answer with text either — telling it "not text" when it
#: wrote none is an instruction it cannot act on.
THINKING_ONLY_NUDGE = (
    "Your last reply carried reasoning but no answer and no tool call, so "
    "nothing reached this stage. Call a tool now — put the result in the tool "
    "call itself, not in your reasoning.")


#: Once the history overflows ``budget``, how far below it a trim brings it:
#: the low-water mark, as a fraction of the budget.
#:
#: Trimming to JUST under the budget was measured (run e81b8108, implementation
#: stage) to refire on every following turn — one or two turns went each time,
#: the next observation put the history back over the line, and one stage
#: compacted three times where one would have done. Each firing is a note the
#: model has to read past AND a model call — the compaction hook folds the
#: dropped turns into a summary — so a refiring trim spends a completion
#: each time to say a little more about a little less.
#: Draining to half the budget gives the conversation room to grow again
#: before the next trim, so compaction is an event rather than a steady state.
TRIM_LOW_WATER = 0.5


def forget_compacted_calls(seen_calls: dict, dropped: list) -> None:
    """Drop from the repeat guard every call whose RESULT compaction just took
    away. The guard refuses a second answer to a call already answered — but
    an answer the model can no longer see is not one it has, and the
    compaction note tells it to read again. Measured on the test fixture
    once trims began draining to the low-water mark: the single arm re-asked
    for a stage brief it had lost and was refused 133 times."""
    gone = {m.get("tool_call_id") for m in dropped
            if isinstance(m, dict) and m.get("role") == "tool"}
    gone.discard(None)
    for key in [k for k, call_id in seen_calls.items() if call_id in gone]:
        del seen_calls[key]


def trim_history(messages: list, budget: int = HISTORY_CHAR_BUDGET,
                 low_water: float = TRIM_LOW_WATER) -> tuple[list, list]:
    """Drop the OLDEST tool observations once the history exceeds ``budget``,
    draining it to ``budget * low_water``. Returns the kept messages and the
    DROPPED ones, in the order they were dropped.

    Kept unconditionally: the system message (persona + workflow + scenario),
    the compaction note, and the tail. Everything else is droppable, including
    the stage turn — deliberately, and it is what makes the rest of the design
    hang together:

    * the TASK survives in the design state — every artifact it asked for is
      committed there or still listed as missing, which the tool results say;
    * what the dropped turns ESTABLISHED survives in the note, folded there by
      the compaction hook (``core/agentic/compaction.py``) — an improvement on
      the count, never something the rest of this list depends on;
    * the SCHEMA and rules are in the turn and go back into it: `compact`'s
      ``restore`` re-attaches a stage turn a trim took, and a rejection
      re-attaches it too (``respec``);
    * the TOOL MENU is redundant with the binding — the schemas go out with
      every single request under native tool calling — so losing its prose
      costs nothing.

    Protecting the turn instead was the first answer and the wrong one: it
    pins a block that grows with the schema at the front of a window it is
    supposed to be making room in.

    The same policy runs in both arms, which is the point: ``single`` hits it
    and ``multi`` does not, and that difference is the mechanism under test, so
    the policy itself must not differ. ``history_dropped`` is reported per stage
    — if it goes high early, the arm is hitting a wall rather than degrading,
    and the result means something different.
    """
    def size(msgs) -> int:
        return sum(message_size(m) for m in msgs)

    if size(messages) <= budget or len(messages) <= 3:
        return messages, []
    target = int(budget * low_water)
    head, rest = messages[:1], list(messages[1:])
    # The compaction note is standing furniture, like the system turn above it:
    # pulled out here so a later trim cannot drop the very message that says
    # something was dropped — and that now carries the summary of it.
    note = [m for m in rest if isinstance(m, dict) and m.get(COMPACTION_NOTE)]
    body = [m for m in rest if not (isinstance(m, dict) and m.get(COMPACTION_NOTE))]
    dropped: list = []
    # Keep at least the last two entries: the live stage instruction and
    # whatever answered it. Below that there is nothing left to trim.
    while len(body) > 2 and size(head + note + body) > target:
        dropped.append(body.pop(0))
    # The dropped run is CONTIGUOUS and starts right after the system turn,
    # which is what lets a caller rebuild the whole conversation in order as
    # `[system] + everything dropped so far + what is left`. Nothing has to
    # record positions, and the compacted part of a transcript can be shown
    # where it actually happened rather than as a count.
    return head + note + body, dropped




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
    REPEAT_ALLOWANCE = budget.REPEAT_ALLOWANCE
    THINKING_ALLOWANCE = budget.THINKING_ALLOWANCE
    ERROR_ALLOWANCE = budget.ERROR_ALLOWANCE
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
        self._summariser = AgenticLLM(config, trajectory, WORKFLOW_ORCHESTRATOR)
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
        #: Per-stage instrumentation, read by ``run_agentic_brief`` into
        #: ``metadata.autonomy`` — see ``empty_stage_stats`` for the keys.
        self.stats: dict = empty_stage_stats()
        #: ``node_type -> heading`` for artifact pools the assignment already
        #: renders in full. Empty for a stage agent, which reads real state.
        self._resolved_labels: dict[str, str] = dict(
            getattr(step, "resolved_labels", ()) or {})

    @property
    def graph_mode(self) -> bool:
        return hasattr(self.state, "element_nodes")

    def _validate(self, section: dict) -> list[str]:
        """The step's own deterministic checks, plus the protocol-leak gate.
        Composed here rather than inside the step table because the gate is a
        property of the TRANSPORT, not of the artifact contract: it catches a
        model that echoes a tool name into the artifact, which the step's own
        checks have no reason to know about."""
        return list(self.step.validate(section)) + protocol_leak_errors(section)

    # ── prompt assembly ─────────────────────────────────────────────────────
    def _retrieval_available(self) -> bool:
        from ..rag.planner import RetrievalPlanner

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
        return (f"{self.persona}\n\n{_WORKFLOW_OVERVIEW}\n\n"
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
        protocol = _PROTOCOL.format(
            menu=tools.tool_menu(self.step, retrieval_available=retrieval_available,
                                 graph_mode=self.graph_mode),
            max_turns=self.MAX_TURNS,
            grounding=_GROUNDING if readable else "",
        )
        # The stage marker deliberately does NOT use the "=== HEADER ===" form:
        # that form means "injected prior-artifact context" everywhere else in
        # the package (the docket and the scenario use it, and readers — the
        # test fixture included — strip on it). A stage boundary is neither.
        # The WHOLE task block in the stage turn, PUSHED rather than fetched
        # by a tool: fetched, the contract could be compacted away with
        # nothing to put it back (run 2b9e911a); pushed, `compact`'s
        # `restore` re-attaches it.
        parts = [stage_brief_block(self.step), protocol]
        resuming = _still_needed(self.step, self.state)
        if resuming:
            parts.append(resuming)
        if self.step.docket and self.graph_mode:
            docket = tools.alignment_docket(self.state, **self.step.docket)
            if docket:
                parts.append(docket)
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
        # Only the artifacts still open. On a first attempt nothing has landed,
        # so this is the full set the golden fixture pins; on a regen it stops
        # the model being offered tools for work already done.
        open_now = tuple(key for key, _t, _r in self.step.submit_fields
                         if key not in set(_landed(self.step, self.state))) or None
        specs = tools.tool_specs(self.step, only=open_now, graph_mode=self.graph_mode,
                                 retrieval_available=retrieval_available)
        # ACCUMULATED across the conversation, not replaced. A loop that
        # continues another's messages may bind a narrower set — the replan
        # round binds only `submit_dev_plan`, because a plan is the one thing
        # it is asking for — and publishing just the live binding made the
        # merged row claim the agent never had `submit_assessment_plan`, which
        # is how it wrote the plan in the first place. The row answers "what
        # tools did this agent have", and the transcript beside it shows which
        # were called when.
        self._specs = _merge_specs(self._specs, specs)
        # Before the first model call: a stage takes minutes, and what the
        # agent was ASKED is the thing a viewer wants first.
        self._publish(live=True)

        # Accepted submits, for a step whose artifact arrives in parts.
        self._accepted = 0
        #: Rejected submits so far, PER ARTIFACT: a rejected artifact costs
        #: THAT artifact (`tools.submit_specs`), never the stage — one counter
        #: for the stage let three bad guesses at one `implementation`
        #: artifact abandon the five beside it and trigger a whole-stage regen
        #: (run 24343e4d: 55.6k prompt / 11.7k completion / 122 s).
        self._submit_attempts: dict[str, int] = {}
        #: The best REJECTED submit of each artifact, accumulated as ONE
        #: section (each rejected payload is already the `{artifact: {...}}`
        #: envelope, so merging them keeps the shape `_commit` wants).
        #: Committed only if the stage ends without a valid one. Deliberately
        #: not committed at rejection time: an invalid artifact under its own
        #: key is truthy to `_landed`, so it would shrink `missing_parts`,
        #: satisfy `step_done` and skip the regen — which is how run 24343e4d
        #: shipped an unusable guide.
        self._best: dict = {}
        # call key -> the tool_call id it was answered under, so a result
        # compaction removes can be forgotten (forget_compacted_calls).
        self._seen_calls: dict[str, str] = {}
        self._refunded = 0
        # Turns spent so far. ONE PER EXECUTED CALL, not per model reply: a
        # reply carrying three calls costs three, which is what keeps the
        # budget the honest unit of work now that every call runs.
        self._turn_no = 0
        while self._turn_no < self.MAX_TURNS + self._refunded:
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
                self.stats["context_len"], _prompt_chars_any(self.messages))
            turn = self.llm.call_tools(self.messages, specs)
            self.stats["batched_calls"] += len(turn.calls)
            if turn.binding_failed:
                # No tool loop is possible against this endpoint. Going round
                # the budget would spend MAX_TURNS x 6 stages of requests to
                # learn the same thing, so give up at once.
                self._give_up("no valid submit")
                return

            # Every call the reply carried, in the order the model made them.
            # A call the budget cannot cover, or one after the call that ended
            # the stage, is still ANSWERED — with a stub saying it did not run
            # — so no tool_call id is left open in a history the single arm
            # sends again.
            queue = [turn, *turn.calls]
            for index, call in enumerate(queue):
                if self._turn_no >= self.MAX_TURNS + self._refunded:
                    self._answer_unexecuted(queue[index:], "the turn budget ran out first")
                    break
                self._turn_no += 1
                self.stats["turns_used"] += 1
                if self._handle_call(call, specs, stage_message) == "return":
                    self._answer_unexecuted(queue[index + 1:], "the stage ended first")
                    return

        self.stats["via_budget_exhaustion"] = True
        # Whatever was rejected along the way is still the MODEL's work, and
        # with a per-artifact budget the ceiling — not the submit budget — is
        # now the usual way a struggling stage ends. Dropping `_best` here
        # would discard it exactly when it is most likely to be all there is.
        self._give_up("turn budget exhausted", last_resort=self._best or None)

    def _handle_call(self, turn: ToolTurn, specs: list, stage_message: str) -> str:
        """One tool call, judged and answered. ``"return"`` ends the stage,
        ``"continue"`` hands the loop the next call or the next model turn."""
        if not turn:
            # The server may have left a correctly-formed call as text.
            # Recover it before treating the turn as prose: otherwise a
            # serving hiccup costs a turn and reads as a model mistake.
            recovered = (tools.parse_tool_call_markup(turn.text)
                         or tools.parse_tool_call_json(turn.text))
            if recovered is not None:
                self.stats["markup_recovered"] += 1
                self.trajectory.log_recovery_event(
                    self.identity, "tool_call_markup_recovered",
                    recovered[0], (turn.text or "")[:100])
                turn = ToolTurn(name=recovered[0], args=recovered[1],
                                call_id=turn.call_id, text=turn.text,
                                message=turn.message)

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
            # No tool call. A model that answered with the bare artifact and
            # got it right has done the work — accept it as an implicit
            # submit rather than burning turns on protocol pedantry (SLM
            # tolerance). Anything else is an invalid turn.
            # warn=False: the model was not asked for JSON on this turn, it
            # was asked to call a tool. A failed parse here is the ordinary
            # case, not something to shout about in the run log.
            parsed = parse_json_response(turn.text, warn=False) if turn.text else {}
            if isinstance(parsed, dict) and parsed:
                section, errors = unwrap_section(parsed, self._validate)
                if not errors:
                    self._commit(section, stage_message, turn.text,
                                 note="implicit_submit")
                    return "return"
            if turn.thinking_only:
                # Not an invalid ACTION: no action was taken, and the reply was
                # not the model choosing to talk. Refunding it keeps the stage
                # budget on the stage's work — the same argument REPEAT_ALLOWANCE
                # already makes, for a turn that likewise produces no
                # observation and no artifact.
                self.stats["thinking_only"] += 1
                if self.stats["thinking_only"] <= self.THINKING_ALLOWANCE:
                    self._refunded += 1
                self._append_text_turn(turn, THINKING_ONLY_NUDGE)
                return "continue"
            self.trajectory.log_recovery_event(
                self.identity, "invalid_action", (turn.text or "")[:100], "")
            self._append_text_turn(turn, INVALID_TURN_NUDGE)
            return "continue"

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

        # Coerce against the spec this tool name was bound with, BEFORE
        # anything reads the arguments: a structured value that arrived as
        # text is a transport artifact, not a model mistake, and must not
        # be charged to the model's submit budget (measured: it cost every
        # stage of every arm its whole budget — see tools.coerce_args).
        salvaged: list[str] = []
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
                  else _spec_parameters(specs, turn.name))
        args = tools.coerce_args(params, turn.args, salvaged=salvaged)
        self.stats["args_salvaged"] += len(salvaged)
        if turn.truncated and not turn.sibling:
            self.stats["truncated_turns"] += 1

        if turn.name.startswith("submit_"):
            args = self._wrap_bare_artifact(turn.name, args)
            args = self._fill_single_key_object(args)
            # Drop what cannot be read, THEN judge what is left. An
            # unreadable argument beside a valid artifact is a dropped
            # argument, not a reason to refuse the artifact; an unreadable
            # argument the artifact needed is the reason it failed, and
            # then — and only then — the model is told about the shape.
            unreadable = tools.shape_bad_keys(params, args)
            for key in unreadable:
                args.pop(key, None)
            section, errors = unwrap_section(args, self._validate)
            if errors and unreadable:
                shape = tools.shape_errors(params, args, unreadable)
                errors = shape + [e for e in errors if e not in shape]
            artifact = turn.name[len("submit_"):]
            spent = self._submit_attempts.get(artifact, 0)
            if errors and spent < self.SUBMIT_BUDGET:
                self._submit_attempts[artifact] = spent = spent + 1
                self.stats["submits_rejected"] += 1
                # Record the argument SHAPE alongside the errors. "expected
                # dict, got str" has two very different causes — a parser
                # that handed the value over as text, or a model that wrote
                # prose where an object belongs — and only the shape tells
                # them apart. Both the RAW shape and the coerced one,
                # because `coerce_args` answers an unparseable argument
                # object with `{}`: recording only the coerced shape made
                # "the parser gave us nothing" and "the model sent nothing"
                # the same empty string in the record (measured: nine
                # rejections reading `args=` on run single_20260901_205901,
                # with no way to tell which had happened).
                self.trajectory.log_recovery_event(
                    self.identity, "submit_rejected",
                    f"{artifact} attempt {spent} | raw={_arg_shape(turn.args)}"
                    f" | args={_arg_shape(args)}"
                    + (" | TRUNCATED" if turn.truncated else ""),
                    "; ".join(errors)[:200])
                self._append_tool_turn(
                    turn, self._reject_message(errors, turn) + self._respec())
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
                left = missing_parts(self.step, self.state)
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
                self._give_up("submit budget spent", last_resort=self._best)
                return "return"
            if unreadable:
                self.stats["dropped_args"] += len(unreadable)
                self.trajectory.log_recovery_event(
                    self.identity, "dropped_argument", ", ".join(unreadable),
                    "arrived as text where a structure was declared; "
                    "the rest of the submit was valid and was accepted")
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
                    else turn.name[len("submit_"):])
            before = set(_landed(self.step, self.state))
            self._commit(section, stage_message,
                         json.dumps(args, ensure_ascii=False), note=note,
                         duplicate=bool(self._accepted))
            landed = set(_landed(self.step, self.state))
            left = missing_parts(self.step, self.state)
            self._accepted += 1
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
                fixable = self._own_violations()
                if fixable and self.stats["repair_turns"] < self.repair_turns:
                    self.stats["repair_turns"] += 1
                    self._append_tool_turn(turn, _repair_request(
                        self.step.name, fixable, self.stats["repair_turns"],
                        self.repair_turns))
                    return "continue"
                if fixable:
                    # Outstanding violations and no repair turn left: say
                    # so, or "the model could not fix this" and "we did not
                    # give it another turn" are indistinguishable — and the
                    # second is a harness parameter, not a finding.
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
            self._append_tool_turn(
                turn, "COMMITTED. " + _still_needed(self.step, self.state))
            return "continue"

        # Anti-loop guard: an identical repeated call gets no second
        # answer — measured failure: a 2B model burned its whole turn
        # budget on six identical read_nodes calls, then needed the
        # fallback. The repeat still costs a turn (the budget is the hard
        # stop) but is recovery plumbing, not a judge-visible tool call,
        # and the observation pushes the model toward submitting.
        call_key = f"{turn.name}:{json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)}"
        if call_key in self._seen_calls:
            self.stats["repeated_calls"] += 1
            # A repeat produces no observation and no artifact, so charging
            # a turn for it spends the budget on the model's confusion and
            # leaves less for its work — measured: 19 of A0's turns. Refund
            # it, but only up to REPEAT_ALLOWANCE, or a model that only ever
            # repeats would never reach the fallback.
            if self.stats["repeated_calls"] <= self.REPEAT_ALLOWANCE:
                self._refunded += 1
            self.trajectory.log_recovery_event(
                self.identity, "repeated_tool_call", turn.name, str(args)[:100])
            self._append_tool_turn(turn, (
                f"You already made this exact {turn.name} call and its result has not "
                "changed. Do not repeat calls — use what you have and submit your "
                "artifact, or call a different tool."))
            return "continue"
        self._seen_calls[call_key] = turn.call_id

        observation = self._execute(turn.name, args)
        self.stats["reads"] += 1
        if observation.startswith("ERROR"):
            # No observation and no artifact — the same case REPEAT_ALLOWANCE
            # and THINKING_ALLOWANCE already refund, and measured at 13% of
            # every tool result over runs 53042a0d and 2559b22d. Bounded, so a
            # model that only ever errors still reaches the ceiling.
            self.stats["tool_errors"] += 1
            if self.stats["tool_errors"] <= self.ERROR_ALLOWANCE:
                self._refunded += 1
        observation += turns_left_hint(self.MAX_TURNS + self._refunded - self._turn_no)
        # The logged tool name carries its scoping argument so the
        # judge-visible trace distinguishes read_nodes(objective) from
        # read_nodes(assessment) — same-name entries with different
        # targets otherwise read as redundant repeats to the BFCL judge.
        scope = str(args.get("node_type") or args.get("relation_id")
                    or args.get("key") or "").strip()
        tool_label = f"tool_{turn.name}" + (f"_{scope}" if scope else "")
        self.trajectory.log_step(
            self.identity, tool_label,
            str(args)[:200], observation[:200])
        self._append_tool_turn(turn, observation)
        return "continue"


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
        """The model's message, appended once per model turn: a sibling call
        shares it with the call before it, which already put it there."""
        if turn.sibling:
            return
        self.messages.append(turn.message if turn.message is not None else {
            "role": "assistant", "content": turn.text or ""})

    def _answer_unexecuted(self, calls: list, why: str) -> None:
        """Close the tool_call ids of calls that will not run, with a stub that
        says so. The chat API requires every call to be answered."""
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
        self._publish(live=True)

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
        already = self._already_in_assignment(action, args)
        if already:
            return already
        executor = tools.executors_for(graph_mode=self.graph_mode).get(action)
        if executor is None:
            return ("ERROR: unknown tool " + repr(action)
                    + ". Use one of the listed tools, or submit.")
        return executor(self.state, self.step, args)

    def _own_violations(self) -> list:
        """This stage's outstanding violations, and a note in the ledger that
        they reached an agent.

        The hook is on the INSTANCE wrapper, not on the staticmethod: callers
        that only have a graph (tests, one-offs) go through the latter and have
        no memory to write to.

        Every other call site pairs a check round with BOTH
        ``trajectory.log_violations_result`` (the ``check`` event
        ``aggregate._review_findings`` reads to synthesize
        ``expert_review.findings``) and ``memory.observe_violations`` (the
        ledger ``result["violations"]`` serves) — see ``run.py``; a violation
        whose ONLY sighting is here (report-only types like P10/P11, which
        skip the deterministic net) must reach both.

        Attributed to ``WORKFLOW_ORCHESTRATOR``, like every other check round
        (``test_work_done_outside_a_tool_loop_is_the_orchestrator_s``): the
        collection pass is the same deterministic function called everywhere
        else, run by the harness rather than chosen by the agent — the agent's
        own act is answering the repair-request turn that follows, not the
        check that produced it."""
        found = self.own_violations(
            self.state, self.design_brief, self.step, self.trajectory)
        if found:
            round_no = self.trajectory.log_violations_result(
                serialize_violations(found, self.identity), agent=WORKFLOW_ORCHESTRATOR)
            self.memory.observe_violations(
                found, round=round_no,
                phase=self.label, family=self.step.family, shown_to_agent=True)
        return found

    @staticmethod
    def own_violations(state, design_brief, step, trajectory) -> list:
        """This stage's own violations — only the ones this agent, right now,
        can actually clear with a submit.

        Structural fixes run FIRST and are not shown: pruning a dangling
        reference or substituting a Bloom verb from the taxonomy is exact and
        free, and spending a model turn on what a lookup does perfectly is the
        waste this whole loop has been trimming. What reaches the agent is what
        is left — the part that needs writing.

        Two things are NOT the part that needs writing, and both were measured
        (test fixture, 2026-09-03) to consume every repair turn in the run:

        * **A work set's own loop sees nothing.** Its commit is a no-op — the
          driver deposits all sets together once the loops close — so the state
          cannot yet show what this Developer just submitted, and every
          violation it would be handed is one its own submit already answered.
          All five AssessmentDevelopers were shown the same `C2`/`plan_coverage`
          gap they had each just filled.
        * **A Designer whose family has a Developer tier sees only its own
          sections.** The element-level checks of that family (`C2`,
          `plan_coverage`, `item_completeness`, the Bloom cross-check) read
          artifacts the tier has not written yet. Asking the Designer to fix
          them is asking it to fix an absence it has no schema to fill: the
          AssessmentDesigner spent all four of its turns on it, re-read the
          same nodes, and finally wrote ``{"action": "Add C2 link for ILO-01"}``
          into its plan — inventing the appearance of a fix, which is the exact
          failure `REPORT_ONLY` and the template purge exist to prevent.

        Neither is dropped from the run: both are collected again by the
        deterministic net after the fan-out and by the reconciliation pass, and
        what nothing can fix is counted as residual. What changes is that
        nobody is asked to fix what they cannot reach.
        """
        from ..outputs import _collect_violations, _collect_violations_prose
        from .fanout import SPECS

        if not step.commits_to_state:
            return []

        graph_mode = hasattr(state, "element_nodes")
        families = [f for f in (step.family, *step.also_repairs)
                    if f in repairs.OWNED_BY_FAMILY]

        def owned() -> list:
            found: list = []
            for family in families:
                violations = (_collect_violations(family, state, design_brief)
                              if graph_mode
                              else _collect_violations_prose(family, state))
                found += [v for v in violations
                          if v.violation_type in repairs.OWNED_BY_FAMILY[family]]
            return found

        ctx = repairs.RepairContext(
            graph=state if graph_mode else None,
            store=None if graph_mode else state,
            trajectory=trajectory, actor=WORKFLOW_ORCHESTRATOR)
        for family in families:
            structural = [v for v in owned()
                          if v.violation_type in repairs.STRUCTURAL
                          and v.violation_type in repairs.OWNED_BY_FAMILY[family]]
            if structural:
                repairs.repair(family, structural, ctx)

        # Everything left after the free fixes, INCLUDING the REPORT_ONLY
        # types. That set says the deterministic net must not write content —
        # it never said the agent cannot. These are precisely the violations
        # only a writer can answer (an activity with no engagement strategy, a
        # criterion its rubric contradicts), and the agent is the writer.
        remaining = owned()
        if graph_mode and step.name in SPECS:
            # The tier has not run. A section node is what this Designer wrote;
            # an element node is what its Developers will write.
            sep = type(state).ELEMENT_SEP
            remaining = [v for v in remaining if sep not in str(v.node_id)]
        return remaining

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
        `dev_plan -> instrument_sets` / `activity_blocks`; it finds nothing for
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
                lookup = self.step.schema_keys.get(key, key)
                properties = (tools.ARTIFACT_SCHEMAS.get(lookup) or {}).get("properties") or {}
                if len(properties) == 1:
                    cached[key] = next(iter(properties))
            object.__setattr__(self.step, "_single_key_cache", cached)
        return cached

    def _wrap_bare_artifact(self, tool: str, args: dict) -> dict:
        """``submit_dev_plan({"instrument_sets": …})`` means
        ``{"dev_plan": {"instrument_sets": …}}``.

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

    @staticmethod
    def _submit_alias(specs: list, args) -> str:
        """Which bound submit tool a bare ``submit`` meant: the one whose
        artifact the payload actually carries, else the stage's first."""
        offered = [name for name in tools.tool_names(specs)
                   if name.startswith("submit_")]
        if isinstance(args, dict):
            for name in offered:
                if name[len("submit_"):] in args:
                    return name
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
        if not self._resolved_labels or action not in ("read_nodes", "read_document"):
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
        from ..rag.planner import RetrievalPlanner

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
        landed_before = set(_landed(self.step, self.state))
        if valid:
            self.capture["section"] = section
        commit = self.step.commit if self.graph_mode else self.step.commit_prose
        commit(self.state, self.trajectory, section)
        action = f"design_{self.step.name}" + (f"_{note}" if note else "")
        if valid and duplicate and not (set(_landed(self.step, self.state)) - landed_before):
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
        return with_progress(stage_brief_block(self.step), self.step, self.state)

    def _respec(self) -> str:
        """The contract, re-attached to a rejection when it is no longer in the
        transcript. Same rule and same function as the single arm's.

        The backstop to `compact`'s `restore`: a turn can be gone for reasons a
        trim did not report (a regen starting a fresh message list, a stage
        turn dropped before this loop's own restore could run)."""
        return respec(self.messages, self.step,
                      with_progress(stage_brief_block(self.step), self.step, self.state))

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
        # The best the MODEL managed, committed as-is rather than discarded: it
        # is the agent's own work, and the repair net can mend it.
        errors = self._validate(last_resort)
        self._commit(last_resort, "", "", note="incomplete", valid=not errors)
