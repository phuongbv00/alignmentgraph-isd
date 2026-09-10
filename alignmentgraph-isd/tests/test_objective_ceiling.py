"""The ILO ceiling: a number derived from the design brief and TOLD to the
agent in its own stage rules.

Objective count is the root multiplier of the pipeline — assessment
obligations are up to three (objective, plan_category) pairs each, the
activity fallback is ``objective_count * ACTIVITIES_PER_OBJECTIVE``, content
modules cover those activities and session guides schedule every one of them.
Run single_20260904_020259 is what an unbounded list costs: 50 objectives ->
161 activities, the implementation stage gave up, and the graph dump carried
0 P10 and 0 P11 edges.

Nothing enforces the ceiling, so what these tests hold is that the number is
reproducible from the scenario file alone, that the number the agent is TOLD
is the number the code computes, and that both decomposition arms are told the
same one.
"""
from __future__ import annotations

import re

from alignmentgraph_isd import HarnessRunConfig
from alignmentgraph_isd.core import dev_plans
from alignmentgraph_isd.core.agentic import react
from alignmentgraph_isd.core.agentic.specialists import STEPS
from alignmentgraph_isd.core.alignment_graph import AlignmentGraph
from alignmentgraph_isd.core.brief import DesignBrief
from alignmentgraph_isd.core.trajectory import TrajectoryLogger

_OUTCOMES = next(s for s in STEPS if s.name == "outcomes")

_GOALS3 = ["goal one", "goal two", "goal three"]


def _brief(duration: str = "", goals: list | None = None, **extra) -> DesignBrief:
    return DesignBrief(context={"duration": duration},
                       learning_goals=_GOALS3 if goals is None else goals,
                       **extra)


def test_the_ceiling_is_a_pure_function_of_the_brief():
    """Same brief, same number — and only two fields move it.

    Reproducibility from the scenario file is what lets this be disclosed as a
    property of the system under test rather than as run variance.
    """
    brief = _brief("Mid-term course (2-4 weeks)")
    assert len({dev_plans.max_objectives(brief) for _ in range(5)}) == 1

    # Nothing about the model, the arm or the run reaches it.
    assert dev_plans.max_objectives(brief) == dev_plans.max_objectives(
        DesignBrief(context={"duration": "Mid-term course (2-4 weeks)"},
                    learning_goals=list(_GOALS3)))


def test_class_size_and_difficulty_do_not_move_the_ceiling():
    """Their absence from the formula is a CLAIM, not an oversight: class size
    changes how a course is delivered, not how many outcomes it has, and
    ``difficulty`` describes the brief's constraints rather than its content
    volume (30/30/30 across the 90 test scenarios, uncorrelated with
    duration). A test that let either one move the number would let the policy
    drift into them silently."""
    base = _brief("Mid-term course (2-4 weeks)")
    expected = dev_plans.max_objectives(base)
    for field, value in (
        ("difficulty", "Hard - Complex requirements with multiple constraints"),
        ("domain", "Mathematics"),
        ("title", "A very much longer course title"),
    ):
        assert dev_plans.max_objectives(_brief(
            "Mid-term course (2-4 weeks)", **{field: value})) == expected, field

    crowded = DesignBrief(
        context={"duration": "Mid-term course (2-4 weeks)",
                 "class_size": "Large (30+ learners)"},
        learning_goals=list(_GOALS3))
    assert dev_plans.max_objectives(crowded) == expected


def test_each_duration_bucket_maps_to_its_documented_multiplier():
    """The three strings the dataset actually uses, and the ordering they
    depend on: "Short-term intensive (within 1 week)" carries "week" and
    "Long-term course (1-6 months)" carries "month", so a matcher that tried
    ``mid`` first would read every bucket in the dataset as ``mid``."""
    for text, bucket in (
        ("Short-term intensive (within 1 week)", "short"),
        ("Mid-term course (2-4 weeks)", "mid"),
        ("Long-term course (1-6 months)", "long"),
    ):
        assert dev_plans.duration_bucket(text) == bucket, text
        assert dev_plans.max_objectives(_brief(text)) == (
            dev_plans.OBJECTIVES_PER_GOAL[bucket] * len(_GOALS3))


def test_an_unstated_duration_gets_the_middle_bucket():
    for text in ("", None, "whenever the cohort is ready"):
        assert dev_plans.duration_bucket(text) == dev_plans.DEFAULT_DURATION_BUCKET


def test_a_brief_with_no_goals_gets_the_floor():
    """The app's sparse path: a ``user_message``-only brief names no learning
    goals, and a bare per-goal product would tell it a ceiling of zero."""
    assert dev_plans.max_objectives(DesignBrief(user_message="build me a course")) == (
        dev_plans.MIN_OBJECTIVES)
    assert dev_plans.max_objectives(None) == dev_plans.MIN_OBJECTIVES


def test_the_top_level_duration_is_honoured_when_context_has_none():
    """The benchmark's scenarios put duration under ``context`` and leave the
    top-level field empty on all 90 of them; the CLI and the app set the
    top-level one. Reading only ``context.duration`` would put every CLI and
    app run silently on the default."""
    top = DesignBrief(duration="Long-term course (1-6 months)",
                      learning_goals=list(_GOALS3))
    assert dev_plans.max_objectives(top) == (
        dev_plans.OBJECTIVES_PER_GOAL["long"] * len(_GOALS3))

    # ...and `context` wins when both are set, because that is the benchmark's.
    both = DesignBrief(duration="Short-term intensive (within 1 week)",
                       context={"duration": "Long-term course (1-6 months)"},
                       learning_goals=list(_GOALS3))
    assert dev_plans.max_objectives(both) == (
        dev_plans.OBJECTIVES_PER_GOAL["long"] * len(_GOALS3))


def _ceiling_in(text: str) -> int:
    found = re.search(r"Write between 1 and (\d+) objectives", text)
    assert found, "the outcomes rules no longer state a ceiling"
    return int(found.group(1))


def test_the_number_in_the_prompt_is_the_number_the_code_computes():
    """The rule ``RULES_ACTIVITY_DEV_PLAN`` already follows for
    ``max_units("activity")``: the told number is IMPORTED, never written
    twice. A designer held to a different number than the code uses gets its
    work taken apart behind it."""
    for duration in ("Short-term intensive (within 1 week)",
                     "Mid-term course (2-4 weeks)",
                     "Long-term course (1-6 months)",
                     ""):
        for goals in (list(_GOALS3), _GOALS3 + ["goal four"], []):
            brief = _brief(duration, goals)
            assert _ceiling_in(_OUTCOMES.task_block(brief)) == (
                dev_plans.max_objectives(brief)), (duration, len(goals))


def test_the_rules_never_claim_the_harness_discards_anything():
    """The ceiling is told and not enforced. A sentence like "only the first N
    reach the design" would be the prompt telling the model something untrue
    about the harness — and would be the easiest thing to leave behind if
    enforcement were ever added and then removed again."""
    text = _OUTCOMES.task_block(_brief("Mid-term course (2-4 weeks)")).lower()
    for claim in ("discard", "will be dropped", "only the first", "reach the design"):
        assert claim not in text, claim


def test_both_arms_are_told_the_same_ceiling():
    """The stage turn is composed once, in ``AgenticStep.task_block``, and both
    loops render it. This is the axis: a ceiling that differed between the
    arms would be a second variable inside ``agent_mode``."""
    brief = _brief("Long-term course (1-6 months)", _GOALS3 + ["goal four"])
    loop = react.ReactLoop(HarnessRunConfig(llm_factory=lambda: None),
                           AlignmentGraph(), TrajectoryLogger(), brief)
    multi_text = _OUTCOMES.task_block(brief)
    assert multi_text in loop.stage_brief("outcomes")
    assert _ceiling_in(multi_text) == dev_plans.max_objectives(brief) == 16


def test_every_other_step_is_untouched_by_the_brief():
    """Only ``outcomes`` carries a per-run number. If a second step ever grows
    one it needs its own measured reason, and this test is where that shows
    up."""
    brief = _brief("Long-term course (1-6 months)")
    for step in STEPS:
        if step.name == "outcomes":
            assert step.rules_vars is not None
            continue
        assert step.rules_vars is None, step.name
        assert step.task_block(brief) == step.task_block(), step.name


# ---------------------------------------------------------------------------
# Accumulation parity. Not part of the ceiling: a pre-existing difference on
# the `context_mode` axis that the ceiling made visible.
# ---------------------------------------------------------------------------

def _two_submits() -> list[dict]:
    """Two instalments that overlap — a regen re-sending what it already
    wrote is the ordinary way this happens."""
    first = {"learning_objectives": [
        {"id": "ILO-01", "statement": "Explain X", "level": "understand",
         "bloom_verb": "explain"},
        {"id": "ILO-02", "statement": "Apply Y", "level": "apply",
         "bloom_verb": "apply"},
    ]}
    second = {"learning_objectives": [
        {"id": "ILO-02", "statement": "apply y", "level": "apply",
         "bloom_verb": "apply"},                      # the same one, recased
        {"id": "ILO-03", "statement": "Analyse Z", "level": "analyze",
         "bloom_verb": "analyze"},
    ]}
    return [first, second]


def _statements(items) -> list[str]:
    return [str(i.get("statement") or "") for i in items]


def test_both_substrates_accumulate_the_same_objectives():
    """``commit_outcomes`` APPENDS element nodes while ``_merge_document``
    REPLACES its key, so a regen or a second accepted submit used to leave the
    two substrates holding different designs. That is a data loss on the
    ``context_mode`` axis itself, not on the alignment machinery that axis
    ablates."""
    from alignmentgraph_isd.core.agentic import specialists
    from alignmentgraph_isd.core.alignment_graph import AlignmentGraph, NodeType
    from alignmentgraph_isd.core.prose_store import ProseStore
    from alignmentgraph_isd.core.trajectory import TrajectoryLogger

    graph, store = AlignmentGraph(), ProseStore()
    for section in _two_submits():
        specialists.commit_outcomes(graph, TrajectoryLogger(), section)
        specialists.commit_outcomes_prose(store, TrajectoryLogger(), section)

    from_graph = _statements(n.get("data") or {}
                             for n in graph.element_nodes(NodeType.OBJECTIVE))
    from_prose = _statements(store.items(str(NodeType.OBJECTIVE), "learning_objectives"))

    assert from_graph == from_prose
    # ...and the repeat was dropped on BOTH, not kept on one.
    assert from_graph == ["Explain X", "Apply Y", "Analyse Z"]


def test_the_single_arm_does_not_append_an_already_additive_document():
    """``ReactLoop._commit`` re-merges prose list fields because a prose commit
    replaces its key. A commit that appends for itself would otherwise land
    ``previous + (previous + new)``."""
    from alignmentgraph_isd.core.agentic import react, specialists
    from alignmentgraph_isd.core.alignment_graph import NodeType

    assert str(NodeType.OBJECTIVE) in specialists.ADDITIVE_PROSE_DOC_KEYS
    assert str(NodeType.OBJECTIVE) not in react._doc_keys(_OUTCOMES)
