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
        # Corrupt both the multi-agent payload (top-level keys) and the
        # single-agent payload (sections nested under design/development).
        design = data.get("design") if isinstance(data.get("design"), dict) else {}
        development = data.get("development") if isinstance(data.get("development"), dict) else {}
        if self.mode == "bloom":
            for container in (data, design):
                for lo in container.get("learning_objectives", []) or []:
                    lo["bloom_verb"] = ""  # -> "missing bloom_verb" violation (objective owner)
        elif self.mode == "rubric":
            for container in (data, development):
                tools = container.get("assessment_tools") or []
                if tools:
                    item = tools[0]
                    item["type"] = "performance_task"
                    item["scoring_criteria"] = "good"  # vague, no observable anchor
                    item.pop("aligned_objective", None)  # -> rubric_consistency (assessment owner)
        result.content = json.dumps(data, ensure_ascii=False)
        return result


def _run(factory, duration: str = "2 days", ablation: str = "full") -> dict:
    config = HarnessRunConfig.from_ablation(ablation, memory={"enabled": False})
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
def test_violation_triggers_repair(factory, duration, owner_agent):
    # In the default fixed-order architecture each specialist self-repairs within
    # its own turn (before downstream artifacts exist), so repair fires but there
    # is nothing downstream to cascade to — cascade is a dynamic-branch feature
    # exercised in test_cascade_fires_in_dynamic_branch.
    result = _run(factory, duration=duration)
    trajectory, metadata = result["trajectory"], result["metadata"]

    assert trajectory["repair_events"], "expected at least one repair event"
    assert metadata["repair_metrics"]["repair_events"] > 0

    repair_agents = {event.get("agent") for event in trajectory["repair_events"]}
    assert owner_agent in repair_agents, f"expected {owner_agent} in {repair_agents}"


def test_cascade_fires_in_dynamic_branch():
    """Cascade (staleness propagation to dependents) is a dynamic-branch feature:
    a late repair invalidates earlier-built dependent nodes."""
    result = _run(lambda: BrokenChatModel("rubric"), ablation="dynamic_full")
    trajectory = result["trajectory"]
    assert trajectory["repair_events"], "expected repair in the dynamic branch"
    assert trajectory["cascade_events"], "expected cascade in the dynamic branch"


# ── Per-agent self-check quality control (the default fixed-order architecture) ─
# Verification + repair are tools each specialist owns and runs within its own
# turn (no separate global verify phase). The single agent self-repairs. Removing
# the QC tools (use_verifier off) leaves generation untouched.

def _run_flags(factory, *, multi_agent, dynamic_graph, use_verifier=True, use_repair=True):
    from alignmentgraph_isd.config import AblationConfig

    config = HarnessRunConfig.from_ablation("full", memory={"enabled": False})
    config.ablation = AblationConfig(
        use_rag=False, use_verifier=use_verifier, use_repair=use_repair,
        multi_agent=multi_agent, dynamic_graph=dynamic_graph,
    )
    config.llm_factory = factory
    brief = DesignBrief(
        id="qc-mode", title="OOP crash course", domain="Software Engineering",
        duration="2 days", context={"duration": "2 days"},
        learning_goals=["Explain encapsulation", "Apply inheritance"],
    )
    return run_design_brief(brief, config)


def test_specialists_self_repair_in_fixed_order():
    """Fixed-order multi-agent: each specialist self-checks and repairs its own
    artifact within its turn (no single-agent repair, no global planner loop)."""
    result = _run_flags(lambda: BrokenChatModel("bloom"), multi_agent=True, dynamic_graph=False)
    trajectory = result["trajectory"]
    assert trajectory["repair_events"], "specialist self-repair should fire"
    repair_agents = {e.get("agent") for e in trajectory["repair_events"]}
    assert "ObjectiveDesignAgent" in repair_agents
    assert "SingleAgent" not in repair_agents
    assert not trajectory["planner_decisions"], "fixed order must not use the dynamic planner"


def test_single_agent_self_repairs_without_specialists():
    """wo-ma: the single agent repairs itself — no specialist repair leaks in."""
    result = _run_flags(lambda: BrokenChatModel("bloom"), multi_agent=False, dynamic_graph=False)
    trajectory = result["trajectory"]
    assert trajectory["repair_events"], "single-agent self-repair should fire"
    assert {e.get("agent") for e in trajectory["repair_events"]} == {"SingleAgent"}


def test_qc_off_disables_verify_and_repair():
    """wo-qc: turning off the QC tools leaves generation intact but no verify/repair."""
    result = _run_flags(lambda: BrokenChatModel("bloom"), multi_agent=True, dynamic_graph=False,
                        use_verifier=False, use_repair=False)
    trajectory = result["trajectory"]
    assert trajectory["verifier_events"] == []
    assert trajectory["repair_events"] == []
    assert len(trajectory["node_edits"]) > 6, "generation (decomposition) must still run"


def test_dynamic_branch_still_uses_global_loop():
    """The dynamic branch (kept for refinement) drives a global verify-repair loop."""
    result = _run(lambda: BrokenChatModel("bloom"), ablation="dynamic_full")
    trajectory = result["trajectory"]
    assert trajectory["planner_decisions"], "dynamic planner should run"
    assert trajectory["repair_events"], "dynamic global loop should repair"
