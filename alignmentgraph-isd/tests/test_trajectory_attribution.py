"""Every deep-log action must be attributed to a real agent — never "".

Regression guard for a 2026-08-27 bug: several harness-level log calls ran
after the specialist's own ``acting_as`` block had already exited (phase
boundaries, the final ADDIE-output validation, the residual audit), so they
fell back to whichever actor happened to be set last — empty on the very
first phase of a run, stale afterwards. Fixed by either widening the
``acting_as`` scope to cover the whole operation, or naming the harness
itself as the actor (``WORKFLOW_ORCHESTRATOR``).
"""
from __future__ import annotations

import pytest

from alignmentgraph_isd import HarnessRunConfig, run_design_brief
from alignmentgraph_isd.core.agents.addie_aggregator import ADDIEOutputAggregator
from alignmentgraph_isd.core.trajectory import WORKFLOW_ORCHESTRATOR

from conftest import FakeChatModel, load_brief


@pytest.mark.parametrize("agent_mode,context_mode", [
    ("multi", "graph"), ("multi", "prose"), ("single", "graph"), ("single", "prose"),
])
def test_no_action_is_ever_attributed_to_nobody(agent_mode, context_mode):
    config = HarnessRunConfig(agent_mode=agent_mode, context_mode=context_mode)
    config.llm_factory = lambda: FakeChatModel()
    result = run_design_brief(load_brief("java_oop_brief.json"), config)

    actions = result["trajectory_deep"]["actions"]
    assert actions
    empty = [a for a in actions if not a.get("agent")]
    assert not empty, f"actions with no agent credited: {empty[:3]}"


@pytest.mark.parametrize("attempt", range(20))
def test_no_action_is_ever_attributed_to_nobody_with_a_live_on_event_consumer(attempt):
    """Regression: a real ``on_event`` consumer (the server, the demo app) makes
    ``run_workflow`` wrap it with ``_graph_attaching``, which serializes a
    ``graph_snapshot`` synchronously inside ``trajectory.emit(...)`` — including
    on the very first ``phase_started``, fired before ``acting_as`` has even
    been entered. `run_design_brief(..., on_event=None)` (the default, used by
    every other test in this file) never exercises that path, so the bug this
    guards survived until the app-facing tests were run for real.

    Repeated 20x (parametrized, not looped, so a failure is bisectable) because
    the graph is genuinely multi-threaded: content_designer/rubric_designer run
    concurrently on separate LangGraph worker threads, and a shared (not
    thread-local) actor/phase was the other half of this bug — a race that a
    single run does not reliably hit.
    """
    config = HarnessRunConfig()
    config.llm_factory = lambda: FakeChatModel()
    result = run_design_brief(load_brief("java_oop_brief.json"), config, on_event=lambda k, p: None)

    actions = result["trajectory_deep"]["actions"]
    assert actions
    empty = [a for a in actions if not a.get("agent")]
    assert not empty, f"actions with no agent credited: {empty[:3]}"


def test_phase_boundaries_are_attributed_to_the_orchestrator_not_a_specialist():
    """A phase_started fires before its specialist sets an identity, and
    phase_finished fires after run_generation_step's trailing self-validation
    loop has already exited it — neither is any one specialist's own action."""
    config = HarnessRunConfig()
    config.llm_factory = lambda: FakeChatModel()
    result = run_design_brief(load_brief("java_oop_brief.json"), config)

    phase_actions = [a for a in result["trajectory_deep"]["actions"]
                     if a["action"] in ("phase_started", "phase_finished")]
    assert phase_actions
    assert all(a["agent"] == WORKFLOW_ORCHESTRATOR for a in phase_actions)


def test_self_validation_is_attributed_to_the_specialist_being_validated():
    """The self-validation loop in run_generation_step runs after agent.run()
    returns; it must still credit the specialist whose output it is checking,
    not whoever ran previously."""
    config = HarnessRunConfig()
    config.llm_factory = lambda: FakeChatModel()
    result = run_design_brief(load_brief("java_oop_brief.json"), config)

    check_actions = [a for a in result["trajectory_deep"]["actions"] if a["action"] == "check"]
    assert check_actions
    assert all(a["agent"] and a["agent"] != WORKFLOW_ORCHESTRATOR for a in check_actions)


def test_final_addie_output_validation_is_attributed_to_the_aggregator():
    """validate_addie() runs after the aggregator's own acting_as block
    exits — it must still be credited to ADDIEOutputAggregator, not fall
    through to whichever specialist ran last."""
    config = HarnessRunConfig()
    config.llm_factory = lambda: FakeChatModel()
    result = run_design_brief(load_brief("java_oop_brief.json"), config)

    final_validations = [
        a for a in result["trajectory_deep"]["actions"]
        if a["action"] == "validate" and a["context"].get("scope") == "addie_output"
    ]
    assert final_validations
    assert all(a["agent"] == ADDIEOutputAggregator.__name__ for a in final_validations)


