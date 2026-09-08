"""Summarising what compaction takes out of an agent's context.

When a conversation outgrows the window, ``trim_history`` removes the oldest
tool observations. What replaces them decides how much of the run survives the
squeeze, and there are two honest options:

* a deterministic NOTE — "N turns went, their findings are in the design state,
  read them again" — free, exact, and carrying none of the content;
* a model-written SUMMARY of the dropped turns, folded into the note.

This module is the second. The summary is rolling: each compaction folds the
previous summary and the newly dropped turns into one, so the note stays a
fixed size no matter how long the run gets and the input to each call is
bounded by (previous summary + what just went).

**This is a HOOK OF THE HARNESS, not an action of the agent.** The agent did
not choose to compact, is not shown this conversation, and has nothing bound
for it — offering it a ``submit_summary`` tool would put the agent's own
tool-protocol costume on an intervention the harness makes over its head, and
the one thing this package is most careful about is who is talking to the model
and inside which context boundary. So the call goes out through
``AgenticLLM.call_prose``: no tools, no ``response_format``, attributed to
``WORKFLOW_ORCHESTRATOR``, and never published as one of that agent's contexts.
``AgenticLLM`` still books its tokens, so it cannot hide from the cost table.

That prose path is the only one left in the package, and it is deliberately
narrow. Generative repairs used to open a second conversation under the OWNING
AGENT'S name and were removed 2026-09-03 for exactly that reason
(``tests/test_one_agent_one_system_prompt.py``). The difference here is the
attribution and the absence of a published context — which is a claim that has
to be checkable, so ``tests/test_compaction.py`` asserts that ``call_prose``
has exactly one caller in ``src/`` and that it is this module.

**On the arm asymmetry.** ``single`` carries one conversation for the whole
brief and compacts constantly; ``multi`` starts each stage fresh and barely
compacts at all. So this costs the two arms very differently — and that is the
POINT, not a confound. The trigger, the prompt, the budget and the fallback are
one implementation shared by both; what differs is how often the window
actually fills, which is exactly the mechanism the decomposition axis is about.
A cost that differs because of the mechanism is the effect being measured; a
cost that differs because the harness gave one arm something it withheld from
the other would be the confound. ``metadata.autonomy`` reports ``compactions``
and ``compaction_summaries`` per stage, so ``compactions - compaction_summaries``
is the summariser's failure rate on this model and the paper can state the
price rather than imply it.

**On the transport, because v1 died of it.** The first version of this module
(2026-09-03, removed 2026-09-05) reached the model through ``AgenticLLM``'s
JSON-mode ``__call__`` while asking for plain prose. A compliant backend
answered with a JSON object, ``_clean`` rejected it as non-prose, and every
compaction of run e81b8108 logged "count only" after a 2.7-4.7k-token
completion — three calls, 11.8k completion tokens, nothing kept. Two things
follow, and both are load-bearing: ``call_prose`` sends no ``response_format``
at all, and ``_clean`` now SALVAGES a JSON-wrapped answer instead of discarding
it, so the exact failure that killed v1 is a recovery here.

Failure is always safe: an empty or unusable answer falls back to the previous
summary — never to empty, or a bad fold would also erase what earlier ones
managed to keep. A summary is an improvement on the note, never a precondition
for compaction working.
"""
from __future__ import annotations

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
    "you are not judging it."
)

_TASK = """\
The turns below were removed from an instructional designer's context to make \
room. Fold them, together with the running summary of everything removed \
earlier, into ONE replacement summary.

Keep: decisions made, artifact ids and names produced or referenced, \
constraints discovered, and anything a later turn would have to know and could \
not re-derive. Drop: tool-call mechanics, repetition, and anything already \
committed to the design state, which the agent can read again.

Write plain prose under {limit} characters. No preamble, no headings, no \
markdown. If there is nothing worth keeping, answer with nothing at all.

=== RUNNING SUMMARY SO FAR ===
{previous}

=== TURNS BEING REMOVED NOW ===
{dropped}"""


def summarize(call_llm, previous: str, dropped: list) -> tuple[str, str]:
    """The new running summary and why it is what it is.

    ``call_llm`` is an :class:`~loop.AgenticLLM` built with the
    ``WORKFLOW_ORCHESTRATOR`` identity — see the module docstring for why this
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
    from .loop import _BRIEF_HEADER_RE, serialize_messages

    lines = []
    for message in serialize_messages(dropped):
        content = str(message.get("content") or "").strip()
        if content and _BRIEF_HEADER_RE.search(content):
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
    """
    text = str(answer or "").strip()
    if not text or text in ("{}", "[]", "null", "None"):
        return ""
    if text.startswith("{") or text.startswith("["):
        return _unwrap(text)
    return text


def _unwrap(text: str) -> str:
    """The single string value of a JSON-wrapped answer, or nothing."""
    from ..llm_io import parse_json_response

    try:
        parsed = parse_json_response(text, warn=False)
    except Exception:  # noqa: BLE001 - the salvage is best-effort by definition
        return ""
    if not isinstance(parsed, dict):
        return ""
    values = [v.strip() for v in parsed.values() if isinstance(v, str) and v.strip()]
    return values[0] if len(values) == 1 else ""
