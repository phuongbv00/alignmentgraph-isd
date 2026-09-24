"""``development_mode``: how much of the planned scale the Developers write.

The PLAN always states the course at full scale. ``"light"`` (the default)
writes a typical, reviewable slice of it — one item per (objective x timing)
pair at the objective's own level, one activity per objective at its level,
two outlined materials per module — and ``"full"`` writes all of it. The mode
changes NUMBERS and a derived assignment in a work set plus one note in its
assignment — never a ``RULES_*`` block, never the ground truth a check
measures — and it is not an ablation axis: a run records it and every arm of
one experiment shares it.
"""
from __future__ import annotations

import pytest

from alignmentgraph_isd import HarnessRunConfig
from alignmentgraph_isd.core import dev_plans, rulebook
from alignmentgraph_isd.core.agentic import react

from conftest import FakeChatModel, load_brief, run_brief

MODULES = [{"id": "MOD-01", "title": "Basics", "objectives": ["ILO-01", "ILO-02"], "minutes": 600},
           {"id": "MOD-02", "title": "Practice", "objectives": ["ILO-03"], "minutes": 120}]
SETS = [
    {"id": "SET-01", "module_id": "MOD-01", "timing": "formative", "format": "quiz",
     "item_counts": {"multiple_choice": 40, "short_answer": 5},
     "covers_objectives": ["ILO-01", "ILO-02"]},
    {"id": "SET-02", "module_id": "MOD-02", "timing": "summative", "format": "practical",
     "item_counts": {"performance_task": 2}, "covers_objectives": ["ILO-03"]}]
TARGETS = {"ILO-01": ["formative"], "ILO-02": ["formative"], "ILO-03": ["summative"]}
LOS = ["ILO-01", "ILO-02", "ILO-03"]
LEVELS = {"ILO-01": "apply", "ILO-02": "understand", "ILO-03": "create"}


def _assessment(mode, levels=LEVELS):
    return dev_plans.assessment_work_sets(
        None, LOS, TARGETS, modules=MODULES, blueprint=SETS, mode=mode, levels=levels)[0]


def test_the_default_is_light_and_a_run_records_it():
    assert HarnessRunConfig().development_mode == "light"
    with pytest.raises(ValueError):
        HarnessRunConfig(development_mode="sample")
    config = HarnessRunConfig(development_mode="full")
    config.llm_factory = FakeChatModel
    result = run_brief(load_brief("minimal_brief.json"), config)
    assert result["metadata"]["run_config"]["development_mode"] == "full"


def test_a_light_set_assigns_one_item_per_pair_at_the_objectives_level():
    sets = _assessment("light")
    quiz, practical = sets
    assert [(ws.module_id, ws.payload["expected_items"]) for ws in sets] == [
        ("MOD-01", dev_plans.LIGHT_ITEMS_PER_TASK), ("MOD-02", dev_plans.LIGHT_ITEMS_PER_TASK)], (
        "a 45-item quiz gets its typical three; a summative practical planned at two is "
        "written at the floor the plan is told")
    assert {pair for ws in sets for pair in ws.pairs} == set(dev_plans.plan_category_pairs(TARGETS))

    rows = quiz.payload["assigned_items"]
    by_pair = {(r["objective"], r["plan_category"]): r for r in rows[:2]}
    # Apply needs an open-response type the task names; understand takes the
    # task's most numerous type. Every row fixes the objective's own level.
    assert by_pair[("ILO-01", "formative")] == {
        "objective": "ILO-01", "plan_category": "formative", "task_id": "SET-01",
        "type": "short_answer", "level": "apply"}
    assert by_pair[("ILO-02", "formative")]["type"] == "multiple_choice"
    assert by_pair[("ILO-02", "formative")]["level"] == "understand"
    assert rows[2]["objective"] == "ILO-01", "the filler cycles the pairs"
    assert [r["type"] for r in practical.payload["assigned_items"]] == ["performance_task"] * 3

    text = dev_plans.render_assessment_set(quiz)
    assert ("item 1: ILO-01 x formative — task SET-01 · short_answer · "
            "required_cognitive_process apply") in text
    assert "write exactly 3 items, one per line" in text
    assert "full scale: 40 multiple_choice, 5 short_answer" in text, "the plan's scale is still stated"
    assert text.endswith(dev_plans.development_note("light", "assessment"))


def test_an_apply_objective_in_a_multiple_choice_task_gets_short_answer_added():
    only_mc = [dict(SETS[0], item_counts={"multiple_choice": 20})]
    quiz = dev_plans.assessment_work_sets(
        None, LOS[:2], {k: TARGETS[k] for k in LOS[:2]}, modules=MODULES[:1],
        blueprint=only_mc, mode="light", levels=LEVELS)[0][0]
    rows = quiz.payload["assigned_items"]
    apply_row = next(r for r in rows if r["objective"] == "ILO-01")
    assert apply_row["type"] == "short_answer" and apply_row["blueprint_type_added"] is True
    assert "short_answer is not in SET-01's item_counts" in dev_plans.render_assessment_set(quiz)
    unknown = dev_plans.light_item_assignment(only_mc[0], [("ILO-01", "formative")], {})
    assert unknown[0]["level"] == "" and unknown[0]["type"] == "multiple_choice", (
        "an objective with no readable level is assigned none, not a guess")


def test_full_writes_the_whole_set_in_batches_that_divide_it():
    sets = _assessment("full")
    quiz = [ws for ws in sets if ws.module_id == "MOD-01"]
    limit = dev_plans.max_units("assessment")
    assert len(quiz) == -(-45 // limit)
    assert sum(ws.payload["expected_items"] for ws in quiz) == 45, "divided, never repeated"
    assert all(ws.payload["expected_items"] <= limit for ws in quiz)
    assert [ws.payload["batch"][0] for ws in quiz] == list(range(1, len(quiz) + 1))
    assert all(set(ws.pairs) == {("ILO-01", "formative"), ("ILO-02", "formative")} for ws in quiz)
    assert all("assigned_items" not in ws.payload for ws in quiz), "full leaves the items to the writer"
    assert "part 2 of" in dev_plans.render_assessment_set(quiz[1])
    assert "LIGHT DEVELOPMENT" not in dev_plans.render_assessment_set(quiz[0])
    assert len({ws.set_id for ws in sets}) == len(sets) == len({ws.ordinal for ws in sets})


def test_a_light_module_gets_one_activity_per_objective_with_a_three_floor():
    plan = {"activity_blocks": [
        {"set_id": "B1", "objectives": ["ILO-01", "ILO-02"], "block_theme": "t",
         "block_minutes": 600, "expected_activities": 11},
        {"set_id": "B2", "objectives": ["ILO-03"], "block_theme": "u",
         "block_minutes": 120, "expected_activities": 1}]}
    light, _ = dev_plans.activity_work_sets(plan, LOS, modules=MODULES, mode="light", levels=LEVELS)
    full, _ = dev_plans.activity_work_sets(plan, LOS, modules=MODULES, mode="full", levels=LEVELS)

    by_module = {ws.module_id: ws.payload["expected_activities"] for ws in light}
    assert by_module == {"MOD-01": dev_plans.LIGHT_ACTIVITIES_PER_MODULE_FLOOR,
                         "MOD-02": dev_plans.LIGHT_ACTIVITIES_PER_MODULE_FLOOR}
    first = next(ws for ws in light if ws.module_id == "MOD-01")
    rows = first.payload["assigned_activities"]
    assert [(r["objective"], r["level"], r["stage"]) for r in rows] == [
        ("ILO-01", "apply", "introduce"), ("ILO-02", "understand", "practise"),
        ("ILO-01", "apply", "apply independently")]
    text = dev_plans.render_activity_set(first)
    assert "activity 1: ILO-01 · learner_cognitive_process apply · introduce" in text
    assert sum(ws.payload["expected_activities"] for ws in full
               if ws.module_id == "MOD-01") >= 10, "full keeps the planner's own scale"
    assert all("assigned_activities" not in ws.payload for ws in full)
    assert {lo for ws in light for lo in ws.objectives} == set(LOS), "every objective keeps a block"

    tight = [dict(MODULES[0], minutes=30), MODULES[1]]
    squeezed, _ = dev_plans.activity_work_sets(plan, LOS, modules=tight, mode="light", levels=LEVELS)
    assert squeezed[0].payload["expected_activities"] == 30 // dev_plans.MIN_ACTIVITY_MINUTES
    assert len(squeezed[0].payload["assigned_activities"]) == 30 // dev_plans.MIN_ACTIVITY_MINUTES


def test_light_materials_are_the_typical_two_and_expected_is_capped():
    media = [{"id": "MED-01", "media_type": "slides", "for_modules": ["MOD-01"]},
             {"id": "MED-02", "media_type": "slides", "for_modules": ["MOD-01"]},
             {"id": "MED-03", "media_type": "video", "for_modules": ["MOD-01"]},
             {"id": "MED-04", "media_type": "slides", "for_modules": ["MOD-01"]}]
    broad = [dict(MODULES[0], expected_materials=5), MODULES[1]]
    light = dev_plans.material_work_units(broad, media, [], mode="light")
    full = dev_plans.material_work_units(broad, media, [], mode="full")
    first = {"light": light[0].payload, "full": full[0].payload}
    assert [m["id"] for m in first["light"]["media_selections"]] == ["MED-01", "MED-03"], (
        "the module's typical media: its most-used type, then the next different one")
    assert first["light"]["expected_materials"] == dev_plans.LIGHT_MATERIALS_PER_MODULE
    assert first["full"]["expected_materials"] == 5
    text = dev_plans.render_material_set(light[0])
    assert "these are 2 of the module's 4 media selections" in text
    assert text.endswith(dev_plans.development_note("light", "material"))
    assert dev_plans.render_material_set(full[0]).endswith(
        dev_plans.development_note("full", "material"))
    one_type = [dict(m, media_type="slides") for m in media]
    assert [m["id"] for m in dev_plans.typical_media(one_type, 2)] == ["MED-01", "MED-02"]

    module_of = {"TLA-0101": "MOD-01", "TLA-0201": "MOD-02"}
    blocks, _ = dev_plans.session_work_sets(
        {"session_blocks": [{"set_id": "SB", "expected_sessions": 6,
                             "activity_ids": ["TLA-0101"], "material_ids": []}]},
        ["TLA-0101", "TLA-0201"], [], modules=MODULES, module_of=module_of, mode="light")
    sessions = {ws.module_id: ws.payload["expected_sessions"] for ws in blocks}
    assert sessions == {"MOD-01": dev_plans.LIGHT_SESSION_GUIDES_PER_MODULE, "MOD-02": 1}
    scheduled = [a for ws in blocks for a in ws.payload["activity_ids"]]
    assert sorted(scheduled) == ["TLA-0101", "TLA-0201"], "a light guide still schedules every id"


def test_the_mode_never_reaches_a_rules_block_and_both_arms_read_one_note():
    rule_text = "\n".join(value for name, value in vars(rulebook).items()
                          if name.startswith("RULES_") and isinstance(value, str))
    for marker in ("LIGHT DEVELOPMENT", "FULL DEVELOPMENT", "length and detail"):
        assert marker not in rule_text, marker
    for family in ("assessment", "activity", "material", "session_guide"):
        assert dev_plans.development_note("light", family).startswith("LIGHT DEVELOPMENT")
    assert dev_plans.development_note("full", "material").startswith("FULL DEVELOPMENT"), (
        "the depth of a material is the one thing the two modes state differently")
    for family in ("assessment", "activity", "session_guide"):
        assert dev_plans.development_note("full", family) == ""

    from alignmentgraph_isd.core.alignment_graph import AlignmentGraph
    from alignmentgraph_isd.core.memory import Memory
    from alignmentgraph_isd.core.trajectory import TrajectoryLogger

    briefs = {}
    for mode in dev_plans.DEVELOPMENT_MODES:
        config = HarnessRunConfig(agent_mode="single", development_mode=mode)
        config.llm_factory = FakeChatModel
        loop = react.ReactLoop(config, Memory(graph=AlignmentGraph()), TrajectoryLogger(),
                               load_brief("minimal_brief.json"))
        briefs[mode] = {stage: loop.stage_brief(stage) for stage in ("assessment", "content")}
    assert dev_plans.development_note("light", "assessment") in briefs["light"]["assessment"]
    assert "LIGHT DEVELOPMENT" not in briefs["full"]["assessment"]
    assert briefs["light"]["assessment"].replace(
        "\n" + dev_plans.development_note("light", "assessment"), "") \
        == briefs["full"]["assessment"], "the note is the only difference"
    assert briefs["light"]["content"].replace(
        dev_plans.development_note("light", "material"),
        dev_plans.development_note("full", "material")) == briefs["full"]["content"], (
        "content differs only by which depth note it carries")


def test_a_light_run_still_covers_what_the_checks_measure():
    config = HarnessRunConfig()
    config.llm_factory = FakeChatModel
    result = run_brief(load_brief("minimal_brief.json"), config)
    coverage = result["graph"]["relation_coverage"]
    for relation in ("C2", "C3", "P10", "P11", "P12", "P13", "P14"):
        assert coverage[relation]["coverage"] == 1.0, relation
    plans = {plan["stage"]: plan for plan in result["plans"]}
    assert all(ws["module_id"] for stage in ("assessment", "activities", "content", "implementation")
               for ws in plans[stage]["work_sets"]), "every work set is one module's share"


@pytest.mark.parametrize("context_mode", ["graph", "prose"])
def test_the_output_says_at_what_scale_it_was_written(context_mode):
    """The blueprint states a quiz at full scale and the design carries a few
    of its items; the output says so in counts, on either substrate, so a
    reader never has to guess why forty were planned and three are there."""
    config = HarnessRunConfig(context_mode=context_mode)
    config.llm_factory = FakeChatModel
    output = run_brief(load_brief("minimal_brief.json"), config)["addie_output"]

    written = output["development"]["assessment_tools"]
    items = [one for t in written for one in (t.get("items") or [])]
    tasks = [t for one in output["design"]["assessment_plan"]["sets"]
             for t in one["assessment_tasks"]]
    assert sum(t["items_written"] for t in tasks) == len(items) > 0
    assert all("item_counts" in t for t in tasks), "the full scale is still stated"

    scope = output["development"]["development_scope"]
    assert scope["mode"] == "light" and scope["items_written"] == len(items)
    assert scope["items_planned"] == sum(sum(t["item_counts"].values()) for t in tasks)
    assert f"{len(items)} of the {scope['items_planned']} assessment items" in scope["note"]
    assert "typical, reviewable slice" in scope["note"]


def test_a_light_summative_task_always_gets_its_full_quota():
    """A summative task is the instrument the course grades on; one item for a
    one-objective task is not an instrument a reviewer can judge. Formative
    and diagnostic tasks keep one item per pair."""
    one_pair = [("ILO-03", "summative")]
    practical = {"id": "SET-02", "timing": "summative", "format": "practical",
                 "item_counts": {"performance_task": 5}, "covers_objectives": ["ILO-03"]}
    rows = dev_plans.light_item_assignment(practical, one_pair, LEVELS)
    assert len(rows) == dev_plans.LIGHT_ITEMS_PER_TASK
    assert {r["objective"] for r in rows} == {"ILO-03"} and {r["level"] for r in rows} == {"create"}
    quiz = {**practical, "id": "SET-01", "timing": "formative", "item_counts": {"multiple_choice": 1}}
    assert len(dev_plans.light_item_assignment(quiz, [("ILO-03", "formative")], LEVELS)) == 1, (
        "a formative task of one planned item writes one")
    tiny = {**practical, "item_counts": {"performance_task": 1}}
    assert len(dev_plans.light_item_assignment(tiny, one_pair, LEVELS)) == 3, (
        "a summative task planned at one item is written at the floor the plan is told")
    assert "a summative task always gets about" in dev_plans.development_note("light", "assessment")
