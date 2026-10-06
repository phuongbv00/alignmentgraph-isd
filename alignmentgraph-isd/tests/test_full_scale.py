"""Every artifact the design plans is written.

The plan states the course at its real scale — a task's ``item_counts``, a
module's media selections — and the Developers write all of it, batching what
one call cannot hold. There is no lighter mode: a run is not configured for
how much of its own plan it writes.
"""
from __future__ import annotations

import pytest

from alignmentgraph_isd import HarnessRunConfig
from alignmentgraph_isd.core import dev_plans

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


def test_no_run_is_configured_for_how_much_of_its_plan_it_writes():
    assert not hasattr(HarnessRunConfig(), "development_mode")
    config = HarnessRunConfig()
    config.llm_factory = FakeChatModel
    result = run_brief(load_brief("minimal_brief.json"), config)
    assert "development_mode" not in result["metadata"]["run_config"]
    assert "development_scope" not in result["addie_output"]["development"]


def test_a_task_is_written_whole_in_batches_that_divide_it():
    sets = dev_plans.assessment_work_sets(
        None, LOS, TARGETS, modules=MODULES, blueprint=SETS)[0]
    quiz = [ws for ws in sets if ws.module_id == "MOD-01"]
    limit = dev_plans.max_units("assessment")
    assert len(quiz) == -(-45 // limit)
    assert sum(ws.payload["expected_items"] for ws in quiz) == 45, "divided, never repeated"
    assert all(ws.payload["expected_items"] <= limit for ws in quiz)
    assert [ws.payload["batch"][0] for ws in quiz] == list(range(1, len(quiz) + 1))
    assert all(set(ws.pairs) == {("ILO-01", "formative"), ("ILO-02", "formative")} for ws in quiz)
    assert "part 2 of" in dev_plans.render_assessment_set(quiz[1])
    assert len({ws.set_id for ws in sets}) == len(sets) == len({ws.ordinal for ws in sets})


def test_every_media_selection_is_a_material_written_in_full():
    media = [{"id": f"MED-0{i}", "media_type": kind, "for_modules": ["MOD-01"]}
             for i, kind in enumerate(("slides", "slides", "video", "slides"), start=1)]
    units = dev_plans.material_work_units([dict(MODULES[0], expected_materials=5), MODULES[1]],
                                          media, [])
    first = units[0].payload
    assert [m["id"] for m in first["media_selections"]] == ["MED-01", "MED-02", "MED-03", "MED-04"]
    assert first["expected_materials"] == 5
    assert dev_plans.render_material_set(units[0]).endswith(dev_plans.depth_note("material"))


def test_a_session_block_schedules_every_id():
    module_of = {"TLA-0101": "MOD-01", "TLA-0201": "MOD-02"}
    blocks, _ = dev_plans.session_work_sets(
        {"session_blocks": [{"set_id": "SB", "expected_sessions": 6,
                             "activity_ids": ["TLA-0101"], "material_ids": []}]},
        ["TLA-0101", "TLA-0201"], [], modules=MODULES, module_of=module_of)
    scheduled = sorted(a for ws in blocks for a in ws.payload["activity_ids"])
    assert scheduled == ["TLA-0101", "TLA-0201"]


@pytest.mark.parametrize("context_mode", ["graph", "prose"])
def test_the_output_states_every_tasks_scale_beside_what_was_written(context_mode):
    config = HarnessRunConfig(context_mode=context_mode)
    config.llm_factory = FakeChatModel
    output = run_brief(load_brief("minimal_brief.json"), config)["addie_output"]
    written = output["development"]["assessment_tools"]
    items = [one for t in written for one in (t.get("items") or [])]
    tasks = [t for one in output["design"]["assessment_plan"]["sets"]
             for t in one["assessment_tasks"]]
    assert sum(t["items_written"] for t in tasks) == len(items) > 0
    assert all("item_counts" in t for t in tasks)


def test_a_run_covers_what_the_checks_measure():
    config = HarnessRunConfig()
    config.llm_factory = FakeChatModel
    result = run_brief(load_brief("minimal_brief.json"), config)
    coverage = result["graph"]["relation_coverage"]
    for relation in ("C2", "C3", "P10", "P11", "P12", "P13", "P14"):
        assert coverage[relation]["coverage"] == 1.0, relation
    plans = {plan["stage"]: plan for plan in result["plans"]}
    assert all(ws["module_id"] for stage in ("assessment", "activities", "content", "implementation")
               for ws in plans[stage]["work_sets"]), "every work set is one module's share"
