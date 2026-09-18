"""Summarising what compaction takes out of an agent's context.

When a conversation outgrows the window, ``trim_history`` removes the oldest
tool observations. What replaces them is a deterministic NOTE ("N turns went,
their findings are in the design state") plus, from this module, a model-written
SUMMARY of the dropped turns folded into that note. The summary is ROLLING:
each compaction folds the previous one and the newly dropped turns into a
single note, so the note stays a fixed size however long the run gets and each
call's input is bounded.

**This is a HOOK OF THE HARNESS, not an action of the agent.** The agent did
not choose to compact, is not shown this conversation, and has nothing bound
for it — a ``submit_summary`` tool would dress an intervention made over the
agent's head as a move in its own protocol. The call goes out through
``AgenticLLM.call_prose``: no tools, no ``response_format``, attributed to
``ORCHESTRATOR``, never published as one of that agent's contexts, and
its tokens still on the cost table.

That prose path is the only one in the package. A call under the OWNING AGENT'S
name would be a second conversation inside that agent's context boundary, which
``tests/test_one_agent_one_system_prompt.py`` rules out; ``tests/
test_compaction.py`` asserts that ``call_prose`` has exactly one caller in
``src/`` and that it is this module.

**On the arm asymmetry.** ``single`` carries one conversation for the whole
brief and compacts constantly; ``multi`` starts each stage fresh and barely
does. The trigger, the prompt, the budget and the fallback are ONE
implementation shared by both, so what differs is only how often the window
fills — the mechanism the decomposition axis is about, not a confound.
``metadata.autonomy`` reports ``compactions`` and ``compaction_summaries`` per
stage; the difference is the summariser's failure rate on this model.

**On the transport.** ``call_prose`` must send no ``response_format``: asking
for prose down a JSON-mode path costs a full completion for nothing, since a
compliant backend answers with a JSON object and ``_clean`` rejects it as
non-prose (measured on run e81b8108: every compaction logged "count only",
three calls and 11.8k completion tokens kept nothing). ``_clean`` also SALVAGES
a JSON-wrapped answer rather than discarding it.

Failure is always safe: an empty or unusable answer falls back to the PREVIOUS
summary, never to empty, or a bad fold would erase what earlier ones kept.

**What the summary is asked to keep.** The Keep list is ORDERED and leads with
the agent's progress through the stage; the Drop clause names design CONTENT
rather than "anything committed", which a model reads as covering the fact of
having committed it. Measured on run 46bd42a5, whose implementation stage
compacted with six of seven artifacts in: the fold described the DESIGN ("SPI
protocol simulations, plan sets AB-01 through AB-12"), all of it state the
agent can read back with its own tools, while the one fact that is NOT
re-readable — six submitted, one owed — went missing.

A prompt is a request, not a guarantee. The deterministic guarantee for the
same failure is ``protocol.with_progress``, which appends ``still_needed`` to
every RE-attached contract, so what the stage owes comes back from the state
whether or not the summariser cooperated.
"""
from __future__ import annotations

import re

from ..llm_io import parse_json_response
from ..trajectory import ORCHESTRATOR
from .protocol import BRIEF_HEADER_RE, lost_briefs
from .transcript import COMPACTION_NOTE, prompt_chars, serialize_messages

#: Characters of dropped material one summarisation may read. Past this the
#: oldest of the dropped turns are themselves elided — a summary of a summary
#: is where this kind of thing stops meaning anything, and the note already
#: says the findings are re-readable from the design state.
MAX_INPUT_CHARS = 12000

#: Characters the running summary may occupy in the live context. It is
#: standing furniture now — never trimmed — so it has to be small enough that
#: it never becomes the reason the window is full.
MAX_SUMMARY_CHARS = 1200

_SYSTEM = (
    "You compress the older part of another agent's working transcript so it "
    "can keep going inside a context window. You are not doing its work and "
    "you are not judging it. You write a RECORD of what happened, never "
    "instructions: you are not in that agent's conversation, you cannot see "
    "the turns it still has, and it cannot answer you."
)

_TASK = """\
The turns below were removed from an instructional designer's context to make \
room. Fold them, together with the running summary of everything removed \
earlier, into ONE replacement summary.

Keep, in this order of priority: (1) where the agent had got to — which \
artifacts it has already submitted, and what it was last told is still \
missing; (2) instructions and constraints it was given that still bind; (3) \
artifact ids and names it must refer to and could not re-derive. Drop: \
tool-call mechanics, repetition, and the CONTENT of artifacts already \
committed — the agent reads those back from the design state with its tools, \
and re-telling it what its own design says spends this summary on the one \
thing it does not need.

Write it in the past tense, as a record. Never address the agent, never tell \
it what to do next, and never say that its work is finished or that nothing \
more is needed — you are summarising turns that are already over and you \
cannot see what it still has to do.

Write plain prose under {limit} characters. No preamble, no headings, no \
markdown. If there is nothing worth keeping, answer with nothing at all.

=== RUNNING SUMMARY SO FAR ===
{previous}

=== TURNS BEING REMOVED NOW ===
{dropped}"""


def summarize(call_llm, previous: str, dropped: list) -> tuple[str, str]:
    """The new running summary and why it is what it is.

    ``call_llm`` is an :class:`~client.AgenticLLM` built with the
    ``ORCHESTRATOR`` identity — see the module docstring for why this
    is the harness's call and not the agent's.

    The outcome is returned rather than inferred. v1 returned the summary
    alone and its caller decided success by ``summary != previous``, which
    cannot tell a model that failed from a fold that had nothing worth
    keeping — and the first of those is a finding about the model while the
    second is a property of the trim. One of ``summarised``,
    ``nothing_dropped``, ``unusable``, ``error``.
    """
    body = _render(dropped)
    if not body.strip():
        # A compaction that removed nothing summarisable must not spend a call.
        return previous, "nothing_dropped"
    prompt = _TASK.format(limit=MAX_SUMMARY_CHARS,
                          previous=previous.strip() or "(nothing removed before now)",
                          dropped=body)
    try:
        answer = call_llm.call_prose([{"role": "system", "content": _SYSTEM},
                                      {"role": "user", "content": prompt}])
    except Exception:  # noqa: BLE001 - a summary is never load-bearing
        return previous, "error"
    text = _clean(answer)
    if not text:
        # Deliberately the PREVIOUS summary, not empty: a failed call must not
        # also erase what earlier ones managed to keep.
        return previous, "unusable"
    # A cut summary is a shorter summary — unlike an artifact it has no
    # required fields to be missing — and the cap truncates it anyway.
    return text[:MAX_SUMMARY_CHARS], "summarised"


def _render(dropped: list) -> str:
    """The dropped turns as text, newest last, oldest elided past the cap.

    A dropped STAGE BRIEF is excluded, and that exclusion is load-bearing:

    * ``compact`` already re-attaches a lost brief VERBATIM at the tail, and
      ``respec`` re-attaches it verbatim on any rejection — so summarising it
      is work done twice for a worse copy;
    * budget: ``respec`` measures the contract at up to 7,400 characters
      against ``MAX_INPUT_CHARS`` 12,000, so one dropped ``implementation``
      brief would take 62% of the whole input allowance and push the tool
      results — the only thing a summary can usefully carry — out through the
      elision below;
    * a PROSE PARAPHRASE of a JSON schema, sitting in a protected,
      never-trimmed message, is a second and worse source of truth for field
      names than the contract it paraphrases. That is how run 2b9e911a's model
      came to invent ``instructor_guidance`` and a dict ``session_guides``.

    One predicate covers all three places a brief can come from: the multi
    arm's stage turn, the single arm's injected contract, and a ``respec``
    re-attachment — every one of them carries ``STAGE_BRIEF_HEADER``.

    An assistant turn's tool calls are rendered as ``[called <names>]`` — the
    NAMES, never the arguments. Keep it that way: the arguments of a ``submit``
    are the agent's own committed artifact, the longest thing in a multi-arm
    transcript, and feeding it back in would spend the input budget
    re-summarising what the design state already holds.
    """
    lines = []
    for message in serialize_messages(dropped):
        content = str(message.get("content") or "").strip()
        if content and BRIEF_HEADER_RE.search(content):
            continue
        calls = message.get("tool_calls") or []
        if calls:
            names = ", ".join(str(c.get("name") or "?") for c in calls)
            content = f"[called {names}] {content}".strip()
        if content:
            lines.append(f"{message.get('role', '?')}: {content}")
    text = "\n".join(lines)
    if len(text) <= MAX_INPUT_CHARS:
        return text
    return "[…older removed turns elided…]\n" + text[-MAX_INPUT_CHARS:]


def _clean(answer) -> str:
    """Prose, or nothing.

    A model asked for plain text under a system prompt it has never seen
    before answers with a refusal, an apology or an empty JSON object often
    enough to be worth naming: none of those is a summary, and committing one
    would put invented framing into the record of what an agent was shown.

    A JSON-WRAPPED summary is salvaged rather than discarded, and that is the
    one real behavioural change from v1. Nothing asks for JSON any more, so an
    object here is the model's own choice — and a small model told to write
    prose wraps it in ``{"summary": "..."}`` often enough that throwing the
    answer away is throwing away a completion we already paid for. Exactly one
    string value is taken; two or more and there is no way to tell which is the
    summary, so it is rejected as before.

    A DIRECTIVE is then dropped sentence by sentence (``_drop_directives``).
    The prompt asks for a record and not for instructions; this is what holds
    when the model ignores that, which run 3ee5b8df is a measurement of. If it
    leaves nothing behind, the caller falls back to the previous summary like
    any other unusable answer.
    """
    text = str(answer or "").strip()
    if not text or text in ("{}", "[]", "null", "None"):
        return ""
    if text.startswith("{") or text.startswith("["):
        text = _unwrap(text)
    # Last, so it applies to a salvaged answer too — a directive does not
    # become acceptable for having arrived wrapped in JSON.
    return _drop_directives(text)


#: Sentences a summary is not allowed to contain, dropped one sentence at a
#: time rather than by rejecting the whole answer.
#:
#: MEASURED (run 3ee5b8df, implementation): the fold came back "The agent has
#: already submitted and analyzed plan sets AB-01 through AB-04 … No further
#: calls are needed." Both halves are wrong — AB-* is the ACTIVITIES stage's
#: work, and the stage went on to need eleven more turns — but the second half
#: is wrong in a way the first is not: it is an INSTRUCTION, sitting in the one
#: message ``trim_history`` never drops, telling the agent to stop. The
#: summariser is a hook of the harness with no view of the agent's remaining
#: turns and no standing to direct it (see the module docstring), so a
#: directive from it is out of scope by construction, not merely inaccurate.
#:
#: The prompt asks for a record in the past tense; this is what makes it hold
#: when the model does not comply, and run 3ee5b8df is one that did not. Kept
#: DELIBERATELY NARROW — a general imperative detector would eat "the brief
#: required the design to use slides", which is exactly the binding constraint
#: the summary exists to carry. Only two shapes are matched: a claim that
#: nothing further is needed, and a sentence that addresses the agent in the
#: second person about what to do.
_DIRECTIVE_PATTERNS = (
    # "No further calls are needed", "nothing more is required", "no additional
    # work is needed" — a completeness verdict the summariser cannot reach.
    re.compile(r"\b(?:no|nothing)\b[^.!?]{0,60}?"
               r"\b(?:further|more|additional|else)\b[^.!?]{0,60}?"
               r"\b(?:needed|required|necessary|remains?|left)\b", re.I),
    # "you should now", "you must submit", "you need to call" — second person
    # plus a directive verb. "You" alone is not enough: "you were told the
    # deadline is fixed" is a record.
    re.compile(r"\byou\b\s+(?:should|must|need to|can now|may now|will now|"
               r"are now|have to)\b", re.I),
    # Bare imperatives the model opens a sentence with. A short, closed list of
    # verbs that only ever direct — never "use", "make" or "ensure", which
    # start plenty of honest reported clauses.
    re.compile(r"^(?:do not|don't|proceed|continue|stop|move on|next,|"
               r"submit |call |skip )", re.I),
)

#: Sentence boundaries, kept simple on purpose: a summary is plain prose under
#: 1,200 characters, and an over-clever splitter is a second thing to be wrong.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _drop_directives(text: str) -> str:
    """The summary with any sentence that directs the agent removed.

    Sentence-level, never answer-level: run 3ee5b8df's fold carried a real
    account of the stage AND a "no further calls are needed", and throwing away
    a completion already paid for because of its last sentence would repeat the
    v1 mistake this module was rewritten to stop making.
    """
    kept = [part for part in _SENTENCE_SPLIT.split(text.strip())
            if part.strip() and not any(p.search(part) for p in _DIRECTIVE_PATTERNS)]
    return " ".join(kept).strip()


def _unwrap(text: str) -> str:
    """The single string value of a JSON-wrapped answer, or nothing."""
    try:
        parsed = parse_json_response(text, warn=False)
    except Exception:  # noqa: BLE001 - the salvage is best-effort by definition
        return ""
    if not isinstance(parsed, dict):
        return ""
    values = [v.strip() for v in parsed.values() if isinstance(v, str) and v.strip()]
    return values[0] if len(values) == 1 else ""


#: What replaces what was taken away. The bracketed part is always true and
#: costs nothing — only observations are dropped, and their findings are in the
#: design state — so it stands whatever the summariser does. A model-written
#: summary of the dropped turns is folded in AFTER it by ``compaction_note``
#: when the compaction hook delivered one (:func:`summarize`); a
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

    ONE implementation, called identically by both arms, so the difference
    between them is a measurement: ``single`` carries one conversation all run
    and reaches this often, ``multi`` starts each stage fresh and barely does.

    ``llm`` is the compaction HOOK's model caller — an ``AgenticLLM`` under the
    ``ORCHESTRATOR`` identity, never the agent's own. Given one, the
    dropped turns are folded into a rolling summary riding in the note
    (:func:`summarize`); given ``None``, the note is the count
    alone. Every failure mode of the hook lands on that fallback, so a
    compaction always succeeds whatever the model does.

    The hook is the harness's call: the agent did not choose to compact, is
    never shown that conversation, has nothing bound for it, and no context is
    published in its name. ``stats`` carries ``compactions`` and
    ``compaction_summaries``; the difference is the hook's failure rate.
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
        if brief and (not budget or prompt_chars(messages) + len(brief) <= budget):
            restored.append((stage, brief))
        else:
            still_lost.append(stage)

    previous = running_summary(messages)
    summary, outcome = previous, "count only"
    if llm is not None:
        with trajectory.acting_as(ORCHESTRATOR):
            summary, outcome = summarize(llm, previous, dropped)
        if outcome == "summarised":
            stats["compaction_summaries"] = stats.get("compaction_summaries", 0) + 1

    # The note names only what could not be put back, so a model whose contract
    # is sitting right there is not sent to fetch it again.
    kept = _with_note(messages, total, still_lost, summary=summary)
    for _stage, brief in restored:
        kept.append({"role": "user", "content": brief})

    trajectory.log_recovery_event(
        ORCHESTRATOR, "context_compacted",
        f"{len(dropped)} turn(s), {total} total"
        + (f", stage brief re-attached: {', '.join(s for s, _ in restored)}" if restored else "")
        + (f", stage brief lost: {', '.join(still_lost)}" if still_lost else ""),
        # Both facts — the outcome and the resulting size — because the paper
        # reports the hook's failure rate against what it was spent on.
        f"{outcome}; live context now {prompt_chars(kept)} chars")
    return kept
