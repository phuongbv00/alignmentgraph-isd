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
"""
from __future__ import annotations

from alignmentgraph_isd.core.agentic import compaction


def _dropped(n: int = 3) -> list:
    return [{"role": "tool", "name": "read_nodes",
             "content": f"ILO-0{i}: apply inheritance to a domain model"} for i in range(n)]


def test_the_summary_folds_the_previous_one_in():
    """Rolling, not accumulating: each compaction folds what went before with
    what just went, so the note stays one fixed-size block however long the run
    gets and each call's input stays bounded."""
    seen = {}

    def model(messages, _retries=0):
        seen["prompt"] = messages[-1]["content"]
        return "Objectives ILO-01..03 established; assessment plan pending."

    out = compaction.summarize(model, "Earlier: scenario read.", _dropped())

    assert out.startswith("Objectives ILO-01")
    assert "Earlier: scenario read." in seen["prompt"], "the fold gets what came before"
    assert "ILO-01" in seen["prompt"], "and what just went"


def test_an_unusable_answer_keeps_the_previous_summary():
    """A failed fold must not also erase what earlier ones managed to keep. A
    model asked for prose under a system turn it has never seen answers with an
    apology, an empty object or nothing often enough to be worth naming."""
    previous = "Objectives established."
    for answer in ("", "   ", "{}", '{"summary": "x"}', "[]", None):
        assert compaction.summarize(lambda *_a, **_k: answer, previous, _dropped()) == previous


def test_a_failing_model_never_breaks_compaction():
    """A summary is an improvement on the note, never a precondition for
    compaction working — the turns are gone either way and the run continues."""
    def explode(*_a, **_k):
        raise RuntimeError("endpoint down")

    assert compaction.summarize(explode, "kept", _dropped()) == "kept"


def test_nothing_dropped_means_nothing_asked():
    calls = []
    assert compaction.summarize(lambda *a, **k: calls.append(a), "kept", []) == "kept"
    assert not calls, "a compaction that removed nothing must not spend a call"


def test_the_input_and_the_output_are_both_bounded():
    """The summary is standing furniture — never trimmed — so it must never
    become the reason the window is full; and folding a summary of a summary
    of a summary is where this stops meaning anything."""
    huge = [{"role": "tool", "content": "x" * 5000} for _ in range(20)]
    seen = {}

    def model(messages, _retries=0):
        seen["len"] = len(messages[-1]["content"])
        return "y" * 5000

    out = compaction.summarize(model, "", huge)

    assert len(out) <= compaction.MAX_SUMMARY_CHARS
    assert seen["len"] < len(huge) * 5000, "the oldest dropped turns are elided"


def test_the_note_carries_the_summary_and_stays_one_note():
    from alignmentgraph_isd.core.agentic.loop import (
        COMPACTION_NOTE, _with_note, running_summary,
    )

    messages = [{"role": "system", "content": "S"}, {"role": "user", "content": "live"}]
    once = _with_note(messages, 4, "objectives ILO-01..03 exist")

    assert running_summary(once) == "objectives ILO-01..03 exist"
    assert "objectives ILO-01..03 exist" in once[1]["content"], "the model actually sees it"
    assert "4 earlier turn(s)" in once[1]["content"], "and how much went"

    twice = _with_note(once, 9, "…and the assessment plan")
    assert len([m for m in twice if m.get(COMPACTION_NOTE)]) == 1, "one note, rewritten"
    assert running_summary(twice) == "…and the assessment plan"


def test_both_arms_go_through_the_same_call():
    """The asymmetry has to be MEASURED, which means it must not be designed:
    one implementation, one trigger, one budget, called identically."""
    import inspect

    from alignmentgraph_isd.core.agentic import loop, react

    for module in (loop, react):
        source = inspect.getsource(module)
        # The CALL, not the definition: `"compact(" in source` also matched
        # `def compact(`, so loop.py passed on its own definition alone.
        assert "self.messages = compact(" in source, (
            f"{module.__name__} never calls the shared compact(), so its loop "
            "cannot recover from a full window")
    # ...and the stats it keeps are declared by both, so a run can be compared.
    for module_stats in (loop.ToolLoop, react.ReactLoop):
        assert "compactions" in inspect.getsource(module_stats.__init__)
