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
    assert {v.metadata["kind"] for v in found} == {
        "unknown_module", "unknown_objective",
        # ...and what that leaves the real course without:
        "module_without_instrument", "objective_without_instrument"}
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


# ── the dev plans speak in modules and instruments ──────────────────────────

def test_every_dev_plan_names_the_module_a_set_belongs_to():
    from alignmentgraph_isd.core.agentic.artifact_schemas import ARTIFACT_SCHEMAS

    for plan, list_key in (("assessment_dev_plan", "instrument_sets"),
                           ("activity_dev_plan", "activity_blocks"),
                           ("implementation_dev_plan", "session_blocks")):
        item = ARTIFACT_SCHEMAS[plan]["properties"][list_key]["items"]
        assert "module_id" in item["required"], plan
    sets = ARTIFACT_SCHEMAS["assessment_dev_plan"]["properties"]["instrument_sets"]["items"]
    assert "instrument_ids" in sets["required"] and "objectives" not in sets["properties"]


def test_an_instrument_set_is_the_pairs_of_the_instruments_it_names():
    modules = [{"id": "MOD-01", "objectives": ["ILO-01"], "minutes": 60},
               {"id": "MOD-02", "objectives": ["ILO-02"], "minutes": 60}]
    instruments = [_instrument("INS-01", "diagnostic", ["ILO-01"]),
                   _instrument("INS-02", "formative", ["ILO-01"]),
                   _instrument("INS-03", "summative", ["ILO-02"], module="MOD-02")]
    targets = {"ILO-01": ["diagnostic", "formative"], "ILO-02": ["summative"]}
    plan = {"instrument_sets": [
        {"set_id": "SET-01", "module_id": "MOD-01", "instrument_ids": ["INS-01", "INS-02"],
         "expected_items": 4},
        {"set_id": "SET-02", "module_id": "MOD-02", "instrument_ids": ["INS-03", "INS-09"],
         "expected_items": 2}]}
    sets, stats = dev_plans.normalize_assessment_dev_plan(
        plan, ["ILO-01", "ILO-02"], targets, modules=modules, instruments=instruments,
        mode="sample")
    assert [(ws.module_id, ws.pairs, ws.source) for ws in sets] == [
        ("MOD-01", (("ILO-01", "diagnostic"), ("ILO-01", "formative")), "llm"),
        ("MOD-02", (("ILO-02", "summative"),), "llm")]
    assert [i["id"] for i in sets[0].payload["instruments"]] == ["INS-01", "INS-02"]
    assert stats["fallback_used"] is False and stats["dropped_lo_refs"] == 1, "INS-09 is not real"


# ── a work set writes what it was commissioned for ──────────────────────────

def test_a_set_that_overruns_its_count_is_cut_to_it_and_loses_nothing_a_check_measures():
    """MEASURED (run aef73e0a): told 3 items a Developer submitted 17, told 3
    activities another wrote 15, told one session guide a third wrote eight."""
    items = [{"question": f"Q{n % 5}", "aligned_objective": "ILO-01" if n < 9 else "ILO-02",
              "plan_category": "formative"} for n in range(12)]
    ws = dev_plans.WorkSet(set_id="AS-01", pairs=(("ILO-01", "formative"), ("ILO-02", "formative")),
                           payload={"expected_items": 3})
    kept, dropped = dev_plans.trim_to_quota(ws, "assessment_tools", items)
    assert len(kept) == 3 and dropped == 9
    assert {i["aligned_objective"] for i in kept} == {"ILO-01", "ILO-02"}, "both pairs survive"
    assert len({i["question"] for i in kept}) == 3, "a repeat goes before anything else"

    activities = [{"activity_name": f"A{n}", "prerequisite_activities": [n] if n else []}
                  for n in range(6)]
    ws = dev_plans.WorkSet(set_id="AB-01", payload={"expected_activities": 3})
    kept, _ = dev_plans.trim_to_quota(ws, "learning_activities", activities)
    assert [a["activity_name"] for a in kept] == ["A0", "A1", "A2"], "a prefix: [2] still means A1"

    guides = [{"session": n, "activity_ids": ["TLA-01", "TLA-02"]} for n in range(1, 5)]
    guides.append({"session": 5, "activity_ids": ["TLA-03"]})
    ws = dev_plans.WorkSet(set_id="SB-01", payload={"expected_sessions": 1})
    kept, _ = dev_plans.trim_to_quota(ws, "session_guides", guides)
    assert [g["session"] for g in kept] == [1, 5], "the guide that schedules a new id is kept"

    ws = dev_plans.WorkSet(set_id="S0", source="agent")
    assert dev_plans.trim_to_quota(ws, "assessment_tools", items) == (items, 0), (
        "a batch that states no count is the single agent's own and is left as written")


# ── the analysis can be divided by, too ─────────────────────────────────────

def test_constraints_written_as_sentences_become_elements_and_topics_are_required():
    from alignmentgraph_isd.core.agentic import tools

    spec = next(s for s in tools.submit_specs(STEP["analysis"])
                if s["function"]["name"] == "submit_context_analysis")
    reshaped: list = []
    args = tools.reshape_args(spec["function"]["parameters"], {"context_analysis": {
        "constraints": ["Budget constraints", {"id": "c2", "description": "Time"}]}},
        reshaped=reshaped)
    assert args["context_analysis"]["constraints"] == [
        {"id": "CON-01", "description": "Budget constraints"}, {"id": "c2", "description": "Time"}]
    assert reshaped == ["context_analysis.constraints[0]"]

    assert specialists.validate_analysis({"task_analysis": {"task_overview": "x"}}) == [
        "task_analysis.topics must be a non-empty list"]


def test_the_blueprint_has_to_reach_every_module_and_every_objective():
    """MEASURED (run b8576814): three instruments, all for one module and one
    objective. Said on the PLAN, it reaches the Designer before any Developer
    runs; P14 and C2 only say it afterwards."""
    plan = {"instruments": [_instrument("INS-01", "summative", ["ILO-01"])],
            "lo_coverage_targets": {"ILO-01": ["summative"]}}
    graph = _design(plan, [])
    graph.add_element_node(NodeType.MODULE, "MOD-02", {"id": "MOD-02"})
    found = {(v.metadata["kind"], v.metadata.get("module_id") or v.metadata.get("lo_id"))
             for v in checks.blueprint_consistency(graph)}
    assert found == {("module_without_instrument", "MOD-02"),
                     ("objective_without_instrument", "ILO-02")}
    assert all(":" not in v.node_id for v in checks.blueprint_consistency(graph)), (
        "on the plan section, so the Designer is shown it before its Developers run")
    assert len({v.key for v in checks.blueprint_consistency(graph)}) == 2


def test_a_reference_spelled_the_way_a_listing_row_invites_still_resolves():
    """MEASURED (run b8576814): `covers_topics: ["TOPIC-001"]` against topics
    `topic_001`..`topic_003` — three correct references and P7 at 0.0."""
    graph = AlignmentGraph()
    for topic in ("topic_001", "topic_002"):
        graph.add_element_node(NodeType.TOPIC, topic, {"id": topic})
    resolve = alignment.resolve_element
    assert resolve(graph, NodeType.TOPIC, "topic_001") == "topic:topic_001"
    for spelling in ("TOPIC-001", "topic:topic_001", "Topic 001", "TOPIC-topic_001"):
        assert resolve(graph, NodeType.TOPIC, spelling) == "topic:topic_001", spelling
    assert resolve(graph, NodeType.TOPIC, "topic_009") == ""
    graph.add_element_node(NodeType.TOPIC, "TOPIC-001", {"id": "TOPIC-001"})
    assert resolve(graph, NodeType.TOPIC, "Topic 001") == "", "two candidates is not a lookup"

    trajectory = TrajectoryLogger()
    fresh = AlignmentGraph()
    fresh.add_element_node(NodeType.TOPIC, "topic_001", {"id": "topic_001"})
    specialists.commit_outcomes(fresh, trajectory, {"course_modules": [
        {"id": "MOD-01", "title": "M", "objectives": ["ILO-01"], "covers_topics": ["TOPIC-001"],
         "minutes": 60}]})
    assert alignment.relation_coverage(fresh, "P7") == (1.0, [])


def test_a_membership_id_the_set_settles_is_filled_in_and_one_the_model_wrote_is_left():
    """MEASURED (run 53a9cd1a): five refusals and a give-up-and-regen over a
    missing `instrument_id` on sets that each listed a single instrument."""
    one = dev_plans.WorkSet(set_id="AS-01", payload={
        "instruments": [_instrument("INS-01", "summative", ["ILO-01"])]})
    items = [{"question": "q", "aligned_objective": "ILO-01", "plan_category": "summative"},
             {"question": "r", "instrument_id": "INS-77"}]
    filled = dev_plans.with_membership(one, "assessment_tools", items)
    assert [i["instrument_id"] for i in filled] == ["INS-01", "INS-77"], "only a MISSING id"
    assert "instrument_id" not in items[0], "the submitted arguments are not rewritten"

    two = dev_plans.WorkSet(set_id="AS-02", payload={"instruments": [
        _instrument("INS-01", "formative", ["ILO-01"]), _instrument("INS-02", "summative", ["ILO-01"]),
        _instrument("INS-03", "summative", ["ILO-01"])]})
    formative, summative = dev_plans.with_membership(two, "assessment_tools", [
        {"aligned_objective": "ILO-01", "plan_category": "formative"},
        {"aligned_objective": "ILO-01", "plan_category": "summative"}])
    assert formative["instrument_id"] == "INS-01", "one instrument of its objective and category"
    assert "instrument_id" not in summative, "two candidates is the writer's to say"

    block = dev_plans.WorkSet(set_id="AB-01", payload={"module": {"id": "MOD-02"}})
    assert dev_plans.with_membership(block, "learning_activities", [{"activity_name": "a"}]) == [
        {"activity_name": "a", "module_id": "MOD-02"}]
