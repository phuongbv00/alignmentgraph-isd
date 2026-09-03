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

**On the arm asymmetry.** ``single`` carries one conversation for the whole
brief and compacts constantly; ``multi`` starts each stage fresh and barely
compacts at all. So this costs the two arms very differently — and that is the
POINT, not a confound. The trigger, the prompt, the budget and the fallback are
one implementation shared by both; what differs is how often the window
actually fills, which is exactly the mechanism the decomposition axis is about.
A cost that differs because of the mechanism is the effect being measured; a
cost that differs because the harness gave one arm something it withheld from
the other would be the confound. ``metadata.autonomy`` reports ``compactions``
and ``compaction_summaries`` per stage so the paper can state the price rather
than imply it.

The call is the ORCHESTRATOR's, not the agent's: the agent did not choose to
compact and is not shown this conversation. It is therefore never published as
one of that agent's contexts — the guard in
``tests/test_one_agent_one_system_prompt.py`` holds that line — while
``AgenticLLM`` still counts its tokens, so it cannot hide from the cost table.

Failure is always safe: an empty or unusable answer falls back to the plain
count note. A summary is an improvement on the note, never a precondition for
compaction working.
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


def summarize(call_llm, previous: str, dropped: list) -> str:
    """The new running summary, or ``""`` when the model gives nothing usable.

    ``call_llm`` is an :class:`~loop.AgenticLLM` — its JSON-mode ``__call__``,
    used here for plain prose. It counts its own tokens and records its own
    ``llm_call``, which is what keeps this off the books nowhere.
    """
    body = _render(dropped)
    if not body.strip():
        return previous
    prompt = _TASK.format(limit=MAX_SUMMARY_CHARS,
                          previous=previous.strip() or "(nothing removed before now)",
                          dropped=body)
    try:
        answer = call_llm([{"role": "system", "content": _SYSTEM},
                           {"role": "user", "content": prompt}], 0)
    except Exception:  # noqa: BLE001 - a summary is never load-bearing
        return previous
    text = _clean(answer)
    if not text:
        # Deliberately the PREVIOUS summary, not empty: a failed call must not
        # also erase what earlier ones managed to keep.
        return previous
    return text[:MAX_SUMMARY_CHARS]


def _render(dropped: list) -> str:
    """The dropped turns as text, newest last, oldest elided past the cap."""
    from .loop import serialize_messages

    lines = []
    for message in serialize_messages(dropped):
        content = str(message.get("content") or "").strip()
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
    """
    text = str(answer or "").strip()
    if not text or text in ("{}", "[]", "null", "None"):
        return ""
    if text.startswith("{") or text.startswith("["):
        return ""
    return text
