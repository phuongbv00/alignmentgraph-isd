"""The shape the benchmark reads.

`isd-agent-benchmark` installs this package and parses the result dict with its
evaluator and pooling scripts. Those readers are in another repository, so
nothing here would catch a change that breaks them — this file pins the
contract from this side.

It asserts structure, not values: which keys exist, and what type each carries.
"""
from __future__ import annotations

import inspect

import pytest

from alignmentgraph_isd import DesignBrief, MetaAgent, run_design_brief
from alignmentgraph_isd.config import HarnessRunConfig
from alignmentgraph_isd.core.runner import run_workflow
from alignmentgraph_isd.core.trajectory import TrajectoryLogger

from conftest import load_brief

# Recorded from results/test_90_benchmark_Qwen3.5-9B_r2_20260726_160306, i.e. a
# run made before the on_event hook existed.
# What the benchmark reads. `trajectory_deep` is additive and deliberately not
# in this set — the point of the assertion below is that adding it did not
# disturb any of these.
RESULT_KEYS = {"addie_output", "trajectory", "metadata", "graph", "graph_dot"}

TRAJECTORY_LISTS = {
    "tool_calls", "reasoning_steps", "agent_interactions", "agent_steps",
    "node_edits", "validation_events", "verifier_events", "repair_events",
    "retrieval_events",
}
TRAJECTORY_SCALARS = {"llm_calls": int, "latency_ms": float}
TOKEN_USAGE_KEYS = {"prompt_tokens", "completion_tokens"}

METADATA_KEYS = {
    "llm", "run_config", "design_brief_id", "violations", "errors",
    "validation_errors", "schema_violations", "audit", "task_attempts",
    "repair_metrics",
}
RUN_CONFIG_KEYS = {
    "enable_verifier", "enable_graph_context", "use_rag",
    "regen_budget", "regen_backoff_seconds",
}
AUDIT_KEYS = {
    "node_counts", "missing_node_types", "missing_section_keys", "schema_violations",
    "objective_node_id", "objective_ids", "objective_count", "unmeasured_objectives",
    "unsupported_objectives", "unevaluated_objectives", "verifier_violations",
    "ready_to_aggregate", "relation_coverage", "summary",
}
REPAIR_METRIC_KEYS = {
    "repair_events", "repair_success_rate", "validation_error_count",
    "verifier_rounds", "peak_violation_count", "residual_violation_count",
}
ADDIE_PHASES = {"analysis", "design", "development", "implementation", "evaluation"}
GRAPH_KEYS = {"nodes", "edges", "objective_alignment", "relation_coverage", "metadata"}
NODE_KEYS = {"type", "id", "data"}
EDGE_KEYS = {"type", "source", "target", "evidence", "rationale", "relation_id", "established_by"}


@pytest.fixture(scope="module")
def result(request):
    config = HarnessRunConfig()
    # Built here rather than via the fixture so this can be module-scoped: the
    # full pipeline runs once for the whole file.
    from conftest import FakeChatModel

    config.llm_factory = lambda: FakeChatModel()
    return run_design_brief(load_brief("java_oop_brief.json"), config)


def test_callers_can_still_omit_on_event():
    """The benchmark adapter calls `MetaAgent(config).run(scenario)` and the
    tests construct `TrajectoryLogger()`; both must keep working untouched."""
    assert inspect.signature(TrajectoryLogger.__init__).parameters["on_event"].default is None
    for func in (run_workflow, MetaAgent.run):
        parameter = inspect.signature(func).parameters["on_event"]
        assert parameter.default is None
        # Keyword-only, so it can never shift an existing positional argument.
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY


def test_result_keys(result):
    """Every key the benchmark reads is present and unchanged.

    Extra keys are allowed — the benchmark picks the ones it wants by name — so
    this is a superset check, not equality. What must never happen is one of
    these going missing or changing meaning.
    """
    assert RESULT_KEYS <= set(result)


def test_the_deep_trajectory_is_additive(result):
    """The detailed record lives in its own key so `trajectory` keeps exactly
    the shape the evaluator and the pooling scripts parse."""
    deep = result["trajectory_deep"]
    assert deep["format"] == "deep"
    assert deep["actions"] and deep["summary"]["action_count"] == len(deep["actions"])

    # It describes the same run without touching the recorded streams.
    assert set(result["trajectory"]) == TRAJECTORY_LISTS | set(TRAJECTORY_SCALARS) | {"token_usage"}
    assert "actions" not in result["trajectory"]

    # Every action says who did it and what kind of work it was.
    for action in deep["actions"]:
        assert action["kind"]
        assert "actor" in action and "phase" in action
        assert action["seq"] >= 1


def test_trajectory_streams(result):
    trajectory = result["trajectory"]
    assert set(trajectory) == TRAJECTORY_LISTS | set(TRAJECTORY_SCALARS) | {"token_usage"}
    for key in TRAJECTORY_LISTS:
        assert isinstance(trajectory[key], list), f"{key} is no longer a list"
    for key, expected in TRAJECTORY_SCALARS.items():
        assert isinstance(trajectory[key], expected), f"{key} changed type"
    assert set(trajectory["token_usage"]) == TOKEN_USAGE_KEYS


def test_agent_step_record_shape(result):
    """`agent_steps` is the complete trace; `tool_calls` is the BFCL-style view
    the benchmark's trajectory scorer reads."""
    step = result["trajectory"]["agent_steps"][0]
    assert set(step) == {"agent_name", "action", "input_summary", "output_summary", "timestamp"}

    call = result["trajectory"]["tool_calls"][0]
    assert set(call) == {"step", "tool", "args", "result", "timestamp"}
    assert set(call["args"]) == {"agent", "action", "input_summary"}


def test_metadata_keys(result):
    metadata = result["metadata"]
    assert set(metadata) == METADATA_KEYS
    assert set(metadata["run_config"]) == RUN_CONFIG_KEYS
    assert set(metadata["audit"]) == AUDIT_KEYS
    assert set(metadata["repair_metrics"]) == REPAIR_METRIC_KEYS


def test_addie_output_phases(result):
    assert set(result["addie_output"]) == ADDIE_PHASES


def test_graph_dump_shape(result):
    """The dump is the auditability contribution and the RQ2 scorer's input."""
    graph = result["graph"]
    assert set(graph) == GRAPH_KEYS
    assert set(graph["nodes"][0]) == NODE_KEYS
    assert set(graph["edges"][0]) == EDGE_KEYS
    assert set(graph["relation_coverage"]) == {f"R{i}" for i in range(1, 14)}

    for flags in graph["objective_alignment"].values():
        assert set(flags) == {"measured", "supported", "evaluated", "bloom_ok", "aligned"}

    assert set(graph["metadata"]) >= {
        "design_brief_id", "generated_at", "node_count", "edge_count",
        "node_counts_by_type", "edge_counts_by_type",
    }


def test_graph_dot_is_a_digraph(result):
    assert result["graph_dot"].lstrip().startswith("digraph")


def test_scenario_id_still_maps_to_brief_id():
    """The one translation point between the benchmark's vocabulary and this
    package's, mirrored by the demo app's scenario import."""
    brief = DesignBrief(**{**{"scenario_id": "BAL-TEEN3-0013"}, "id": "BAL-TEEN3-0013"})
    assert brief.id == "BAL-TEEN3-0013"
