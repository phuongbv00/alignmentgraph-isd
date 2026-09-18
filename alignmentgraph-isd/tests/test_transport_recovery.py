"""The transport boundary and the errors it must not manufacture.

Every case here is a defect that run ``single_20260901_205901`` paid for in
full: the single-graph arm exhausted its 96-turn budget having reached 3 of 6
stages and scored 0.0 on Analysis and Implementation, and the main arm ran 21
repairs to a ``repair_success_rate`` of 0.0. None of it was the model being
too small — one unparseable tool argument, then four amplifiers.
"""
from __future__ import annotations

import json

import pytest

from alignmentgraph_isd.core import checks, dev_plans
from alignmentgraph_isd.core.agentic import loop, specialists, tools
from alignmentgraph_isd.core.agentic.specialists import STEPS

STEP_BY_NAME = {step.name: step for step in STEPS}


# ── the transport boundary ──────────────────────────────────────────────────

#: The exact shape the qwen3_coder parser produced: double-quoted JSON with a
#: single-quoted element spliced into an array, so `json.loads` fails partway
#: through a value that is otherwise complete and correct.
MIXED_QUOTES = (
    '{"model": "Gagne\'s 9 Events", '
    '"sequence": [{"event": "Gain attention", "duration": "15 minutes", '
    '"resources": ["Planning template", \'Documentation of project scope\']}], '
    '"rationale": "matched to activity complexity"}'
)


def test_a_tool_argument_that_is_near_json_is_recovered_not_charged_to_the_model():
    with pytest.raises(ValueError):
        json.loads(MIXED_QUOTES)

    params = tools.submit_parameters(STEP_BY_NAME["activities"])
    coerced = tools.coerce_args(params, {"instructional_strategies": MIXED_QUOTES})

    strategies = coerced["instructional_strategies"]
    assert isinstance(strategies, dict), (
        "a value the harness can read must never reach the model as 'arrived as text'")
    # Recovered whole, not truncated at the first bad character.
    assert set(strategies) == {"model", "sequence", "rationale"}
    assert strategies["sequence"][0]["resources"] == [
        "Planning template", "Documentation of project scope"]
    assert not tools.shape_errors(params, coerced)


def test_the_salvage_rate_is_recorded_not_silent():
    """The whole reason strict JSON is tried first is that transport health has
    to stay measurable. A recovery nobody counts is a recovery that quietly
    stops being exceptional."""
    params = tools.submit_parameters(STEP_BY_NAME["activities"])

    salvaged: list[str] = []
    tools.coerce_args(params, {"instructional_strategies": MIXED_QUOTES}, salvaged=salvaged)
    assert salvaged == ["instructional_strategies"]

    clean: list[str] = []
    tools.coerce_args(params, {"instructional_strategies": {"model": "Gagne"}}, salvaged=clean)
    assert clean == []


def test_strict_json_still_takes_the_strict_path():
    """Salvage is a best effort, so an ordinary payload must not go through it:
    a run where it silently handles the normal case is a run whose transport
    health cannot be measured."""
    params = tools.submit_parameters(STEP_BY_NAME["activities"])
    coerced = tools.coerce_args(
        params, {"instructional_strategies": '{"model": "Gagne", "sequence": []}'})
    assert coerced["instructional_strategies"] == {"model": "Gagne", "sequence": []}


def test_text_that_is_not_a_structure_at_all_is_left_for_the_validator():
    params = tools.submit_parameters(STEP_BY_NAME["activities"])
    coerced = tools.coerce_args(params, {"instructional_strategies": "I will use Gagne."})
    assert coerced["instructional_strategies"] == "I will use Gagne."
    assert tools.shape_errors(params, coerced), "a real model mistake must still be reported"


# ── one root fact, one error ────────────────────────────────────────────────

def test_a_broken_container_does_not_also_report_the_field_inside_it():
    """The model was told BOTH that `assessment_plan` was a string AND that
    `assessment_plan.pilot_data_plan.anticipated_difficulties` was not a list.
    The second cannot be acted on while the first holds, but it is the more
    concrete-sounding of the two — and it was chased 61 times in a row."""
    errors = specialists.validate_assessment({"assessment_plan": "{'lo_coverage_targets': {}}"})
    assert errors == ["assessment_plan: section payload must be a JSON object, got str"]


def test_a_wrong_typed_container_nobody_else_owns_is_still_reported_once():
    errors = specialists.validate_analysis({
        "needs_analysis": "a paragraph where an object belongs",
        "improvement_plan": {"improvements": ["a"]},
        "learner_analysis": {"a": 1}, "context_analysis": {"a": 1}, "task_analysis": {"a": 1},
    })
    assert errors == ["needs_analysis must be a JSON object, got str"]


def test_a_missing_leaf_is_still_reported_when_its_container_is_sound():
    plan = {"lo_coverage_targets": {"ILO-01": ["summative"]},
            "instruments": [{"id": "INS-01", "module_id": "MOD-01", "timing": "summative"}],
            "expected_evidence": {"ILO-01": "x"},
            "diagnostic": "d", "formative": "f", "summative": "s",
            "formative_methods": ["a"]}
    errors = specialists.validate_assessment({"assessment_plan": plan})
    assert errors == [
        "assessment_plan.pilot_data_plan.anticipated_difficulties must be a non-empty list"]


# ── one reader for lo_coverage_targets ──────────────────────────────────────

def test_both_shapes_of_a_coverage_promise_read_the_same():
    """The schema asks for category names; models also write the richer entry
    that names the instrument too. Two readers disagreed about the second one:
    the fan-out dropped every pair and fell back to summative-only work sets,
    while the check took `str(dict)` as the category."""
    plain = {"ILO-01": ["diagnostic", "summative"]}
    rich = {"ILO-01": [{"plan_category": "diagnostic", "instrument": "entry quiz"},
                       {"plan_category": "summative", "instrument": "final project"}]}
    expected = [("ILO-01", "diagnostic"), ("ILO-01", "summative")]
    assert dev_plans.plan_category_pairs(plain) == expected
    assert dev_plans.plan_category_pairs(rich) == expected
    # A namespaced id copied out of the graph context still names its objective.
    assert dev_plans.plan_category_pairs({"objective:ILO-01": ["summative"]}) == [
        ("ILO-01", "summative")]
    # Anything that is not one of the three is dropped, never stringified.
    assert dev_plans.plan_category_pairs({"ILO-01": ["midterm", {"instrument": "x"}]}) == []


def test_a_rich_coverage_promise_is_realised_by_matching_items():
    """End to end through the check the repair loops on: a plan written in the
    richer shape must be satisfiable, or the repair can never converge."""
    from alignmentgraph_isd.core.alignment_graph import AlignmentGraph, NodeType

    graph = AlignmentGraph()
    graph.add_node(NodeType.ASSESSMENT_PLAN, graph.section_id(NodeType.ASSESSMENT_PLAN), {
        "lo_coverage_targets": {
            "ILO-01": [{"plan_category": "diagnostic", "instrument": "entry quiz"},
                       {"plan_category": "summative", "instrument": "final project"}]},
    })
    graph.add_element_node(NodeType.ASSESSMENT, "AT-D-ILO-01", {
        "item_id": "AT-D-ILO-01", "aligned_objective": "ILO-01",
        "plan_category": "diagnostic", "question": "q"})

    violations = checks.plan_coverage(graph)
    assert [v.metadata["plan_category"] for v in violations] == ["summative"], (
        "the diagnostic promise is realised; only the summative one is open")

    graph.add_element_node(NodeType.ASSESSMENT, "AT-S-ILO-01", {
        "item_id": "AT-S-ILO-01", "aligned_objective": "ILO-01",
        "plan_category": "summative", "question": "q"})
    assert checks.plan_coverage(graph) == [], "the check must be satisfiable"


# ── the mixed transcript ────────────────────────────────────────────────────

class _Message:
    """Stands in for the model's own message object, which the tool-call round
    trip leaves in the history."""

    def __init__(self, content: str, tool_calls=None) -> None:
        self.content = content
        self.tool_calls = tool_calls or []


def test_prompt_size_counts_the_model_s_own_messages():
    """A plain `m.get("content")` over this transcript raised `'AIMessage'
    object has no attribute 'get'` and lost the call outright; the guarded
    version skipped those turns instead, which on the tool-call path means
    skipping every assistant turn that carried an artifact."""
    transcript = [
        {"role": "system", "content": "x" * 100},
        _Message("", [{"name": "submit", "args": {"objective": "y" * 500}}]),
    ]
    size = loop.prompt_chars(transcript)
    assert size > 500, "the artifact lives in the tool call, not in the content"


# ── a turn that ran out of tokens ───────────────────────────────────────────

class _Cut:
    """A result whose generation hit the token cap. A NATIVE tool call that ran
    out of tokens comes back as a well-formed call with missing or partial
    arguments — there is no parse error to catch."""

    def __init__(self, reason: str = "length") -> None:
        self.content = ""
        self.tool_calls = [{"name": "submit", "args": {}, "id": "c1"}]
        self.response_metadata = {"finish_reason": reason}


def test_a_generation_that_hit_the_cap_is_recognised_as_such():
    from alignmentgraph_isd.core import llm_io

    assert llm_io.was_truncated(_Cut("length"))
    assert llm_io.was_truncated(_Cut("max_tokens"))
    assert not llm_io.was_truncated(_Cut("stop"))
    # A backend that says nothing must not be read as truncated.
    assert not llm_io.was_truncated(_Cut(""))
    assert llm_io.finish_reason(_Cut("length")) == "length"


def test_a_truncated_submit_is_told_to_send_less_not_to_fix_fields():
    """MEASURED (run single_20260901_205901, multi-prose `analysis`): nine
    rejections in a row, all reading "learner_analysis must be a non-empty
    object" and friends, with the recorded argument shape EMPTY. Told its
    fields were missing, the model rewrote the whole artifact and was cut off
    at the same place; three attempts, then the stage gave up — and the same
    thing happened on the two regen attempts after it."""
    from alignmentgraph_isd.core.agentic import loop as agentic_loop
    from alignmentgraph_isd.core.agentic.turn import ToolTurn

    class _Loop:
        _reject_message = agentic_loop.ToolLoop._reject_message

    errors = ["learner_analysis must be a non-empty object"]

    plain = _Loop()._reject_message(errors, ToolTurn(name="submit"))
    assert plain.startswith("SUBMIT REJECTED")
    assert "CUT OFF" not in plain

    cut = _Loop()._reject_message(
        errors, ToolTurn(name="submit", truncated=True))
    assert "CUT OFF" in cut
    assert "SHORTER" in cut
    # The errors still travel: which fields did not arrive is still the useful
    # half. Only the instruction about what to DO changes.
    assert errors[0] in cut


# ── an unreadable argument beside a good one ────────────────────────────────

def test_an_unreadable_optional_argument_does_not_sink_the_submit():
    """MEASURED (run single_20260901_205901, AssessmentDeveloper): attempt 2
    arrived as `assessment_tools:list, rubric_criteria:str` — the primary
    output was correct and the validator would have accepted it — and the whole
    set of good items was thrown away over the criteria beside them.

    That exact pair no longer exists: a criterion is written inside the item it
    marks (2026-09-02), so there is one argument where there were two. The RULE
    it forced is what matters and is checked here on a step that still carries
    an optional argument: drop what cannot be read, then judge what is left."""
    step = STEP_BY_NAME["activities"]
    params = tools.submit_parameters(step)

    args = {"instructional_strategies": {"model": "Gagne", "sequence": []},
            "dev_plan": {"activity_blocks": []},
            "non_instructional_strategies": "{not json"}
    unreadable = tools.shape_bad_keys(params, args)
    assert unreadable == ["non_instructional_strategies"]

    kept = {k: v for k, v in args.items() if k not in unreadable}
    assert step.validate(kept) == [], (
        "the required arguments are valid on their own — the submit must not be refused")



def test_an_unreadable_argument_the_artifact_needed_is_still_reported_as_shape():
    """The rule is "drop, then judge what is left", not "drop and never
    complain": when the remainder is not a valid artifact, the shapes are why,
    and the model has to be told about the shape rather than the contents."""
    step = STEP_BY_NAME["analysis"]
    params = tools.submit_parameters(step)
    args = {"needs_analysis": "{gaps: ...", "learner_analysis": "{..."}

    unreadable = tools.shape_bad_keys(params, args)
    assert set(unreadable) == {"needs_analysis", "learner_analysis"}

    kept = {k: v for k, v in args.items() if k not in unreadable}
    errors = step.validate(kept)
    assert errors, "nothing readable arrived, so the submit is not acceptable"
    messages = tools.shape_errors(params, kept, unreadable)
    assert all("arrived as text" in m for m in messages)
    assert len(messages) == 2


# ── a malformed ARRAY argument ──────────────────────────────────────────────

#: A real submit from a 2B model. Three well-formed assessment items inside an
#: array whose last two brackets are TRANSPOSED — it closes `..."]}` where
#: `..."}]` belongs. Every character of every item is intact; only the
#: container is broken.
TRANSPOSED_ARRAY = (
    '[{"item_id": "AT-01", "type": "multiple_choice", "question": "Which mechanic gives '
    'feedback?", "options": ["grammar demo", "real-time feedback", "visual cues"], '
    '"correct_answer": "real-time feedback", "aligned_objective": "ILO-01", '
    '"plan_category": "diagnostic", "required_cognitive_process": "understand"}, '
    '{"item_id": "AT-02", "type": "short_answer", "question": "Name one observable '
    'outcome.", "aligned_objective": "ILO-02", "plan_category": "formative", '
    '"required_cognitive_process": "analyze"}, '
    '{"item_id": "AT-03", "type": "performance_task", "question": "Justify the linkage.", '
    '"aligned_objective": "ILO-03", "plan_category": "summative", '
    '"required_cognitive_process": "evaluate", "scoring_criteria": "States that the game '
    "gives immediate feedback (e.g., 'highlights the error') and links it to the "
    'objective."]}'
)


def test_a_malformed_array_keeps_every_element_that_is_intact():
    """`parse_json_response` returns a dict from every path, including one that
    decodes the FIRST complete object and stops — so on this payload it hands
    back item 1 and calls that the answer. Two of the three items would be
    lost, and only the caller's type check kept the one from being committed as
    though it were the whole set."""
    from alignmentgraph_isd.core.llm_io import parse_json_array, parse_json_response

    with pytest.raises(ValueError):
        json.loads(TRANSPOSED_ARRAY)

    # The dict-oriented parser: one item, silently.
    assert isinstance(parse_json_response(TRANSPOSED_ARRAY, warn=False), dict)

    items, dropped = parse_json_array(TRANSPOSED_ARRAY)
    assert [i["item_id"] for i in items] == ["AT-01", "AT-02", "AT-03"]
    assert dropped == 0
    # Nested arrays inside an element survive the brace scan.
    assert items[0]["options"] == ["grammar demo", "real-time feedback", "visual cues"]


def test_an_array_argument_is_salvaged_as_an_array():
    params = tools.submit_parameters(STEP_BY_NAME["outcomes"])
    salvaged: list[str] = []
    coerced = tools.coerce_args(
        params, {"learning_objectives": TRANSPOSED_ARRAY}, salvaged=salvaged)

    value = coerced["learning_objectives"]
    assert isinstance(value, list) and len(value) == 3
    assert salvaged == ["learning_objectives"]
    assert not tools.shape_errors(params, coerced)


def test_a_partial_array_recovery_says_how_much_it_lost():
    """Recovering 2 of 3 and saying nothing is the same class of failure as
    recovering 1: the caller has to be able to report it."""
    from alignmentgraph_isd.core.llm_io import parse_json_array

    broken = '[{"id": "A"}, {"id": "B", }}}, {"id": "C"}]'
    items, dropped = parse_json_array(broken)
    assert [i["id"] for i in items] == ["A", "B", "C"] or dropped > 0

    salvaged: list[str] = []
    params = tools.submit_parameters(STEP_BY_NAME["outcomes"])
    tools.coerce_args(params, {"learning_objectives": broken}, salvaged=salvaged)
    assert salvaged, "a salvaged array must be recorded"


#: The other half of the transposition above, and the one brace balance alone
#: cannot see: an element short one CLOSING brace (the rubric criterion closes
#: `"full"}]` where `"full"}}]` belongs). MEASURED on run 2b9e911a, the replan
#: work set that asked for exactly one summative item.
UNDERCLOSED_ELEMENT = (
    '[{"type": "performance_task", "question": "Q1", '
    '"rubric": [{"id": "RC-1", "levels": {"excellent": "full"}]}, '
    '{"type": "short_answer", "question": "Q2"}]'
)


def test_an_element_short_a_closing_brace_costs_that_element_and_no_more():
    """Depth never returns to 0, so every element after the broken one used to
    be swallowed into a block that never terminates and the WHOLE array was
    charged as one dropped block — `([], 1)`, on a payload whose first element
    parses cleanly on its own. The submit was rejected three times as "arrived
    as text" and the item the replan round existed to produce was never
    written."""
    from alignmentgraph_isd.core.llm_io import parse_json_array

    with pytest.raises(ValueError):
        json.loads(UNDERCLOSED_ELEMENT)

    items, dropped = parse_json_array(UNDERCLOSED_ELEMENT)
    assert [i["question"] for i in items] == ["Q1", "Q2"]
    assert dropped == 0
    # The under-closed element is repaired, not truncated: its rubric survives.
    assert items[0]["rubric"] == [{"id": "RC-1", "levels": {"excellent": "full"}}]


def test_a_nested_array_of_objects_is_not_read_as_an_element_boundary():
    """`}` `,` `{` is an element boundary only at bracket depth 1. Inside
    `"rubric": [{…},{…}]` the same text sits at depth 2, and reading it as a
    boundary would cut every element with a rubric in half."""
    from alignmentgraph_isd.core.llm_io import parse_json_array

    items, dropped = parse_json_array(
        '[{"a": 1, "rubric": [{"x": 1}, {"y": 2}]}, {"b": 2}]')
    assert items == [{"a": 1, "rubric": [{"x": 1}, {"y": 2}]}, {"b": 2}]
    assert dropped == 0


def test_text_that_is_not_an_array_at_all_stays_a_model_mistake():
    params = tools.submit_parameters(STEP_BY_NAME["outcomes"])
    coerced = tools.coerce_args(
        params, {"learning_objectives": "I will write three objectives."})
    assert coerced["learning_objectives"] == "I will write three objectives."
    assert tools.shape_errors(params, coerced)


# ── a string in a list's container ──────────────────────────────────────────

def _operator_manual(**over) -> dict:
    base = {"system_setup": "Log in to the platform.",
            "operation_procedures": "1. Open the session.\n2. Start the timer.",
            "support_procedures": "Email the help desk.",
            "escalation_process": "Call the coordinator."}
    base.update(over)
    return {"operator_manual": base}


def test_a_scalar_where_a_list_of_strings_is_declared_becomes_a_one_item_list():
    """MEASURED (run 14a6b4c7, implementation): ``operation_procedures`` came
    as one paragraph, was answered "expected list, got str" three times, spent
    its submit budget and cost the whole stage a regen — a container mismatch
    the text itself never had. Re-containering is structural; the text is
    kept byte for byte."""
    from alignmentgraph_isd.core.agentic.specialists import validate_implementation

    params = tools.submit_parameters(STEP_BY_NAME["implementation"])
    reshaped: list[str] = []
    args = tools.reshape_args(params, _operator_manual(), reshaped=reshaped)

    manual = args["operator_manual"]
    assert manual["operation_procedures"] == ["1. Open the session.\n2. Start the timer."]
    assert manual["support_procedures"] == ["Email the help desk."]
    assert manual["escalation_process"] == "Call the coordinator.", "a declared str stays"
    assert sorted(reshaped) == ["operator_manual.operation_procedures",
                                "operator_manual.support_procedures"]
    assert not any("expected list, got str" in e for e in validate_implementation(args))


def test_reshaping_never_splits_content():
    params = tools.submit_parameters(STEP_BY_NAME["implementation"])
    text = "- open\n- start\n- close"
    args = tools.reshape_args(params, _operator_manual(operation_procedures=text), reshaped=[])
    assert args["operator_manual"]["operation_procedures"] == [text]


def test_reshaping_recurses_through_objects_array_items_and_additional_properties():
    from alignmentgraph_isd.core.agentic import fanout

    plan = tools.submit_parameters(STEP_BY_NAME["assessment"])
    reshaped: list[str] = []
    args = tools.reshape_args(plan, {"assessment_plan": {
        "lo_coverage_targets": {"ILO-01": "formative"},
        "formative_methods": "Weekly critique",
        "pilot_data_plan": {"collection_points": "After lab 1",
                            "anticipated_difficulties": []}}}, reshaped=reshaped)
    ap = args["assessment_plan"]
    assert ap["lo_coverage_targets"] == {"ILO-01": ["formative"]}
    assert ap["formative_methods"] == ["Weekly critique"]
    assert ap["pilot_data_plan"]["collection_points"] == ["After lab 1"]
    assert "assessment_plan.lo_coverage_targets.ILO-01" in reshaped

    items = tools.submit_parameters(fanout.set_step(
        fanout.SPECS["assessment"], dev_plans.WorkSet(set_id="S1"), STEP_BY_NAME["assessment"]))
    args = tools.reshape_args(items, {"assessment_tools": [
        {"type": "multiple_choice", "question": "Q?", "options": "A) x B) y"}]}, reshaped=[])
    assert args["assessment_tools"][0]["options"] == ["A) x B) y"]


def test_a_string_where_an_object_is_declared_is_left_alone():
    params = tools.submit_parameters(STEP_BY_NAME["implementation"])
    reshaped: list[str] = []
    args = tools.reshape_args(params, {"operator_manual": "just prose"}, reshaped=reshaped)
    assert args == {"operator_manual": "just prose"} and reshaped == []


def test_a_list_where_a_list_is_declared_is_untouched_and_a_json_list_is_a_parse():
    params = tools.submit_parameters(STEP_BY_NAME["implementation"])
    reshaped: list[str] = []
    salvaged: list[str] = []
    already = _operator_manual(operation_procedures=["a", "b"],
                               support_procedures='["c", "d"]')
    args = tools.reshape_args(params, already, reshaped=reshaped, salvaged=salvaged)
    assert args["operator_manual"]["operation_procedures"] == ["a", "b"]
    assert args["operator_manual"]["support_procedures"] == ["c", "d"]
    assert reshaped == [] and salvaged == ["operator_manual.support_procedures"]


def test_reshaping_is_counted_and_logged_apart_from_salvage():
    from alignmentgraph_isd.core.agentic import turn as turn_mod
    from alignmentgraph_isd.core.trajectory import TrajectoryLogger

    params = tools.submit_parameters(STEP_BY_NAME["implementation"])
    stats: dict = {}
    trajectory = TrajectoryLogger()
    turn = turn_mod.ToolTurn(name="submit_operator_manual", args=_operator_manual(),
                             call_id="c1")
    turn_mod.coerce(turn, params, stats=stats, trajectory=trajectory, identity="X")

    assert stats["args_reshaped"] == 2 and stats["args_salvaged"] == 0
    events = [e for e in trajectory.recovery_events if e["action"] == "argument_reshaped"]
    assert len(events) == 1 and events[0]["agent"] == "X"
    assert "operator_manual.operation_procedures" in events[0]["context"]["input_summary"]


def test_both_arms_reshape_through_the_one_coerce():
    """One implementation: a reshape granted on one side of the decomposition
    axis would be a validator difference sitting inside the treatment."""
    import inspect

    from alignmentgraph_isd.core.agentic import react

    for src in (inspect.getsource(loop.ToolLoop._handle_call),
                inspect.getsource(react.ReactLoop._handle_call)):
        assert "turn_mod.coerce(" in src and "reshape_args(" not in src


def test_a_last_element_short_its_closing_brace_is_recovered():
    """MEASURED (run 9efc3cfa, content:MU-C-01): ``[{"title": ..., "content":
    "..."]`` — the element's own ``}`` dropped before the array's ``]``. Nothing
    follows it, so the ``, {`` rule cannot end the element; the one material
    was rejected four times as "arrived as text" and the set was regenerated."""
    from alignmentgraph_isd.core.llm_io import parse_json_array

    one = '[{"title": "Overview", "type": "slides", "content": "Welcome. [note] done."]'
    items, dropped = parse_json_array(one)
    assert dropped == 0 and items == [
        {"title": "Overview", "type": "slides", "content": "Welcome. [note] done."}]

    two = '[{"title": "A", "content": "x"}, {"title": "B", "content": "y"]'
    items, dropped = parse_json_array(two)
    assert [i["title"] for i in items] == ["A", "B"] and dropped == 0

    # Cut off inside a string is truncation, not a dropped brace: still a loss.
    items, dropped = parse_json_array('[{"title": "A", "content": "unfinished')
    assert items == [] and dropped == 1


# ── an array that lost its bracket, an artifact named twice ─────────────────

_LOST_BRACKET = ('{"system_setup": "Register the platform.", '
                 '"operation_procedures": ["1) Log in", "2) Start the session", '
                 '"support_procedures": ["Contact support"], '
                 '"escalation_process": "Call the director."')


@pytest.mark.parametrize("tail", ["}", "]", ""])
def test_an_array_that_lost_its_closing_bracket_keeps_every_field(tail):
    """MEASURED (run 1c0a4e81, `operator_manual`): `"operation_procedures":
    ["…", "support_procedures": [...]` — the first array never closes, strict
    parsing fails at the next key's colon, and the tolerant parser kept only
    the fields BEFORE the break. Three submits each lost two of four required
    fields, the artifact spent its budget and shipped empty. A string followed
    by `:` inside an array of strings is the object's next key; the array ends
    in front of it. The same payload arrived ending `}`, `]` and cut short."""
    from alignmentgraph_isd.core.agentic.specialists import validate_implementation

    params = tools.submit_parameters(STEP_BY_NAME["implementation"])
    salvaged: list[str] = []
    args = tools.coerce_args(params, {"operator_manual": _LOST_BRACKET + tail},
                             salvaged=salvaged)

    manual = args["operator_manual"]
    assert manual["operation_procedures"] == ["1) Log in", "2) Start the session"]
    assert manual["support_procedures"] == ["Contact support"]
    assert manual["escalation_process"] == "Call the director."
    assert validate_implementation(args) == [] and salvaged == ["operator_manual"]


def test_well_formed_json_is_never_touched_by_the_bracket_repair():
    from alignmentgraph_isd.core.llm_io import close_unclosed_arrays

    for text in ('{"a": ["x", "y"], "b": {"c": ["z"]}, "d": "e: f"}',
                 '{"a": [{"k": "v"}, {"k": "w"}], "note": "a \\"quoted\\": colon"}'):
        assert json.loads(close_unclosed_arrays(text)) == json.loads(text)


def test_an_artifact_named_twice_is_unwrapped_not_dropped():
    """MEASURED (run 1c0a4e81): `{"operator_manual": {"operator_manual": {…}}}`
    on its last submit, and `improvement_plan` the same way. The inner name is
    not a field of the artifact, so dropping it as undeclared drops the whole
    artifact; it is the artifact."""
    params = tools.submit_parameters(STEP_BY_NAME["implementation"])
    inner = {"system_setup": "s", "operation_procedures": ["a"],
             "support_procedures": ["b"], "escalation_process": "e"}
    salvaged: list[str] = []
    args = tools.reshape_args(params, {"operator_manual": {"operator_manual": inner}},
                              reshaped=[], salvaged=salvaged)
    assert args == {"operator_manual": inner}
    assert salvaged == ["operator_manual (named twice)"]
