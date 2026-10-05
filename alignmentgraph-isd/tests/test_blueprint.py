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

from conftest import add_assessment, load_brief

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
    assert dev_plans.module_ceiling(5, 4, 12) == 3, "within a week"
    assert dev_plans.module_ceiling(5, 5, 24) == 4, "up to a month"
    assert dev_plans.module_ceiling(6, 9, 48) == dev_plans.MAX_MODULES
    assert dev_plans.module_ceiling(2, 7, 48) == 2, "never more modules than objectives"
    assert dev_plans.module_ceiling(6, 1, 48) == 1, "nor than topics"
    assert dev_plans.module_ceiling(5, 5, 0) == dev_plans.MODULES_UNKNOWN_LENGTH
    assert dev_plans.module_ceiling(0, 0, 12) == 3, "a count not written yet does not bind"


def test_a_course_length_is_a_ceiling_on_its_hours_not_a_timetable():
    """The briefs state a length band, never hours. Read as calendar time at a
    full timetable, "1-6 months" came to 720 h and each module was written to
    14,400 minutes (tune-10, 2026-09-23). The band is a ceiling by length, a
    stated number of hours wins, and modules written past the ceiling are
    scaled to it while the Outcome Designer's numbers stay on them."""
    from alignmentgraph_isd.core import checks
    from alignmentgraph_isd.core.brief import DesignBrief

    def brief(duration: str) -> DesignBrief:
        return DesignBrief.model_validate({
            "id": "B", "title": "t", "learning_goals": ["g"],
            "context": {"duration": duration}})

    assert checks.duration_hours(brief("Short-term intensive (within 1 week)")) == 12
    assert checks.duration_hours(brief("Mid-term course (2-4 weeks)")) == 24
    assert checks.duration_hours(brief("Long-term course (1-6 months)")) == 48
    assert checks.duration_hours(brief("3 days (18 hours)")) == 18, "stated hours win"
    assert checks.duration_hours(brief("")) == 0.0

    modules = [{"id": "MOD-01", "minutes": 14400}, {"id": "MOD-02", "minutes": 14400},
               {"id": "MOD-03", "minutes": 7200}]
    capped = dev_plans.effective_minutes(modules, 48 * 60)
    assert sum(capped.values()) in (2880, 2881) and capped["MOD-01"] == capped["MOD-02"]
    assert capped["MOD-03"] * 2 in (capped["MOD-01"], capped["MOD-01"] + 1, capped["MOD-01"] - 1)
    assert dev_plans.effective_minutes([{"id": "MOD-01", "minutes": 600}], 48 * 60) == {}, (
        "the model's own number is kept when it fits")
    assert dev_plans.module_minutes({"minutes": 14400, "minutes_effective": 1440}) == 1440
    assert dev_plans.module_minutes({"minutes": 600}) == 600


def test_the_outcome_designer_is_told_this_course_s_ceiling_and_it_is_never_enforced():
    """The RULE is in the pinned prompt; the NUMBER depends on the course, so
    it arrives through the state read — and only until the modules exist."""
    graph, trajectory = AlignmentGraph(), TrajectoryLogger()
    brief = load_brief("minimal_brief.json")     # "2 days": within a week
    for topic in ("TOP-01", "TOP-02"):
        graph.add_element_node(NodeType.TOPIC, topic, {"id": topic})
    text = alignment_state.read(graph, brief, STEP["outcomes"]).text
    assert "course_modules: at most 2 for this course" in text

    many = [{"id": f"MOD-0{n}", "title": f"Module {n}", "objectives": ["ILO-01"],
             "covers_topics": ["TOP-01"], "minutes": 30}
            for n in range(1, 6)]
    assert specialists.validate_outcomes({"course_modules": many}) == []
    specialists.commit_outcomes(graph, trajectory, {"course_modules": many})
    assert "course_modules: at most" not in alignment_state.read(graph, brief, STEP["outcomes"]).text


def test_a_module_must_name_its_objectives_its_topics_and_its_time():
    """Each of the three is load-bearing, so each is asked of the author while
    it is still in the conversation. `objectives` and `minutes` are what every
    later family divides and sizes its work by. `covers_topics` is what ties
    the module back to the instructional analysis, and it is the whole source
    of P7 -- declared optional it left that relation unable to fire for a
    module the model simply did not fill it in for."""
    errors = specialists.validate_outcomes({"course_modules": [
        {"id": "MOD-01", "title": "M", "objectives": [], "covers_topics": [],
         "minutes": 0}]})
    assert errors == ["course_modules[0].objectives must list at least one objective id",
                      "course_modules[0].covers_topics must list at least one topic id",
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

def test_the_coverage_targets_are_derived_from_the_tasks_at_the_commit():
    """The plan used to say when each objective is assessed twice, per task
    and per objective, and the model kept the two apart: MEASURED (run t1
    20261002_134550), about twelve pairs promised against five and a half the
    tasks assess, in both multi arms. The harness now writes
    ``lo_coverage_targets`` from the tasks, on both substrates, and a value the
    model wrote anyway is not kept beside them."""
    submitted = {"assessment_plan": {
        "sets": [{"module_id": "MOD-01", "assessment_tasks": [
            _set("AT-01", "formative", ["ILO-01", "objective:ILO-02"]),
            _set("AT-02", "summative", ["ILO-01"])]}],
        "lo_coverage_targets": {"ILO-01": ["diagnostic"], "ILO-09": ["summative"]}}}
    graph, store, trajectory = AlignmentGraph(), ProseStore(), TrajectoryLogger()
    specialists.commit_assessment(graph, trajectory, submitted)
    specialists.commit_assessment_prose(store, trajectory, submitted)
    expected = {"ILO-01": ["formative", "summative"], "ILO-02": ["formative"]}
    assert graph.get_node("assessment_plan_0")["data"]["lo_coverage_targets"] == expected
    assert store.get("assessment_plan")["lo_coverage_targets"] == expected


def test_a_plan_whose_targets_disagree_with_its_tasks_reports_no_pair():
    """An archived plan carries the model's own targets; the blueprint check no
    longer compares them with the tasks, since a run never holds two."""
    plan = {"sets": [_set("SET-01", "summative", ["ILO-01", "ILO-02"])],
            "lo_coverage_targets": {"ILO-01": ["summative", "diagnostic"]}}
    graph = _design(plan, [])
    assert checks.blueprint_consistency(graph) == []


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


def test_the_prose_arm_checks_what_reads_the_plan_alone():
    plan = {"sets": [_set("SET-01", "formative", ["ILO-01"], module="MOD-05")],
            "lo_coverage_targets": {"ILO-01": ["summative"]}}
    found = checks.blueprint_consistency_data("assessment_plan", plan)
    assert [v.metadata["kind"] for v in found] == ["no_summative_task"]


def test_a_blueprint_with_no_summative_task_is_handed_back():
    """The rule the plan is written under — a course that never grades what it
    taught has no evidence that it worked — and the summative half of the
    evaluation is built from summative tasks, so without one it reads
    ABSENT. Reported on the plan while it is still the only thing written;
    which task becomes summative is the Designer's."""
    formative_only = {"sets": [_set("SET-01", "formative", ["ILO-01"]),
                               _set("SET-02", "diagnostic", ["ILO-01"])],
                      "lo_coverage_targets": {"ILO-01": ["formative", "diagnostic"]}}
    kinds = [v.metadata["kind"] for v in checks.blueprint_consistency_data(
        "assessment_plan", formative_only)]
    assert kinds.count("no_summative_task") == 1
    with_summative = {"sets": [_set("SET-01", "summative", ["ILO-01"])],
                      "lo_coverage_targets": {"ILO-01": ["summative"]}}
    assert "no_summative_task" not in [v.metadata["kind"] for v in
                                       checks.blueprint_consistency_data("assessment_plan", with_summative)]
    thin = {"sets": [dict(_set("SET-01", "summative", ["ILO-01"]),
                          assessment_tasks=[{"id": "AT-01", "timing": "summative",
                                             "covers_objectives": ["ILO-01"],
                                             "item_counts": {"performance_task": 1}}])],
            "lo_coverage_targets": {"ILO-01": ["summative"]}}
    found = [v for v in checks.blueprint_consistency_data("assessment_plan", thin)
             if v.metadata.get("kind") == "thin_summative_task"]
    assert len(found) == 1 and found[0].metadata["item_total"] == 1
    assert not checks.blueprint_consistency_data("assessment_plan", {"sets": []}), (
        "an empty blueprint reports nothing, as every other kind does")
    violation = checks.Violation(
        node_id="assessment_plan_0", edge_type="", violation_type="blueprint_consistency",
        message="none summative", metadata={"kind": "no_summative_task"})
    ctx = repairs.RepairContext(graph=AlignmentGraph(), store=None,
                                trajectory=TrajectoryLogger(), actor=ORCHESTRATOR)
    assert repairs.repair("assessment_designer", [violation], ctx) == [violation]


# ── every item belongs to a set ─────────────────────────────────────

def _item(item_id: str, lo: str, category: str, set_id: str) -> dict:
    return {"item_id": item_id, "aligned_objective": lo, "plan_category": category,
            "task_id": set_id}


def test_the_blueprint_check_is_owned_and_handed_back():
    """No lookup half is left: what it reports is the Designer's to settle."""
    for kind in ("blueprint_consistency",):
        assert repairs.OWNER_BY_VIOLATION[kind] == "assessment_designer"
        assert kind not in repairs.STRUCTURAL and kind not in repairs.REPORT_ONLY
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

    sets, _stats = fanout.SPECS["assessment"].plan_sets(graph, payload, "light")
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
    sets, stats = dev_plans.assessment_work_sets(
        plan, ["ILO-01", "ILO-02"], targets, modules=modules, blueprint=sets,
        mode="light")
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

    errors = specialists.validate_analysis({"task_analysis": {"task_overview": "x"}})
    assert "task_analysis.topics must be a non-empty list" in errors
    assert "task_analysis.entry_behaviors: required field is missing or empty" in errors


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
             {"question": "r", "task_id": "SET-77"}]
    filled = dev_plans.with_membership(one, "assessment_tools", items)
    assert [i["task_id"] for i in filled] == ["SET-01", "SET-77"], "only a MISSING id"
    assert "task_id" not in items[0], "the submitted arguments are not rewritten"

    two = dev_plans.WorkSet(set_id="AS-02", payload={"sets": [
        _set("SET-01", "formative", ["ILO-01"]), _set("SET-02", "summative", ["ILO-01"]),
        _set("SET-03", "summative", ["ILO-01"])]})
    formative, summative = dev_plans.with_membership(two, "assessment_tools", [
        {"aligned_objective": "ILO-01", "plan_category": "formative"},
        {"aligned_objective": "ILO-01", "plan_category": "summative"}])
    assert formative["task_id"] == "SET-01", "one set of its objective and category"
    assert "task_id" not in summative, "two candidates is the writer's to say"

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

    item = {"task_id": "SET-01", "rubric": [
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
        {"task_id": "SET-01", "rubric": [{"id": "C1", "description": "x"}]}]})


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
    the set's own header id. Only an archived plan can carry such a promise:
    a run's targets are derived from the tasks.
    """
    modules = [{"id": "MOD-01", "title": "M", "minutes": 60, "objectives": ["ILO-01"]}]
    plan = {"sets": [_set("SET-01", "summative", ["ILO-01"])],
            "lo_coverage_targets": {"ILO-01": ["summative", "diagnostic"]}}
    sets, stats = dev_plans.assessment_work_sets(
        None, ["ILO-01"], plan["lo_coverage_targets"], modules=modules,
        blueprint=plan["sets"], mode="light")

    assert [list(ws.pairs) for ws in sets] == [[("ILO-01", "summative")]], (
        "the diagnostic promise is the check's to report, not work to hand out"
    )
    assert all(ws.payload.get("sets") for ws in sets), (
        "a set-less set shows its Developer no set_id to write"
    )


def test_a_plan_with_no_sets_still_divides_by_the_promise():
    """The fallback for an archived design from before the blueprint, and for
    one whose ``sets`` never landed: without them there is nothing else
    to divide."""
    sets, _stats = dev_plans.assessment_work_sets(
        None, ["ILO-01"], {"ILO-01": ["summative", "diagnostic"]},
        modules=None, blueprint=[], mode="light")
    assert sorted(p for ws in sets for p in ws.pairs) == [
        ("ILO-01", "diagnostic"), ("ILO-01", "summative")]


def test_an_item_cannot_be_filed_under_the_wrong_task():
    """It is not an id the model writes any more. An item lives INSIDE the
    task it belongs to (``fanout._attach_to_parent``) and is stamped with
    that task's own `timing`, so the membership and the plan category it
    implies are structural. The check that policed both went with them: on
    run 50932ed8 it was every one of the seven residual violations."""
    from alignmentgraph_isd.core import checks as checks_mod

    assert not hasattr(checks_mod, "set_alignment")
    assert "set_alignment" not in repairs.OWNER_BY_VIOLATION


def test_a_self_named_nested_task_list_is_unwrapped_at_the_transport():
    """``"assessment_tasks": {"assessment_tasks": [...]}`` means the list.

    Run d7722e8e: the model named the nested list twice, ``plan_tasks`` found
    no list on the set, read the SET ITSELF as the task, and every activity in
    the design prepared for ``SET-01`` rather than for one of the three tasks
    under it."""
    from alignmentgraph_isd.core.agentic import tools

    params = {"type": "object",
              "properties": {"assessment_plan": tools.ARTIFACT_SCHEMAS["assessment_plan"]}}
    tasks = [{"id": "AT-01", "timing": "diagnostic", "covers_objectives": ["ILO-01"]},
             {"id": "AT-02", "timing": "summative", "covers_objectives": ["ILO-01"]}]
    reshaped: list = []
    out = tools.reshape_args(
        params,
        {"assessment_plan": {"sets": [{"id": "SET-01", "module_id": "MOD-01",
                                       "assessment_tasks": {"assessment_tasks": tasks}}]}},
        reshaped=reshaped)

    assert [t["id"] for t in dev_plans.plan_tasks(out["assessment_plan"])] == ["AT-01", "AT-02"]
    assert reshaped == ["assessment_plan.sets[0].assessment_tasks"]


def test_a_self_named_wrapper_with_a_sibling_is_left_for_the_validator():
    """A list has nowhere to keep a sibling, so the unwrap declines rather
    than dropping what it cannot carry."""
    from alignmentgraph_isd.core.agentic import tools

    params = {"type": "object",
              "properties": {"assessment_plan": tools.ARTIFACT_SCHEMAS["assessment_plan"]}}
    wrapped = {"assessment_tasks": [{"id": "AT-01"}], "note": "kept"}
    reshaped: list = []
    out = tools.reshape_args(
        params, {"assessment_plan": {"sets": [{"id": "SET-01", "assessment_tasks": wrapped}]}},
        reshaped=reshaped)

    assert out["assessment_plan"]["sets"][0]["assessment_tasks"] == wrapped
    assert reshaped == []


def test_the_blueprint_has_a_ceiling_on_how_many_tasks_it_carries():
    """Every other family had one and this one did not.

    `sets` is one per module and says nothing about how many tasks a set
    lists, while the fan-out gives one work set per task — so the task count is
    what the Developer tier is sized off. MEASURED (run 69d754e4): 15 tasks
    against 4 modules, three of them for a module that did not exist; those
    reached no work set, nobody wrote their items, and C2 closed at 0.80.

    TOLD, never enforced, like `MAX_OBJECTIVES`: the check hands it back while
    the plan is still the only thing written, and nothing trims the blueprint.
    """
    short = [{"id": f"MOD-0{i}", "minutes": 90} for i in range(1, 5)]
    long = [{"id": f"MOD-0{i}", "minutes": 240} for i in range(1, 5)]
    assert dev_plans.task_ceiling(short) == 4 + 1, "one summative each, one diagnostic"
    assert dev_plans.task_ceiling(long) == 4 + 4 + 1, "a long module may add a formative"
    assert dev_plans.task_ceiling([{"id": "MOD-01"}]) == 2, "unstated minutes: no formative"
    # Bounded by the work-set cap too: a task past it reaches no Developer.
    assert dev_plans.task_ceiling(long * 3) == dev_plans.MAX_SETS_HARD_CAP
    # No modules yet is "not written", not "zero allowed".
    assert dev_plans.task_ceiling([]) == dev_plans.MAX_SETS_HARD_CAP
    assert dev_plans.long_modules(short + long[:1]) == ["MOD-01"]

    def tasks(n: int) -> dict:
        timings = ("diagnostic", "formative", "summative")
        return {"sets": [{"module_id": "MOD-01", "assessment_tasks": [
            {"id": f"AT-{i:02d}", "timing": timings[i % 3], "covers_objectives": ["ILO-01"]}
            for i in range(n)]}]}

    def over(n: int, minutes: int) -> list:
        return [v for v in checks.blueprint_consistency_data(
            "assessment_plan_0", tasks(n), modules={"MOD-01"}, objectives={"ILO-01"},
            module_data=[{"id": "MOD-01", "minutes": minutes}])
            if v.metadata.get("kind") == "too_many_tasks"]

    assert not over(2, 90), "a diagnostic and a summative fit a short module"
    assert not over(3, 240), "a long module may carry all three timings"
    short_three = over(3, 90)
    assert len(short_three) == 1 and short_three[0].metadata["ceiling"] == 2
    # The hint names WHAT is beyond the default, not just that something is.
    assert "MOD-01/formative" in short_three[0].repair_hint
    crowded = over(5, 240)
    assert crowded[0].metadata["task_count"] == 5 and crowded[0].metadata["ceiling"] == 3
    assert "MOD-01/diagnostic" in crowded[0].repair_hint
    assert "2 diagnostic tasks" in crowded[0].repair_hint
    # Without module documents, ids alone are judged as modules of unstated length.
    assert [v.metadata["ceiling"] for v in checks.blueprint_consistency_data(
        "assessment_plan_0", tasks(4), modules={"MOD-01"}, objectives={"ILO-01"})
        if v.metadata.get("kind") == "too_many_tasks"] == [2]


def test_the_ceiling_finding_is_handed_back_rather_than_repaired():
    """Which task to drop is a design judgment: it is returned so it reaches
    the Designer as an open issue."""
    assert "blueprint_consistency" in repairs.OWNED_BY_FAMILY["assessment_designer"]
    violation = checks.Violation(
        node_id="assessment_plan_0", edge_type="",
        violation_type="blueprint_consistency", message="too many",
        metadata={"kind": "too_many_tasks"})
    ctx = repairs.RepairContext(graph=AlignmentGraph(), store=None,
                                trajectory=TrajectoryLogger(), actor=ORCHESTRATOR)
    assert repairs.repair("assessment_designer", [violation], ctx) == [violation]


# ── one id per task ─────────────────────────────────────────────────────────

def test_a_repeated_task_id_is_renamed_at_the_commit_on_both_substrates():
    """MEASURED (2B run, 2026-09-24): six tasks all `AT-01`, and 53 items in
    one task. Settled at the commit — the first keeps its id, each repeat gets
    the next free one — and recorded; the grammar cannot refuse a repeat."""
    plan = {"assessment_plan": {
        "sets": [{"module_id": "MOD-01", "assessment_tasks": [
                      _set("AT-01", "diagnostic", ["ILO-01"]),
                      _set("AT-01", "summative", ["ILO-01"])]},
                 {"module_id": "MOD-02", "assessment_tasks": [
                      _set("AT-01", "summative", ["ILO-02"], module="MOD-02"),
                      _set("AT-03", "formative", ["ILO-02"], module="MOD-02")]}],
        "lo_coverage_targets": {"ILO-01": ["diagnostic", "summative"],
                                "ILO-02": ["summative", "formative"]}}}
    renamed, pairs = dev_plans.dedupe_task_ids(plan["assessment_plan"])
    assert pairs == [("AT-01", "AT-02"), ("AT-01", "AT-04")]
    assert [t["id"] for t in dev_plans.plan_tasks(renamed)] == ["AT-01", "AT-02", "AT-04", "AT-03"]
    assert dev_plans.dedupe_task_ids(renamed) == (renamed, []), "distinct ids are left alone"

    graph, store, trajectory = AlignmentGraph(), ProseStore(), TrajectoryLogger()
    specialists.commit_assessment(graph, trajectory, plan)
    specialists.commit_assessment_prose(store, trajectory, plan)
    in_graph = sorted(n["data"]["id"] for n in graph.element_nodes(NodeType.ASSESSMENT))
    in_prose = sorted(t["id"] for t in dev_plans.plan_tasks(store.get("assessment_plan")))
    assert in_graph == in_prose == ["AT-01", "AT-02", "AT-03", "AT-04"]
    events = [e for e in trajectory.recovery_events if e["action"] == "duplicate_task_id_renamed"]
    assert len(events) == 2 and "AT-01 -> AT-02" in events[0]["context"]["input_summary"]

    # A plan that reached the check without the commit says what it would do.
    found = checks.blueprint_consistency_data("assessment_plan_0", plan["assessment_plan"])
    dup = [v for v in found if v.metadata.get("kind") == "duplicate_task_id"]
    assert [v.metadata["count"] for v in dup] == [3]
    assert not [v for v in checks.blueprint_consistency_data("assessment_plan_0", renamed)
                if v.metadata.get("kind") == "duplicate_task_id"]


def test_a_plan_without_coverage_targets_is_accepted_at_the_submit():
    """The model is never asked for ``lo_coverage_targets``; the commit writes
    it. MEASURED (run t1 20261005_205508): the submit still demanded it, every
    plan was refused, and the assessment stage was cut at its turn ceiling in
    10 of 10 runs on both multi arms."""
    from test_agentic_loop import _ASSESSMENT

    plan = {k: v for k, v in _ASSESSMENT["assessment_plan"].items()
            if k != "lo_coverage_targets"}
    assert specialists.validate_assessment({"assessment_plan": plan}) == []
    step = STEP["assessment"]
    assert step.validate({"assessment_plan": plan}) == []
