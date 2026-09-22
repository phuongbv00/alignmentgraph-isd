"""Summarising what compaction takes out of an agent's context.

When the window fills, `trim_history` removes the oldest turns. What replaces
them decides how much of the run survives: a count says how much was lost and
nothing about what, a summary keeps the part a later turn would have needed.

On the ARM ASYMMETRY, because it is the reason this exists in the form it does.
`single` carries one conversation for the whole brief and reaches compaction
far sooner than `multi`, which starts each stage fresh — so this costs the two
arms differently. That is the mechanism the decomposition axis is about, not
noise around it: the trigger, the prompt, the budget and the fallback are one
implementation shared by both, and what differs is only how often the window
actually fills. A cost that differs because of the harness would be the
confound; this one differs because of the thing being measured, and
`metadata.autonomy` counts it per stage so the price can be stated.

On the TRANSPORT, which is what killed the first version. It reached the model
through `AgenticLLM`'s JSON-mode call while asking for prose, a compliant
backend answered with JSON, and the summariser threw it away — run e81b8108,
three calls, 11.8k completion tokens, nothing kept. It is back as a HOOK OF
THE HARNESS: no tool is bound (the agent did not choose to compact, so
compaction is not an action in its protocol), no `response_format` is sent, and
the call is attributed to the orchestrator and publishes no context.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from alignmentgraph_isd import HarnessRunConfig
from alignmentgraph_isd.core.agentic import compaction
from alignmentgraph_isd.core.agentic.client import AgenticLLM
from alignmentgraph_isd.core.agentic.compaction import (
    _with_note,
    compact,
    compaction_note,
    running_summary,
)
from alignmentgraph_isd.core.agentic.protocol import stage_brief_block
from alignmentgraph_isd.core.agentic.transcript import COMPACTION_NOTE, trim_history
from alignmentgraph_isd.core.agentic.specialists import STEPS
from alignmentgraph_isd.core.trajectory import ORCHESTRATOR

from conftest import FakeChatModel, load_brief, run_brief


class _Model:
    """The hook's caller: an object with `call_prose`, which is all
    `summarize` is allowed to know about it."""

    def __init__(self, answer="A summary.") -> None:
        self.answer = answer
        self.seen: list = []

    def call_prose(self, messages, *, max_tokens: int = 0, extra_body=None):
        self.seen.append(messages)
        self.capped = max_tokens
        self.body = extra_body or {}
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def _without_docstrings(source: str) -> str:
    """The code alone. A source-text guard that reads the docstrings too fires
    on the very paragraph that explains why the thing is forbidden."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef,
                                 ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = node.body
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def _dropped(n: int = 3) -> list:
    return [{"role": "tool", "name": "read_nodes",
             "content": f"ILO-0{i}: apply inheritance to a domain model"} for i in range(n)]


class _Trajectory:
    """Enough of TrajectoryLogger for `compact`: an `acting_as` block and a
    recovery event."""

    def __init__(self) -> None:
        self.events: list = []

    def acting_as(self, actor, phase=None, *, force_identity=False):
        from contextlib import nullcontext
        return nullcontext()

    def log_recovery_event(self, agent, kind, detail, summary):
        self.events.append((agent, kind, detail, summary))


# ---------------------------------------------------------------- the fold

def test_the_summary_folds_the_previous_one_in():
    """Rolling, not accumulating: each compaction folds what went before with
    what just went, so the note stays one fixed-size block however long the run
    gets and each call's input stays bounded."""
    model = _Model("Objectives ILO-01..03 established; assessment plan pending.")

    out, outcome = compaction.summarize(model, "Earlier: scenario read.", _dropped())

    assert outcome == "summarised"
    assert out.startswith("Objectives ILO-01")
    prompt = model.seen[0][-1]["content"]
    assert "Earlier: scenario read." in prompt, "the fold gets what came before"
    assert "ILO-01" in prompt, "and what just went"


def test_no_response_format_is_ever_sent():
    """The regression test for the bug that killed v1: a summary asked for as
    prose under `response_format={"type": "json_object"}` came back as JSON and
    was discarded on every compaction of run e81b8108. Nothing on this path may
    reintroduce it — and nothing may bind a tool either, because compaction is
    the harness acting over the agent's head, not a move in its protocol.

    What is forbidden is a TOOL or a response format, named exactly. The list
    used to hold a bare ``bind(`` as a proxy for ``bind_tools(``, which also
    caught ``bind(max_tokens=…)`` — a spend cap, the opposite of giving this
    path a capability: it takes one away, and the fold needs it because the
    answer is truncated on arrival anyway (``SUMMARY_MAX_TOKENS``)."""
    code = _without_docstrings(inspect.getsource(AgenticLLM.call_prose).lstrip())
    code += _without_docstrings(inspect.getsource(compaction))
    for forbidden in ("response_format", "json_object", "bind_tools", "tools=",
                      "tool_choice"):
        assert forbidden not in code, f"{forbidden} is back on the prose path"

    class _Naked:
        def __init__(self):
            self.bound = False

        def bind_tools(self, *a, **k):
            self.bound = True
            return self

        def bind(self, **k):
            self.bound = True
            return self

        def invoke(self, messages):
            from conftest import _Result
            return _Result(content="prose")

    naked = _Naked()
    config = HarnessRunConfig()
    config.llm_factory = lambda: naked
    from alignmentgraph_isd.core.trajectory import TrajectoryLogger

    caller = AgenticLLM(config, TrajectoryLogger(), ORCHESTRATOR)
    assert caller.call_prose([{"role": "user", "content": "x"}]) == "prose"
    assert not naked.bound, "the hook bound something to the model"


def test_a_json_wrapped_summary_is_salvaged():
    """The exact failure mode that killed v1, turned into a recovery.

    Nothing asks for JSON any more, so an object here is the model's own
    choice — and a small model told to write prose wraps it often enough that
    discarding the answer discards a completion already paid for. One string
    value is taken; with two there is no way to tell which is the summary."""
    one = _Model('{"summary": "Objectives ILO-01..03 established."}')
    assert compaction.summarize(one, "kept", _dropped()) == (
        "Objectives ILO-01..03 established.", "summarised")

    two = _Model('{"summary": "a", "notes": "b"}')
    assert compaction.summarize(two, "kept", _dropped()) == ("kept", "unusable")


@pytest.mark.parametrize("answer", ["", "   ", "{}", "[]", "null", "None", None])
def test_an_unusable_answer_keeps_the_previous_summary(answer):
    """A failed fold must not also erase what earlier ones managed to keep. A
    model asked for prose under a system turn it has never seen answers with an
    apology, an empty object or nothing often enough to be worth naming."""
    assert compaction.summarize(_Model(answer), "Objectives established.",
                                _dropped()) == ("Objectives established.", "unusable")


def test_a_failing_model_never_breaks_compaction():
    """A summary is an improvement on the note, never a precondition for
    compaction working — the turns are gone either way and the run continues."""
    assert compaction.summarize(
        _Model(RuntimeError("endpoint down")), "kept", _dropped()) == ("kept", "error")


def test_nothing_dropped_means_nothing_asked():
    model = _Model()
    assert compaction.summarize(model, "kept", []) == ("kept", "nothing_dropped")
    assert not model.seen, "a compaction that removed nothing must not spend a call"


def test_the_outcome_tells_a_failed_model_from_an_empty_fold():
    """Why `summarize` returns the outcome instead of letting the caller infer
    it. v1 returned the summary alone and success was `summary != previous`,
    which reads identically for a model that errored and a trim that had
    nothing worth keeping — the first is a finding about the model, the second
    a property of the trim, and only one of them belongs in a failure rate."""
    outcomes = {compaction.summarize(_Model(a), "kept", d)[1]
                for a, d in ((RuntimeError("x"), _dropped()), ("", _dropped()),
                             ("fine", []), ("fine", _dropped()))}
    assert outcomes == {"error", "unusable", "nothing_dropped", "summarised"}


def test_the_input_and_the_output_are_both_bounded():
    """The summary is standing furniture — never trimmed — so it must never
    become the reason the window is full; and folding a summary of a summary
    of a summary is where this stops meaning anything."""
    huge = [{"role": "tool", "content": "x" * 5000} for _ in range(20)]
    model = _Model("y" * 5000)

    out, _outcome = compaction.summarize(model, "", huge)

    assert len(out) <= compaction.MAX_SUMMARY_CHARS
    assert len(model.seen[0][-1]["content"]) < 20 * 5000, "the oldest dropped turns are elided"


# ------------------------------------------------------- what is NOT fed in

def test_a_dropped_stage_brief_is_never_summarised():
    """The contract is excluded from the fold, for four reasons in ascending
    order of force.

    BUDGET first: `respec` measures a brief at up to 7,400 characters against
    `MAX_INPUT_CHARS` 12,000, so one dropped `implementation` brief takes 62%
    of the whole input allowance and pushes the tool results — the only thing
    a summary can usefully carry — out through the elision.

    Then: `compact` already re-attaches a lost brief VERBATIM at the tail, and
    `respec` re-attaches it verbatim on any rejection, so a paraphrase is work
    done twice for a worse copy. And a prose paraphrase of a JSON schema,
    sitting in a protected never-trimmed message, is a second and worse source
    of truth for field names than the contract it paraphrases — which is how
    run 2b9e911a's model came to invent `instructor_guidance` and a dict
    `session_guides`.
    """
    step = {s.name: s for s in STEPS}["implementation"]
    brief = stage_brief_block(step)
    model = _Model()

    compaction.summarize(model, "", [{"role": "user", "content": brief}] + _dropped())

    prompt = model.seen[0][-1]["content"]
    assert "--- STAGE:" not in prompt, "the contract went into the fold"
    for field in ("session_guides", "operator_manual", "instructor_guide"):
        assert field not in prompt, f"{field} reached the summariser from the schema"
    assert "ILO-01" in prompt, "the observations must still be there"


def test_a_committed_artifact_is_not_fed_back_in():
    """A tool call renders as its NAME, never its arguments. The arguments of a
    `submit` are the agent's own committed artifact — the longest thing in a
    multi-arm transcript — and it is in the design state, one read away."""
    model = _Model()
    dropped = [{"role": "assistant", "content": "",
                "tool_calls": [{"name": "submit_assessment_plan",
                                "args": {"assessment_plan": {"x": "y" * 4000}}}]}]

    compaction.summarize(model, "", dropped)

    prompt = model.seen[0][-1]["content"]
    assert "[called submit_assessment_plan]" in prompt
    assert "yyyy" not in prompt, "the artifact was fed back into its own summary"


# ------------------------------------------------------------------ the note

def test_the_note_carries_the_summary_and_stays_one_note():
    messages = [{"role": "system", "content": "S"}, {"role": "user", "content": "live"}]
    once = _with_note(messages, 4, summary="objectives ILO-01..03 exist")

    assert running_summary(once) == "objectives ILO-01..03 exist"
    assert "objectives ILO-01..03 exist" in once[1]["content"], "the model actually sees it"
    assert "4 earlier turn(s)" in once[1]["content"], "and how much went"

    twice = _with_note(once, 9, summary="…and the assessment plan")
    assert len([m for m in twice if m.get(COMPACTION_NOTE)]) == 1, "one note, rewritten"
    assert running_summary(twice) == "…and the assessment plan"


def test_the_bracket_closes_before_the_summary_begins():
    """The count and the brief-lost sentence are harness facts; the summary is
    a model's account of turns nobody can see any more. Run together, the
    second borrows the authority of the first."""
    note = compaction_note(3, ("implementation",), summary="A model wrote this.")["content"]

    bracket, _, tail = note.partition("]")
    assert "implementation" in bracket, "the brief-lost sentence is inside the bracket"
    assert "A model wrote this." not in bracket
    assert "A model wrote this." in tail


def test_a_note_carrying_a_summary_survives_the_next_trim():
    """The summary is standing furniture. If a trim could take it, every fold
    would restart from nothing and the rolling summary would never roll."""
    messages = ([{"role": "system", "content": "S"}]
                + [compaction_note(4, summary="ILO-01..03 exist")]
                + [{"role": "tool", "content": "x" * 3000} for _ in range(10)])

    kept, dropped = trim_history(messages, budget=4000)

    assert dropped
    assert running_summary(kept) == "ILO-01..03 exist"


# ---------------------------------------------------------------- the boundary

def test_call_prose_has_exactly_one_caller_and_it_is_the_hook():
    """The line that replaces the one `test_one_agent_one_system_prompt.py`
    closed.

    Generative repairs used to compose a second conversation under a second
    system prompt and publish it under the OWNING AGENT'S name; they were
    removed 2026-09-03 because the context boundary IS the `agent_mode` axis.
    `call_prose` reopens a prose path, and the only thing separating it from
    what was removed is who it is attributed to and that it publishes nothing —
    a distinction that has to be enforced, not merely intended. One caller, and
    it is the harness's own hook.
    """
    src = Path(compaction.__file__).parent.parent.parent
    callers: list[str] = []
    for path in src.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "call_prose"):
                callers.append(f"{path.relative_to(src)}:{node.lineno}")

    assert len(callers) == 1, f"call_prose has drifted beyond the hook: {callers}"
    assert callers[0].startswith("core/agentic/compaction.py"), callers


def test_the_hook_never_publishes_a_context():
    """The agent did not choose to compact and is never shown this
    conversation, so it is not one of that agent's contexts — while
    `AgenticLLM` still books the tokens, so the hook cannot hide from the cost
    table.

    This needs its own test: none of the three guards in
    `test_one_agent_one_system_prompt.py` catches it. The hook's conversation is
    two messages, so it slips past `test_one_conversation_is_one_context`'s
    `len(messages) >= 4` filter; its system turn is a single constant, so
    `test_an_agent_is_never_given_a_second_system_prompt` would pass; and the
    toolless check only looks at contexts that were published at all.
    """
    config = HarnessRunConfig(agent_mode="single", context_mode="graph")
    config.llm_factory = lambda: FakeChatModel()
    # Small enough that the one conversation the single arm carries overflows.
    config.llm_context_window = 12000
    config.llm_completion_reserve = 8192
    result = run_brief(load_brief("java_oop_brief.json"), config)

    assert [c for c in result["contexts"]], "no contexts published at all"
    orchestrator = [c for c in result["contexts"] if c["agent"] == ORCHESTRATOR]
    assert not orchestrator, f"the hook published a context: {orchestrator}"

    events = [e for e in result["trajectory"]["events"]
              if e.get("action") == "context_compacted"]
    assert events, "the window never filled, so this proved nothing"
    assert all(e["agent"] == ORCHESTRATOR for e in events), (
        "a compaction was attributed to an agent rather than to the harness")
    assert any("summarised" in e["context"]["output_summary"] for e in events), (
        "the hook was never actually exercised")


def test_the_price_is_counted_per_stage():
    """`compactions - compaction_summaries` is the hook's failure rate on this
    model, and it is only readable if both numbers are reported per stage and
    over the same population."""
    config = HarnessRunConfig(agent_mode="multi", context_mode="graph")
    config.llm_factory = lambda: FakeChatModel()
    config.llm_context_window = 12000
    config.llm_completion_reserve = 8192
    autonomy = run_brief(load_brief("java_oop_brief.json"), config)["metadata"]["autonomy"]

    assert autonomy
    for stage, stats in autonomy.items():
        assert "compactions" in stats, stage
        assert "compaction_summaries" in stats, stage
        assert stats["compaction_summaries"] <= stats["compactions"], stage


def test_a_failed_fold_is_still_counted_as_a_compaction():
    """The two counters exist to be subtracted. A compaction whose model call
    failed has to raise the denominator and not the numerator, or a run where
    the hook never delivered reads as a run that never compacted."""
    stats: dict = {}
    messages = [{"role": "system", "content": "S"}, {"role": "user", "content": "live"}]

    compact(messages, _dropped(), 3, trajectory=_Trajectory(), stats=stats,
            llm=_Model(RuntimeError("endpoint down")))

    assert stats["compactions"] == 1
    assert stats.get("compaction_summaries", 0) == 0


def test_compaction_still_works_without_a_model():
    """`llm=None` is not only a test convenience: it is the shape every failure
    of the hook degrades to, so the note has to stand on its own."""
    stats: dict = {}
    messages = [{"role": "system", "content": "S"}, {"role": "user", "content": "live"}]

    kept = compact(messages, _dropped(), 3, trajectory=_Trajectory(), stats=stats)

    assert stats["compactions"] == 1
    assert "3 earlier turn(s)" in kept[1]["content"]
    assert running_summary(kept) == ""


def test_a_summary_never_carries_an_instruction():
    """MEASURED (run 3ee5b8df, implementation): the fold came back "The agent
    has already submitted and analyzed plan sets AB-01 through AB-04 … No
    further calls are needed." — and the stage then needed eleven more turns.

    The second sentence is wrong in a way the first is not. The summariser is a
    hook of the harness: it is not in the agent's conversation, cannot see the
    turns it still has, and has no standing to direct it — and its output lands
    in the one message `trim_history` never drops. So a directive from it is
    out of scope by construction, and the prompt asking for a record is not
    enough on a model that ignores the prompt.

    Sentence-level, never answer-level: that fold also carried a real account
    of the stage, and discarding a completion already paid for over its last
    sentence is the v1 mistake this module was rewritten to stop making."""
    from alignmentgraph_isd.core.agentic.compaction import _clean

    kept = _clean("The agent had already submitted plan sets AB-01 through "
                  "AB-04. No further calls are needed.")
    assert kept == "The agent had already submitted plan sets AB-01 through AB-04."

    for directive in ("No further calls are needed.",
                      "Nothing more is required.",
                      "You should now call submit_dev_plan.",
                      "You must submit the operator_manual next.",
                      "Do not read the activities again.",
                      "Proceed to the implementation stage."):
        assert _clean(f"The stage ran. {directive}") == "The stage ran.", directive

    # A summary that is ONLY a directive leaves nothing, and `summarize` then
    # falls back to the previous summary like any other unusable answer.
    assert _clean("No further calls are needed.") == ""


def test_the_directive_filter_keeps_a_reported_obligation():
    """The filter has to be narrow or it eats the summary's job. A constraint
    the agent was GIVEN is exactly what the Keep list asks for, and it is
    phrased with the same words a directive uses — "must", "required",
    "should". What separates them is who is being addressed, so only the
    second person and a bare imperative are matched."""
    from alignmentgraph_isd.core.agentic.compaction import _clean

    for record in (
        "The brief required the design to use slides (PDF) and video (mp4).",
        "The agent was told the operator_manual must reference the actual materials.",
        "It was rejected because assessment_plan.lo_coverage_targets was missing.",
        "The constraint said learners should work in pairs.",
        "No objectives were left unassessed after the re-dispatch round.",
    ):
        assert _clean(record) == record, record


def test_a_directive_is_dropped_even_when_it_arrives_wrapped_in_json():
    """The salvage path and the filter are ordered, not alternatives: a
    directive does not become acceptable for having arrived inside
    `{"summary": ...}`."""
    import json

    from alignmentgraph_isd.core.agentic.compaction import _clean

    wrapped = json.dumps({"summary": "The stage ran. No further calls are needed."})
    assert _clean(wrapped) == "The stage ran."



def test_a_compacted_result_is_forgotten_whatever_shape_the_guard_keeps():
    """The repeat guard keeps a call id AND a digest per answered read; a
    result compaction takes must leave the guard with it, or the model is told
    to read again and refused for having read."""
    from alignmentgraph_isd.core.agentic.transcript import forget_compacted_calls
    from alignmentgraph_isd.core.agentic.turn import SeenCall

    seen = {"a": SeenCall("c1", "d1"), "b": SeenCall("c2", "d2"), "legacy": "c3"}
    forget_compacted_calls(seen, [{"role": "tool", "tool_call_id": "c1"},
                                  {"role": "tool", "tool_call_id": "c3"}])
    assert list(seen) == ["b"]


def test_the_fold_pays_only_for_what_it_can_keep():
    """The prompt asks for `MAX_SUMMARY_CHARS` and `_clean` truncates to it, so
    a completion past that is bought and thrown away.

    MEASURED (run 7123a976, a 9B model): two folds returned 5,985 and 3,849
    completion tokens against a 1,200-character limit and cost 122 s and 67 s
    of a 683 s run — 28% of the wall clock, cut by 95% on arrival. The limit
    was in the prompt the whole time; the model ignored it, so it is bound."""
    model = _Model()

    compaction.summarize(model, "", [{"role": "user", "content": "x" * 400}])

    assert model.capped == compaction.SUMMARY_MAX_TOKENS
    assert compaction.SUMMARY_MAX_TOKENS * 3 >= compaction.MAX_SUMMARY_CHARS, \
        "the cap must leave room for the summary the fold actually keeps"


def test_the_cap_goes_out_under_both_names():
    """`langchain-openai` sends `max_tokens` as `max_completion_tokens`, the
    newer OpenAI field. A backend that predates it ignores the unknown key in
    silence — MEASURED (run aba81e58): the cap went out and a fold came back
    with 6,427 completion tokens against 512, which is 209 s of a 1,229 s run
    spent on text discarded at 1,200 characters. `extra_body` rides into the
    request JSON untouched, so the legacy name travels too."""
    from alignmentgraph_isd.core.agentic import client

    code = inspect.getsource(client.AgenticLLM.call_prose)
    assert "extra_body" in code and '"max_tokens"' in code, \
        "the legacy spelling must go out beside the new one"


def test_an_ignored_cap_is_on_the_record():
    """An overspend nobody can see is one nobody fixes."""
    from alignmentgraph_isd.core.agentic import client

    assert "completion_cap_ignored" in inspect.getsource(client.AgenticLLM.call_prose)


def test_the_fold_is_not_asked_to_think():
    """It compresses a transcript it is handed whole: there is nothing to
    reason about, and on a ladder served with thinking ON the reasoning is
    billed in the same completion budget as the answer.

    MEASURED (run bdb68b56): one fold returned 4,701 completion tokens
    carrying 1,061 CHARACTERS — about 350 tokens of summary and 4,350 of
    reasoning — and took 244 s, a third of that run's model time. It is also
    what makes the cap safe: sized for the summary alone, it would be spent on
    reasoning before a character of answer appeared."""
    model = _Model()

    compaction.summarize(model, "", [{"role": "user", "content": "x" * 400}])

    assert model.body.get("chat_template_kwargs") == {"enable_thinking": False}


def test_a_failed_fold_says_what_failed():
    """`error` on its own is unattributable: run bdb68b56 spent 244 s, was
    accounted for in full, and still came back `error` with nothing anywhere
    naming what raised."""
    noted: list = []

    class _Raises:
        identity = "Orchestrator"
        trajectory = type("T", (), {
            "log_recovery_event": lambda self, *a: noted.append(a)})()

        def call_prose(self, messages, **kwargs):
            raise RuntimeError("the backend hung up")

    summary, outcome = compaction.summarize(_Raises(), "kept", [{"role": "user", "content": "x"}])

    assert (summary, outcome) == ("kept", "error")
    assert noted and "RuntimeError" in noted[0][1:] or any("hung up" in str(a) for a in noted[0])
