"""The pilot-data half of the evaluation_quality check + its repair
(core/checks.py::evaluation_quality_data, core/repairs.py::repair_pilot_data_plan).

The aggregator builds the whole formative half of ADDIE Evaluation from
assessment_plan.pilot_data_plan; before this check nothing enforced it, and a
small model that dropped or thinned it shipped an evaluation phase the rubric
scored 0-2 (measured on both arms)."""
from __future__ import annotations

from alignmentgraph_isd.core import checks, repairs
from alignmentgraph_isd.core.alignment_graph import AlignmentGraph, NodeType
from alignmentgraph_isd.core.trajectory import TrajectoryLogger

_GOOD_PILOT = {
    "collection_points": ["After module 1", "Before the final task"],
    "anticipated_difficulties": [
        {"area": "ILO-01", "rationale": "Hard concept.", "detected_by": "Exit tickets",
         "first_revision": "Add a worked example."},
        {"area": "MOD-02", "rationale": "Dense module.", "detected_by": "Exit tickets",
         "first_revision": "Split into two sessions."},
    ],
}

_BASE_PLAN = {
    "formative": ["Weekly critique"],
    "formative_methods": ["Weekly critique with rubric"],
    "lo_coverage_targets": {"ILO-01": ["formative"]},
}


def _quality_violations(plan: dict):
    return [v for v in checks.evaluation_quality_data("assessment_plan_0", plan)
            if v.metadata.get("section") == "pilot_data_plan"]


def test_complete_pilot_data_plan_passes():
    assert _quality_violations({**_BASE_PLAN, "pilot_data_plan": _GOOD_PILOT}) == []


def test_missing_or_thin_pilot_data_plan_is_flagged():
    assert _quality_violations(_BASE_PLAN)  # missing entirely
    one_difficulty = {
        **_GOOD_PILOT,
        "anticipated_difficulties": _GOOD_PILOT["anticipated_difficulties"][:1],
    }
    assert _quality_violations({**_BASE_PLAN, "pilot_data_plan": one_difficulty})
    no_points = {**_GOOD_PILOT, "collection_points": []}
    assert _quality_violations({**_BASE_PLAN, "pilot_data_plan": no_points})


def _graph_with_plan_and_objectives(plan: dict) -> AlignmentGraph:
    graph = AlignmentGraph()
    graph.add_node(NodeType.ASSESSMENT_PLAN, graph.section_id(NodeType.ASSESSMENT_PLAN), plan)
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {
        "id": "ILO-01", "level": "evaluate", "statement": "Evaluate designs."})
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-02", {
        "id": "ILO-02", "level": "remember", "statement": "List the pillars."})
    return graph


def _ctx(graph, llm_response: str = "") -> repairs.RepairContext:
    return repairs.RepairContext(
        graph=graph, store=None, trajectory=TrajectoryLogger(),
        call_llm=lambda messages, max_retries=0: llm_response, actor="Test")


def test_repair_fallback_grounds_difficulties_in_real_objectives():
    graph = _graph_with_plan_and_objectives(dict(_BASE_PLAN))
    violation = _quality_violations(_BASE_PLAN)[0]

    repairs.repair_pilot_data_plan(_ctx(graph, llm_response=""), violation)

    plan = graph.get_node(graph.section_id(NodeType.ASSESSMENT_PLAN))["data"]
    pilot = plan["pilot_data_plan"]
    assert plan.get("repaired") is True
    assert pilot["collection_points"]
    areas = [d["area"] for d in pilot["anticipated_difficulties"]]
    # Highest cognitive demand first, anchored to the objective id — the
    # rubric grades pilot data by the module learners struggled in, so a bare
    # LO id no longer suffices (2026-08-28, measured: item 28 scored 2.5 on
    # exactly this bare-id output).
    assert "ILO-01" in areas[0]
    assert all(d["first_revision"] for d in pilot["anticipated_difficulties"])
    # And the repaired plan now passes the check that flagged it.
    assert _quality_violations(plan) == []


def test_repair_fallback_anchors_areas_to_topics_when_available():
    graph = _graph_with_plan_and_objectives(dict(_BASE_PLAN))
    graph.add_element_node(NodeType.TOPIC, "TOP-01", {
        "id": "TOP-01", "topic": "Interactive content design"})
    violation = _quality_violations(_BASE_PLAN)[0]

    repairs.repair_pilot_data_plan(_ctx(graph, llm_response=""), violation)

    pilot = graph.get_node(graph.section_id(NodeType.ASSESSMENT_PLAN))["data"]["pilot_data_plan"]
    areas = [d["area"] for d in pilot["anticipated_difficulties"]]
    assert "Interactive content design" in areas[0] and "ILO-01" in areas[0]


def test_repair_prefers_a_cooperative_llm_answer():
    graph = _graph_with_plan_and_objectives(dict(_BASE_PLAN))
    violation = _quality_violations(_BASE_PLAN)[0]
    llm = (
        '{"collection_points": ["After the VR intro"], "anticipated_difficulties": ['
        '{"area": "ILO-01", "rationale": "r", "detected_by": "d", "first_revision": "f1"},'
        '{"area": "ILO-02", "rationale": "r", "detected_by": "d", "first_revision": "f2"}]}'
    )

    repairs.repair_pilot_data_plan(_ctx(graph, llm_response=llm), violation)

    pilot = graph.get_node(graph.section_id(NodeType.ASSESSMENT_PLAN))["data"]["pilot_data_plan"]
    assert pilot["collection_points"] == ["After the VR intro"]
    assert [d["area"] for d in pilot["anticipated_difficulties"]] == ["ILO-01", "ILO-02"]


def test_render_method_flattens_dict_entries():
    """Regression: a repair that received {"instrument", "cadence"} dicts used
    to ship literal Python-dict text into the judged output."""
    assert repairs._render_method(
        {"instrument": "Exit Ticket", "cadence": "After each module"}
    ) == "Exit Ticket — After each module"
    assert repairs._render_method("Weekly critique") == "Weekly critique"
