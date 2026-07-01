"""Deterministic coverage for the verifier -> specialist-repair -> cascade path.

A clean generation produces no violations (see ``test_clean_run_has_no_repair``),
so the repair/cascade trajectory events stay at zero — exactly what a benchmark
run shows. These tests force an *owned* verifier violation (via a tight schedule
or a corrupted agent payload) and assert the full pipeline routes it to the right
specialist ``repair()`` and records ``repair_events``/``cascade_events``.

Note: ``coverage``, ``activity_support`` and ``evaluation_alignment`` are healed at
generation time (agents add the missing items/edges), so they are not reachable
via payload corruption alone; the three owners exercised below are the ones a
malformed input can actually surface.
"""
from __future__ import annotations

import json

import pytest
from conftest import FakeChatModel

from alignmentgraph_isd import DesignBrief, HarnessRunConfig, run_design_brief


class BrokenChatModel(FakeChatModel):
    """Fake model that corrupts one agent's output to force a verifier violation."""

    def __init__(self, mode: str) -> None:
        self.mode = mode

    def invoke(self, messages):
        result = super().invoke(messages)
        data = json.loads(result.content)
        if self.mode == "bloom" and "learning_objectives" in data:
            for lo in data["learning_objectives"]:
                lo["bloom_verb"] = ""  # -> "missing bloom_verb" violation (objective owner)
        elif self.mode == "rubric" and data.get("assessment_tools"):
            item = data["assessment_tools"][0]
            item["type"] = "performance_task"
            item["scoring_criteria"] = "good"  # vague, no observable anchor
            item.pop("aligned_objective", None)  # -> rubric_consistency violation (assessment owner)
        result.content = json.dumps(data, ensure_ascii=False)
        return result


def _run(factory, duration: str = "2 days") -> dict:
    config = HarnessRunConfig.from_ablation("full", memory={"enabled": False})
    config.llm_factory = factory
    brief = DesignBrief(
        id="repair-repro",
        title="OOP crash course",
        domain="Software Engineering",
        duration=duration,
        context={"duration": duration},
        learning_goals=["Explain encapsulation", "Apply inheritance"],
    )
    return run_design_brief(brief, config)


def test_clean_run_has_no_repair_or_cascade():
    result = _run(lambda: FakeChatModel(), duration="2 days")
    trajectory = result["trajectory"]
    assert trajectory["repair_events"] == []
    assert trajectory["cascade_events"] == []
    assert result["metadata"]["repair_metrics"]["repair_events"] == 0


@pytest.mark.parametrize(
    "factory, duration, owner_agent",
    [
        (lambda: FakeChatModel(), "2 hours", "ImplementationPlanAgent"),
        (lambda: BrokenChatModel("bloom"), "2 days", "ObjectiveDesignAgent"),
        (lambda: BrokenChatModel("rubric"), "2 days", "AssessmentDesignAgent"),
    ],
    ids=["feasibility->implementation", "bloom->objective", "rubric->assessment"],
)
def test_violation_triggers_repair_and_cascade(factory, duration, owner_agent):
    result = _run(factory, duration=duration)
    trajectory, metadata = result["trajectory"], result["metadata"]

    assert trajectory["repair_events"], "expected at least one repair event"
    assert trajectory["cascade_events"], "expected at least one cascade event"
    assert metadata["repair_metrics"]["repair_events"] > 0
    assert metadata["repair_metrics"]["cascade_count"] > 0

    repair_agents = {event.get("agent") for event in trajectory["repair_events"]}
    assert owner_agent in repair_agents, f"expected {owner_agent} in {repair_agents}"
