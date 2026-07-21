"""P1.5: structured trajectory events + headline repair metrics in metadata."""
from __future__ import annotations

from alignmentgraph_isd import run_design_brief
from alignmentgraph_isd.core.trajectory import TrajectoryLogger

from conftest import load_brief


def test_trajectory_has_structured_event_streams(fake_config):
    result = run_design_brief(load_brief("minimal_brief.json"), fake_config)
    traj = result["trajectory"]
    for key in ("validation_events", "verifier_events", "repair_events"):
        assert key in traj, key
    # at least one verifier round and one addie validation pass happened
    assert traj["verifier_events"], "expected a verifier round"
    assert any(e["scope"] == "addie_output" for e in traj["validation_events"])


def test_metadata_exposes_repair_metrics(fake_config):
    result = run_design_brief(load_brief("minimal_brief.json"), fake_config)
    metrics = result["metadata"]["repair_metrics"]
    for key in (
        "repair_events", "repair_success_rate",
        "validation_error_count", "residual_violation_count",
    ):
        assert key in metrics, key
    assert "validation_errors" in result["metadata"]


def test_repair_logs_structured_repair_events():
    from alignmentgraph_isd import HarnessRunConfig
    from alignmentgraph_isd.core.agents.assessment_design import AssessmentDesignAgent
    from alignmentgraph_isd.core.agents.pedagogical_verifier import VerifierViolation
    from alignmentgraph_isd.core.graph import AlignmentGraph

    graph = AlignmentGraph()
    graph.add_node("objective", "objective_0", {"learning_objectives": [{"id": "LO-01", "statement": "Apply X"}]})
    graph.add_element_node("objective", "LO-01", {"id": "LO-01", "statement": "Apply X"})
    traj = TrajectoryLogger()
    config = HarnessRunConfig()

    violation = VerifierViolation(
        node_id="objective:LO-01", edge_type="measures", violation_type="R3",
        message="LO-01 unmeasured", metadata={"lo_id": "LO-01"},
    )
    AssessmentDesignAgent(config, graph, traj).repair([violation])

    assert traj.repair_events, "expected a structured repair event"
    assert traj.repair_events[0]["violation_type"] == "R3"
    assert "assessment_tools" in traj.repair_events[0]["repaired_fields"]


def test_summary_metrics_computes_repair_success_rate():
    traj = TrajectoryLogger()
    traj.log_verifier_result([{"type": "coverage"}, {"type": "coverage"}, {"type": "bloom"}])
    metrics = traj.summary_metrics(residual_violation_count=1)
    assert metrics["peak_violation_count"] == 3
    assert metrics["repair_success_rate"] == (3 - 1) / 3
