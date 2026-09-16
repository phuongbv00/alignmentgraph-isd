"""A repair turn may only raise what its agent can actually clear.

2026-09-03, from a real transcript. The AssessmentDesigner spent all four of
its turns on ``C2``/``plan_coverage`` — "objective ILO-01 has no assessment
item" — at a point in the run where NO assessment item can exist: items are
written by the Developer tier, which has not run. It re-read the same nodes,
hit the repeat guard, and finally submitted ``{"action": "Add C2 link for
ILO-01"}`` into its plan: the appearance of a fix, which is precisely what the
template purge and ``REPORT_ONLY`` exist to prevent.

Two distinct scoping rules come out of it, both measured on the test fixture
where together they were consuming every repair turn in the run:

* a work set's loop sees nothing, because its commit is a no-op and the state
  cannot yet show what it submitted;
* a Designer with a pending Developer tier sees only violations on its OWN
  section nodes.

Neither drops a violation from the run: the deterministic net after the
fan-out and the reconciliation pass collect them again, and what nothing can
fix is counted as residual.
"""
from __future__ import annotations

from dataclasses import replace

from alignmentgraph_isd.core.agentic.repair_turn import own_violations
from alignmentgraph_isd.core.agentic.specialists import STEPS
from alignmentgraph_isd.core.alignment_graph import AlignmentGraph, NodeType
from alignmentgraph_isd.core.trajectory import TrajectoryLogger

from conftest import load_brief

_STEP = {step.name: step for step in STEPS}


def _graph_before_the_developer_tier() -> AlignmentGraph:
    """What the AssessmentDesigner leaves behind: objectives, a plan, no items."""
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {
        "id": "ILO-01", "level": "apply", "statement": "Apply X to Y."})
    graph.add_node(NodeType.ASSESSMENT_PLAN, graph.section_id(NodeType.ASSESSMENT_PLAN), {
        "summative": ["Capstone"],
        "formative": ["Weekly check-in"],   # intent declared...
        "formative_methods": [],            # ...and no method named: the Designer's own gap
        "lo_coverage_targets": {"ILO-01": ["summative"]},
    })
    return graph


def _shown(step, graph) -> list[str]:
    return sorted({v.violation_type for v in own_violations(
        graph, load_brief("minimal_brief.json"), step, TrajectoryLogger())})


def test_the_designer_is_asked_only_about_what_it_wrote_itself():
    graph = _graph_before_the_developer_tier()
    shown = _shown(_STEP["assessment"], graph)

    assert "evaluation_quality" in shown, (
        "the plan's own missing formative_methods IS the Designer's to fix")
    for premature in ("C2", "plan_coverage", "item_completeness"):
        assert premature not in shown, (
            f"{premature} is about assessment items, which the Developer tier "
            "has not written yet — the Designer has no schema to fill them with")


def test_the_premature_violations_are_still_there_to_be_found():
    """The filter is about WHO IS ASKED, not about what the run knows. The same
    checks must still report the gap, or the fix would be hiding it."""
    from alignmentgraph_isd.core.outputs import _collect_violations

    found = {v.violation_type for v in _collect_violations(
        "assessment_designer", _graph_before_the_developer_tier(),
        load_brief("minimal_brief.json"))}
    assert {"C2", "plan_coverage"} <= found


def test_a_work_set_is_never_handed_a_violation_it_has_already_answered():
    """``fanout.set_step`` gives a work set a no-op commit — the driver deposits
    every set together once the loops close. So the state at check time predates
    this Developer's own submit, and everything it would be shown is a gap its
    submit already filled."""
    work_set_step = replace(_STEP["assessment"], name="assessment:AS-01",
                            commits_to_state=False)
    assert _shown(work_set_step, _graph_before_the_developer_tier()) == []


def test_the_filter_is_keyed_on_the_pending_tier_not_on_the_violation_type():
    """C2 and plan_coverage are not intrinsically unshowable — they are
    unshowable to an agent whose Developer tier has not run. Same step, same
    graph, same checks; only the tier is gone, and they come through."""
    no_tier = replace(_STEP["assessment"], name="assessment_without_a_tier")
    shown = _shown(no_tier, _graph_before_the_developer_tier())

    assert {"C2", "plan_coverage"} <= set(shown)
