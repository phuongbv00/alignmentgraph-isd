"""``development_mode``: how much of the planned scale the Developers write.

The PLAN always states the course at full scale. ``"sample"`` (the default)
writes a representative sample of it and ``"full"`` writes all of it. The mode
changes NUMBERS in a work set and one sentence of its assignment — never a
``RULES_*`` block, never the ground truth a check measures — and it is not an
ablation axis: a run records it and every arm of one experiment shares it.
"""
from __future__ import annotations

import pytest

from alignmentgraph_isd import HarnessRunConfig
from alignmentgraph_isd.core import dev_plans, rulebook
from alignmentgraph_isd.core.agentic import react

from conftest import FakeChatModel, load_brief, run_brief

MODULES = [{"id": "MOD-01", "title": "Basics", "objectives": ["ILO-01", "ILO-02"], "minutes": 600},
           {"id": "MOD-02", "title": "Practice", "objectives": ["ILO-03"], "minutes": 120}]
INSTRUMENTS = [
    {"id": "INS-01", "module_id": "MOD-01", "timing": "formative", "format": "quiz",
     "item_counts": {"multiple_choice": 40, "short_answer": 5},
     "covers_objectives": ["ILO-01", "ILO-02"]},
    {"id": "INS-02", "module_id": "MOD-02", "timing": "summative", "format": "practical",
     "item_counts": {"performance_task": 2}, "covers_objectives": ["ILO-03"]}]
TARGETS = {"ILO-01": ["formative"], "ILO-02": ["formative"], "ILO-03": ["summative"]}
LOS = ["ILO-01", "ILO-02", "ILO-03"]


def _assessment(mode):
    return dev_plans.normalize_assessment_dev_plan(
        None, LOS, TARGETS, modules=MODULES, instruments=INSTRUMENTS, mode=mode)[0]


def test_the_default_is_sample_and_a_run_records_it():
    assert HarnessRunConfig().development_mode == "sample"
    with pytest.raises(ValueError):
        HarnessRunConfig(development_mode="partial")
    config = HarnessRunConfig(development_mode="full")
    config.llm_factory = FakeChatModel
    result = run_brief(load_brief("minimal_brief.json"), config)
    assert result["metadata"]["run_config"]["development_mode"] == "full"


def test_a_sample_writes_a_few_items_of_each_instrument_and_never_drops_a_pair():
    sets = _assessment("sample")
    assert [(ws.module_id, ws.payload["expected_items"]) for ws in sets] == [
        ("MOD-01", dev_plans.SAMPLE_ITEMS_PER_INSTRUMENT), ("MOD-02", 2)], (
        "a 45-item quiz is sampled; a 2-item practical is already smaller than a sample")
    assert {pair for ws in sets for pair in ws.pairs} == set(dev_plans.plan_category_pairs(TARGETS))
    text = dev_plans.render_assessment_set(sets[0])
    assert "full scale: 40 multiple_choice, 5 short_answer" in text, "the plan's scale is still stated"
    assert text.endswith(dev_plans.development_note("sample", "assessment"))


def test_full_writes_the_whole_instrument_in_batches_that_divide_it():
    sets = _assessment("full")
    quiz = [ws for ws in sets if ws.module_id == "MOD-01"]
    limit = dev_plans.max_units("assessment")
    assert len(quiz) == -(-45 // limit)
    assert sum(ws.payload["expected_items"] for ws in quiz) == 45, "divided, never repeated"
    assert all(ws.payload["expected_items"] <= limit for ws in quiz)
    assert [ws.payload["batch"][0] for ws in quiz] == list(range(1, len(quiz) + 1))
    assert all(set(ws.pairs) == {("ILO-01", "formative"), ("ILO-02", "formative")} for ws in quiz)
    assert "part 2 of" in dev_plans.render_assessment_set(quiz[1])
    assert "SAMPLE DEVELOPMENT" not in dev_plans.render_assessment_set(quiz[0])
    assert len({ws.set_id for ws in sets}) == len(sets) == len({ws.ordinal for ws in sets})


def test_a_sampled_module_gets_a_sequence_of_activities_bounded_by_its_minutes():
    plan = {"activity_blocks": [
        {"set_id": "B1", "objectives": ["ILO-01", "ILO-02"], "block_theme": "t",
         "block_minutes": 600, "expected_activities": 11},
        {"set_id": "B2", "objectives": ["ILO-03"], "block_theme": "u",
         "block_minutes": 120, "expected_activities": 1}]}
    sample, _ = dev_plans.normalize_activity_dev_plan(plan, LOS, modules=MODULES, mode="sample")
    full, _ = dev_plans.normalize_activity_dev_plan(plan, LOS, modules=MODULES, mode="full")

    by_module = {ws.module_id: ws.payload["expected_activities"] for ws in sample}
    assert by_module == {"MOD-01": 2 * dev_plans.SAMPLE_ACTIVITIES_PER_OBJECTIVE,
                         "MOD-02": dev_plans.SAMPLE_ACTIVITIES_PER_MODULE_FLOOR}
    assert sum(ws.payload["expected_activities"] for ws in full
               if ws.module_id == "MOD-01") >= 10, "full keeps the planner's own scale"
    assert {lo for ws in sample for lo in ws.objectives} == set(LOS), "every objective keeps a block"

    tight = [dict(MODULES[0], minutes=30), MODULES[1]]
    squeezed, _ = dev_plans.normalize_activity_dev_plan(plan, LOS, modules=tight, mode="sample")
    assert squeezed[0].payload["expected_activities"] == 30 // dev_plans.MIN_ACTIVITY_MINUTES


def test_a_sampled_module_gets_at_most_two_materials_and_a_guide_or_two():
    media = [{"id": f"MED-0{n}", "media_type": "slides", "for_modules": ["MOD-01"]}
             for n in range(1, 5)]
    sample = dev_plans.material_work_units(MODULES, media, [], mode="sample")
    full = dev_plans.material_work_units(MODULES, media, [], mode="full")
    first = {"sample": sample[0].payload, "full": full[0].payload}
    assert len(first["sample"]["media_selections"]) == dev_plans.SAMPLE_MATERIALS_PER_MODULE
    assert first["sample"]["expected_materials"] == dev_plans.SAMPLE_MATERIALS_PER_MODULE
    assert first["full"]["expected_materials"] == 4

    module_of = {"TLA-0101": "MOD-01", "TLA-0201": "MOD-02"}
    blocks, _ = dev_plans.normalize_implementation_dev_plan(
        {"session_blocks": [{"set_id": "SB", "expected_sessions": 6,
                             "activity_ids": ["TLA-0101"], "material_ids": []}]},
        ["TLA-0101", "TLA-0201"], [], modules=MODULES, module_of=module_of, mode="sample")
    sessions = {ws.module_id: ws.payload["expected_sessions"] for ws in blocks}
    assert sessions == {"MOD-01": dev_plans.SAMPLE_SESSION_GUIDES_PER_MODULE, "MOD-02": 1}
    scheduled = [a for ws in blocks for a in ws.payload["activity_ids"]]
    assert sorted(scheduled) == ["TLA-0101", "TLA-0201"], "a sampled guide still schedules every id"


def test_the_mode_never_reaches_a_rules_block_and_both_arms_read_one_sentence():
    rule_text = "\n".join(value for name, value in vars(rulebook).items()
                          if name.startswith("RULES_") and isinstance(value, str))
    assert "SAMPLE DEVELOPMENT" not in rule_text
    for family in ("assessment", "activity", "material", "session_guide"):
        assert dev_plans.development_note("sample", family).startswith("SAMPLE DEVELOPMENT")
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
        briefs[mode] = loop.stage_brief("assessment")
    assert dev_plans.development_note("sample", "assessment") in briefs["sample"]
    assert "SAMPLE DEVELOPMENT" not in briefs["full"]
    assert briefs["sample"].replace("\n" + dev_plans.development_note("sample", "assessment"), "") \
        == briefs["full"], "the sentence is the only difference"


def test_a_sampled_run_still_covers_what_the_checks_measure():
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

    items = output["development"]["assessment_tools"]
    instruments = output["design"]["assessment_plan"]["instruments"]
    assert sum(i["items_written"] for i in instruments) == len(items) > 0
    assert all("item_counts" in i for i in instruments), "the full scale is still stated"

    scope = output["development"]["development_scope"]
    assert scope["mode"] == "sample" and scope["items_written"] == len(items)
    assert scope["items_planned"] == sum(sum(i["item_counts"].values()) for i in instruments)
    assert f"{len(items)} of the {scope['items_planned']} assessment items" in scope["note"]
    assert "representative sample" in scope["note"]
