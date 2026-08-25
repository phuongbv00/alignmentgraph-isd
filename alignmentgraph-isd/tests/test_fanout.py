"""End-to-end coverage of the dev-plan fan-out (2026-08-28) that the more
targeted test files don't already exercise: the ``dev_plan`` trajectory
event's shape/content in both arms, worker attribution to the Developer's OWN
identity (not the Designer's), and id-collision remap surviving a real run.
Per-family mechanics (normalize/remap/regen) are unit-tested directly in
test_dev_plans.py; topology in test_ablation_flags.py; per-set regen budget
in test_empty_section_regen.py; phase bracketing in test_on_event.py."""
from __future__ import annotations

from alignmentgraph_isd import HarnessRunConfig, run_design_brief
from alignmentgraph_isd.core.trajectory import WORKFLOW_ORCHESTRATOR

from conftest import FakeChatModel, load_brief


def _run(mode: str = "multi", context_mode: str = "graph"):
    brief = load_brief("minimal_brief.json")
    config = HarnessRunConfig(llm_factory=lambda: FakeChatModel(), agent_mode=mode, context_mode=context_mode)
    return run_design_brief(brief, config)


def test_dev_plan_events_fire_once_per_fanout_family_multi_arm():
    result = _run("multi")
    dev_plan_events = [e for e in result["trajectory"]["events"] if e["action"] == "dev_plan"]
    families = {e["context"]["family"] for e in dev_plan_events}
    assert families == {"assessment_designer", "activity_designer", "content_designer", "rubric_designer"}
    assert len(dev_plan_events) == 4, "each fan-out family logs its dev plan exactly once"

    by_family = {e["context"]["family"]: e for e in dev_plan_events}
    # assessment/activity plan an LLM-proposed grouping; content/rubric are
    # deterministic (no LLM decision to make).
    assert by_family["assessment_designer"]["context"]["source"] in ("llm", "fallback")
    assert by_family["activity_designer"]["context"]["source"] in ("llm", "fallback")
    assert by_family["content_designer"]["context"]["source"] == "deterministic"
    assert by_family["rubric_designer"]["context"]["source"] == "deterministic"

    for event in dev_plan_events:
        ctx = event["context"]
        assert ctx["set_count"] >= 1
        assert isinstance(ctx["sets"], list) and ctx["sets"]
        assert all("set_id" in s for s in ctx["sets"])
        # Orchestration metadata, attributed to the family that decided it —
        # never the pipeline-boundary identity.
        assert event["agent"] != WORKFLOW_ORCHESTRATOR
        assert event["agent"].endswith("DesignerAgent")


def test_dev_plan_events_fire_in_prose_arm_too():
    result = _run("multi", context_mode="prose")
    dev_plan_events = [e for e in result["trajectory"]["events"] if e["action"] == "dev_plan"]
    families = {e["context"]["family"] for e in dev_plan_events}
    assert families == {"assessment_designer", "activity_designer", "content_designer", "rubric_designer"}


def test_dev_plan_event_fires_once_per_fanout_state_single_arm():
    result = _run("single")
    dev_plan_events = [e for e in result["trajectory"]["events"] if e["action"] == "dev_plan"]
    families = {e["context"]["family"] for e in dev_plan_events}
    assert families == {"assessment_designer", "activity_designer", "content_designer", "rubric_designer"}
    for event in dev_plan_events:
        assert event["agent"] == "SingleDesignerAgent"


def test_workers_are_attributed_to_the_developer_not_the_designer():
    """Worker llm_call rows must name the Developer class — the Designer
    commits the pooled result at finalize, but never calls the model for an
    individual set itself."""
    result = _run("multi")
    llm_actions = [a for a in result["trajectory_deep"]["actions"] if a["action"] == "llm_call"]
    agents = {a["agent"] for a in llm_actions}
    assert "AssessmentDeveloperAgent" in agents
    assert "ActivityDeveloperAgent" in agents
    assert "MaterialDeveloperAgent" in agents
    assert "RubricDeveloperAgent" in agents
    # Every logged action carries a real agent — no fan-out worker fell
    # through to an empty/misattributed actor (the concurrency race this
    # architecture had to be made safe against — see AlignmentGraph's lock).
    assert all(a.get("agent") for a in result["trajectory_deep"]["actions"])


def test_id_collision_across_sets_is_remapped_not_overwritten_end_to_end():
    """Every canned Developer response in conftest.py reuses the SAME id
    space (AT-01.., TLA-01.., MAT-01.., RC-01..) across every work set that
    matches it, since the fake model can't vary by set the way a real one
    would -- so a real run already exercises the remap path on every family
    without any special-casing here."""
    result = _run("multi")
    graph = result["graph"]
    for node_type in ("assessment", "activity", "material", "rubric"):
        ids = [n["id"] for n in graph["nodes"] if n["type"] == node_type]
        assert len(ids) == len(set(ids)), f"{node_type} ids collided: {ids}"
        elements = [n for n in graph["nodes"] if n["type"] == node_type and ":" in n["id"]]
        # Every committed element carries the set that produced it.
        assert all(n["data"].get("plan_set") for n in elements), \
            f"{node_type} element missing plan_set stamp"
