"""The conversation as data: how it is measured, how much of it fits, what goes
when it does not, and how it is published.

Everything here is about the MESSAGE LIST and nothing about what is said in it.
Both arms depend on that being one implementation: ``agent_mode`` is the
context BOUNDARY, so a budget, a trim policy or a size function that differed
between them would mix "saw less" with "did less" and put a harness parameter
inside the treatment.

The unit problem this module exists to solve: the window is a TOKEN limit, this
code can only count CHARACTERS, and the conversion is model-specific. It is
measured on the run's own traffic (:class:`TokenRatio`) rather than assumed,
because every response reports ``prompt_tokens`` for a prompt whose character
count is already known.

What is deliberately NOT here: the note that replaces trimmed turns and the
model-written summary folded into it (``compaction.py``), and the wording a
stage is given (``protocol.py``). This module drops turns; it never explains
them and never writes one.
"""
from __future__ import annotations

import json
import threading

from ..memory import Transcript


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

    The model's REASONING channel is read off the object too, when the backend
    reports one separately (``additional_kwargs["reasoning_content"]`` — what a
    serving-side reasoning parser splits out of ``content``). It belongs in the
    record: the transcript answers what this agent did, and thinking that only
    ever existed in a discarded field answers it for half the turn. It is NOT
    sent anywhere — the model is given the live message objects, never this
    copy, and an ``AIMessage``'s ``additional_kwargs`` does not survive the
    conversion to a request body, so the model is never shown its own
    reasoning back. It is likewise NOT counted by ``message_size``: that
    measures what is being sent, and this is not.
    """
    out: list[dict] = []
    for message in messages:
        reasoning = ""
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
            extra = getattr(message, "additional_kwargs", None)
            if isinstance(extra, dict):
                reasoning = str(extra.get("reasoning_content") or "")
        entry: dict = {"role": role, "content": str(content or "")}
        if name:
            entry["name"] = str(name)
        if isinstance(message, dict) and message.get(SUPERSEDED):
            # The record keeps what the agent was actually shown; the live
            # message — and so every size figure — holds the stub.
            entry[SUPERSEDED] = True
            entry["original_content"] = str(message.get("original_content") or "")
        if reasoning:
            entry["reasoning"] = reasoning
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
      ``tools``     tool calls and their results. On this harness that is most
                    of the context.

    The bound tool SCHEMAS are context too but are not in the message list, so
    they are reported beside this: folded in, the three would stop summing.
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

    Purely additive: with no consumer this is a no-op. NOT written into
    ``trajectory``/``trajectory_deep`` — the judge reads those and the
    benchmark compares them across arms, so a second copy of every artifact
    would change what is measured to serve a viewer.

    Published PER TURN while a run is watched, and once more when the loop
    ends. Skipped entirely when nobody is watching
    (``TrajectoryLogger.is_observed``): the emit is a no-op without a consumer,
    but SERIALIZING the transcript to build one is not, and a benchmark run
    must not pay it.

    The bound SCHEMAS go out too — under native tool calling they are half of
    what the model sees.

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
        "chars": prompt_chars(messages),
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
        memory.remember_context(Transcript(
            id=payload["id"], agent=agent, phase=phase, label=label, attempt=attempt,
            messages=payload["messages"], tools=payload["tools"],
            tokens={key: payload[key] for key in
                    ("chars", "budget", "tokens", "total_tokens", "token_budget",
                     "token_window", "token_reserve",
                     "schema_tokens", "ratio_measured", "compacted")}))


def prompt_chars(messages: list) -> int:
    """Prompt size over a mixed transcript: plain dicts AND the model's own
    message objects, which the tool-call round trip puts in the history.

    The ONLY prompt-size function: it counts ``tool_calls`` too, which is
    where a submit's artifact lives."""
    return sum(message_size(m) for m in messages)


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

    Not a tokenizer library and not a constant. ``tiktoken`` is OpenAI's
    vocabulary while the ladder serves Qwen, so it would be a different
    estimate rather than a correct one, and the real tokenizer means pulling
    ``transformers`` into a package the benchmark installs plain (see
    ``tests/test_import_isolation.py``).

    Every response reports ``prompt_tokens`` for a prompt whose character count
    we know, so dividing them gives this model's ratio on this run's own
    content, self-correcting per model and per artifact shape.

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


#: Marks the note compaction leaves in the conversation. A flag rather than a
#: string match, so the note's wording can change without changing what is
#: protected from the next trim.
COMPACTION_NOTE = "compaction_note"


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


#: Flag on a live tool-result message whose content was replaced by
#: ``SUPERSEDED_STUB``; its original rides beside it as ``original_content``.
SUPERSEDED = "superseded"
SUPERSEDED_STUB = "[superseded by a later read_alignment_state — use that one]"


def supersede_earlier(messages: list, name: str, keep_call_id: str, *,
                      prefix: str = "=== ALIGNMENT STATE") -> int:
    """Replace every EARLIER result of tool ``name`` still in the live
    transcript with a one-line stub, keeping the newest (``keep_call_id``).

    A state read is a snapshot, and an agent that reads, submits and reads
    again accumulates one per round. The old ones are wrong by then — a small
    model that re-reads its context acts on the stale one as readily as on the
    new — and each is up to ``READ_CHAR_BUDGET`` characters of a window that
    is already short. The message stays where it is with its ``tool_call_id``,
    so the request remains well-formed. The ORIGINAL is kept on the message
    (``original_content``) and published flagged by ``serialize_messages``:
    the record shows what the agent saw, the window holds what it needs.
    ``message_size`` reads ``content``, so the stub is what is counted —
    which is what is sent. Returns how many were replaced."""
    replaced = 0
    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "tool":
            continue
        if message.get("name") != name or message.get(SUPERSEDED):
            continue
        if message.get("tool_call_id") == keep_call_id:
            continue
        if not str(message.get("content", "")).startswith(prefix):
            continue        # a refused repeat or an error: not a snapshot
        message["original_content"] = message.get("content", "")
        message["content"] = SUPERSEDED_STUB
        message[SUPERSEDED] = True
        replaced += 1
    return replaced


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
    for key in [k for k, seen in seen_calls.items()
                if getattr(seen, "call_id", seen) in gone]:
        del seen_calls[key]


def trim_history(messages: list, budget: int = HISTORY_CHAR_BUDGET,
                 low_water: float = TRIM_LOW_WATER) -> tuple[list, list]:
    """Drop the OLDEST tool observations once the history exceeds ``budget``,
    draining it to ``budget * low_water``. Returns the kept messages and the
    DROPPED ones, in the order they were dropped.

    Kept unconditionally: the system message, the compaction note, and the
    tail. Everything else is droppable INCLUDING the stage turn, which the rest
    of the design is built to survive:

    * the TASK is in the design state — every artifact it asked for is
      committed there or named as missing by the tool results;
    * what the dropped turns ESTABLISHED goes into the note, folded there by
      the compaction hook (``core/agentic/compaction.py``);
    * the SCHEMA comes back: ``compact``'s ``restore`` re-attaches a stage turn
      a trim took, and ``respec`` re-attaches it on a rejection;
    * the TOOL MENU is redundant with the binding, which goes out with every
      request.

    Protecting the stage turn instead pins a block that grows with the schema
    at the front of the window it is supposed to be making room in.

    ONE policy for both arms: ``single`` hits it and ``multi`` does not, and
    that difference is the mechanism under test, so the policy must not differ.
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


def append_assistant(messages: list, turn) -> None:
    """The model's own message, appended once per model TURN.

    A batched reply is several calls sharing one assistant message: only the
    first carries it, and a sibling would otherwise put a duplicate of it in
    the history the next request sends.
    """
    if getattr(turn, "sibling", False):
        return
    messages.append(turn.message if turn.message is not None else {
        "role": "assistant", "content": getattr(turn, "text", "") or ""})


def answer_unexecuted(messages: list, calls: list, why: str, *,
                      trajectory, identity: str) -> bool:
    """Close the tool_call ids of calls that will NOT run, with a stub saying
    so. Returns whether anything was appended.

    The chat API requires every call in an assistant message to be answered, so
    a call the budget cannot cover — or one after the call that ended the run —
    leaves an open id in a history that is sent again. ONE implementation for
    both arms: the single arm re-sends its whole conversation every turn, so an
    id left open there is a malformed request on every following call, and an
    arm-specific version of this would be a transport difference sitting inside
    the decomposition axis.
    """
    calls = [c for c in calls if c and c.call_id]
    if not calls:
        return False
    append_assistant(messages, calls[0])
    for call in calls:
        messages.append({"role": "tool", "tool_call_id": call.call_id,
                         "name": call.name,
                         "content": f"[not executed — {why}.]"})
    trajectory.log_recovery_event(
        identity, "calls_not_executed", ", ".join(c.name for c in calls), why)
    return True
