"""A run whose outcomes stage leaves no course modules STOPS.

The modules are the key all four fan-out families divide their work by. The
harness does not stand one in — deciding how a course divides is the Outcome
Designer's — so no later stage runs, what exists is aggregated, and the run
says why it ended. Returned rather than raised: a benchmark then scores the
shortfall against the agent instead of losing the scenario.
"""
from __future__ import annotations

import pytest

from alignmentgraph_isd import HarnessRunConfig
from alignmentgraph_isd.core.runner import NO_MODULES

from conftest import FakeChatModel, load_brief, run_brief


class _NeverWritesModules(FakeChatModel):
    """Answers every call as the fixture does, except that the course modules
    always arrive empty — as a small model that cannot produce the artifact."""

    def invoke(self, messages):
        result = super().invoke(messages)
        for call in result.tool_calls:
            if "course_modules" in (call.get("args") or {}):
                # A COPY: the canned payload is shared by every test in the suite.
                call["args"] = {**call["args"], "course_modules": []}
        return result


def _run(agent_mode: str, context_mode: str) -> dict:
    config = HarnessRunConfig(agent_mode=agent_mode, context_mode=context_mode, regen_budget=0)
    config.llm_factory = _NeverWritesModules
    return run_brief(load_brief("minimal_brief.json"), config)


@pytest.mark.parametrize("context_mode", ["graph", "prose"])
def test_the_multi_arm_runs_no_stage_after_outcomes(context_mode):
    result = _run("multi", context_mode)

    assert NO_MODULES in result["metadata"]["errors"]
    assert list(result["metadata"]["autonomy"]) == ["analysis", "outcomes"]
    assert result["metadata"]["autonomy"]["outcomes"]["run_stopped"] is True
    stopped = [e for e in result["trajectory"]["events"] if e["action"] == "run_stopped"]
    assert len(stopped) == 1 and stopped[0]["agent"] == "Orchestrator"
    phases = {e["context"].get("phase") for e in result["trajectory"]["events"]}
    assert not phases & {"assessment", "activities", "content", "implementation"}

    # What the agents DID write still ships, and nothing was written for them.
    design = result["addie_output"]["design"]
    assert design["learning_objectives"], "the objectives landed and are reported"
    assert design.get("content_structure", {}).get("modules", []) == []
    assert result["addie_output"]["development"]["assessment_tools"] == []
    assert not [e for e in result["trajectory"]["events"] if e["action"] == "route"], (
        "there is no design to reconcile")


def test_the_single_arm_cannot_start_a_family_that_has_no_module_to_divide_by():
    result = _run("single", "graph")

    assert NO_MODULES in result["metadata"]["errors"]
    assert result["metadata"]["autonomy"]["design"]["run_stopped"] is True
    assert result["addie_output"]["development"]["assessment_tools"] == []
    graph_types = {node["type"] for node in result["graph"]["nodes"]}
    assert not graph_types & {"assessment", "activity", "material", "session_guide"}


def test_a_run_with_modules_is_not_stopped():
    config = HarnessRunConfig()
    config.llm_factory = FakeChatModel
    result = run_brief(load_brief("minimal_brief.json"), config)
    assert NO_MODULES not in result["metadata"]["errors"]
    assert "run_stopped" not in result["metadata"]["autonomy"]["outcomes"]
    assert [m["id"] for m in result["addie_output"]["design"]["content_structure"]["modules"]] == [
        "MOD-01", "MOD-02"]
