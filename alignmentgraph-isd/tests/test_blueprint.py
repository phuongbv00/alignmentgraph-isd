"""The course's modules and the assessment blueprint built on them.

A module is the structural unit the Outcome Designer writes right after the
objectives; the assessment plan's ``sets`` say what learners sit in each
module, and every question-level item names the set it is part of.
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


def _set(set_id: str, timing: str, covers: list[str], module: str = "MOD-01") -> dict:
    return {"id": set_id, "module_id": module, "timing": timing, "format": "quiz",
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

def test_a_pair_a_set_promises_is_added_to_the_coverage_targets():
    plan = {"sets": [_set("SET-01", "formative", ["ILO-01", "objective:ILO-02"]),
                            # keeps the ONE summative promise, so the plan is
                            # inconsistent in the direction this test is about
                            # and in no other.
                            _set("SET-02", "summative", ["ILO-01"])],
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


def test_a_set_naming_nothing_real_is_handed_back_not_guessed():
    plan = {"sets": [_set("SET-01", "summative", ["ILO-07"], module="MOD-05")],
            "lo_coverage_targets": {"ILO-07": ["summative"]}}
    graph, trajectory = _design(plan, []), TrajectoryLogger()
    found = checks.blueprint_consistency(graph)
    assert {v.metadata["kind"] for v in found} == {
        "unknown_module", "unknown_objective",
        # ...and what that leaves the real course without:
        "module_without_set", "objective_without_set"}
    assert repairs.repair("assessment_designer", found, _ctx(graph, trajectory)) == found
    assert not trajectory.repair_events


def test_a_promise_no_set_can_keep_is_handed_back_before_the_fanout():
    """The work-set planner divides the INSTRUMENTS, so this pair would reach
    no Developer. Nothing read it until now: it surfaced only as
    ``plan_coverage`` once the Developers had run and no agent was left."""
    plan = {"sets": [_set("SET-01", "summative", ["ILO-01", "ILO-02"])],
            "lo_coverage_targets": {"ILO-01": ["summative", "diagnostic"],
                                    "ILO-02": ["summative"]}}
    graph, trajectory = _design(plan, []), TrajectoryLogger()
    found = [v for v in checks.blueprint_consistency(graph)
             if v.metadata["kind"] == "unassessed_pair"]
    assert [(v.metadata["lo_id"], v.metadata["plan_category"]) for v in found] == [
        ("ILO-01", "diagnostic")]
    assert ":" not in found[0].node_id, (
        "anchored on the plan, so the pre-tier element filter does not withhold it")

    assert repairs.repair("assessment_designer", found, _ctx(graph, trajectory)) == found, (
        "no lookup settles it — writing the set is the Designer's")
    assert not trajectory.repair_events


def test_the_prose_arm_checks_both_halves_that_read_the_plan_alone():
    plan = {"sets": [_set("SET-01", "formative", ["ILO-01"], module="MOD-05")],
            "lo_coverage_targets": {"ILO-01": ["summative"]}}
    found = checks.blueprint_consistency_data("assessment_plan", plan)
    assert [v.metadata["kind"] for v in found] == ["unpromised_pair", "unassessed_pair"]


# ── every item belongs to a set ─────────────────────────────────────

def _item(item_id: str, lo: str, category: str, set_id: str) -> dict:
    return {"item_id": item_id, "aligned_objective": lo, "plan_category": category,
            "set_id": set_id}


def test_an_item_is_filed_under_the_one_set_its_own_fields_identify():
    plan = {"sets": [_set("SET-01", "formative", ["ILO-01"]),
                            _set("SET-02", "summative", ["ILO-01", "ILO-02"]),
                            _set("SET-03", "summative", ["ILO-02"])]}
    graph = _design(plan, [
        _item("AT-01", "ILO-01", "formative", "SET-01"),        # right
        _item("AT-02", "ILO-01", "summative", "quiz-2"),        # unknown, one candidate
        _item("AT-03", "ILO-01", "summative", "SET-01"),        # wrong timing, one candidate
        _item("AT-04", "ILO-02", "summative", ""),              # two candidates
    ])
    trajectory = TrajectoryLogger()
    found = checks.set_alignment(graph)
    assert [v.node_id for v in found] == ["assessment:AT-02", "assessment:AT-03", "assessment:AT-04"]

    left = repairs.repair("assessment_designer", found, _ctx(graph, trajectory))
    assert [v.node_id for v in left] == ["assessment:AT-04"], "two candidates is not a lookup"
    assert graph.get_node("assessment:AT-02")["data"]["set_id"] == "SET-02"
    assert graph.get_node("assessment:AT-03")["data"]["set_id"] == "SET-02"
    assert {e["target"] for e in graph.get_edges(relation_id="P14")} == {
        "assessment:AT-01", "assessment:AT-02", "assessment:AT-03"}


def test_a_plan_with_no_sets_gives_the_items_nothing_to_belong_to():
    graph = _design({"lo_coverage_targets": {"ILO-01": ["summative"]}},
                    [_item("AT-01", "ILO-01", "summative", "")])
    assert checks.set_alignment(graph) == []
    assert alignment.relation_coverage(graph, "P14") == (0.0, ["module:MOD-01"])


def test_both_checks_are_owned_and_structural():
    for kind in ("blueprint_consistency", "set_alignment"):
        assert repairs.OWNER_BY_VIOLATION[kind] == "assessment_designer"
        assert kind in repairs.STRUCTURAL and kind not in repairs.REPORT_ONLY
    assert {"P7", "P12", "P13", "P14"} <= repairs.REPORT_ONLY
    assert HarnessRunConfig().agent_mode == "multi"


# ── the dev plans speak in modules and sets ──────────────────────────

def test_every_work_set_names_the_module_it_belongs_to():
    """A set never spans two modules — the module is the partition every
    family divides by, and its id is what the assignment names first."""
    from alignmentgraph_isd.core.agentic import fanout

    graph = _design({"sets": [
        _set("SET-01", "summative", ["ILO-01"]),
        _set("SET-02", "summative", ["ILO-02"], module="MOD-02")],
        "lo_coverage_targets": {"ILO-01": ["summative"], "ILO-02": ["summative"]}}, [])
    graph.add_element_node(NodeType.MODULE, "MOD-02", {"id": "MOD-02"})
    modules = [{"id": "MOD-01", "objectives": ["ILO-01"], "minutes": 60},
               {"id": "MOD-02", "objectives": ["ILO-02"], "minutes": 60}]
    payload = {"modules": modules,
               "assessment_plan": graph.get_node("assessment_plan_0")["data"]}

    sets, _stats = fanout.SPECS["assessment"].plan_sets(graph, payload, "sample")
    assert [ws.module_id for ws in sets] == ["MOD-01", "MOD-02"]
    assert [ws.set_id for ws in sets] == ["AS-SET-01", "AS-SET-02"], (
        "a set id says which set it writes, so deriving again names it "
        "the same and only new sets run")


def test_a_work_set_is_the_pairs_of_the_assessment_sets_it_names():
    modules = [{"id": "MOD-01", "objectives": ["ILO-01"], "minutes": 60},
               {"id": "MOD-02", "objectives": ["ILO-02"], "minutes": 60}]
    sets = [_set("SET-01", "diagnostic", ["ILO-01"]),
                   _set("SET-02", "formative", ["ILO-01"]),
                   _set("SET-03", "summative", ["ILO-02"], module="MOD-02")]
    targets = {"ILO-01": ["diagnostic", "formative"], "ILO-02": ["summative"]}
    plan = {"sets": [
        {"set_id": "SET-01", "module_id": "MOD-01", "set_ids": ["SET-01", "SET-02"],
         "expected_items": 4},
        {"set_id": "SET-02", "module_id": "MOD-02", "set_ids": ["SET-03", "SET-09"],
         "expected_items": 2}]}
    sets, stats = dev_plans.normalize_assessment_dev_plan(
        plan, ["ILO-01", "ILO-02"], targets, modules=modules, blueprint=sets,
        mode="sample")
    assert [(ws.module_id, ws.pairs, ws.source) for ws in sets] == [
        ("MOD-01", (("ILO-01", "diagnostic"), ("ILO-01", "formative")), "llm"),
        ("MOD-02", (("ILO-02", "summative"),), "llm")]
    assert [i["id"] for i in sets[0].payload["sets"]] == ["SET-01", "SET-02"]
    assert stats["fallback_used"] is False and stats["dropped_lo_refs"] == 1, "SET-09 is not real"


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
    """MEASURED (run b8576814): three sets, all for one module and one
    objective. Said on the PLAN, it reaches the Designer before any Developer
    runs; P14 and C2 only say it afterwards."""
    plan = {"sets": [_set("SET-01", "summative", ["ILO-01"])],
            "lo_coverage_targets": {"ILO-01": ["summative"]}}
    graph = _design(plan, [])
    graph.add_element_node(NodeType.MODULE, "MOD-02", {"id": "MOD-02"})
    found = {(v.metadata["kind"], v.metadata.get("module_id") or v.metadata.get("lo_id"))
             for v in checks.blueprint_consistency(graph)}
    assert found == {("module_without_set", "MOD-02"),
                     ("objective_without_set", "ILO-02")}
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
    missing `set_id` on sets that each listed a single set."""
    one = dev_plans.WorkSet(set_id="AS-01", payload={
        "sets": [_set("SET-01", "summative", ["ILO-01"])]})
    items = [{"question": "q", "aligned_objective": "ILO-01", "plan_category": "summative"},
             {"question": "r", "set_id": "SET-77"}]
    filled = dev_plans.with_membership(one, "assessment_tools", items)
    assert [i["set_id"] for i in filled] == ["SET-01", "SET-77"], "only a MISSING id"
    assert "set_id" not in items[0], "the submitted arguments are not rewritten"

    two = dev_plans.WorkSet(set_id="AS-02", payload={"sets": [
        _set("SET-01", "formative", ["ILO-01"]), _set("SET-02", "summative", ["ILO-01"]),
        _set("SET-03", "summative", ["ILO-01"])]})
    formative, summative = dev_plans.with_membership(two, "assessment_tools", [
        {"aligned_objective": "ILO-01", "plan_category": "formative"},
        {"aligned_objective": "ILO-01", "plan_category": "summative"}])
    assert formative["set_id"] == "SET-01", "one set of its objective and category"
    assert "set_id" not in summative, "two candidates is the writer's to say"

    block = dev_plans.WorkSet(set_id="AB-01", payload={"module": {"id": "MOD-02"}})
    assert dev_plans.with_membership(block, "learning_activities", [{"activity_name": "a"}]) == [
        {"activity_name": "a", "module_id": "MOD-02"}]


# ── what the last open findings of a clean run were ─────────────────────────

def test_a_criterion_is_scorable_by_its_levels_not_by_the_words_of_its_title():
    """MEASURED (run 53a9cd1a): "Clear definition and naming of all three
    phases" was flagged for the word "clear" while its levels said precisely
    what each grade looks like."""
    levels = {"excellent": "Clearly names and defines all three phases with precise terminology.",
              "satisfactory": "Lists three phases but lacks precise definitions.",
              "needs_improvement": "Lists fewer than three phases."}
    vague = {"id": "SC-01", "description": "Clear definition and naming of all three phases"}
    assert checks.rubric_consistency_items([("AT-01/SC-01", {**vague, "levels": levels})]) == []
    assert checks.rubric_consistency_items([("AT-01/SC-01", {**vague, "levels": {}})])
    assert checks.rubric_consistency_items(
        [("AT-01/SC-01", {**vague, "levels": {"excellent": "good", "satisfactory": "ok"}})]), (
        "a level that describes nothing redeems nothing")
    assert checks.rubric_consistency_items([("AT-01/X", {"id": "X", "levels": levels})]), (
        "levels do not excuse a criterion that names nothing")


def test_a_criterion_with_no_levels_is_refused_while_its_author_can_still_write_them():
    from alignmentgraph_isd.core.agentic import fanout

    item = {"set_id": "SET-01", "rubric": [
        {"id": "C1", "description": "Selects the right tool", "levels": {}}]}
    (error,) = fanout.assessment_item_errors([item])
    assert error.startswith("assessment_tools[0].rubric[0].levels")
    item["rubric"][0]["levels"] = {
        "excellent": "Selects the tool and justifies it against both constraints.",
        "satisfactory": "Selects the tool with a partial justification.",
        "needs_improvement": "Selects a tool that cannot meet the task."}
    assert fanout.assessment_item_errors([item]) == []
    # Shared by both arms: the single agent's batch goes through the same rules.
    assert fanout.output_errors(fanout.SPECS["assessment"], {"assessment_tools": [
        {"set_id": "SET-01", "rubric": [{"id": "C1", "description": "x"}]}]})


def test_a_module_no_media_selection_serves_reaches_the_content_designer_before_its_developers():
    """MEASURED (runs b8576814, 53a9cd1a): every media selection named
    `for_modules: ["MOD-01"]`; MOD-02's Developer was handed no medium, picked
    one, and that material was the run's P6 violation both times."""
    from alignmentgraph_isd.core.agentic import repair_turn

    graph = AlignmentGraph()
    for module in ("MOD-01", "MOD-02"):
        graph.add_element_node(NodeType.MODULE, module, {"id": module})
    assert checks.media_coverage(graph) == [], "no media yet is the stage not having run"
    graph.add_element_node(NodeType.MEDIA_SELECTION, "MED-01", {
        "id": "MED-01", "media_type": "slides", "for_modules": ["module:MOD-01"]})
    found = checks.media_coverage(graph)
    assert [(v.violation_type, v.node_id) for v in found] == [("media_coverage", "module:MOD-02")]
    assert "for_modules includes MOD-02" in found[0].repair_hint

    own = repair_turn.collect_own(graph, load_brief("minimal_brief.json"), STEP["content"])
    assert "media_coverage" in {v.violation_type for v in own}, (
        "anchored on an element, but about what the Designer wrote — not withheld")
    assert repairs.OWNER_BY_VIOLATION["media_coverage"] == "content_designer"
    assert "media_coverage" in repairs.REPORT_ONLY

    graph.add_element_node(NodeType.MEDIA_SELECTION, "MED-02", {"id": "MED-02", "media_type": "video"})
    assert checks.media_coverage(graph) == [], "a selection naming no module serves them all"


def test_the_fanout_divides_the_sets_and_never_the_promise():
    """A promised pair no set covers gets no work set.

    It would be a set with no set in it, and ``render_assessment_set``
    drops the whole "set each item's set_id to one of these ids" block
    for such a set — so its Developer is shown no set and reaches for
    the set's own header id. ``unassessed_pair`` is what reports the pair,
    while the Designer can still add the set.
    """
    modules = [{"id": "MOD-01", "title": "M", "minutes": 60, "objectives": ["ILO-01"]}]
    plan = {"sets": [_set("SET-01", "summative", ["ILO-01"])],
            "lo_coverage_targets": {"ILO-01": ["summative", "diagnostic"]}}
    sets, stats = dev_plans.normalize_assessment_dev_plan(
        None, ["ILO-01"], plan["lo_coverage_targets"], modules=modules,
        blueprint=plan["sets"], mode="sample")

    assert [list(ws.pairs) for ws in sets] == [[("ILO-01", "summative")]], (
        "the diagnostic promise is the check's to report, not work to hand out"
    )
    assert all(ws.payload.get("sets") for ws in sets), (
        "a set-less set shows its Developer no set_id to write"
    )
    assert [v.metadata["kind"] for v in checks.blueprint_consistency_data(
        "assessment_plan", plan, modules={"MOD-01"}, objectives={"ILO-01"})
    ] == ["unassessed_pair"], "and it IS reported, on the plan, to its author"


def test_a_plan_with_no_sets_still_divides_by_the_promise():
    """The fallback for an archived design from before the blueprint, and for
    one whose ``sets`` never landed: without them there is nothing else
    to divide."""
    sets, _stats = dev_plans.normalize_assessment_dev_plan(
        None, ["ILO-01"], {"ILO-01": ["summative", "diagnostic"]},
        modules=None, blueprint=[], mode="sample")
    assert sorted(p for ws in sets for p in ws.pairs) == [
        ("ILO-01", "diagnostic"), ("ILO-01", "summative")]
