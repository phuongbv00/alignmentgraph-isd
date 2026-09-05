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

from alignmentgraph_isd import HarnessRunConfig
from alignmentgraph_isd.core.aggregate import ADDIEOutputAggregator
from alignmentgraph_isd.core.trajectory import WORKFLOW_ORCHESTRATOR

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


def test_no_action_is_ever_attributed_to_nobody_with_a_live_on_event_consumer():
    """Regression: a real ``on_event`` consumer (the server, the demo app) makes
    ``run_agentic_brief`` wrap it with ``_graph_attaching``, which serializes a
    ``graph_snapshot`` synchronously inside ``trajectory.emit(...)`` — including
    on the very first ``phase_started``, fired before ``acting_as`` has even
    been entered. `run_brief(..., on_event=None)` (the default, used by
    every other test in this file) never exercises that path, so the bug this
    guards survived until the app-facing tests were run for real.

    Was repeated 20x while the LangGraph pipeline ran content_designer and
    rubric_designer concurrently on worker threads, so the shared-actor half of
    this bug needed several attempts to surface. The executor is sequential now
    and ``trajectory.py`` keeps plain instance state, so every one of those runs
    was deterministically identical to the first: 19 copies of one assertion,
    at ~1s of pipeline each. Restore the parametrize if a concurrent fan-out
    comes back.
    """
    config = HarnessRunConfig()
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
    assert all(a["agent"] == WORKFLOW_ORCHESTRATOR for a in phase_actions)


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
    assert all(a["agent"] == WORKFLOW_ORCHESTRATOR for a in outside), sorted(
        {(a["action"], a["agent"]) for a in outside if a["agent"] != WORKFLOW_ORCHESTRATOR})

    # An agent's own acts stay the agent's: a submit and a read are things it
    # chose inside its loop.
    inside = [a for a in result["trajectory_deep"]["actions"] if a["action"] == "agent_step"]
    assert inside and all(a["agent"] != WORKFLOW_ORCHESTRATOR for a in inside)


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


