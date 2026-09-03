"""End-to-end coverage of the Developer tier that the more targeted test files
don't already exercise: the ``dev_plan`` trajectory
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
    # The agentic executor is the only one since 2026-09-01; the fan-out moved
    # with it (core/agentic/fanout.py) and keeps the same shared normalization
    # what it was written for.
    config = HarnessRunConfig(llm_factory=lambda: FakeChatModel(), agent_mode=mode,
                              context_mode=context_mode, )
    return run_design_brief(brief, config)


def test_dev_plan_events_fire_once_per_fanout_family_multi_arm():
    """One per family, plus one per REPLAN round. A family whose Developers
    leave a gap is planned again by its Designer (core/agentic/replan.py), and
    that second division of the work is a second dev plan — the event has to
    say so or the trace under-reports what the Developers were asked for."""
    result = _run("multi")
    dev_plan_events = [e for e in result["trajectory"]["events"] if e["action"] == "dev_plan"]
    families = {e["context"]["family"] for e in dev_plan_events}
    assert families == {"assessment_designer", "activity_designer", "content_designer"}

    rounds = [p for p in result["plans"] if p["stage"] == "assessment"]
    assert len(dev_plan_events) == 3 + (len(rounds) - 1), (
        "one dev_plan event per family per planning round")

    by_family = {e["context"]["family"]: e for e in dev_plan_events}
    # assessment/activity ask the model for a grouping; content derives one unit
    # per committed module and needs no decision.
    assert by_family["assessment_designer"]["context"]["source"] in ("llm", "fallback")
    assert by_family["activity_designer"]["context"]["source"] in ("llm", "fallback")
    assert by_family["content_designer"]["context"]["source"] in ("deterministic", "llm")

    for event in dev_plan_events:
        ctx = event["context"]
        assert ctx["set_count"] >= 1
        assert isinstance(ctx["sets"], list) and ctx["sets"]
        assert all("set_id" in s for s in ctx["sets"])
        # Planning the sets is the ORCHESTRATOR's work, not one Developer's:
        # it reads state no single Developer owns, and picking the split is
        # what makes them separable in the first place. (Before the Developer
        # tier moved into core/agentic, the dispatching Designer logged it.)
        assert event["agent"] == WORKFLOW_ORCHESTRATOR


def test_dev_plan_events_fire_in_prose_arm_too():
    result = _run("multi", context_mode="prose")
    dev_plan_events = [e for e in result["trajectory"]["events"] if e["action"] == "dev_plan"]
    families = {e["context"]["family"] for e in dev_plan_events}
    assert families == {"assessment_designer", "activity_designer", "content_designer"}


def test_the_single_arm_plans_no_work_sets_at_all():
    """The single arm has no Developer tier and no dev-plan hop: since
    2026-09-01 it is one ReAct loop that decides its own batching and submits a
    family across as many calls as it judges it needs. So the absence of these
    events IS the axis, not a gap in the record — what it batched is in
    ``autonomy.design.submits_per_stage`` instead."""
    result = _run("single")

    assert not [e for e in result["trajectory"]["events"] if e["action"] == "dev_plan"]
    assert result["metadata"]["autonomy"]["design"]["submits_per_stage"]


def test_workers_are_attributed_to_the_developer_not_the_designer():
    """Worker llm_call rows must name the Developer class — the stage commits
    the pooled result, but never calls the model for an individual set."""
    result = _run("multi")
    llm_actions = [a for a in result["trajectory_deep"]["actions"] if a["action"] == "llm_call"]
    agents = {a["agent"] for a in llm_actions}
    assert "AssessmentDeveloperAgent" in agents
    assert "ActivityDeveloperAgent" in agents
    assert "MaterialDeveloperAgent" in agents
    # No RubricDeveloperAgent: rubrics are written by the Assessment Developer
    # that wrote the items they mark, in the same call (2026-09-01).
    assert "RubricDeveloperAgent" not in agents
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
    # No "rubric": a criterion is a field of the assessment item it marks, not
    # an element pool of its own (2026-09-02). Its remap still runs — the same
    # `remap_and_tag` — but it lands on the parent, which the next assertion
    # checks directly.
    for node_type in ("assessment", "activity", "material"):
        ids = [n["id"] for n in graph["nodes"] if n["type"] == node_type]
        assert len(ids) == len(set(ids)), f"{node_type} ids collided: {ids}"
        elements = [n for n in graph["nodes"] if n["type"] == node_type and ":" in n["id"]]
        assert elements, f"{node_type} produced nothing"
        # `plan_set` marks an element a WORK SET produced. An element the repair
        # net synthesised carries no set because no set produced it — that is
        # the stamp doing its job, not failing at it, and the two are exactly
        # what a reader needs to tell apart.
        stamped = [n for n in elements if n["data"].get("plan_set")]
        assert stamped, f"{node_type}: no element came from a work set at all"

    # The criteria arrived, inside the items that carry them. Their ids need to
    # be unique only WITHIN an item: a criterion is a field, not a node, so the
    # same RC-01 on two different items collides with nothing — which is
    # precisely what stopped being true of the item ids above.
    items = [n["data"] for n in graph["nodes"] if n["type"] == "assessment" and ":" in n["id"]]
    assert any(i.get("rubric") for i in items), "no item carries a rubric criterion"
    for item in items:
        rc_ids = [rc.get("id") for rc in (item.get("rubric") or [])]
        assert len(rc_ids) == len(set(rc_ids)), f"{item.get('item_id')}: {rc_ids}"
