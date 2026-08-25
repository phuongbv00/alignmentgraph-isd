"""The ``on_event`` observation hook.

Two things are under test: that a consumer sees enough to drive a live UI, and
that adding the hook changed nothing for the callers that do not pass one — the
benchmark being the one that matters.
"""
from __future__ import annotations

import inspect

import pytest

from alignmentgraph_isd import HarnessCancelled, run_design_brief
from alignmentgraph_isd.core.workflow import GENERATION_ORDER
from alignmentgraph_isd.core.trajectory import TrajectoryLogger

from conftest import load_brief


@pytest.fixture
def brief():
    return load_brief("java_oop_brief.json")


def collect(brief, config, **kwargs):
    """Run once, returning (result, events) where events are (kind, payload)."""
    events: list[tuple[str, dict]] = []
    result = run_design_brief(brief, config, on_event=lambda k, p: events.append((k, p)))
    return result, events


def kinds(events) -> list[str]:
    return [kind for kind, _ in events]


# ── the default path is undisturbed ──────────────────────────────────────────

def test_trajectory_logger_still_constructs_bare():
    """The benchmark and several existing tests call ``TrajectoryLogger()`` with
    no arguments. Adding the hook must not have made anything required."""
    signature = inspect.signature(TrajectoryLogger.__init__)
    on_event = signature.parameters["on_event"]
    assert on_event.default is None
    TrajectoryLogger()  # must not raise


def test_default_path_result_is_structurally_unchanged(brief, fake_config):
    """Timestamps and latencies vary run to run, so equality is asserted over
    everything that should NOT vary."""
    without = run_design_brief(brief, fake_config)
    with_hook, _ = collect(brief, fake_config)

    assert with_hook["addie_output"] == without["addie_output"]

    def node_ids(result):
        return sorted(n["id"] for n in result["graph"]["nodes"])

    def edge_keys(result):
        return sorted(
            (e["type"], e["source"], e["target"], e["relation_id"]) for e in result["graph"]["edges"]
        )

    assert node_ids(with_hook) == node_ids(without)
    assert edge_keys(with_hook) == edge_keys(without)
    assert with_hook["graph"]["objective_alignment"] == without["graph"]["objective_alignment"]
    assert with_hook["graph"]["relation_coverage"] == without["graph"]["relation_coverage"]

    assert sorted(with_hook["trajectory"]) == sorted(without["trajectory"])
    for key, value in without["trajectory"].items():
        if isinstance(value, list):
            assert len(with_hook["trajectory"][key]) == len(value), f"stream {key} changed length"


def test_a_raising_consumer_cannot_break_a_run(brief, fake_config):
    """Observation is never load-bearing: a consumer that fails on every event
    must yield the same result as no consumer at all."""
    def boom(kind, payload):
        raise ValueError("consumer is broken")

    result = run_design_brief(brief, fake_config, on_event=boom)
    baseline = run_design_brief(brief, fake_config)
    assert result["addie_output"] == baseline["addie_output"]
    assert len(result["graph"]["nodes"]) == len(baseline["graph"]["nodes"])


# ── the consumer sees enough to drive a UI ───────────────────────────────────

def test_every_recorded_stream_is_mirrored(brief, fake_config):
    _, events = collect(brief, fake_config)
    seen = set(kinds(events))
    for kind in ("agent_step", "node_edit", "llm_call", "validation_event", "check_event"):
        assert kind in seen, f"no {kind} event reached the consumer"


def test_phases_are_bracketed_in_order(brief, fake_config):
    _, events = collect(brief, fake_config)
    started = [p["phase"] for k, p in events if k == "phase_started"]
    finished = [p["phase"] for k, p in events if k == "phase_finished"]

    # Every phase that starts must finish, exactly once -- but NOT necessarily
    # in the same relative order: content_designer/rubric_designer run on
    # separate LangGraph worker threads (a pre-existing parallel fan-out;
    # every dev-plan fan-out family adds the same kind of sibling-thread
    # execution for its own dispatch/develop/finalize nodes), so which one's
    # phase_finished lands first is a genuine scheduling race, not a bug.
    assert sorted(started) == sorted(finished), "every phase that starts must finish, exactly once"

    # Six specialists in ADDIE order; content_designer/rubric_designer are the
    # one genuinely-parallel pair and may start in either relative order, but
    # both must sit strictly between activity_designer and
    # implementation_planner.
    order = [p for p in started if p in GENERATION_ORDER]
    assert set(order) == set(GENERATION_ORDER)
    index = {phase: i for i, phase in enumerate(order)}
    assert index["outcome_designer"] < index["assessment_designer"] < index["activity_designer"]
    assert index["activity_designer"] < index["content_designer"] < index["implementation_planner"]
    assert index["activity_designer"] < index["rubric_designer"] < index["implementation_planner"]
    assert started[-1] == "aggregate"

    totals = {p["total"] for _, p in events if p.get("total")}
    assert len(totals) == 1, "phase_total must be stable across a run"
    assert len(started) == totals.pop()


def test_llm_calls_are_announced_before_they_run(brief, fake_config):
    """The point of ``llm_started``: without it a viewer sees nothing for the
    tens of seconds a real call takes."""
    _, events = collect(brief, fake_config)
    depth = 0
    starts = 0
    for kind in kinds(events):
        if kind == "llm_started":
            depth += 1
            starts += 1
        elif kind == "llm_finished":
            depth -= 1
            assert depth >= 0, "llm_finished arrived without a matching llm_started"
    assert starts > 0
    assert depth == 0, "an llm_started was never followed by llm_finished"


def test_llm_events_describe_the_call_without_carrying_its_content(brief, fake_config):
    """These are progress signals, not a second copy of the trace. What the UI
    shows for a step comes from the recorded trajectory, so that what is on
    screen is exactly what the run produced."""
    _, events = collect(brief, fake_config)

    started = [p for k, p in events if k == "llm_started"]
    finished = [p for k, p in events if k == "llm_finished"]
    assert started and finished

    assert set(started[0]) == {"agent", "prompt_chars", "message_count", "retries_left"}
    assert set(finished[0]) == {
        "agent", "duration_ms", "response_chars", "prompt_tokens", "completion_tokens",
    }


def test_final_graph_snapshot_matches_the_returned_graph(brief, fake_config):
    """A consumer that only ever listens to events must end up with exactly the
    graph the caller gets back."""
    result, events = collect(brief, fake_config)
    snapshots = [p for k, p in events if k == "graph_snapshot"]
    assert snapshots, "no graph_snapshot reached the consumer"

    final = snapshots[-1]
    assert sorted(n["id"] for n in final["nodes"]) == sorted(n["id"] for n in result["graph"]["nodes"])
    assert len(final["edges"]) == len(result["graph"]["edges"])
    assert final["objective_alignment"] == result["graph"]["objective_alignment"]


def test_graph_snapshots_grow_monotonically(brief, fake_config):
    _, events = collect(brief, fake_config)
    counts = [len(p["nodes"]) for k, p in events if k == "graph_snapshot"]
    assert counts == sorted(counts), "the live graph shrank between snapshots"
    assert counts[-1] > counts[0], "the graph never grew — snapshots are not live"


# ── cancellation ─────────────────────────────────────────────────────────────

def test_cancellation_propagates_out_of_the_run(brief, fake_config):
    """``HarnessCancelled`` derives from BaseException precisely so it survives
    the broad ``except Exception`` handlers in the node and agent layers."""
    seen: list[str] = []

    def cancel_on_third(kind, payload):
        seen.append(kind)
        if len(seen) >= 3:
            raise HarnessCancelled()

    with pytest.raises(HarnessCancelled):
        run_design_brief(brief, fake_config, on_event=cancel_on_third)
