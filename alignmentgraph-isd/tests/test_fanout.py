"""End-to-end coverage of the Developer tier that the more targeted test files
don't already exercise: the ``dev_plan`` trajectory
event's shape/content in both arms, worker attribution to the Developer's OWN
identity (not the Designer's), and id-collision remap surviving a real run.
Per-family mechanics (normalize/remap/regen) are unit-tested directly in
test_dev_plans.py; topology in test_ablation_flags.py; per-set regen budget
in test_empty_section_regen.py; phase bracketing in test_on_event.py."""
from __future__ import annotations

from alignmentgraph_isd import HarnessRunConfig
from alignmentgraph_isd.core.trajectory import ORCHESTRATOR

from conftest import FakeChatModel, load_brief, run_brief


def _run(mode: str = "multi", context_mode: str = "graph"):
    brief = load_brief("minimal_brief.json")
    # The agentic executor is the only one since 2026-09-01; the fan-out moved
    # with it (core/agentic/fanout.py) and keeps the same shared normalization
    # what it was written for.
    config = HarnessRunConfig(llm_factory=lambda: FakeChatModel(), agent_mode=mode,
                              context_mode=context_mode, )
    return run_brief(brief, config)


def test_work_set_events_fire_once_per_fanout_family_multi_arm():
    """One per family, plus one per RE-DISPATCH round. A family whose
    Developers leave a gap is dispatched again (core/agentic/redispatch.py), and
    that second division of the work is a second event — the trace would
    otherwise under-report what the Developers were asked for."""
    result = _run("multi")
    work_set_events = [e for e in result["trajectory"]["events"] if e["action"] == "work_sets"]
    families = {e["context"]["family"] for e in work_set_events}
    assert families == {"assessment_designer", "activity_designer", "content_designer",
                        "implementation_planner"}

    replans = sum(len([p for p in result["plans"] if p["stage"] == stage]) - 1
                  for stage in {p["stage"] for p in result["plans"]})
    assert len(work_set_events) == len(families) + replans, (
        "one dev_plan event per family per planning round")

    by_family = {e["context"]["family"]: e for e in work_set_events}
    # No family asks the model how to divide its own work: each grouping is
    # derived from an artifact of the design (a set, a module).
    assert {e["context"]["source"] for e in work_set_events} == {"deterministic"}
    assert set(by_family) == families

    for event in work_set_events:
        ctx = event["context"]
        assert ctx["set_count"] >= 1
        assert isinstance(ctx["sets"], list) and ctx["sets"]
        assert all("set_id" in s for s in ctx["sets"])
        # Planning the sets is the ORCHESTRATOR's work, not one Developer's:
        # it reads state no single Developer owns, and picking the split is
        # what makes them separable in the first place. (Before the Developer
        # tier moved into core/agentic, the dispatching Designer logged it.)
        assert event["agent"] == ORCHESTRATOR


def test_work_set_events_fire_in_prose_arm_too():
    result = _run("multi", context_mode="prose")
    work_set_events = [e for e in result["trajectory"]["events"] if e["action"] == "work_sets"]
    families = {e["context"]["family"] for e in work_set_events}
    assert families == {"assessment_designer", "activity_designer", "content_designer",
                        "implementation_planner"}


def test_the_single_arm_plans_no_work_sets_at_all():
    """The single arm has no Developer tier and no dev-plan hop: since
    2026-09-01 it is one ReAct loop that decides its own batching and submits a
    family across as many calls as it judges it needs. So the absence of these
    events IS the axis, not a gap in the record — what it batched is in
    ``autonomy.design.submits_per_stage`` instead."""
    result = _run("single")

    assert not [e for e in result["trajectory"]["events"] if e["action"] == "work_sets"]
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


def test_every_scheduled_artifact_lands_in_exactly_one_session_block():
    """The invariant the implementation fan-out exists for.

    P10/P11 coverage used to depend on a planner naming every activity id in a
    single submit — which it could neither see (``tools.render_listing`` stops
    at ``READ_CHAR_BUDGET``: a 161-activity design truncates) nor write under
    the completion cap. It is now a property of a deterministic division:
    every activity and every material lands in exactly one block, derived from
    the module each one was written for, and each block's Developer writes the
    guides for its own sessions.

    Assigning the work is not fabricating the record — the P10/P11 edge still
    comes from the ``activity_ids`` a Developer wrote (the rule
    ``audit.AUDIT_ONLY_VIOLATION_TYPES`` states), and this test asserts only
    the division.
    """
    from alignmentgraph_isd.core import dev_plans
    from alignmentgraph_isd.core.agentic import fanout
    from alignmentgraph_isd.core.alignment_graph import AlignmentGraph, NodeType

    graph = AlignmentGraph()
    for i in range(1, 162):
        graph.add_element_node(NodeType.ACTIVITY, f"TLA-{i:04d}", {"id": f"TLA-{i:04d}"})
    for i in range(1, 7):
        graph.add_element_node(NodeType.MATERIAL, f"MAT-{i:04d}", {"id": f"MAT-{i:04d}"})

    spec = fanout.SPECS["implementation"]
    # With modules and without: an artifact whose module is unknown still has
    # to land somewhere, which is what a design that lost its modules leaves.
    for modules in ([], [{"id": "MOD-01", "title": "M", "minutes": 600,
                          "objectives": ["ILO-01"]}]):
        sets, stats = spec.plan_sets(graph, {"modules": modules})
        assert sets
        scheduled = [i for ws in sets
                     for i in ws.payload["activity_ids"] + ws.payload["material_ids"]]
        assert len(scheduled) == len(set(scheduled)), "an artifact was scheduled twice"
        assert set(scheduled) == ({f"TLA-{i:04d}" for i in range(1, 162)}
                                  | {f"MAT-{i:04d}" for i in range(1, 7)})
        # Every block fits in one Developer call, and its sessions are numbered
        # before any of them runs — Developers never coordinate.
        limit = dev_plans.max_units("session_guide")
        starts = []
        for ws in sets:
            size = len(ws.payload["activity_ids"]) + len(ws.payload["material_ids"])
            assert size <= limit, f"{ws.set_id} carries {size} scheduled artifacts"
            starts.append(ws.payload["first_session"])
        assert starts == sorted(starts) and len(set(starts)) == len(starts)
        assert stats["source"] == "deterministic", "no model proposed this grouping"



def test_session_guides_are_element_nodes_that_carry_the_delivery_edges():
    """The guides are the artifact the Developer tier writes, P10/P11 hang off
    THOSE nodes, and the aggregator joins them back where the ADDIE output
    contract keeps them — so the deliverable's shape is unchanged."""
    result = _run("multi")
    graph = result["graph"]

    guides = [n for n in graph["nodes"] if n["type"] == "session_guide"]
    assert guides, "the session guides were not produced as element nodes"
    assert all(n["data"].get("plan_set") for n in guides), (
        "a guide came from no work set")

    sources = {e["source"] for e in graph["edges"]
               if e.get("relation_id") in ("P10", "P11")}
    assert sources and sources <= {n["id"] for n in guides}

    joined = result["addie_output"]["development"]["instructor_guide"]["session_guides"]
    assert len(joined) == len(guides)
    # ...and the plan section keeps only the guide's framing.
    section = [n for n in graph["nodes"] if n["id"] == "implementation_plan_0"][0]
    assert "session_guides" not in section["data"].get("instructor_guide", {})
    # The harness-only plan never reaches the deliverable.
    assert "dev_plan" not in result["addie_output"]["implementation"]


def _shape(result: dict) -> tuple:
    graph = result["graph"]
    nodes = [(n["id"], n["type"], n.get("data")) for n in graph["nodes"]]
    edges = sorted((e["source"], e["target"], e.get("type") or e.get("relation"))
                   for e in graph["edges"])
    plans = [(p["stage"], [ws["set_id"] for ws in p["work_sets"]]) for p in result["plans"]]
    return nodes, edges, plans


def test_parallel_workers_produce_the_same_graph_as_sequential():
    """``fanout_workers`` changes WHEN the Developers run, never what lands:
    the commits stay in plan order, so the graph's insertion order — which is
    what every later listing and the aggregate's lists come out in — is the
    same whatever the worker count. Contexts are compared as a SET: their
    publication order is the workers' and is allowed to differ."""
    brief = load_brief("minimal_brief.json")
    runs = {n: run_brief(brief, HarnessRunConfig(llm_factory=lambda: FakeChatModel(),
                                                 agent_mode="multi", fanout_workers=n))
            for n in (1, 3)}
    assert _shape(runs[1]) == _shape(runs[3])
    assert runs[1]["addie_output"] == runs[3]["addie_output"]
    assert ({c["agent"] for c in runs[1]["contexts"]}
            == {c["agent"] for c in runs[3]["contexts"]})
    assert runs[1]["metadata"]["run_config"]["fanout_workers"] == 1
    assert runs[3]["metadata"]["run_config"]["fanout_workers"] == 3
    assert (runs[1]["metadata"]["token_usage"]["llm_calls"]
            == runs[3]["metadata"]["token_usage"]["llm_calls"])


def test_the_default_is_one_worker():
    assert HarnessRunConfig().fanout_workers == 1


def test_the_event_says_which_artifact_each_set_was_derived_from():
    """Every family's sets are derived from an artifact of the design, so two
    sets of one module cover the same objectives and are told apart by
    nothing else. An event carrying `objectives` alone showed three
    assessment sets as three identical rows — which is what the LLM judge
    reads as redundancy."""
    result = _run("multi")
    events = {e["context"]["phase"]: e["context"]["sets"]
              for e in result["trajectory"]["events"] if e["action"] == "work_sets"}

    for phase, sets in events.items():
        assert all(s["module_id"] for s in sets), phase
        keys = [(s["module_id"], tuple(s.get("for_sets") or ())) for s in sets]
        assert len(keys) == len(set(keys)) or phase.endswith("R1"), (
            f"{phase}: two sets with the same grouping key are indistinguishable")

    assessment = events["assessment"]
    assert all(s["for_sets"] for s in assessment), (
        "an assessment set writes for a named set of the blueprint")
    assert len({tuple(s["for_sets"]) for s in assessment}) == len(assessment)
