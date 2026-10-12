"""The 2x2 held to its parity specification, offline.

``docs/guides/ablation_parity.md`` lists what the ``agent_mode`` axis varies
(D1-D7) and what it must hold constant (C1-C21). These are the invariants of
its §6, checked on all four arms with a fake model that writes what it is
asked for — so a rule that one arm keeps and the other does not shows up here,
before a real run spends money finding it.

I1  the four arms land the same number of artifacts in every unit;
I2  no stage is cut by the turn ceiling or by the submit budget while the
    model makes progress;
I3  a model that only resends what is refused is closed after the same
    number of submits on both arms;
I4  no unit holds more than it is commissioned for, and nothing twice;
I5  the same bad submit is refused with the same errors on both arms;
I6  the single agent is shown the same commission a Developer is handed;
I7  each held-constant rule is reached through one function, on the source.
"""
from __future__ import annotations

import inspect
from collections import Counter
from functools import lru_cache

import pytest

from conftest import FakeChatModel, load_brief, run_brief

from alignmentgraph_isd import HarnessRunConfig
from alignmentgraph_isd.core import dev_plans
from alignmentgraph_isd.core.agentic import budget, fanout, loop, react, specialists, turn
from alignmentgraph_isd.core.agentic.specialists import STEPS
from alignmentgraph_isd.core.alignment_graph import AlignmentGraph
from alignmentgraph_isd.core.prose_store import ProseStore
from alignmentgraph_isd.core.trajectory import TrajectoryLogger

ARMS = [(a, c) for a in ("multi", "single") for c in ("graph", "prose")]
STEP = {s.name: s for s in STEPS}


@lru_cache(maxsize=None)
def _run(agent_mode: str, context_mode: str) -> dict:
    return run_brief(load_brief("minimal_brief.json"), HarnessRunConfig(
        llm_factory=lambda: FakeChatModel(), agent_mode=agent_mode,
        context_mode=context_mode))


def _per_unit(result: dict) -> dict:
    """What the run wrote, counted by the unit each artifact belongs to."""
    out = result["addie_output"]
    dev, design = out["development"], out["design"]
    activities = design.get("learning_activities") or dev.get("learning_activities") or []
    guides = (out["implementation"].get("instructor_guide") or {}).get("session_guides") or []
    return {
        "items": Counter({t["id"]: len(t.get("items") or []) for t in dev["assessment_tools"]}),
        "activities": Counter(str(a.get("module_id")) for a in activities),
        "materials": Counter(str(m.get("linked_module")) for m in dev["learner_materials"]),
        "scheduled": sorted({i for g in guides
                             for i in (g.get("activity_ids") or []) + (g.get("material_ids") or [])}),
    }


# ── I1 ──────────────────────────────────────────────────────────────────────

def test_i1_the_four_arms_land_the_same_artifacts_in_every_unit():
    counts = {arm: _per_unit(_run(*arm)) for arm in ARMS}
    reference = counts[("multi", "graph")]
    assert reference["items"] and reference["materials"]
    for arm, mine in counts.items():
        for family in ("items", "activities", "materials"):
            assert mine[family] == reference[family], (arm, family)
        assert len(mine["scheduled"]) == len(reference["scheduled"]), arm


# ── I2 ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("arm", ARMS, ids=lambda a: "+".join(a))
def test_i2_no_stage_is_cut_while_the_model_makes_progress(arm):
    autonomy = _run(*arm)["metadata"]["autonomy"]
    for stage, record in autonomy.items():
        if not isinstance(record, dict):
            continue
        assert not record.get("via_budget_exhaustion"), (arm, stage)
        assert not record.get("abandoned_stages"), (arm, stage)
        assert not record.get("prompt_exceeds_window"), (arm, stage)


# ── I3 ──────────────────────────────────────────────────────────────────────

_BAD = {"needs_analysis": {"problem_definition": "x", "gaps": [],
                           "performance_analysis": "y", "priority_matrix": {}}}


def _rejections(trajectory) -> int:
    return sum(1 for e in trajectory.recovery_events if e["action"] == "submit_rejected")


def test_i3_a_refused_artifact_is_closed_after_the_same_submits_on_both_arms():
    """One artifact resent unchanged and refused every time, far past the
    budget: both arms stop taking it after ``SUBMIT_BUDGET``. The constrained
    pass is off so the count is the budget's alone."""
    from test_agentic_loop import ScriptedModel, call

    resends = budget.SUBMIT_BUDGET + 5

    model = ScriptedModel([call("submit_needs_analysis", _BAD)] * resends)
    config = HarnessRunConfig(llm_factory=lambda: model, structured_outputs=False)
    multi_log = TrajectoryLogger()
    from alignmentgraph_isd.core.agentic.client import AgenticLLM

    step = STEP["analysis"]
    loop.ToolLoop(config, AlignmentGraph(), multi_log, load_brief("minimal_brief.json"),
                  step, AgenticLLM(config, multi_log, step.identity)).run()

    from test_agentic_react import _Scripted

    single_model = _Scripted([("submit_analysis", _BAD)] * resends)
    single_config = HarnessRunConfig(llm_factory=lambda: single_model,
                                     structured_outputs=False)
    single_log = TrajectoryLogger()
    react.ReactLoop(single_config, AlignmentGraph(), single_log,
                    load_brief("minimal_brief.json")).run()

    assert _rejections(multi_log) == _rejections(single_log) == budget.SUBMIT_BUDGET


# ── I4 ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("arm", ARMS, ids=lambda a: "+".join(a))
def test_i4_no_unit_holds_more_than_its_commission_or_anything_twice(arm):
    result = _run(*arm)
    dev = result["addie_output"]["development"]
    plan = result["addie_output"]["design"].get("assessment_plan") or {}
    stated = {t["id"]: sum((t.get("item_counts") or {}).values())
              for s in plan.get("sets") or [] for t in s.get("assessment_tasks") or []}
    for task in dev["assessment_tools"]:
        items = task.get("items") or []
        floor = max(stated.get(task["id"], 0), dev_plans.TASK_ITEMS_FLOOR)
        assert len(items) <= floor, (arm, task["id"])
        keys = [dev_plans.same_artifact_key("assessment_tools", i) for i in items]
        assert len(keys) == len(set(keys)), (arm, task["id"])
    keys = [dev_plans.same_artifact_key("learner_materials", m) for m in dev["learner_materials"]]
    assert len(keys) == len(set(keys)), arm


# ── I5 ──────────────────────────────────────────────────────────────────────

def _design(substrate: str):
    from test_agentic_loop import _ANALYSIS, _ASSESSMENT, _OUTCOMES

    state = AlignmentGraph() if substrate == "graph" else ProseStore()
    suffix = "" if substrate == "graph" else "_prose"
    for name, payload in (("analysis", _ANALYSIS), ("outcomes", _OUTCOMES),
                          ("assessment", {"assessment_plan": _ASSESSMENT["assessment_plan"]})):
        getattr(specialists, f"commit_{name}{suffix}")(state, TrajectoryLogger(), payload)
    return state


@pytest.mark.parametrize("substrate", ["graph", "prose"])
def test_i5_the_same_bad_items_are_refused_with_the_same_errors(substrate):
    """An item naming an objective that does not exist and below its
    objective's level: the Developer's validator and the single agent's say
    the same thing about it."""
    from test_agentic_loop import _ASSESSMENT

    state = _design(substrate)
    spec = fanout.SPECS["assessment"]
    work_set = fanout.derived_sets("assessment", state)[0]
    item = dict(_ASSESSMENT["assessment_tools"][0], aligned_objective="ILO-99",
                task_id="AT-01")
    developer = fanout.set_step(spec, work_set, STEP["assessment"], state)
    by_developer = developer.validate({"assessment_tools": [item]})

    single = react.ReactLoop(HarnessRunConfig(llm_factory=lambda: None), state,
                             TrajectoryLogger(), load_brief("minimal_brief.json"))
    by_single = single._validate(STEP["assessment"], {"assessment_tools": [item]})

    assert by_developer, "the item must be refused for the comparison to mean anything"
    assert set(by_developer) <= set(by_single)


# ── I6 ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("substrate", ["graph", "prose"])
def test_i6_the_single_agent_is_shown_what_a_developer_is_handed(substrate):
    state = _design(substrate)
    spec = fanout.SPECS["assessment"]
    single = react.ReactLoop(HarnessRunConfig(llm_factory=lambda: None), state,
                             TrajectoryLogger(), load_brief("minimal_brief.json"))
    shown = single._commission(STEP["assessment"])
    owed = fanout.owed_sets("assessment", state)
    assert owed and shown
    for work_set, _output, _left in owed[:react.ReactLoop.COMMISSION_SHOWN]:
        assignment = spec.render(work_set)
        assert assignment in shown
        assert assignment in fanout.set_step(spec, work_set, STEP["assessment"], state).intro


# ── I7 ──────────────────────────────────────────────────────────────────────

def test_i7_each_held_constant_rule_has_one_implementation():
    """On the source: the single arm reaches every C-row rule through the
    function the multi arm uses, and keeps no copy of its own."""
    single = inspect.getsource(react)
    stage = inspect.getsource(loop)
    for shared in ("turn_mod.SubmitBudget", "fanout.progress_mark"):
        assert shared in single and shared in stage, shared
    for shared in ("fanout.commit_sets", "fanout.route_items", "fanout.owed_sets",
                   "spec.render(", "turn_mod.constrained_pass"):
        assert shared in single, shared
    for retired in ("SUBMIT_CAP", "unit_quotas", "_within_quota", "trim_to_quota",
                    "without_repeats", "_progress_mark"):
        assert retired not in single, retired
    assert not hasattr(budget, "SUBMIT_CAP")
    assert turn.SubmitBudget().limit == budget.SUBMIT_BUDGET == loop.ToolLoop.SUBMIT_BUDGET


def test_i4_a_task_takes_its_stated_count_whichever_set_writes_into_it():
    """A set grouping two tasks of one pair, or a re-dispatched set with its
    quota whole again, cannot fill a task past what it states (MEASURED, run t1
    20261011_163858: 19 items in a task stating 13, none in its sibling). The
    first item for an objective the task holds nothing for is still kept — the
    gap a re-dispatch is sent to close."""
    work_set = dev_plans.WorkSet(set_id="AS-AT-01", payload={"sets": [
        {"id": "AT-01", "item_counts": {"short_answer": 2}},
        {"id": "AT-02", "item_counts": {"short_answer": 2}}]})
    held = [{"task_id": "AT-01", "aligned_objective": "ILO-01", "question": "q1"},
            {"task_id": "AT-01", "aligned_objective": "ILO-01", "question": "q2"}]
    sent = [{"task_id": "AT-01", "aligned_objective": "ILO-01", "question": "q3"},
            {"task_id": "AT-01", "aligned_objective": "ILO-04", "question": "q4"},
            {"task_id": "AT-02", "aligned_objective": "ILO-01", "question": "q5"}]
    kept, dropped = dev_plans.within_task_counts(work_set, sent, held)
    assert [i["question"] for i in kept] == ["q4", "q5"] and dropped == 1


@pytest.mark.parametrize("substrate", ["graph", "prose"])
def test_i5_an_empty_submit_is_written_again_for_the_set_a_developer_holds(substrate):
    """Pass 2 for a submit that carried no item is tightened by the first owed
    work set, so it names only that set's tasks — the schema the Developer
    holding that set decodes under (C5). Left untightened it wrote for the
    first, already full, task again (MEASURED, run t1 20261011_171005)."""
    from alignmentgraph_isd.core.agentic import grammar, tools

    state = _design(substrate)
    single = react.ReactLoop(HarnessRunConfig(llm_factory=lambda: None), state,
                             TrajectoryLogger(), load_brief("minimal_brief.json"))
    step = STEP["assessment"]
    params = tools.spec_parameters(
        tools.react_specs(STEPS, frozenset(), current="assessment",
                          open_fields=("assessment_tools",)), "submit_assessment")
    by_single = single._pass_params(step, {}, params)
    work_set, _output, _left = fanout.owed_sets("assessment", state)[0]
    by_developer = grammar.tighten_parameters(
        params, grammar.Vocabulary.of(state), work_set=work_set)
    task_ids = lambda p: p["properties"]["assessment_tools"]["items"]["properties"]["task_id"]["enum"]  # noqa: E731
    assert task_ids(by_single) == task_ids(by_developer)
    assert set(task_ids(by_single)) == {t["id"] for t in work_set.payload["sets"]}


@pytest.mark.parametrize("substrate", ["graph", "prose"])
def test_i5_a_plan_that_drops_a_task_holding_items_is_refused_on_both_arms(substrate):
    """A resubmitted plan that renames a task holding items would orphan them
    (MEASURED, run t1 20261012_090924: 36 items, then filed under the wrong
    task). Both arms' validators refuse it with the same error."""
    import copy

    from test_agentic_loop import _ASSESSMENT

    from alignmentgraph_isd.core.agentic.client import AgenticLLM

    state = _design(substrate)
    spec = fanout.SPECS["assessment"]
    work_set = fanout.derived_sets("assessment", state)[0]
    item = dict(_ASSESSMENT["assessment_tools"][0], task_id="AT-01")
    fanout.commit_sets(spec, state, TrajectoryLogger(), [work_set],
                       [{"set_id": work_set.set_id, "assessment_tools": [item]}])
    plan = copy.deepcopy(_ASSESSMENT["assessment_plan"])
    plan["sets"][0]["assessment_tasks"][0]["id"] = "AT-0101"
    section = {"assessment_plan": plan}

    config = HarnessRunConfig(llm_factory=lambda: None)
    step, log = STEP["assessment"], TrajectoryLogger()
    multi = loop.ToolLoop(config, state, log, load_brief("minimal_brief.json"), step,
                          AgenticLLM(config, log, step.identity))
    single = react.ReactLoop(config, state, log, load_brief("minimal_brief.json"))
    by_multi = [e for e in multi._validate(section) if "drops task" in e]
    by_single = [e for e in single._validate(step, section) if "drops task" in e]
    assert by_multi and by_multi == by_single


def test_items_of_a_task_go_to_its_next_batch_once_a_batch_is_closed():
    """A task written in batches is several work sets; on the multi arm each is
    its own Developer. The single agent names the TASK, so routing must pass a
    batch whose budget is spent, or the next batch is unreachable (MEASURED,
    run t1 20261013_012331: AS-AT-01-02 never received an item)."""
    work_sets = [dev_plans.WorkSet(set_id="AS-AT-01-01", payload={"sets": [{"id": "AT-01"}]}),
                 dev_plans.WorkSet(set_id="AS-AT-01-02", payload={"sets": [{"id": "AT-01"}]})]
    output = fanout.SPECS["assessment"].outputs[0]
    import unittest.mock as mock
    with mock.patch.object(fanout, "derived_sets", lambda stage, state: work_sets), \
         mock.patch.object(fanout, "remaining", lambda state, output, ws: 3):
        item = {"task_id": "AT-01", "question": "q"}
        assert fanout.route_items("assessment", None, output, [item])[0][0].set_id == "AS-AT-01-01"
        routed = fanout.route_items("assessment", None, output, [item],
                                    frozenset({"AS-AT-01-01"}))
        assert routed[0][0].set_id == "AS-AT-01-02"
