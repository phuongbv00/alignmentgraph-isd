"""What both arms are told, and how a turn is answered.

The shared protocol surface: the instructed ADDIE order, a stage's contract
turn and how it is found again once compaction has taken it, the sentence that
says what a stage still owes, the reply to a turn that broke the protocol, the
gate that keeps tool names out of the artifact, and the record a stage leaves
behind.

Every one of these is SHARED ON PURPOSE. The wording lands in the transcript,
the transcript is what the model sees, and a nudge or a countdown worded
differently on each side of the decomposition axis is a second variable. The
arms differ in who holds the context and who walks the stages; they must not
differ in the words used to run one turn.

What is NOT here: each arm's own system prompt. ``ToolLoop`` and ``ReactLoop``
describe genuinely different jobs — six stage loops against one conversation —
and that difference IS the treatment, so each keeps its own.
"""
from __future__ import annotations

import json
import re

from . import budget
from .specialists import STEPS, missing_parts

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


def landed_parts(step, state) -> tuple[str, ...]:
    """Which of ``step``'s declared artifacts the state now holds."""
    view = step.view(state) if hasattr(state, "element_nodes") else step.view_prose(state)
    return tuple(key for key, _type, _required in step.submit_fields if view.get(key))


def still_needed(step, state) -> str:
    """What this stage already holds and what it still owes, from the STATE.

    ONE renderer, so the sentence cannot drift between the place a stage OPENS
    and the place a submit is answered. Computed from the state and never from
    `attempt` or any loop counter — the rule `missing_parts` already carries,
    because a regen resets a counter and the arms would then disagree.

    Without it a stage re-run from a fresh context opens byte-identically to
    its first attempt, listing all six of `implementation`'s artifacts however
    many are committed, so the retry re-issues every read and re-sends finished
    work — measured on run 24343e4d, three attempts at 55.6k prompt / 11.7k
    completion tokens / 122 s. Only the multi arm has this hole; the single arm
    never restarts a stage and gets the same sentence from `_committed_note`.
    """
    landed, left = landed_parts(step, state), missing_parts(step, state)
    if not landed or not left:
        return ""
    return (f"{step.name} still needs: {', '.join(left)}. "
            f"Already committed: {', '.join(landed)} — submit the next part on "
            "its own and do not resend those.")


def with_progress(brief: str, step, state) -> str:
    """A stage's contract, RE-attached, plus what the state says it still owes.

    On a first issue this is the identity function — nothing is committed,
    `still_needed` returns "" — which keeps the opening turn byte-identical
    for the golden fixture and makes it safe to route every re-attachment
    through here without a flag.

    MEASURED FAILURE (run 46bd42a5, implementation): a contract re-attached
    VERBATIM after compaction dropped 20 turns still ended "This stage has 7 of
    them: instructor_orientation, system_check, ...", while six were already
    committed and the tool results saying so were what the trim took. The model
    read it as the stage starting and re-submitted the committed six, one per
    turn, until the ceiling ended the stage; `dev_plan`, the one artifact
    genuinely missing, was never written and the fan-out divided the delivery
    deterministically — so the agent's own grouping, which is what `agent_mode`
    measures, came from the backstop.

    The sentence is `still_needed`'s, so a stage OPENING, a submit being
    answered and a contract coming BACK all say the same thing.
    """
    resuming = still_needed(step, state)
    return f"{brief}\n\n{resuming}" if resuming else brief



#: The instructed workflow. Both arms get this, verbatim: the pivot makes the
#: agents autonomous in HOW they execute a stage, never in WHAT ORDER the stages
#: run. Stating it once here (and nowhere else) is what keeps that true.
def _workflow_overview() -> str:
    """The instructed stage order, GENERATED from the step table.

    Never hand-written: a list beside the table that defines the thing is a
    list that will disagree with it, and a stage named here but absent from the
    table tells every agent in every run to expect a step that does not exist.
    Same rule as the planner's per-block budget, interpolated from
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


WORKFLOW_OVERVIEW = _workflow_overview()


#: The header a stage's turn carries, and the regex that finds it again. ONE
#: marker: the turn IS the brief.
#:
#: Reading the stage name back OUT of the text is what lets one implementation
#: serve both arms — the multi arm builds this turn per stage loop and the
#: single arm has it injected into its one conversation as each stage comes up,
#: and neither difference reaches `brief_stages`/`lost_briefs`/`respec`.
STAGE_BRIEF_HEADER = "--- STAGE: {stage} ---"


BRIEF_HEADER_RE = re.compile(
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
        found.update(BRIEF_HEADER_RE.findall(str(content or "")))
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
    it could not see. And from the other arm (run 2b9e911a, implementation):
    once compaction took the brief, the model invented
    ``instructor_guidance`` and ``session_guides`` as a dict, was rejected
    eight times across three regens, and the artifact never committed.

    Re-attached only when it is actually gone: at up to 7,400 characters,
    pasting it onto every rejection pushes out the transcript it is meant to
    sit beside. PASTED rather than asked for — a paste costs no turn and is
    certain to arrive.
    """
    if step.name in brief_stages(messages):
        return ""
    return "\n\nThe contract for this stage, again:\n" + brief


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
