"""The Designer's work-set plan must actually reach the Developers.

MEASURED BUG, found 2026-09-03 while splitting the stage submit into one tool
per artifact. ``commit_assessment`` stripped ``dev_plan`` and wrote it nowhere,
``commit_activities`` stored only its two strategy keys, and
``run._dispatch_payload`` reads the fan-out's input back OUT of the design
state — so ``normalize_assessment_dev_plan`` was handed ``None`` on every run
and the deterministic fallback always ran. On the test fixture both families
reported ``source=fallback`` every single time.

Nothing failed loudly: the fallback produces reasonable sets. What was lost is
the thing the ablation is about — the agent's own grouping decision, the
``instrument_hint``/``block_theme`` that keeps two Developers writing the same
objective from writing the same thing twice, and the ``expected_activities``
field that was added to the planner's rules for exactly this purpose.

The plan is kept ON the plan section, where the graph dump shows an auditor how
the family was divided up, and stripped at aggregation so the deliverable does
not carry harness bookkeeping.
"""
from __future__ import annotations

import pytest

from alignmentgraph_isd.core.aggregate import _merge_node_data
from alignmentgraph_isd.core.agentic import fanout, specialists as sp
from alignmentgraph_isd.core.agentic.run import _dispatch_payload
from alignmentgraph_isd.core.alignment_graph import AlignmentGraph, NodeType
from alignmentgraph_isd.core.prose_store import ProseStore
from alignmentgraph_isd.core.trajectory import TrajectoryLogger

_PLAN = {"summative": ["Capstone"],
         "lo_coverage_targets": {"ILO-01": ["summative"], "ILO-02": ["summative"]}}
_DEV_PLAN = {"instrument_sets": [
    {"set_id": "SET-A", "objectives": ["ILO-01", "ILO-02"],
     "plan_categories": ["summative"],
     "instrument_hint": "one integrated case scenario"}]}


def _graph_with_two_objectives() -> tuple[AlignmentGraph, TrajectoryLogger]:
    graph, trajectory = AlignmentGraph(), TrajectoryLogger()
    for i in (1, 2):
        graph.add_element_node(NodeType.OBJECTIVE, f"ILO-0{i}",
                               {"id": f"ILO-0{i}", "level": "apply"})
    return graph, trajectory


def test_the_planners_own_grouping_is_what_the_fanout_uses():
    graph, trajectory = _graph_with_two_objectives()
    sp.commit_assessment(graph, trajectory, {"assessment_plan": _PLAN})
    sp.commit_assessment(graph, trajectory, {"dev_plan": _DEV_PLAN})

    payload = _dispatch_payload(graph, fanout.SPECS["assessment"])
    assert payload.get("dev_plan") == _DEV_PLAN, "the dev plan never reached the planner"

    work_sets, stats = fanout.SPECS["assessment"].plan_sets(graph, payload)
    assert not stats["fallback_used"], "the agent planned, and the fallback ran anyway"
    # One set, because that is what the agent asked for — the fallback would
    # have made one per (objective, category) pair.
    assert len(work_sets) == 1
    assert set(work_sets[0].objectives) == {"ILO-01", "ILO-02"}


def test_a_second_submit_does_not_drop_the_first():
    """The plan and the dev plan arrive in SEPARATE calls now, so a section
    commit that replaces rather than merges loses whichever came first."""
    graph, trajectory = _graph_with_two_objectives()
    sp.commit_assessment(graph, trajectory, {"dev_plan": _DEV_PLAN})
    sp.commit_assessment(graph, trajectory, {"assessment_plan": _PLAN})

    data = graph.get_node(graph.section_id(NodeType.ASSESSMENT_PLAN))["data"]
    assert data.get("dev_plan") == _DEV_PLAN, "the dev plan was overwritten"
    assert data.get("lo_coverage_targets"), "the plan was overwritten"


def test_the_deliverable_does_not_carry_the_dev_plan():
    """It is harness bookkeeping: the judge scores the ADDIE output, and a work
    -set plan in the assessment plan is neither instructional design nor
    something a course could use."""
    graph, trajectory = _graph_with_two_objectives()
    sp.commit_assessment(graph, trajectory, {"assessment_plan": _PLAN, "dev_plan": _DEV_PLAN})

    shipped = _merge_node_data(graph.section_nodes(NodeType.ASSESSMENT_PLAN))
    assert "dev_plan" not in shipped
    assert shipped.get("lo_coverage_targets"), "the plan itself must still ship"
    # ...but the graph, which is the auditability contribution, still holds it.
    assert graph.get_node(graph.section_id(NodeType.ASSESSMENT_PLAN))["data"]["dev_plan"]


@pytest.mark.parametrize("nested", [False, True])
def test_a_dev_plan_nested_inside_the_plan_is_still_kept(nested):
    """A model that puts the dev plan inside `assessment_plan` — which the
    schema's own layout invites — must not lose it. That nesting is why the
    stripping existed in the first place."""
    graph, trajectory = _graph_with_two_objectives()
    payload = ({"assessment_plan": {**_PLAN, "dev_plan": _DEV_PLAN}} if nested
               else {"assessment_plan": _PLAN, "dev_plan": _DEV_PLAN})
    sp.commit_assessment(graph, trajectory, payload)

    assert _dispatch_payload(graph, fanout.SPECS["assessment"])["dev_plan"] == _DEV_PLAN


def test_the_prose_arm_keeps_it_the_same_way():
    """Same rule on the blackboard: the axis is the alignment machinery, and a
    dev plan that survives on one substrate and not the other would put a
    planning difference on it."""
    store, trajectory = ProseStore(), TrajectoryLogger()
    sp.commit_assessment_prose(store, trajectory, {"assessment_plan": _PLAN})
    sp.commit_assessment_prose(store, trajectory, {"dev_plan": _DEV_PLAN})

    doc = store.get("assessment_plan")
    assert doc.get("dev_plan") == _DEV_PLAN
    assert doc.get("lo_coverage_targets")


def test_the_activity_planners_blocks_reach_its_developers_too():
    graph, trajectory = _graph_with_two_objectives()
    blocks = {"activity_blocks": [
        {"set_id": "BLOCK-A", "objectives": ["ILO-01", "ILO-02"],
         "block_theme": "one shared progression", "expected_activities": 3}]}
    sp.commit_activities(graph, trajectory, {
        "instructional_strategies": {"model": "Gagné"}, "dev_plan": blocks})

    payload = _dispatch_payload(graph, fanout.SPECS["activities"])
    assert payload.get("dev_plan") == blocks
    work_sets, stats = fanout.SPECS["activities"].plan_sets(graph, payload)
    assert not stats["fallback_used"]
    assert len(work_sets) == 1
