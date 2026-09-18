"""The course's modules and the assessment blueprint built on them.

A module is the structural unit the Outcome Designer writes right after the
objectives; the assessment plan's ``instruments`` say what learners sit in each
module, and every question-level item names the instrument it is part of.
"""
from __future__ import annotations

from alignmentgraph_isd import HarnessRunConfig
from alignmentgraph_isd.core import checks, dev_plans, repairs
from alignmentgraph_isd.core.agentic import alignment_state, specialists
from alignmentgraph_isd.core.alignment_graph import AlignmentGraph, NodeType, alignment
from alignmentgraph_isd.core.prose_store import ProseStore
from alignmentgraph_isd.core.trajectory import ORCHESTRATOR, TrajectoryLogger

from conftest import load_brief

STEP = {step.name: step for step in specialists.STEPS}


def _instrument(ins_id: str, timing: str, covers: list[str], module: str = "MOD-01") -> dict:
    return {"id": ins_id, "module_id": module, "timing": timing, "format": "quiz",
            "item_counts": {"multiple_choice": 10}, "covers_objectives": covers}


def _design(plan: dict, items: list[dict]) -> AlignmentGraph:
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.MODULE, "MOD-01", {"id": "MOD-01"})
    for lo in ("ILO-01", "ILO-02"):
        graph.add_element_node(NodeType.OBJECTIVE, lo, {"id": lo})
    graph.add_node(NodeType.ASSESSMENT_PLAN, graph.section_id(NodeType.ASSESSMENT_PLAN), plan)
    for item in items:
        graph.add_element_node(NodeType.ASSESSMENT, item["item_id"], item)
    return graph


def _ctx(graph, trajectory) -> repairs.RepairContext:
    return repairs.RepairContext(graph=graph, store=None, trajectory=trajectory,
                                 actor=ORCHESTRATOR)


# ── how many modules ────────────────────────────────────────────────────────

def test_the_module_ceiling_is_the_tightest_of_objectives_topics_and_course_length():
    assert dev_plans.module_ceiling(5, 4, 20) == 3, "within a week"
    assert dev_plans.module_ceiling(5, 5, 120) == 4, "up to a month"
    assert dev_plans.module_ceiling(6, 9, 720) == dev_plans.MAX_MODULES
    assert dev_plans.module_ceiling(2, 7, 720) == 2, "never more modules than objectives"
    assert dev_plans.module_ceiling(6, 1, 720) == 1, "nor than topics"
    assert dev_plans.module_ceiling(5, 5, 0) == dev_plans.MODULES_UNKNOWN_LENGTH
    assert dev_plans.module_ceiling(0, 0, 20) == 3, "a count not written yet does not bind"


def test_the_outcome_designer_is_told_this_course_s_ceiling_and_it_is_never_enforced():
    """The RULE is in the pinned prompt; the NUMBER depends on the course, so
    it arrives through the state read — and only until the modules exist."""
    graph, trajectory = AlignmentGraph(), TrajectoryLogger()
    brief = load_brief("minimal_brief.json")     # "2 days": within a week
    for topic in ("TOP-01", "TOP-02"):
        graph.add_element_node(NodeType.TOPIC, topic, {"id": topic})
    text = alignment_state.read(graph, brief, STEP["outcomes"]).text
    assert "course_modules: at most 2 for this course" in text

    many = [{"id": f"MOD-0{n}", "title": f"Module {n}", "objectives": ["ILO-01"], "minutes": 30}
            for n in range(1, 6)]
    assert specialists.validate_outcomes({"course_modules": many}) == []
    specialists.commit_outcomes(graph, trajectory, {"course_modules": many})
    assert "course_modules: at most" not in alignment_state.read(graph, brief, STEP["outcomes"]).text


def test_a_module_must_name_its_objectives_and_its_time():
    errors = specialists.validate_outcomes({"course_modules": [
        {"id": "MOD-01", "title": "M", "objectives": [], "minutes": 0}]})
    assert errors == ["course_modules[0].objectives must list at least one objective id",
                      "course_modules[0].minutes must be a positive number"]


def test_modules_accumulate_the_same_way_on_both_substrates():
    first = {"course_modules": [{"id": "MOD-01", "title": "Basics", "objectives": ["ILO-01"],
                                 "minutes": 60}]}
    again = {"course_modules": [{"id": "MOD-09", "title": "basics ", "objectives": ["ILO-01"],
                                 "minutes": 60},
                                {"id": "MOD-02", "title": "Practice", "objectives": ["ILO-02"],
                                 "minutes": 90}]}
    graph, store, trajectory = AlignmentGraph(), ProseStore(), TrajectoryLogger()
    for payload in (first, again):
        specialists.commit_outcomes(graph, trajectory, payload)
        specialists.commit_outcomes_prose(store, trajectory, payload)
    in_graph = [n["data"]["id"] for n in graph.element_nodes(NodeType.MODULE)]
    in_prose = [m["id"] for m in store.items("objective", "course_modules")]
    assert in_graph == in_prose == ["MOD-01", "MOD-02"], "the repeated title is dropped by both"


# ── the blueprint agrees with itself ────────────────────────────────────────

def test_a_pair_an_instrument_promises_is_added_to_the_coverage_targets():
    plan = {"instruments": [_instrument("INS-01", "formative", ["ILO-01", "objective:ILO-02"])],
            "lo_coverage_targets": {"objective:ILO-01": ["summative"]}}
    graph, trajectory = _design(plan, []), TrajectoryLogger()
    found = checks.blueprint_consistency(graph)
    assert [(v.metadata["lo_id"], v.metadata["plan_category"]) for v in found] == [
        ("ILO-01", "formative"), ("ILO-02", "formative")]

    assert repairs.repair("assessment_designer", found, _ctx(graph, trajectory)) == []
    targets = graph.get_node("assessment_plan_0")["data"]["lo_coverage_targets"]
    assert targets == {"objective:ILO-01": ["summative", "formative"], "ILO-02": ["formative"]}, (
        "added to the entry the model already wrote, under the key it used")
    assert checks.blueprint_consistency(graph) == []
    assert [e["context"]["rule"] for e in trajectory.repair_events] == ["repair_blueprint_pairs"]


def test_an_instrument_naming_nothing_real_is_handed_back_not_guessed():
    plan = {"instruments": [_instrument("INS-01", "summative", ["ILO-07"], module="MOD-05")],
            "lo_coverage_targets": {"ILO-07": ["summative"]}}
    graph, trajectory = _design(plan, []), TrajectoryLogger()
    found = checks.blueprint_consistency(graph)
    assert {v.metadata["kind"] for v in found} == {"unknown_module", "unknown_objective"}
    assert repairs.repair("assessment_designer", found, _ctx(graph, trajectory)) == found
    assert not trajectory.repair_events


def test_the_prose_arm_checks_the_half_that_reads_the_plan_alone():
    plan = {"instruments": [_instrument("INS-01", "formative", ["ILO-01"], module="MOD-05")],
            "lo_coverage_targets": {"ILO-01": ["summative"]}}
    found = checks.blueprint_consistency_data("assessment_plan", plan)
    assert [v.metadata["kind"] for v in found] == ["unpromised_pair"]


# ── every item belongs to an instrument ─────────────────────────────────────

def _item(item_id: str, lo: str, category: str, instrument: str) -> dict:
    return {"item_id": item_id, "aligned_objective": lo, "plan_category": category,
            "instrument_id": instrument}


def test_an_item_is_filed_under_the_one_instrument_its_own_fields_identify():
    plan = {"instruments": [_instrument("INS-01", "formative", ["ILO-01"]),
                            _instrument("INS-02", "summative", ["ILO-01", "ILO-02"]),
                            _instrument("INS-03", "summative", ["ILO-02"])]}
    graph = _design(plan, [
        _item("AT-01", "ILO-01", "formative", "INS-01"),        # right
        _item("AT-02", "ILO-01", "summative", "quiz-2"),        # unknown, one candidate
        _item("AT-03", "ILO-01", "summative", "INS-01"),        # wrong timing, one candidate
        _item("AT-04", "ILO-02", "summative", ""),              # two candidates
    ])
    trajectory = TrajectoryLogger()
    found = checks.instrument_alignment(graph)
    assert [v.node_id for v in found] == ["assessment:AT-02", "assessment:AT-03", "assessment:AT-04"]

    left = repairs.repair("assessment_designer", found, _ctx(graph, trajectory))
    assert [v.node_id for v in left] == ["assessment:AT-04"], "two candidates is not a lookup"
    assert graph.get_node("assessment:AT-02")["data"]["instrument_id"] == "INS-02"
    assert graph.get_node("assessment:AT-03")["data"]["instrument_id"] == "INS-02"
    assert {e["target"] for e in graph.get_edges(relation_id="P14")} == {
        "assessment:AT-01", "assessment:AT-02", "assessment:AT-03"}


def test_a_plan_with_no_instruments_gives_the_items_nothing_to_belong_to():
    graph = _design({"lo_coverage_targets": {"ILO-01": ["summative"]}},
                    [_item("AT-01", "ILO-01", "summative", "")])
    assert checks.instrument_alignment(graph) == []
    assert alignment.relation_coverage(graph, "P14") == (0.0, ["module:MOD-01"])


def test_both_checks_are_owned_and_structural():
    for kind in ("blueprint_consistency", "instrument_alignment"):
        assert repairs.OWNER_BY_VIOLATION[kind] == "assessment_designer"
        assert kind in repairs.STRUCTURAL and kind not in repairs.REPORT_ONLY
    assert {"P7", "P12", "P13", "P14"} <= repairs.REPORT_ONLY
    assert HarnessRunConfig().agent_mode == "multi"
