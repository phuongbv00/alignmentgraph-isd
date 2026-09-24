"""The per-run submit schema (``core/agentic/grammar.py``).

What it must hold to: it only ever TIGHTENS the declared contract, it reads the
same design to the same schema on either substrate, it says a fixed assignment
as constants and a stated count as bounds, and nothing it produces uses a
keyword the serving stack's grammar backend refuses.
"""
from __future__ import annotations

import json

import pytest

from alignmentgraph_isd.core import dev_plans
from alignmentgraph_isd.core.agentic import fanout, grammar, specialists, tools
from alignmentgraph_isd.core.agentic.artifact_schemas import ARTIFACT_SCHEMAS
from alignmentgraph_isd.core.agentic.specialists import STEPS
from alignmentgraph_isd.core.alignment_graph import AlignmentGraph, NodeType
from alignmentgraph_isd.core.prose_store import ProseStore
from alignmentgraph_isd.core.trajectory import TrajectoryLogger

from test_agentic_loop import _ANALYSIS, _ASSESSMENT, _OUTCOMES

STEP_BY_NAME = {s.name: s for s in STEPS}

_OUTCOMES_TWO = {
    "learning_objectives": _OUTCOMES["learning_objectives"] + [
        {"id": "ILO-02", "level": "analyze",
         "statement": "Analyze a class hierarchy for misplaced responsibilities.",
         "bloom_verb": "analyze"}],
    "course_modules": [
        {"id": "MOD-01", "title": "Inheritance in practice", "objectives": ["ILO-01"],
         "covers_topics": ["TOP-01"], "minutes": 120},
        {"id": "MOD-02", "title": "Reading hierarchies", "objectives": ["ILO-02"],
         "covers_topics": ["TOP-01"], "minutes": 240}],
}


def _design(substrate: str):
    """The same design, committed the way each arm commits it."""
    trajectory = TrajectoryLogger()
    if substrate == "graph":
        state = AlignmentGraph()
        specialists.commit_analysis(state, trajectory, _ANALYSIS)
        specialists.commit_outcomes(state, trajectory, _OUTCOMES_TWO)
        specialists.commit_assessment(state, trajectory, _ASSESSMENT)
    else:
        state = ProseStore()
        specialists.commit_analysis_prose(state, trajectory, _ANALYSIS)
        specialists.commit_outcomes_prose(state, trajectory, _OUTCOMES_TWO)
        specialists.commit_assessment_prose(state, trajectory, _ASSESSMENT)
    return state


# ── it reads the design, not the substrate ──────────────────────────────────

def test_the_same_design_yields_the_same_schema_on_both_substrates():
    """The constrained pass must sit on the transport, not on the
    `context_mode` axis: nothing the grammar reads is part of the bundle that
    axis ablates, so a graph and a blackboard holding one design bind one
    schema."""
    on_graph = grammar.Vocabulary.of(_design("graph"))
    on_prose = grammar.Vocabulary.of(_design("prose"))
    assert on_graph == on_prose
    assert on_graph.objectives == ("ILO-01", "ILO-02")
    assert on_graph.module_ids == ("MOD-01", "MOD-02")
    assert on_graph.task_ids == ("AT-01",)
    assert on_graph.topics == ("TOP-01",) and on_graph.constraints == ("CON-01",)
    for step in STEPS:
        base = tools.tool_specs(step)
        assert (grammar.tighten_specs(base, on_graph) == grammar.tighten_specs(base, on_prose)), (
            step.name)


def test_binding_a_schema_is_the_harness_s_read_not_the_agent_s():
    """The vocabulary is read inside the agent's scope, on the graph substrate
    with an observer stamping every read: it must be recorded as the
    orchestrator's, like every other harness probe."""
    from alignmentgraph_isd.core.trajectory import ORCHESTRATOR

    trajectory = TrajectoryLogger()
    graph = AlignmentGraph(observer=trajectory.graph_observer())
    specialists.commit_outcomes(graph, trajectory, _OUTCOMES_TWO)
    before = len(trajectory.actions)
    with trajectory.acting_as("OutcomeDesignerAgent"):
        grammar.Vocabulary.of(graph)
    reads = [a for a in trajectory.actions[before:]
             if a["action"] in ("node_read", "edge_read")]
    assert reads, "the vocabulary is read off the graph"
    assert {a["agent"] for a in reads} == {ORCHESTRATOR}


# ── it only ever tightens ───────────────────────────────────────────────────

def _every_property(schema: dict, path: str = ""):
    """(path, property schema) for every declared property, recursively,
    descending arrays and prefixItems."""
    if not isinstance(schema, dict):
        return
    for name, prop in (schema.get("properties") or {}).items():
        yield f"{path}.{name}", prop
        yield from _every_property(prop, f"{path}.{name}")
    if isinstance(schema.get("items"), dict):
        yield from _every_property(schema["items"], f"{path}[]")
    for index, row in enumerate(schema.get("prefixItems") or []):
        yield from _every_property(row, f"{path}[{index}]")


@pytest.mark.parametrize("step", [s for s in STEPS], ids=lambda s: s.name)
def test_a_stage_schema_is_the_declared_one_narrowed_never_widened(step):
    vocab = grammar.Vocabulary.of(_design("graph"), course_hours=24)
    for spec in grammar.tighten_specs(tools.tool_specs(step), vocab):
        name = spec["function"]["name"]
        if not name.startswith("submit_"):
            continue
        params = spec["function"]["parameters"]
        base = tools.spec_parameters(tools.tool_specs(step), name)
        assert set(params["properties"]) == set(base["properties"]), name
        assert params["required"] == base["required"], name
        # Every enum the tightened schema carries is a subset of the base's,
        # where the base declared one, and every required list is still
        # floored.
        declared = dict(_every_property(base))
        for path, prop in _every_property(params):
            if "enum" in prop and "enum" in declared.get(path, {}):
                assert set(prop["enum"]) <= set(declared[path]["enum"]), (name, path)
            if path in declared and declared[path].get("minItems"):
                assert prop.get("minItems", 0) >= declared[path]["minItems"], (name, path)
            assert prop.get("additionalProperties") is not False or path.endswith(
                "lo_coverage_targets"), (name, path)


def test_an_empty_pool_leaves_the_field_as_declared():
    """Before the outcomes stage has written anything there is no objective
    to name: the field stays a string, exactly where `reference_errors`
    stands down, so the grammar never refuses a run its first artifact."""
    vocab = grammar.Vocabulary.of(AlignmentGraph())
    item = grammar.artifact_property("assessment_tools", "array", True, vocab)["items"]
    assert item["properties"]["aligned_objective"] == \
        ARTIFACT_SCHEMAS["assessment_tools"]["properties"]["aligned_objective"]
    plan = grammar.artifact_property("assessment_plan", "object", True, vocab)
    assert "prefixItems" not in plan["properties"]["sets"]
    assert "additionalProperties" in plan["properties"]["lo_coverage_targets"]
    assert plan["properties"]["lo_coverage_targets"]["additionalProperties"] is not False


# ── what it says ────────────────────────────────────────────────────────────

def test_references_are_enums_over_the_ids_that_exist():
    vocab = grammar.Vocabulary.of(_design("graph"))
    item = grammar.artifact_property("assessment_tools", "array", True, vocab)["items"]
    assert item["properties"]["aligned_objective"]["enum"] == ["ILO-01", "ILO-02"]
    assert item["properties"]["task_id"]["enum"] == ["AT-01"]
    activity = grammar.artifact_property("learning_activities", "array", True, vocab)["items"]
    assert activity["properties"]["aligned_objectives"]["items"]["enum"] == ["ILO-01", "ILO-02"]
    assert activity["properties"]["module_id"]["enum"] == ["MOD-01", "MOD-02"]
    assert activity["properties"]["prepares_for_assessment"]["items"]["enum"] == ["AT-01"]
    media = grammar.artifact_property("media_selections", "array", True, vocab)["items"]
    assert media["properties"]["for_modules"]["items"]["enum"] == ["MOD-01", "MOD-02"]
    assert media["properties"]["respects_constraints"]["items"]["enum"] == ["CON-01"]
    modules = grammar.artifact_property("course_modules", "array", True, vocab)
    assert modules["items"]["properties"]["covers_topics"]["items"]["enum"] == ["TOP-01"]


def test_the_assessment_plan_is_one_set_per_module_within_its_allowance():
    """The ceiling the plan is TOLD (`too_many_tasks`) in the shape of the
    request: one set per module in course order, each bounded by the module's
    own allowance — the first module carries the course's diagnostic and a
    module longer than the formative threshold one formative task."""
    vocab = grammar.Vocabulary.of(_design("graph"))
    plan = grammar.artifact_property("assessment_plan", "object", True, vocab)
    sets = plan["properties"]["sets"]
    assert sets["minItems"] == sets["maxItems"] == 2 and sets["items"] is False
    first, second = sets["prefixItems"]
    assert first["properties"]["module_id"]["const"] == "MOD-01"
    assert second["properties"]["module_id"]["const"] == "MOD-02"
    # MOD-01: 120 min -> summative + the course's diagnostic = 2
    # MOD-02: 240 min -> summative + formative = 2
    assert first["properties"]["assessment_tasks"]["maxItems"] == 2
    assert second["properties"]["assessment_tasks"]["maxItems"] == 2
    assert sum(dev_plans.task_allowance(m, i) for i, m in enumerate(vocab.modules)) == \
        dev_plans.task_ceiling(list(vocab.modules))
    targets = plan["properties"]["lo_coverage_targets"]
    assert set(targets["properties"]) == {"ILO-01", "ILO-02"}
    assert "required" not in targets and targets["minProperties"] == 1, (
        "which objectives the plan promises stays the model's")
    assert targets["additionalProperties"] is False
    # The task schema is declared once and every row refers to it, so the
    # spec does not grow by a task schema per module.
    assert plan["$defs"]["assessment_task"]["properties"]["covers_objectives"]["items"]["enum"] == \
        ["ILO-01", "ILO-02"]
    assert first["properties"]["assessment_tasks"]["items"] == {"$ref": "#/$defs/assessment_task"}
    step = STEP_BY_NAME["assessment"]
    params = tools.spec_parameters(
        grammar.tighten_specs(tools.tool_specs(step), vocab), "submit_assessment_plan")
    assert "assessment_task" in params["$defs"] and "$defs" not in params["properties"]["assessment_plan"]
    many = grammar.Vocabulary(objectives=vocab.objectives, modules=tuple(
        {"id": f"MOD-0{i}", "minutes": 200} for i in range(1, 6)))
    base = json.dumps(tools.tool_specs(step))
    tight = json.dumps(grammar.tighten_specs(tools.tool_specs(step), many))
    assert len(tight) < 1.5 * len(base), (len(base), len(tight))
    assert targets["properties"]["ILO-01"]["items"]["enum"] == \
        ARTIFACT_SCHEMAS["assessment_plan"]["properties"]["lo_coverage_targets"][
            "additionalProperties"]["items"]["enum"]


def test_a_light_assignment_becomes_constants_and_a_count_becomes_bounds():
    """What a light work set FIXES — objective, category, task, type, and a
    level at or above the objective's — is said as `const`/`enum` per row, and
    the number of rows is the number of items."""
    state = _design("graph")
    step = STEP_BY_NAME["assessment"]
    sets, _stats = fanout.SPECS["assessment"].plan_sets(
        state, {"assessment_plan": _ASSESSMENT["assessment_plan"],
                "modules": fanout.course_modules(state)}, "light")
    work_set = sets[0]
    rows = work_set.payload["assigned_items"]
    assert rows and rows[0]["objective"] == "ILO-01" and rows[0]["level"] == "apply"
    dev_step = fanout.set_step(fanout.SPECS["assessment"], work_set, step, state)
    assert dev_step.work_set is work_set
    specs = grammar.tighten_specs(tools.tool_specs(dev_step), grammar.Vocabulary.of(state),
                                  work_set=work_set, mode="light")
    params = tools.spec_parameters(specs, "submit_assessment_tools")
    items = params["properties"]["assessment_tools"]
    assert items["minItems"] == items["maxItems"] == len(rows) and items["items"] is False
    row = items["prefixItems"][0]["properties"]
    assert row["aligned_objective"]["const"] == "ILO-01"
    assert row["plan_category"]["const"] == "summative"
    assert row["task_id"]["const"] == "AT-01"
    assert row["type"]["const"] == rows[0]["type"]
    assert row["required_cognitive_process"]["enum"] == ["apply", "analyze", "evaluate", "create"]


def test_an_activity_block_fixes_module_objective_and_level_per_row():
    state = _design("graph")
    step = STEP_BY_NAME["activities"]
    sets, _stats = fanout.SPECS["activities"].plan_sets(
        state, {"modules": fanout.course_modules(state)}, "light")
    block = next(ws for ws in sets if ws.module_id == "MOD-02")
    rows = block.payload["assigned_activities"]
    params = grammar.tighten_parameters(
        tools.submit_parameters(fanout.set_step(fanout.SPECS["activities"], block, step, state)),
        grammar.Vocabulary.of(state), work_set=block, mode="light")
    activities = params["properties"]["learning_activities"]
    assert activities["minItems"] == activities["maxItems"] == len(rows)
    first = activities["prefixItems"][0]["properties"]
    assert first["module_id"]["const"] == "MOD-02"
    assert first["aligned_objectives"]["prefixItems"] == [{"const": "ILO-02"}]
    assert first["aligned_objectives"]["items"]["enum"] == ["ILO-01", "ILO-02"]
    assert first["learner_cognitive_process"]["enum"] == ["analyze", "evaluate", "create"]


def test_a_light_material_is_bound_to_its_module_s_media_and_never_to_a_length():
    state = _design("graph")
    specialists.commit_content(state, TrajectoryLogger(), {"media_selections": [
        {"id": "MS-01", "media_type": "slides", "for_modules": ["MOD-01"],
         "respects_constraints": ["CON-01"]},
        {"id": "MS-02", "media_type": "video", "for_modules": ["MOD-02"],
         "respects_constraints": ["CON-01"]}]})
    step = STEP_BY_NAME["content"]
    sets, _stats = fanout.SPECS["content"].plan_sets(
        state, {"modules": fanout.course_modules(state),
                "media_selections": fanout.media_selections(state)}, "light")
    unit = next(ws for ws in sets if ws.module_id == "MOD-01")
    params = grammar.tighten_parameters(
        tools.submit_parameters(fanout.set_step(fanout.SPECS["content"], unit, step, state)),
        grammar.Vocabulary.of(state), work_set=unit, mode="light")
    item = params["properties"]["learner_materials"]["items"]["properties"]
    assert item["linked_module"]["const"] == "MOD-01"
    assert item["type"]["enum"] == ["slides"]
    # The depth of a light material is TOLD, never decoded: a length bound is
    # a hard stop mid-word.
    assert "maxLength" not in item["content"]


def test_a_session_guide_may_schedule_only_what_its_block_was_handed():
    block = dev_plans.WorkSet(set_id="SB-MOD-01", payload={
        "activity_ids": ["TLA-0101", "TLA-0102"], "material_ids": ["MAT-0101"],
        "expected_sessions": 1, "first_session": 1})
    guide = grammar.artifact_property("session_guides", "array", True,
                                      grammar.Vocabulary(), work_set=block)
    assert guide["items"]["properties"]["activity_ids"]["items"]["enum"] == ["TLA-0101", "TLA-0102"]
    assert guide["items"]["properties"]["material_ids"]["items"]["enum"] == ["MAT-0101"]
    assert guide["minItems"] == 1 and "maxItems" not in guide, "how many sessions is the writer's"


# ── it compiles ─────────────────────────────────────────────────────────────

def test_every_schema_the_module_can_produce_uses_only_compiled_keywords():
    state = _design("graph")
    vocab = grammar.Vocabulary.of(state, course_hours=24)
    produced = []
    for step in STEPS:
        produced += grammar.tighten_specs(tools.tool_specs(step), vocab)
        spec = fanout.SPECS.get(step.name)
        if spec is None:
            continue
        parsed = {"assessment_plan": _ASSESSMENT["assessment_plan"],
                  "modules": fanout.course_modules(state), "media_selections": []}
        for mode in ("light", "full"):
            sets, _ = spec.plan_sets(state, parsed, mode)
            for ws in sets:
                dev = fanout.set_step(spec, ws, step, state)
                produced += grammar.tighten_specs(tools.tool_specs(dev), vocab,
                                                  work_set=ws, mode=mode)
    produced += grammar.tighten_specs(tools.react_specs(STEPS, frozenset()), vocab)
    assert produced
    for spec in produced:
        assert grammar.xgrammar_safe(spec["function"]["parameters"]) == [], spec["function"]["name"]
        json.dumps(spec)     # and it serialises
    assert grammar.xgrammar_safe({"type": "array", "uniqueItems": True}) == ["$: uniqueItems"]
    assert grammar.xgrammar_safe({"type": "string", "pattern": "x", "maxLength": 3})


def test_the_base_specs_are_not_mutated_by_tightening():
    """The golden fixture pins `tool_specs`; tightening returns new objects."""
    step = STEP_BY_NAME["outcomes"]
    base = tools.tool_specs(step)
    before = json.dumps(base, sort_keys=True)
    grammar.tighten_specs(base, grammar.Vocabulary.of(_design("graph")))
    assert json.dumps(base, sort_keys=True) == before
    assert json.dumps(ARTIFACT_SCHEMAS, sort_keys=True) == json.dumps(
        tools.ARTIFACT_SCHEMAS, sort_keys=True)


def test_the_decoder_schema_closes_every_object_but_an_open_map():
    """Pass 2 decodes under closed objects, or a grammar that allows any key
    allows a reply that never ends (four of five `operator_manual` passes ran
    to the completion cap); the bound contract stays open."""
    vocab = grammar.Vocabulary.of(_design("graph"))
    bound = tools.spec_parameters(
        grammar.tighten_specs(tools.tool_specs(STEP_BY_NAME["assessment"]), vocab),
        "submit_assessment_plan")
    assert bound["additionalProperties"] is True
    closed = grammar.for_decoder(bound)
    assert closed["additionalProperties"] is False
    plan = closed["properties"]["assessment_plan"]
    assert plan["additionalProperties"] is False
    assert plan["properties"]["expected_evidence"]["additionalProperties"] == {"type": "string"}, (
        "an open map keeps its value schema")
    assert closed["$defs"]["assessment_task"]["additionalProperties"] is False
    assert grammar.xgrammar_safe(closed) == []


def test_the_bound_specs_come_out_of_the_transcript_budget():
    """The specs go out with every request; a budget that ignored them let
    the history fill the window the specs then overflowed."""
    from alignmentgraph_isd import HarnessRunConfig
    from alignmentgraph_isd.core.agentic.transcript import history_budget, specs_chars

    config = HarnessRunConfig(llm_context_window=16384, llm_completion_reserve=8192)
    specs = grammar.tighten_specs(tools.react_specs(STEPS, frozenset()),
                                  grammar.Vocabulary.of(_design("graph")))
    whole = history_budget(config)
    assert history_budget(config, specs) == max(whole - specs_chars(specs), whole // 4)
    assert history_budget(config, specs) < whole
