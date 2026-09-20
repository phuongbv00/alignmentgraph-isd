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

from alignmentgraph_isd import DesignBrief, MetaAgent
from alignmentgraph_isd.config import HarnessRunConfig
from alignmentgraph_isd.core.trajectory import TrajectoryLogger

from conftest import load_brief, run_brief

# What the benchmark reads. `trajectory_deep` is additive and deliberately not
# in this set. The judge surface is exactly `tool_calls`/`reasoning_steps`/
# `agent_interactions` (the evaluator's `_format_trajectory`); everything else
# an agent did travels in the single type-tagged `events` list (2026-08-27:
# it replaced the six per-type streams, and the token/latency scalars moved to
# `metadata.token_usage` where the benchmark's uniform accounter overwrites
# them — the pooling script `ablation/08_pool_ablation_runs.py` reads `events`
# with a per-stream fallback for pre-existing runs).
# `graph_dot` went 2026-09-11: DOT is a RENDERING of `graph`, reproducible from
# it byte-for-byte, so shipping both made the weaker one a second artifact to
# keep in step. `alignmentgraph-isd dot <graph.json>` renders it on demand.
RESULT_KEYS = {"addie_output", "trajectory", "metadata", "graph"}

TRAJECTORY_LISTS = {"tool_calls", "reasoning_steps", "agent_interactions", "events"}
# Every action that can reach `events` (the ones `_record_event` writes). Listed
# explicitly, because this file exists to PIN the contract — and checked against
# the taxonomy below, because the list went stale silently once already:
# `reconcile` had been recorded since 2026-08-27 and never appeared here, since
# the fixture happened to leave no residual cross-family violation to route.
EVENT_ACTIONS = {
    # recovery events
    "retry", "regen_empty_section", "agent_error", "llm_error", "salvage_truncated",
    "invalid_action", "submit_rejected", "submit_invalid_final", "repeated_tool_call",
    "commit_invalid_section", "agentic_fallback", "agentic_gave_up", "budget_exhausted",
    "tool_binding_unavailable", "tool_call_markup_recovered", "repair_unfilled",
    "duplicate_submit", "bare_artifact_wrapped", "context_compacted",
    "duplicate_element_dropped", "commit_did_not_land", "thinking_only_reply",
    "dropped_argument", "argument_reshaped", "tool_choice_downgraded",
    "read_of_assignment_id", "repair_declined", "run_stopped",
    "excess_artifacts_trimmed",
    "items_without_parent",
    "calls_not_executed", "repair_window_closed",
    # structured records
    "repair", "node_add", "node_update", "doc_write", "validate", "check", "audit",
    "retrieval", "work_sets", "reconcile", "converge",
}

#: Actions that only ever reach the deep action log, never `events`.
ACTION_LOG_ONLY = {
    "phase_started", "phase_finished", "node_read", "node_write", "edge_read",
    "edge_write", "edge_walk", "llm_call", "agent_step", "retrieval_query",
}


def test_the_event_vocabulary_is_the_whole_taxonomy():
    """A new action that can land in `events` must be declared here, or the
    contract test above silently stops covering it."""
    from alignmentgraph_isd.core.trajectory import TrajectoryAction

    assert EVENT_ACTIONS | ACTION_LOG_ONLY == {a.value for a in TrajectoryAction}
    assert not EVENT_ACTIONS & ACTION_LOG_ONLY
TOKEN_USAGE_KEYS = {"prompt_tokens", "completion_tokens", "total_tokens", "llm_calls"}

# `violations` and `schema_violations` were dropped 2026-08-27: both were
# byte-for-byte copies of `audit.violations` / `audit.schema_violations`
# with no reader anywhere (benchmark, scripts, server, tests).
METADATA_KEYS = {
    "llm", "token_usage", "run_config", "design_brief_id", "errors",
    "validation_errors", "audit", "task_attempts",
    "repair_metrics",
    # Per-stage autonomy record. Its context_len series is what the
    # decomposition axis is read off, so it is part of the contract, not a
    # debugging extra.
    "autonomy",
}
RUN_CONFIG_KEYS = {
    "agent_mode", "context_mode", "development_mode",
    # The trim budget the stages ran under: it changes what a results dir
    # means, so it is self-describing.
    "max_turns", "submit_budget", "history_char_budget",
    "use_rag", "regen_budget", "regen_backoff_seconds",
    # Serving posture: how many requests the run was allowed to keep in flight
    # (core/ratelimit.py). Recorded because a 429-throttled arm and a clean one
    # are otherwise indistinguishable in a results dir.
    "llm_max_concurrency", "fanout_workers", "protocol_rev", "llm_min_interval_seconds",
}
# The audit's VERDICT and what stopped it — not a second copy of the graph.
# `node_counts`, `relation_coverage`, `unmeasured_objectives`,
# `unsupported_objectives` and `violations` were dropped 2026-09-16: each is a
# measurement already owned by `graph.json` or `violations.json` in the same
# results dir, and the last two were a second IMPLEMENTATION of a predicate
# `viz.objective_annotations` already computes. See
# `GraphAuditResult.to_dict`; `test_the_audit_does_not_re_copy_the_graph`
# below is the guard.
AUDIT_KEYS = {
    "missing_node_types", "missing_section_keys", "schema_violations",
    "objective_ids", "objective_count",
    "ready_to_aggregate", "summary",
}
REPAIR_METRIC_KEYS = {
    "repair_events", "repair_success_rate", "validation_error_count",
    "check_rounds", "peak_violation_count", "residual_violation_count",
}
ADDIE_PHASES = {"analysis", "design", "development", "implementation", "evaluation"}
GRAPH_KEYS = {"nodes", "edges", "objective_alignment", "relation_coverage",
              # `node_id -> violation types` for EVERY node type. Objectives
              # had `objective_alignment`; an activity linked to no objective,
              # a material whose module does not exist, an item with no answer
              # key had no signal on the graph at all.
              "node_violations",
              # The display semantics: the payload is what BOTH renderers read,
              # so what a thing is called, which layer it is on and whether it
              # is marked bad are decided here and not twice.
              "legend", "schema_version", "metadata"}
NODE_KEYS = {"type", "id", "data",
             # `detail`/`level`/`repaired` are why no renderer reads `data` to
             # draw — which is in turn why the server's wire frame can drop
             # `data` and still be a complete picture.
             "label", "kind", "detail", "level", "repaired"}
EDGE_KEYS = {"type", "source", "target", "evidence", "rationale", "relation_id", "established_by",
             "id", "layer", "tier", "invalid", "invalid_reason"}


@pytest.fixture(scope="module")
def result(request):
    config = HarnessRunConfig()
    # Built here rather than via the fixture so this can be module-scoped: the
    # full pipeline runs once for the whole file.
    from conftest import FakeChatModel

    config.llm_factory = lambda: FakeChatModel()
    return run_brief(load_brief("java_oop_brief.json"), config)


def test_callers_can_still_omit_on_event():
    """The benchmark adapter calls `MetaAgent(config).run(scenario)` and the
    tests construct `TrajectoryLogger()`; both must keep working untouched.

    `MetaAgent.run` is the whole public surface since `run_design_brief` was
    removed 2026-09-05, so this is the one signature to hold — `run_brief` in
    conftest is the suite's own wrapper and asserting on it would test the
    fixture."""
    assert inspect.signature(TrajectoryLogger.__init__).parameters["on_event"].default is None
    parameter = inspect.signature(MetaAgent.run).parameters["on_event"]
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
    assert set(result["trajectory"]) == TRAJECTORY_LISTS
    assert "actions" not in result["trajectory"]

    # Every action has the stable timestamp/agent/action/context envelope,
    # and — 2026-08-27 — a real, non-empty agent: harness-level events (phase
    # boundaries, routing checkpoints, the residual audit) are attributed to
    # ORCHESTRATOR rather than falling back to whoever acted last.
    for action in deep["actions"]:
        assert list(action) == ["timestamp", "agent", "action", "context"]
        assert action["agent"], action
        assert action["action"]
        assert isinstance(action["context"], dict)


def test_trajectory_streams(result):
    trajectory = result["trajectory"]
    assert set(trajectory) == TRAJECTORY_LISTS
    for key in TRAJECTORY_LISTS:
        assert isinstance(trajectory[key], list), f"{key} is no longer a list"
    # Every event has the same concurrent-writer-safe envelope, agent included.
    for event in trajectory["events"]:
        assert event["action"] in EVENT_ACTIONS, event
        assert list(event) == ["timestamp", "agent", "action", "context"]
        assert event["agent"], event
    assert set(result["metadata"]["token_usage"]) == TOKEN_USAGE_KEYS


def test_agent_step_record_shape(result):
    """`tool_calls` is the BFCL-style view the benchmark's trajectory scorer
    reads; the full untruncated step record lives only in the deep action log.
    `agent_interactions` carries exactly the fields the scorer formats
    (agent/action/iteration) — no second copy of the output summary."""
    call = result["trajectory"]["tool_calls"][0]
    assert set(call) == {"step", "tool", "args", "result", "timestamp"}
    assert set(call["args"]) == {"agent", "action", "input_summary"}

    interaction = result["trajectory"]["agent_interactions"][0]
    assert set(interaction) == {"iteration", "agent", "action", "timestamp"}

    step_action = next(a for a in result["trajectory_deep"]["actions"]
                       if a["action"] == "agent_step")
    assert {"agent_action", "input_summary", "output_summary"} <= set(step_action["context"])


def test_metadata_keys(result):
    metadata = result["metadata"]
    assert set(metadata) == METADATA_KEYS
    assert set(metadata["run_config"]) == RUN_CONFIG_KEYS
    assert set(metadata["audit"]) == AUDIT_KEYS
    assert set(metadata["repair_metrics"]) == REPAIR_METRIC_KEYS


def test_the_audit_does_not_re_copy_the_graph(result):
    """`metadata.audit` is the verdict; the measurements have their own owner.

    Written against the OWNERS rather than against a key list, because the
    failure this guards is not "a key came back" — it is the copy and the
    original answering differently, which only shows once both are on disk.
    Each pair below was byte-for-byte equal on run 16cef50d, which is why the
    copy went rather than the original.
    """
    audit, graph = result["metadata"]["audit"], result["graph"]
    assert audit  # this is the graph arm; the prose arm's audit is empty

    assert "violations" not in audit
    # The ledger is the owner, and it is the richer one: it says what became of
    # each finding, which a residual snapshot cannot. What made the copy safe
    # to drop is that both were the SAME list — the `residual` that
    # `_reconcile` returns is handed to `audit()` and to `memory.settle()` in
    # the same breath — and this is what that identity looks like from outside:
    # the count the audit's own metrics report is the ledger's open set.
    still_open = [f for f in result["violations"] if f["outcome"] == "open"]
    assert result["metadata"]["repair_metrics"]["residual_violation_count"] == len(still_open)

    for absent, owner in (
        ("relation_coverage", graph["relation_coverage"]),
        ("node_counts", graph["metadata"]["node_counts_by_type"]),
    ):
        assert absent not in audit
        assert owner, f"{absent} left the audit, so {absent}'s owner must carry it"

    # The C2/C3 legs of `objective_alignment` ARE the two objective lists the
    # audit used to publish beside them, from a second implementation.
    assert "unmeasured_objectives" not in audit
    assert "unsupported_objectives" not in audit
    for flags in graph["objective_alignment"].values():
        assert {"assessed_by", "practiced_by"} <= set(flags)


def test_addie_output_phases(result):
    assert set(result["addie_output"]) == ADDIE_PHASES


def test_graph_dump_shape(result):
    """The dump is the auditability contribution and the RQ2 scorer's input."""
    graph = result["graph"]
    assert set(graph) == GRAPH_KEYS
    assert set(graph["nodes"][0]) == NODE_KEYS
    assert set(graph["edges"][0]) == EDGE_KEYS
    from alignmentgraph_isd.core.alignment_graph import alignment
    # MATRIX, not REGISTRY: the registry also holds the two structural
    # relations, which are navigation and carry no coverage figure.
    assert set(graph["relation_coverage"]) == set(alignment.MATRIX)
    assert len(alignment.MATRIX) == 17   # 3 core + 14 secondary

    for flags in graph["objective_alignment"].values():
        # `bloom_ok` stays the conjunction — `to_dot` and every archived run
        # read it — beside the two halves it used to hide and the checks' own
        # wording, which is what lets a reader see WHICH rule failed. It is no
        # longer a leg of `aligned`, which is the structural triad C2/C3/C4.
        assert set(flags) == {"assessed_by", "practiced_by", "prepares_for", "aligned",
                              "bloom_ok", "bloom_assessment_ok", "bloom_activity_ok",
                              "bloom_notes",
                              # The legs as an ORDERED renderable list, which is
                              # what `aligned` is now derived from.
                              "legs"}
        # Named by the relations themselves — `relation_id` and the registry's
        # own `edge_type` verb. They read `measured`/`supported`/`prepares`
        # until 2026-09-14, a third set of names for C2/C3/C4.
        assert [leg["relation_id"] for leg in flags["legs"]] == ["C2", "C3", "C4"]
        assert [leg["verb"] for leg in flags["legs"]] == [
            "assessed_by", "practiced_by", "prepares_for"]
        assert flags["aligned"] == all(leg["ok"] for leg in flags["legs"])

    assert set(graph["metadata"]) >= {
        "design_brief_id", "generated_at", "node_count", "edge_count",
        "node_counts_by_type", "edge_counts_by_type",
    }


def test_dot_renders_from_the_payload(result):
    """The DOT is a view of the dump, not a second artifact beside it."""
    from alignmentgraph_isd.core.alignment_graph import viz

    assert viz.to_dot(result["graph"]).lstrip().startswith("digraph")


def test_prose_arm_omits_graph_keys_but_keeps_the_rest_of_the_contract():
    """The prose arm runs graph-free, so ``graph`` is ABSENT — the benchmark
    writes ``<agent_id>_graph.json`` only when the key exists, so absence
    (never an empty placeholder) is the contract. Everything
    else the benchmark reads keeps its shape; ``metadata.audit`` is empty
    (nothing to audit is the auditability contrast, not a missing field)."""
    from conftest import FakeChatModel

    config = HarnessRunConfig(context_mode="prose")
    config.llm_factory = lambda: FakeChatModel()
    result = run_brief(load_brief("java_oop_brief.json"), config)

    assert (RESULT_KEYS - {"graph"}) <= set(result)
    assert "graph" not in result
    # Its inspectability artifact is the raw blackboard instead (saved as
    # <agent_id>_prose.json): verbatim per-step documents, no relations, no
    # coverage — content dump, not an audit.
    prose = result["prose"]
    assert set(prose) == {"documents", "metadata"}
    assert prose["documents"]["objective"]["learning_objectives"]
    assert prose["metadata"]["document_count"] == len(prose["documents"])
    assert set(result["addie_output"]) == ADDIE_PHASES
    assert set(result["metadata"]) == METADATA_KEYS
    assert set(result["metadata"]["run_config"]) == RUN_CONFIG_KEYS
    assert result["metadata"]["audit"] == {}
    assert set(result["trajectory"]) == TRAJECTORY_LISTS
    assert set(result["metadata"]["token_usage"]) == TOKEN_USAGE_KEYS


def test_scenario_id_still_maps_to_brief_id():
    """The one translation point between the benchmark's vocabulary and this
    package's, mirrored by the demo app's scenario import."""
    brief = DesignBrief(**{**{"scenario_id": "BAL-TEEN3-0013"}, "id": "BAL-TEEN3-0013"})
    assert brief.id == "BAL-TEEN3-0013"
