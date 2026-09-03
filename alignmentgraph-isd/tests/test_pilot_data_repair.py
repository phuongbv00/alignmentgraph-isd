"""The pilot-data half of the evaluation_quality check + its repair
(core/checks.py::evaluation_quality_data, core/repairs.py::repair_pilot_data_plan).

The aggregator builds the whole formative half of ADDIE Evaluation from
assessment_plan.pilot_data_plan; before this check nothing enforced it, and a
small model that dropped or thinned it shipped an evaluation phase the rubric
scored 0-2 (measured on both arms)."""
from __future__ import annotations

from alignmentgraph_isd.core import checks, repairs
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




def _ctx(graph, llm_response: str = "") -> repairs.RepairContext:
    return repairs.RepairContext(
        graph=graph, store=None, trajectory=TrajectoryLogger(), actor="Test")
