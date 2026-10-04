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
from .specialists import STEPS, missing_parts, view_as_harness

#: Every tool name the arm can ever bind. Protocol vocabulary, and therefore
#: words that must never appear in a design artifact.
#: NOT "submit": it is ordinary English ("learners submit their project"), and
#: including it made the gate fire on legitimate content — measured in run
#: single_20260831_160530, where the model then burned two turns arguing with
#: an error it could not act on ("I see the issue. The artifact is rejected
#: because it mentions `submit`..."). Every name here is underscored and has no
#: ordinary-English reading.
_PROTOCOL_WORDS = (
    "read_alignment_state", "read_node", "list_documents", "read_document",
    # Names an archived prompt or a model's habit may still carry.
    "read_nodes", "read_edges", "coverage_gaps",
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
    view = view_as_harness(step, state)
    return tuple(key for key, _type, _required in step.submit_fields if view.get(key))


def still_needed(step, state, closed: tuple[str, ...] = (),
                 also_owed: tuple[str, ...] = ()) -> str:
    """What this stage already holds and what it still owes, from the STATE.

    ONE renderer, so the sentence cannot drift between the place a stage OPENS
    and the place a submit is answered. Computed from the state and never from
    `attempt` or any loop counter — the rule `missing_parts` already carries,
    because a regen resets a counter and the arms would then disagree.

    ``closed`` names the parts the loop will no longer accept — an artifact
    that spent its submit budget. They are missing from the state but must
    not be listed as owed: "leave X" beside "still needs X" is an instruction
    no model can satisfy, and a model that follows the second half resubmits
    X until the turn ceiling ends the stage. A closed part is named as
    closed instead, so the sentence and the loop's own rule agree.

    ``also_owed`` names what the stage owes beyond its declared artifacts —
    the single arm's Developer-tier lists (``fanout.missing_outputs``), which
    that arm writes inside the stage and the multi arm never does.

    Without it a stage re-run from a fresh context opens byte-identically to
    its first attempt, listing all six of `implementation`'s artifacts however
    many are committed, so the retry re-issues every read and re-sends finished
    work — measured on run 24343e4d, three attempts at 55.6k prompt / 11.7k
    completion tokens / 122 s. Only the multi arm has this hole; the single arm
    never restarts a stage and gets the same sentence from `_committed_note`.
    """
    landed = landed_parts(step, state)
    owed = missing_parts(step, state) + tuple(also_owed)
    left = tuple(p for p in owed if p not in closed)
    shut = tuple(p for p in closed if p in owed)
    if not landed or not (left or shut):
        return ""
    parts = []
    if left:
        parts.append(f"{step.name} still needs: {', '.join(left)}.")
    if shut:
        parts.append(f"Closed, do not submit again: {', '.join(shut)}.")
    parts.append(f"Already committed: {', '.join(landed)} — submit the next part on "
                 "its own and do not resend those.")
    return " ".join(parts)


def with_progress(brief: str, step, state, closed: tuple[str, ...] = (),
                  also_owed: tuple[str, ...] = ()) -> str:
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
    resuming = still_needed(step, state, closed, also_owed)
    if not resuming:
        return brief
    # Said TWICE: straight after the stage marker and again at the end. At
    # the end alone it was measured not to hold (run 9efc3cfa,
    # implementation): the contract's own list of seven artifacts came first,
    # and after each re-attachment the model walked that list from the top —
    # 8 of the stage's 25 turns re-sent `system_check` and the closed
    # `prototype_execution`. The marker stays the first line, which is what
    # `brief_stages` and the fixture read a brief by.
    header, _, body = brief.partition("\n")
    return (f"{header}\nRESUMING, not starting: {resuming}\n"
            f"The contract below is for reference; write ONLY what is still needed."
            f"\n{body}\n\n{resuming}")



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
    (the scenario and a Developer's assignment use it, and readers — the test fixture
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


#: Which agent-facing protocol a run spoke, recorded in
#: ``metadata.run_config`` so that runs on either side of a change to the
#: tools an agent is bound or to how a stage ends are never pooled by mistake.
#: 14 = an activity that names no assessment task is refused while the design
#: has one, and the prose arm's activity Developers are shown the tasks they
#: prepare for with their questions. 13 = the single arm's submit offers only the artifacts its stage still
#: owes, the next of them required, so a landed plan is never re-sent; the
#: instalment instruction names no tool. 12 = the single arm binds only the current stage's submit, and a request
#: the serving window refuses is refunded and answered with a harder trim
#: instead of a nudge (both arms). 11 = the single arm finishes a fan-out stage only once its item lists
#: exist, and closes a stage that spent its submit cap so the run moves on;
#: the prose arm's activity Developers are handed TASK ids for C4; a key
#: fused onto a declared field's name is read as that field. 10 = a rejection the constrained pass cannot fix (a question restating its
#: objective) goes straight back to the agent, and the pass's own prompt is
#: trimmed to the window with its schema counted. 9 = an assessment item whose
#: question restates its objective's own sentence is refused at the submit. 8 = every field a rubric sub-item reads is REQUIRED in the artifact
#: contract (the analysis prose, the improvement plan's summary and goals, the
#: plan's expected evidence and formative methods, the strategy model, an
#: activity's duration and materials, a guide's objectives and prose) and
#: held to at the submit. 7 = a rejected submit written again by the model under the artifact's
#: per-run schema (references as enums over the ids that exist, a light
#: assignment's rows as constants, stated counts as bounds), with no tools
#: bound; the bound submit tools declare that schema too. 6 = an assessment
#: plan that states the summative procedure and the
#: adoption criteria in words, and modules whose minutes are held to what a
#: course of the brief's length carries. 5 = the course's modules written by
#: the outcomes stage and dividing every
#: family's work, an assessment blueprint of sets, 17 relations (3 core: the
#: edges of the constructive-alignment triad), a run that stops when no module
#: is written, an outcomes stage that writes no course goal of its own — what
#: the course is for is the brief's, which every stage is already shown — and
#: a development mode of ``light`` or ``full``, where a light assignment fixes
#: each item's objective, type and cognitive level and each activity's
#: objective and level, the mode states a material's depth, and the pilot
#: data plan names its collection points in words.
PROTOCOL_REV = 14

#: The answer to a repeated read whose result is unchanged — ONE wording for
#: both arms, and only ever said when it is true (``turn.answer_read`` has
#: just re-derived the result and compared it).
REPEAT_UNCHANGED = ("You already called {name} with these arguments and the result has not "
                    "changed since the last call. Use what you have.")

#: A read whose every id an earlier read in this conversation already
#: answered, unchanged: nothing new would come back.
READ_ALREADY_SHOWN = ("Every id in this read_node call ({ids}) is already shown above, "
                     "unchanged, from your earlier reads. Use what you have.")


def open_issues_pointer(stage: str, count: int, round_index: int, rounds: int) -> str:
    """The answer to a submit that completed a stage whose own checks still
    fail: THAT they fail, and where to look. Never the details — those are the
    agent's to read (``read_alignment_state``), so that seeing a problem,
    fixing it and checking again is one loop the agent drives. The count and
    the round are here because an agent that does not look must still have
    been told, once, that there was something to see."""
    return (f"COMMITTED. {count} open issue(s) on {stage} (round {round_index} of {rounds}) — "
            "call read_alignment_state to see them, fix them, and submit only what changes. "
            "If a point is wrong or you cannot act on it, submit nothing.")


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
    ``constrained_passes`` / ``constrained_pass_rejected``: how many rejected
    submits were written again under the artifact's per-run schema
    (``turn.constrained_pass``) and how many of those the validator still
    refused. The first is the transport's recovery rate on this model — a
    measurement about the model, reported by size — and the second is what
    the grammar cannot reach. ``constrained_pass_skipped``: rejections that
    were never sent to a pass, because no decoder can fix them or the prompt
    would not fit the window.
    ``tool_errors``: tool calls that came back ERROR (13% of every tool
    result over runs 53042a0d/2559b22d), so the ceiling is read against
    turns that DID something.
    ``n_sets``..``set_submits_rejected``: the Developer tier's own counters,
    kept separate so "the dispatch OR any one of ten sets gave up" is not one
    number."""
    return {"turns_used": 0, "submits_rejected": 0, "repeated_calls": 0,
            "history_dropped": 0, "gave_up": False, "reads": 0, "assignment_reads": 0,
            "rereads_changed": 0, "state_reads": 0, "blind_submits": 0,
            "via_budget_exhaustion": False,
            "compactions": 0, "compaction_summaries": 0,
            "context_len": 0, "batched_calls": 0, "markup_recovered": 0,
            "args_salvaged": 0,
        "args_reshaped": 0, "truncated_turns": 0, "dropped_args": 0,
            "repair_turns": 0, "tool_errors": 0, "endpoint_failures": 0,
            "constrained_passes": 0, "constrained_pass_rejected": 0,
            "constrained_pass_skipped": 0,
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


#: Why an instalment that adds nothing is put to the constrained pass: the
#: schema it decodes under states the whole set, so the request says so.
INSTALMENT_PASS_REASON = (
    "what you sent repeats what is already kept. {owed} Write the WHOLE set, "
    "every item DIFFERENT from the others, the kept one(s) included.")


#: What the constrained pass asks. The call the model made is answered with
#: this, then the model writes the artifact again with no tools bound and the
#: artifact's schema enforced by the decoder. ONE wording for both arms.
CONSTRAINED_PASS_REQUEST = (
    "Your call to {tool} was not accepted:\n- {errors}\n"
    "Write the arguments of {tool} again, as ONE JSON object whose top-level key(s) "
    "are {keys}. Keep what was right in what you sent; fix only what is listed. "
    "Write the JSON object and nothing else."
)


#: The rejection of an assessment item whose question is its objective's own
#: sentence (``fanout.item_restatement_errors``). A constant because the
#: constrained pass recognises it (``turn.grammar_cannot_fix``): a decoder
#: holds the shape of an artifact and cannot hold "not the objective's
#: wording", so a pass over this rejection alone is a second full completion
#: that writes the same copy again.
ITEM_RESTATES_OBJECTIVE = (
    "assessment_tools[{index}].question: restates {lo}'s own wording — write "
    "the task the learner performs on the subject matter (a case, data, a "
    "problem to solve), not the objective sentence")
