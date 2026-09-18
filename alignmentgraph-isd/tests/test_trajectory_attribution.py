"""Every deep-log action must be attributed to a real agent — never "".

Regression guard for a 2026-08-27 bug: several harness-level log calls ran
after the specialist's own ``acting_as`` block had already exited (phase
boundaries, the final ADDIE-output validation, the residual audit), so they
fell back to whichever actor happened to be set last — empty on the very
first phase of a run, stale afterwards. Fixed by either widening the
``acting_as`` scope to cover the whole operation, or naming the harness
itself as the actor (``ORCHESTRATOR``).
"""
from __future__ import annotations

import pytest

from alignmentgraph_isd import HarnessRunConfig
from alignmentgraph_isd.core.aggregate import ADDIEOutputAggregator
from alignmentgraph_isd.core.trajectory import ORCHESTRATOR

from conftest import FakeChatModel, load_brief, run_brief


@pytest.mark.parametrize("agent_mode,context_mode", [
    ("multi", "graph"), ("multi", "prose"), ("single", "graph"), ("single", "prose"),
])
def test_no_action_is_ever_attributed_to_nobody(agent_mode, context_mode):
    config = HarnessRunConfig(agent_mode=agent_mode, context_mode=context_mode)
    config.llm_factory = lambda: FakeChatModel()
    result = run_brief(load_brief("java_oop_brief.json"), config)

    actions = result["trajectory_deep"]["actions"]
    assert actions
    empty = [a for a in actions if not a.get("agent")]
    assert not empty, f"actions with no agent credited: {empty[:3]}"


@pytest.mark.parametrize("fanout_workers", [1, 3])
def test_no_action_is_ever_attributed_to_nobody_with_a_live_on_event_consumer(fanout_workers):
    """Regression: a real ``on_event`` consumer (the server, the demo app) makes
    ``MetaAgent.run`` wraps it with ``_graph_attaching``, which serializes a
    ``graph_snapshot`` synchronously inside ``trajectory.emit(...)`` — including
    on the very first ``phase_started``, fired before ``acting_as`` has even
    been entered. `run_brief(..., on_event=None)` (the default, used by
    every other test in this file) never exercises that path, so the bug this
    guards survived until the app-facing tests were run for real.

    Run with the sequential fan-out and with a parallel one: under
    ``fanout_workers > 1`` the Developers log from worker threads, each under
    its own attribution scope (``trajectory._scope``), and an action credited
    to nobody is the shared-actor race this guards against.
    """
    config = HarnessRunConfig(fanout_workers=fanout_workers)
    config.llm_factory = lambda: FakeChatModel()
    result = run_brief(load_brief("java_oop_brief.json"), config, on_event=lambda k, p: None)

    actions = result["trajectory_deep"]["actions"]
    assert actions
    empty = [a for a in actions if not a.get("agent")]
    assert not empty, f"actions with no agent credited: {empty[:3]}"


def test_phase_boundaries_are_attributed_to_the_orchestrator_not_a_specialist():
    """A phase_started fires before its specialist sets an identity, and
    phase_finished fires after the stage's trailing self-validation
    loop has already exited it — neither is any one specialist's own action."""
    config = HarnessRunConfig()
    config.llm_factory = lambda: FakeChatModel()
    result = run_brief(load_brief("java_oop_brief.json"), config)

    phase_actions = [a for a in result["trajectory_deep"]["actions"]
                     if a["action"] in ("phase_started", "phase_finished")]
    assert phase_actions
    assert all(a["agent"] == ORCHESTRATOR for a in phase_actions)


def test_work_done_outside_a_tool_loop_is_the_orchestrator_s():
    """Attribution answers WHO ACTED (2026-09-02).

    The check rounds and the deterministic repair net run AFTER a tool loop has
    returned. No agent chose them, saw them, or could have done otherwise, so
    crediting the specialist inflates what the trace says it did. Which
    family's output was inspected is not lost — it is a field on the record,
    and `repairs.OWNER_BY_VIOLATION` maps every type to its owner."""
    config = HarnessRunConfig()
    config.llm_factory = lambda: FakeChatModel()
    result = run_brief(load_brief("java_oop_brief.json"), config)

    outside = [a for a in result["trajectory_deep"]["actions"]
               if a["action"] in ("check", "repair", "reconcile", "audit")]
    assert outside
    assert all(a["agent"] == ORCHESTRATOR for a in outside), sorted(
        {(a["action"], a["agent"]) for a in outside if a["agent"] != ORCHESTRATOR})

    # An agent's own acts stay the agent's: a submit and a read are things it
    # chose inside its loop.
    inside = [a for a in result["trajectory_deep"]["actions"] if a["action"] == "agent_step"]
    assert inside and all(a["agent"] != ORCHESTRATOR for a in inside)


def test_final_addie_output_validation_is_attributed_to_the_aggregator():
    """validate_addie() runs after the aggregator's own acting_as block
    exits — it must still be credited to ADDIEOutputAggregator, not fall
    through to whichever specialist ran last."""
    config = HarnessRunConfig()
    config.llm_factory = lambda: FakeChatModel()
    result = run_brief(load_brief("java_oop_brief.json"), config)

    final_validations = [
        a for a in result["trajectory_deep"]["actions"]
        if a["action"] == "validate" and a["context"].get("scope") == "addie_output"
    ]
    assert final_validations
    assert all(a["agent"] == ADDIEOutputAggregator.__name__ for a in final_validations)




def test_a_worker_thread_has_its_own_scope_and_inherits_the_phase():
    """A fan-out worker enters ``acting_as`` on its own thread: it starts from
    the root scope's phase, sets its own actor, and leaves the root untouched
    — so the orchestrator's next event on the main thread is still its own."""
    import threading

    from alignmentgraph_isd.core.trajectory import TrajectoryLogger

    trajectory = TrajectoryLogger()
    seen: dict = {}
    with trajectory.acting_as("Orchestrator", phase="content"):
        def worker():
            seen["inherited"] = (trajectory._actor, trajectory._phase)
            with trajectory.acting_as("MaterialDeveloperAgent"):
                trajectory.log_action("node_read", node_id="n")
                seen["inside"] = (trajectory._actor, trajectory._phase)
            seen["after"] = trajectory._actor
        t = threading.Thread(target=worker)
        t.start(); t.join()
        assert trajectory._actor == "Orchestrator"

    assert seen["inherited"] == ("Orchestrator", "content")
    assert seen["inside"] == ("MaterialDeveloperAgent", "content")
    assert seen["after"] == "Orchestrator"
    event = trajectory.actions[-1]
    assert event["agent"] == "MaterialDeveloperAgent" and event["context"]["phase"] == "content"


def test_steps_logged_from_many_threads_are_numbered_densely():
    import threading

    from alignmentgraph_isd.core.trajectory import TrajectoryLogger

    trajectory = TrajectoryLogger()
    threads = [threading.Thread(target=lambda i=i: [
        trajectory.log_step(f"A{i}", "act", "in", "out") for _ in range(50)])
        for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    indices = [c["step"] for c in trajectory.tool_calls]
    assert sorted(indices) == list(range(1, 401))
    assert [r["iteration"] for r in trajectory.agent_interactions] == indices


def test_the_harness_asking_what_has_landed_is_the_orchestrators_read_not_the_agents():
    """MEASURED (run 4bb81369): the Trajectory tab showed "Read graph 90x"
    under the NeedsAnalyst — an agent bound NO read tool. The reads were the
    harness's own (which of the stage's artifacts have landed, asked several
    times a turn; a commit's lookup of the section it merges into), made
    inside the agent's scope and stamped with its name by the graph observer.
    They happened, so they stay on the record — under the ORCHESTRATOR, whose
    they are. What an agent read is a claim the trace has to support."""
    config = HarnessRunConfig()
    config.llm_factory = lambda: FakeChatModel()
    result = run_brief(load_brief("minimal_brief.json"), config)

    actions = result["trajectory_deep"]["actions"]
    reads = [a for a in actions if a["action"] in ("node_read", "edge_read")]
    assert not [a for a in reads if a["agent"] == "NeedsAnalystAgent"], (
        "an agent with no read tool was recorded reading the graph")
    in_analysis = [a for a in reads if a["context"]["phase"] == "analysis"]
    assert in_analysis and {a["agent"] for a in in_analysis} == {ORCHESTRATOR}, (
        "the probes are RECORDED, under the actor that made them")
    # The WRITE a commit makes is the agent's act and keeps the agent's name...
    assert any(a["action"] == "node_write" and a["agent"] == "NeedsAnalystAgent"
               for a in actions)
    # ...and an agent that does read is still recorded reading.
    assert any(a["agent"] == "AssessmentDesignerAgent" for a in reads)


def test_read_attribution_reaches_only_its_own_thread_and_only_reads():
    import threading

    from alignmentgraph_isd.core.alignment_graph import AlignmentGraph, NodeType

    seen: list[tuple] = []
    graph = AlignmentGraph(observer=lambda kind, fields: seen.append((kind, fields.get("agent"))))
    graph.add_element_node(NodeType.GAP, "GAP-01", {"id": "GAP-01"})
    seen.clear()

    with graph.reads_as("Orchestrator"):
        graph.element_nodes(NodeType.GAP)
        graph.add_element_node(NodeType.GAP, "GAP-02", {"id": "GAP-02"})
        other = threading.Thread(target=lambda: graph.element_nodes(NodeType.GAP))
        other.start(); other.join()
    graph.element_nodes(NodeType.GAP)

    reads = [agent for kind, agent in seen if kind.endswith("_read")]
    writes = [agent for kind, agent in seen if kind.endswith("_write")]
    assert reads[0] == "Orchestrator", "this thread's read is booked to the named actor"
    assert reads.count("Orchestrator") == 1, "not the other thread's, nor the one after the block"
    assert writes and set(writes) == {None}, "a write keeps whoever is acting"
