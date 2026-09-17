"""Unit tests of the tool loop (core/agentic/loop.py): act→observe over the
graph, deterministic submit validation, budgets, and what a step does when it
exhausts them."""
from __future__ import annotations

import json
from dataclasses import replace

import pytest

from alignmentgraph_isd import HarnessRunConfig
from alignmentgraph_isd.core.agentic import loop as loop_module
from alignmentgraph_isd.core.agentic.client import AgenticLLM
from alignmentgraph_isd.core.agentic.loop import ToolLoop
from alignmentgraph_isd.core.agentic import budget, protocol, specialists, tools
from alignmentgraph_isd.core.agentic.specialists import STEPS
from alignmentgraph_isd.core.alignment_graph import AlignmentGraph, NodeType
from alignmentgraph_isd.core.trajectory import TrajectoryLogger

from conftest import load_brief

STEP_BY_NAME = {step.name: step for step in STEPS}


class _Result:
    def __init__(self, content: str = "", tool_calls: list | None = None) -> None:
        self.content = content
        self.tool_calls = tool_calls or []
        self.usage_metadata = None


def batch(*calls: dict) -> dict:
    """SEVERAL native tool calls in ONE model reply — what a model that
    batches its reads sends. Each is a :func:`call` marker."""
    return {"__batch__": list(calls)}


def call(name: str, args: dict) -> dict:
    """A scripted NATIVE tool call turn (what ``.tool_calls`` carries).

    ``call("submit", {...})`` is shorthand: a stage binds one submit tool per
    artifact (``tools.submit_specs``), so the plain name is resolved to the
    tool that carries the FIRST key of the payload — resolved by
    :class:`ScriptedModel` against what the loop actually bound, so a wrapped
    or mis-keyed payload still lands on a real tool and is judged by the loop
    rather than bouncing off an unknown-tool error the test is not about.

    A real model sends one artifact per call. These tests are about the loop's
    mechanics — coercion, rejection, budget, history — and keeping their
    payloads whole keeps each one about the thing it is named after; the
    parts/completion behaviour has its own tests, which name tools
    explicitly."""
    return {"__tool__": name, "args": args}


class ScriptedModel:
    """Returns a fixed sequence of responses, shared across factory calls.

    A response is either a :func:`call` marker (the model called a tool) or a
    string (the model answered with text and called nothing) — the two shapes
    the loop has to tell apart under native tool calling."""

    def __init__(self, responses: list) -> None:
        self._responses = list(responses)
        self.invocations = 0
        self.bound_tools: list | None = None

    def bind(self, **_kwargs) -> "ScriptedModel":
        return self

    def bind_tools(self, specs) -> "ScriptedModel":
        self.bound_tools = list(specs)
        return self

    def _submit_tool(self, args) -> str:
        """Which bound submit tool a plain ``submit`` means here."""
        bound = [str(spec.get("function", {}).get("name", ""))
                 for spec in (self.bound_tools or [])]
        offered = [n for n in bound if n.startswith("submit_")]
        if isinstance(args, dict):
            for name in offered:
                if name[len("submit_"):] in args:
                    return name
        return offered[0] if offered else "submit"

    def invoke(self, _messages) -> _Result:
        self.invocations += 1
        response = self._responses.pop(0) if self._responses else "{}"
        if isinstance(response, dict) and "__batch__" in response:
            return _Result(tool_calls=[
                {"name": (self._submit_tool(c["args"]) if c["__tool__"] == "submit"
                          else c["__tool__"]),
                 "args": c["args"], "id": f"c{self.invocations}.{i}"}
                for i, c in enumerate(response["__batch__"], start=1)])
        if isinstance(response, dict) and "__tool__" in response:
            name = response["__tool__"]
            if name == "submit":
                name = self._submit_tool(response["args"])
            return _Result(tool_calls=[{"name": name,
                                        "args": response["args"],
                                        "id": f"c{self.invocations}"}])
        return _Result(content=response if isinstance(response, str)
                       else json.dumps(response))


_ANALYSIS = {
    "needs_analysis": {
        "problem_definition": "Gap between current and desired OOP skill.",
        "gaps": [{"id": "GAP-01", "description": "No OOP modeling skill", "evidence": "Reviews"}],
        "priority_matrix": {"high": ["GAP-01"], "medium": [], "low": []},
    },
    "learner_analysis": {"target_audience": "Junior engineers"},
    "context_analysis": {"constraints": [{"id": "CON-01", "description": "2-day schedule"}],
                         "environment": "Classroom"},
    "task_analysis": {"topics": [{"id": "TOP-01", "topic": "Encapsulation", "subtopics": []}]},
    "improvement_plan": {"improvements": [
        {"id": "IMP-01", "addresses_gap": "GAP-01", "action": "Add a guided lab."}]},
}

_OUTCOMES = {
    "course_goal": {"statement": "Learners can design OOP-based solutions."},
    "learning_objectives": [
        {"id": "ILO-01", "level": "apply",
         "statement": "Apply inheritance to a domain model with 80% of tests passing.",
         "bloom_verb": "apply"},
    ],
}

_ASSESSMENT_DEV_PLAN = {"dev_plan": {"instrument_sets": [
    {"set_id": "SET-01", "objectives": ["ILO-01"], "plan_categories": ["formative"],
     "expected_items": 1, "instrument_hint": "one check", "rationale": "one objective"}]}}

_ASSESSMENT = {
    "assessment_plan": {
        "lo_coverage_targets": {"ILO-01": ["summative"]},
        "expected_evidence": {"ILO-01": "A working artifact."},
        "formative_methods": ["Weekly critique with rubric"],
        "pilot_data_plan": {
            "collection_points": ["After the first lab"],
            "anticipated_difficulties": [
                {"area": "ILO-01", "rationale": "Abstraction is hard for these learners.",
                 "detected_by": "Weekly critique with rubric",
                 "first_revision": "Add a worked example before the lab."},
                {"area": "ILO-01", "rationale": "Time pressure in the lab.",
                 "detected_by": "Weekly critique with rubric",
                 "first_revision": "Split the lab into two sessions."},
            ],
        },
    },
    "assessment_tools": [
        {"item_id": "AT-01", "type": "performance_task", "question": "Build the model.",
         "aligned_objective": "ILO-01", "plan_category": "summative",
         "required_cognitive_process": "apply",
         "scoring_criteria": "Rubric scores correctness 0-4."},
    ],
    "expert_review": {"reviewers": ["SME"], "review_criteria": ["Alignment"],
                      "feedback_summary": "Aligned."},
}


def _harness(responses: list[str]):
    model = ScriptedModel(responses)
    config = HarnessRunConfig(llm_factory=lambda: model)
    graph = AlignmentGraph()
    trajectory = TrajectoryLogger()
    brief = load_brief("minimal_brief.json")
    return model, config, graph, trajectory, brief


def _loop(config, graph, trajectory, brief, step, **kwargs) -> ToolLoop:
    llm = AgenticLLM(config, trajectory, step.identity)
    return ToolLoop(config, graph, trajectory, brief, step, llm, **kwargs)


def test_tool_call_then_submit_commits_and_logs_the_trace():
    step = STEP_BY_NAME["assessment"]
    model, config, graph, trajectory, brief = _harness([
        call("read_nodes", {"node_type": "objective"}),
        call("coverage_gaps", {"relation_id": "C2"}),
        call("submit", _ASSESSMENT),
        call("submit_dev_plan", _ASSESSMENT_DEV_PLAN),
    ])
    specialists.commit_outcomes(graph, trajectory, _OUTCOMES)

    _loop(config, graph, trajectory, brief, step).run()

    # `assessment` is a DISPATCH stage since the Developer tier came back: one
    # submit lands the PLAN, one the dev plan (required since 2026-09-05), and
    # the items are produced per work set (fanout.py).
    assert graph.get_node(graph.section_id(NodeType.ASSESSMENT_PLAN))["data"]
    tools_used = [tc["tool"] for tc in trajectory.tool_calls]
    # Tool labels carry their scoping argument so the judge-visible trace
    # distinguishes reads of different targets.
    assert f"{step.identity}.tool_read_nodes_objective" in tools_used
    assert f"{step.identity}.tool_coverage_gaps_C2" in tools_used
    # The commit label names the ARTIFACT this call carried: a stage writes one
    # artifact per call, and six identical `design_implementation` entries
    # would read to the trajectory judge as repetition rather than as the
    # stage doing what it was asked.
    assert f"{step.identity}.design_assessment_assessment_plan" in tools_used
    # Four: two reads, the plan submit, the dev-plan submit — and nothing
    # more, because the stage has no optional artifact left to ask for.
    assert model.invocations == 4


def test_rejected_submit_returns_errors_and_second_submit_lands():
    step = STEP_BY_NAME["outcomes"]
    _model, config, graph, trajectory, brief = _harness([
        call("submit", {"learning_objectives": []}),
        call("submit", _OUTCOMES),
    ])
    specialists.commit_analysis(graph, trajectory, _ANALYSIS)

    _loop(config, graph, trajectory, brief, step).run()

    assert graph.element_nodes(NodeType.OBJECTIVE)
    rejected = [e for e in trajectory.recovery_events if e["action"] == "submit_rejected"]
    assert rejected  # and the rejection carried the deterministic errors
    assert "learning_objectives" in rejected[0]["context"]["output_summary"]


def test_bare_artifact_is_accepted_as_implicit_submit():
    step = STEP_BY_NAME["analysis"]
    model, config, graph, trajectory, brief = _harness([json.dumps(_ANALYSIS)])

    _loop(config, graph, trajectory, brief, step).run()

    assert graph.element_nodes(NodeType.GAP)
    assert model.invocations == 1
    assert any(tc["tool"].endswith("design_analysis_implicit_submit")
               for tc in trajectory.tool_calls)


def test_done_step_makes_no_llm_call():
    step = STEP_BY_NAME["analysis"]
    model, config, graph, trajectory, brief = _harness([json.dumps(_ANALYSIS)])
    specialists.commit_analysis(graph, trajectory, _ANALYSIS)

    _loop(config, graph, trajectory, brief, step).run()

    assert model.invocations == 0


def test_wrapped_submit_is_unwrapped_deterministically():
    """Regression for the measured 2B failure: the whole artifact wrapped
    under an extra "artifact" key on submit must land as the section itself,
    not as an empty-looking node that zeroes the phase."""
    step = STEP_BY_NAME["outcomes"]
    _model, config, graph, trajectory, brief = _harness([
        call("submit", {"artifact": _OUTCOMES}),
    ])
    specialists.commit_analysis(graph, trajectory, _ANALYSIS)

    _loop(config, graph, trajectory, brief, step).run()

    # The unwrapped artifact lands as real element nodes (there is no
    # objective_0 full-list section any more — elements are the single
    # source of truth), and no node carries the stray "artifact" wrapper key.
    elements = graph.element_nodes(NodeType.OBJECTIVE)
    assert elements
    assert all("artifact" not in n["data"] for n in elements)
    assert not any(e["action"] == "submit_rejected" for e in trajectory.recovery_events)


def test_invalid_commit_on_spent_budget_is_recovery_not_a_judge_visible_step():
    step = STEP_BY_NAME["outcomes"]
    bad = call("submit", {"learning_objectives": []})
    # Every submit invalid AND an invalid fallback: nothing valid ever shows
    # up, so the commit is recovery plumbing, never a judge-visible step.
    _model, config, graph, trajectory, brief = _harness(
        [bad] * (ToolLoop.SUBMIT_BUDGET + 1) + ["{}"])
    specialists.commit_analysis(graph, trajectory, _ANALYSIS)

    _loop(config, graph, trajectory, brief, step).run()

    assert not any("design_outcomes" in tc["tool"] for tc in trajectory.tool_calls)
    assert any(e["action"] == "commit_invalid_section" for e in trajectory.recovery_events)


def test_repeated_identical_tool_call_is_not_reanswered():
    """Measured 2B failure: six identical read_nodes calls burned the whole
    turn budget. A repeat gets a nudge instead of a second answer, and never
    shows up as a judge-visible tool call."""
    step = STEP_BY_NAME["assessment"]
    read = call("read_nodes", {"node_type": "objective"})
    _model, config, graph, trajectory, brief = _harness([
        read, read, read,
        call("submit", _ASSESSMENT),
    ])
    specialists.commit_outcomes(graph, trajectory, _OUTCOMES)

    _loop(config, graph, trajectory, brief, step).run()

    assert graph.get_node(graph.section_id(NodeType.ASSESSMENT_PLAN))["data"]
    reads = [tc for tc in trajectory.tool_calls if "tool_read_nodes" in tc["tool"]]
    assert len(reads) == 1  # answered once, repeats are recovery plumbing
    repeats = [e for e in trajectory.recovery_events if e["action"] == "repeated_tool_call"]
    assert len(repeats) == 2


def test_analysis_is_not_finished_until_every_part_has_arrived():
    """Measured 2B failure: after a truncation rejection the model trimmed
    improvement_plan away entirely; the run shipped zero IMPROVEMENT nodes and
    the program-improvement rubric item scored 0.

    Since analysis may be submitted in parts, the VALIDATOR can no longer be
    what requires it — rejecting a first instalment for the parts it does not
    yet carry is the whole failure this split exists to remove. The
    requirement moved to the completeness probe: a part that never arrives
    keeps the step unfinished, which is what the regen loop and the single
    arm's stage menu both read."""
    from alignmentgraph_isd.core.agentic.specialists import (
        commit_analysis, missing_parts, step_done, validate_analysis,
    )

    step = STEP_BY_NAME["analysis"]

    # A partial submit is ACCEPTED — that is the point.
    trimmed = {k: v for k, v in _ANALYSIS.items() if k != "improvement_plan"}
    assert validate_analysis(trimmed) == []
    assert validate_analysis(_ANALYSIS) == []

    graph = AlignmentGraph()
    trajectory = TrajectoryLogger()
    commit_analysis(graph, trajectory, trimmed)
    assert missing_parts(step, graph) == ("improvement_plan",)
    assert not step_done(step, graph), "a missing part must keep the step open"

    commit_analysis(graph, trajectory,
                    {"improvement_plan": _ANALYSIS["improvement_plan"]})
    assert missing_parts(step, graph) == ()
    assert step_done(step, graph)
    # And the part that arrived second is really in the graph, not overwritten
    # by the earlier commit's empty value for it.
    assert graph.element_nodes(NodeType.IMPROVEMENT)
    assert graph.element_nodes(NodeType.GAP), "the first instalment survived the second"


def test_the_implementation_stage_is_not_finished_without_the_guides():
    """instructor_guide/operator_manual are scored by two rubric items and both
    measured 0 when a 2B model economized them away.

    The guarantee MOVED (2026-09-03) and is stronger for it. It used to be the
    validator rejecting a submit that omitted them — which only worked while
    one call carried the whole stage. Each artifact has its own submit tool
    now, so the validator judges what arrived and COMPLETION is what holds the
    guides: the stage is not finished until every required artifact is in the
    state, and the loop keeps the turn and names what is still missing."""
    from alignmentgraph_isd.core.agentic import fanout
    from alignmentgraph_isd.core.agentic.specialists import (
        commit_implementation, missing_parts, step_done, validate_implementation,
    )

    from conftest import _IMPLEMENTATION

    step = STEP_BY_NAME["implementation"]
    complete = _IMPLEMENTATION
    # Each artifact is valid on its own — that is what one submit per artifact
    # means, and rejecting the first correct instalment would be the bug.
    for key, value in complete.items():
        assert validate_implementation({key: value}) == [], key
    assert validate_implementation({}), "an empty submit is still an error"
    # ...and an artifact under invented keys is NOT valid. MEASURED (run
    # e81b8108): the filter below tested the wrong token and accepted any
    # non-empty dict, so a guide with no ``session_guides`` was COMMITTED and
    # nothing was ever scheduled (18 P10/P11 gaps in the audit).
    wrong = validate_implementation({"instructor_guide": {
        "instructor_role": "Facilitator", "responsibilities": ["setup"]}})
    assert any("instructor_guide.overview" in e for e in wrong), wrong
    assert not any("operator_manual" in e for e in wrong), (
        "only the artifact that arrived is judged")
    assert validate_implementation({"operator_manual": "prose"}), "wrong type must fail"
    # The session guides are NOT part of this artifact since 2026-09-07: they
    # are element nodes written per session block by the Developer tier, and a
    # nested copy here would be a second source for the list P10 is established
    # from. Rejected with the field named, never dropped silently.
    nested = validate_implementation({"instructor_guide": {
        **complete["instructor_guide"],
        "session_guides": [{"session": 1, "activity_ids": ["TLA-01"]}]}})
    assert any("instructor_guide.session_guides" in e for e in nested), nested
    # A session guide with prose but no ids schedules nothing. The guarantee
    # moved with the artifact: it is now the Developer tier's item rule, which
    # BOTH arms are held to (fanout.output_errors).
    no_ids = fanout.session_guide_errors([{"session": 1, "activities": ["lab"]}])
    assert any("session_guides[0].activity_ids" in e for e in no_ids), no_ids

    graph, trajectory = AlignmentGraph(), TrajectoryLogger()
    without_guides = {k: v for k, v in complete.items()
                      if k not in ("instructor_guide", "operator_manual")}
    commit_implementation(graph, trajectory, without_guides)
    assert set(missing_parts(step, graph)) == {"instructor_guide", "operator_manual",
                                               "dev_plan"}
    assert not step_done(step, graph)

    commit_implementation(graph, trajectory, {
        k: complete[k] for k in ("instructor_guide", "operator_manual")})
    assert set(missing_parts(step, graph)) == {"dev_plan"}
    assert not step_done(step, graph)
    # The plan is a required artifact of this stage: it is what divides the
    # delivery into the blocks the guides are written from.
    commit_implementation(graph, trajectory, {"dev_plan": {"session_blocks": []}})
    assert missing_parts(step, graph) == ()
    assert step_done(step, graph)
    # The second commit did not overwrite the first.
    data = graph.get_node(graph.section_id(NodeType.IMPLEMENTATION_PLAN))["data"]
    assert set(data) >= set(complete)


def test_unknown_tool_and_disallowed_type_come_back_as_error_observations():
    step = STEP_BY_NAME["assessment"]
    _model, config, graph, trajectory, brief = _harness([
        call("read_nodes", {"node_type": "rubric"}),  # not readable here
        call("frobnicate", {}),
        call("submit", _ASSESSMENT),
    ])
    specialists.commit_outcomes(graph, trajectory, _OUTCOMES)

    loop = _loop(config, graph, trajectory, brief, step)
    assert loop._execute("read_nodes", {"node_type": "rubric"}).startswith("ERROR")
    assert loop._execute("frobnicate", {}).startswith("ERROR")
    loop.run()
    assert graph.get_node(graph.section_id(NodeType.ASSESSMENT_PLAN))["data"]


def test_string_encoded_tool_arguments_are_coerced_not_rejected():
    """MEASURED FAILURE (single_20260831_152628, Qwen3.5 on vLLM with
    --tool-call-parser qwen3_coder): the model called submit correctly on every
    stage of every arm, but each structured argument arrived as a STRING holding
    its JSON, so the validator answered "expected list, got str" and all 28
    stages fell through to the scripted fallback. A transport artifact must not
    be charged to the model's submit budget."""
    step = STEP_BY_NAME["outcomes"]
    stringified = {k: json.dumps(v, ensure_ascii=False) for k, v in _OUTCOMES.items()}
    _model, config, graph, trajectory, brief = _harness([call("submit", stringified)])
    specialists.commit_analysis(graph, trajectory, _ANALYSIS)

    _loop(config, graph, trajectory, brief, step).run()

    assert graph.element_nodes(NodeType.OBJECTIVE), "the coerced submit must land"
    assert not any(e["action"] == "submit_rejected" for e in trajectory.recovery_events)
    # `agentic_gave_up`, not `agentic_fallback`: the latter has had no emitter
    # since the scripted rescue went (2026-09-01), so asserting its absence
    # asserted nothing. This one CAN fire, which is the point.
    assert not any(e["action"] == "agentic_gave_up" for e in trajectory.recovery_events)


def test_whole_argument_object_as_one_json_string_is_coerced():
    """The other shape parsers produce: not per-value strings, but the entire
    arguments object as one JSON string."""
    step = STEP_BY_NAME["outcomes"]
    _model, config, graph, trajectory, brief = _harness([
        call("submit", json.dumps(_OUTCOMES, ensure_ascii=False))])
    specialists.commit_analysis(graph, trajectory, _ANALYSIS)

    _loop(config, graph, trajectory, brief, step).run()

    assert graph.element_nodes(NodeType.OBJECTIVE)
    assert not any(e["action"] == "submit_rejected" for e in trajectory.recovery_events)


def test_a_string_where_a_structure_was_declared_is_dropped_not_swallowed():
    """Coercion must not paper over a real model mistake — with ONE deliberate
    exception, added 2026-09-04.

    A string where an ARRAY was declared is unreadable and stays unreadable:
    it is dropped, reported as `dropped_argument`, and the artifact it was
    supposed to be does not exist. That is the guard.

    The exception is an artifact whose schema example is an object with exactly
    ONE key: there, a bare string has only one thing it can mean, and
    `_fill_single_key_object` reads it as that field. It is a real loss of
    strictness — "not json at all" now lands as a course goal — and it is worth
    it: MEASURED (run single_20260904_020259), a 2B model sent a perfectly good
    goal sentence as a bare string, was rejected three times, spent the submit
    budget, gave up the stage, and left `design.course_goal` null with C1 at 0
    of 50 objectives covered. A bad goal the judge can score beats no goal at
    all."""
    step = STEP_BY_NAME["outcomes"]
    _model, config, graph, trajectory, brief = _harness([
        call("submit", {"course_goal": "not json at all",
                        "learning_objectives": "also not json"}),
        call("submit", _OUTCOMES),
    ])
    specialists.commit_analysis(graph, trajectory, _ANALYSIS)

    _loop(config, graph, trajectory, brief, step).run()

    actions = [e["action"] for e in trajectory.recovery_events]
    # The array field: unreadable, dropped, and SAID SO.
    dropped = [e for e in trajectory.recovery_events if e["action"] == "dropped_argument"]
    assert dropped, "a string where an array was declared must not be swallowed"
    assert "learning_objectives" in str(dropped[0]["context"]["input_summary"])
    # The single-key object: read as its one field, and SAID SO.
    assert "bare_artifact_wrapped" in actions
    assert graph.element_nodes(NodeType.OBJECTIVE), "and the retry must still land"


def test_a_course_goal_sent_as_a_bare_string_still_lands():
    """MEASURED FAILURE (run single_20260904_020259, Qwen3.5-2B on the pod).

    The model sent ``course_goal`` as a bare sentence instead of
    ``{"statement": ...}``. Its schema declares an object, so validation
    answered "course_goal.statement must be a non-empty string" on all three
    submit attempts, the budget ran out, the stage gave up — and the run
    shipped `design.course_goal` null with C1, one of the five core relations,
    covering 0 of 50 objectives. One malformed envelope cost a core relation."""
    step = STEP_BY_NAME["outcomes"]
    goal = "Learners build a maths-education website end to end."
    _model, config, graph, trajectory, brief = _harness([
        call("submit", {"course_goal": goal,
                        "learning_objectives": _OUTCOMES["learning_objectives"]}),
    ])
    specialists.commit_analysis(graph, trajectory, _ANALYSIS)

    _loop(config, graph, trajectory, brief, step).run()

    committed = (graph.get_node(graph.section_id(NodeType.COURSE_GOAL)) or {}).get("data") or {}
    assert committed.get("statement") == goal, (
        "a bare-string course goal was not read as its only field")
    assert not [e for e in trajectory.recovery_events
                if e["action"] == "submit_rejected"], "and it cost no submit attempt"


def test_the_same_objective_written_many_times_is_committed_once():
    """MEASURED FAILURE (run single_20260904_020259): one submit carried 50
    learning objectives with 4 distinct statements — one of them 32 times.

    Nothing capped it, and every downstream family sizes itself off the
    objective count: 63 assessment work sets, 126 items, 36 activity blocks,
    161 activities, 373 nodes, 347 model calls, 955 seconds, 1.19M tokens for
    a design that contains four objectives.

    The drop is COUNTED, not absorbed: how much a size pads is a finding about
    the model class this study is about, so `duplicate_element_dropped` carries
    it into the trajectory rather than the harness quietly tidying up."""
    step = STEP_BY_NAME["outcomes"]
    padded = [
        {"id": f"ILO-{i:02d}", "level": "apply", "bloom_verb": "apply",
         "statement": "Learners apply interactive web content structures."}
        for i in range(1, 33)
    ] + [{"id": "ILO-33", "level": "understand", "bloom_verb": "explain",
          "statement": "Learners explain software engineering methodologies."}]
    _model, config, graph, trajectory, brief = _harness([
        call("submit", {"course_goal": {"statement": "Build a website."},
                        "learning_objectives": padded}),
    ])
    specialists.commit_analysis(graph, trajectory, _ANALYSIS)

    _loop(config, graph, trajectory, brief, step).run()

    statements = [(n.get("data") or {}).get("statement")
                  for n in graph.element_nodes(NodeType.OBJECTIVE)]
    assert len(statements) == 2, f"33 submitted, 2 distinct, committed {len(statements)}"
    assert len(set(statements)) == 2
    dropped = [e for e in trajectory.recovery_events
               if e["action"] == "duplicate_element_dropped"]
    assert dropped, "the padding must be recorded, not silently absorbed"
    assert "31 of 33" in str(dropped[0]["context"]["input_summary"])


def test_protocol_words_in_the_artifact_are_rejected():
    """MEASURED FAILURE (single_20260831_152628): every arm leaked tool names
    into judge-scored content — 33 occurrences in the full pipeline, including
    an assessment item asking learners to map SDLC phases to 'read_nodes' and
    'read_edges'. Same shape as the placeholder gate: rejected with an
    actionable message, not silently repaired."""
    from alignmentgraph_isd.core.agentic.protocol import protocol_leak_errors

    leaked = {**_ASSESSMENT}
    leaked["assessment_tools"] = [dict(_ASSESSMENT["assessment_tools"][0],
                                       question="Map each phase to read_nodes.")]
    assert protocol_leak_errors(leaked), "a leaked tool name must be caught"
    assert not protocol_leak_errors(_ASSESSMENT), "clean content must pass"
    # Ordinary English that merely resembles a tool name is not a match.
    assert not protocol_leak_errors({"a": "Ask learners to list documents they read."})
    # "submit" is ordinary English and must NOT be gated — measured in run
    # single_20260831_160530, where gating it made the model burn two turns
    # arguing with an error it could not act on.
    assert not protocol_leak_errors({"a": "Learners submit their project by Friday."})

    step = STEP_BY_NAME["assessment"]
    _model, config, graph, trajectory, brief = _harness([
        call("submit", leaked),
        call("submit", _ASSESSMENT),
    ])
    specialists.commit_outcomes(graph, trajectory, _OUTCOMES)
    _loop(config, graph, trajectory, brief, step).run()

    rejected = [e for e in trajectory.recovery_events if e["action"] == "submit_rejected"]
    assert rejected and "tool names" in rejected[0]["context"]["output_summary"]
    assert graph.get_node(graph.section_id(NodeType.ASSESSMENT_PLAN))["data"], \
        "the clean retry must land"



def test_the_model_is_told_how_many_turns_remain():
    """MEASURED FAILURE (single_20260831_160530): 10 of 13 fallbacks were
    'turn budget exhausted', and the single+graph arm spent all eight turns
    reading on 6 of 7 stages without ever submitting. The budget is stated once
    in the system prompt and never again; a small model does not track it."""
    step = STEP_BY_NAME["assessment"]
    seen: list[str] = []

    class _Watching(ScriptedModel):
        def invoke(self, messages):
            seen.append("\n".join(
                str(m.get("content", "")) for m in messages if isinstance(m, dict)))
            return super().invoke(messages)

    read = call("read_nodes", {"node_type": "objective"})
    reads = [dict(read, args={"node_type": "objective", "n": i})
             for i in range(ToolLoop.MAX_TURNS)]
    model = _Watching(reads)
    config = HarnessRunConfig(llm_factory=lambda: model)
    graph = AlignmentGraph()
    trajectory = TrajectoryLogger()
    brief = load_brief("minimal_brief.json")
    specialists.commit_outcomes(graph, trajectory, _OUTCOMES)

    ToolLoop(config, graph, trajectory, brief, step,
             AgenticLLM(config, trajectory, step.identity)).run()

    # any(), not seen[-1]: the assertion is that the warning was issued at all,
    # not which turn it landed on.
    assert any("turn(s) left" in t for t in seen), (
        "the model was never told its budget was running out")


def test_a_committed_submit_enters_the_history():
    """MEASURED FAILURE: the loop returned straight after committing, so the
    submit turn never joined the transcript. The single arm therefore carried
    NO record of anything it had produced — its whole "accumulated context" was
    one system turn plus N copies of the stage boilerplate, and the
    decomposition axis was reading prompt duplication instead of accumulated
    work."""
    step = STEP_BY_NAME["outcomes"]
    _model, config, graph, trajectory, brief = _harness([call("submit", _OUTCOMES)])
    specialists.commit_analysis(graph, trajectory, _ANALYSIS)

    loop = _loop(config, graph, trajectory, brief, step)
    loop.run()

    roles = [m.get("role") if isinstance(m, dict) else "assistant" for m in loop.messages]
    assert "tool" in roles, "the submit turn and its result must close the exchange"
    joined = " ".join(str(m.get("content", "")) for m in loop.messages if isinstance(m, dict))
    assert "COMMITTED" in joined
    # Every tool call is answered: an unanswered one makes the NEXT request
    # malformed, which only the single arm would discover, mid-run.
    assert roles.count("tool") == sum(
        1 for m in loop.messages
        if getattr(m, "tool_calls", None) or (isinstance(m, dict) and m.get("tool_calls")))


def test_the_scenario_is_stated_once_not_once_per_stage():
    """The brief is byte-identical for all six stages, so a per-stage copy is
    duplication, not accumulation — and duplication is what the single arm was
    accumulating before this. It lives in the system turn, which trim_history
    never drops, so it also cannot fall out of the window mid-run."""
    step = STEP_BY_NAME["outcomes"]
    _model, config, graph, trajectory, brief = _harness([call("submit", _OUTCOMES)])
    specialists.commit_analysis(graph, trajectory, _ANALYSIS)

    loop = _loop(config, graph, trajectory, brief, step)
    loop.run()

    system = loop.messages[0]
    assert system["role"] == "system" and "=== SCENARIO ===" in system["content"]
    rest = " ".join(str(m.get("content", "")) for m in loop.messages[1:] if isinstance(m, dict))
    assert "=== SCENARIO ===" not in rest, "the brief is repeated in a stage turn"


def test_message_size_counts_the_tool_call_payload():
    """An assistant turn that submits an artifact carries an EMPTY content and
    the whole artifact in its tool call. Measured: context_len reported ~24k
    chars for a run that burned 744k tokens, because the one thing the single
    arm accumulates was the one thing the size function could not see."""
    from alignmentgraph_isd.core.agentic.transcript import message_size, trim_history

    empty_content_with_payload = {"role": "assistant", "content": "",
                                  "tool_calls": [{"name": "submit", "args": _ASSESSMENT}]}
    assert message_size(empty_content_with_payload) > 500
    assert message_size({"role": "user", "content": "abc"}) == 3

    # ...and trimming therefore fires on the real size, not on the visible half.
    messages = [{"role": "system", "content": "S"}]
    messages += [dict(empty_content_with_payload) for _ in range(20)]
    messages += [{"role": "user", "content": "LIVE"}]
    _trimmed, dropped = trim_history(messages, budget=2000)
    assert len(dropped) > 0, "a transcript of payload-carrying turns must still be trimmed"


def test_tool_call_left_as_text_by_the_server_is_recovered():
    """MEASURED FAILURE (run single_20260831_180940): replies arriving as
    `<tool_call><function=read_nodes><parameter=node_type>…` in the CONTENT,
    with an empty tool_calls. The model called the tool correctly; the serving
    parser did not reconstruct it. Left alone each one costs a turn, earns a
    protocol nudge, and pushes the stage toward its fallback — for a reason
    that has nothing to do with the model."""
    step = STEP_BY_NAME["assessment"]
    markup = ("<tool_call>\n<function=read_nodes>\n<parameter=node_type>\n"
              "objective\n</parameter>\n</function>\n</tool_call>")
    _model, config, graph, trajectory, brief = _harness([
        markup, call("submit", _ASSESSMENT), call("submit_dev_plan", _ASSESSMENT_DEV_PLAN)])
    specialists.commit_outcomes(graph, trajectory, _OUTCOMES)

    _loop(config, graph, trajectory, brief, step).run()

    assert graph.get_node(graph.section_id(NodeType.ASSESSMENT_PLAN))["data"]
    # The recovered call is a real, judge-visible read — not an invalid turn.
    assert any("tool_read_nodes_objective" in tc["tool"] for tc in trajectory.tool_calls)
    assert not any(e["action"] == "invalid_action" for e in trajectory.recovery_events)
    # ...and the recovery is COUNTED, so its rate per model size is visible:
    # it bounds how much of this arm's behaviour is really the serving stack's.
    recovered = [e for e in trajectory.recovery_events
                 if e["action"] == "tool_call_markup_recovered"]
    assert len(recovered) == 1 and recovered[0]["context"]["input_summary"] == "read_nodes"


def test_prose_really_is_prose_and_is_not_mistaken_for_a_call():
    """The recovery must not fire on ordinary text — a model that reasons out
    loud gets the protocol nudge, which is the correct answer to that."""
    step = STEP_BY_NAME["assessment"]
    _model, config, graph, trajectory, brief = _harness([
        "I need to check the constraint node first before writing anything.",
        call("submit", _ASSESSMENT),
    ])
    specialists.commit_outcomes(graph, trajectory, _OUTCOMES)

    _loop(config, graph, trajectory, brief, step).run()

    assert any(e["action"] == "invalid_action" for e in trajectory.recovery_events)
    assert not any(e["action"] == "tool_call_markup_recovered"
                   for e in trajectory.recovery_events)


def test_tool_choice_is_sent_explicitly():
    """vLLM's --enable-auto-tool-choice is what engages the tool-call parser,
    and LangChain's bind_tools omits `tool_choice`. Without it the server can
    hand a correctly-formed call back as raw markup in `content` instead of
    parsing it into `tool_calls`.

    Traced 2026-08-31 by diffing the harness's outgoing payload against a probe
    that scored 100% well-formed in all four transport x turn-shape cells:
    `tool_choice` was the only field that differed."""
    seen: dict = {}

    class _Recording(ScriptedModel):
        def bind_tools(self, specs, **kwargs):
            seen.update(kwargs)
            return super().bind_tools(specs)

    step = STEP_BY_NAME["analysis"]
    model = _Recording([call("submit", _ANALYSIS)])
    config = HarnessRunConfig(llm_factory=lambda: model)
    graph = AlignmentGraph()
    trajectory = TrajectoryLogger()
    ToolLoop(config, graph, trajectory, load_brief("minimal_brief.json"), step,
             AgenticLLM(config, trajectory, step.identity)).run()

    assert seen.get("tool_choice") == "auto", (
        "tool_choice was not sent; the serving-side parser may not engage")
    assert graph.element_nodes(NodeType.GAP)


def test_a_backend_that_rejects_tool_choice_still_binds():
    """Not every chat model's bind_tools takes tool_choice. Falling back to a
    plain binding keeps such a backend working rather than losing the whole
    stage."""
    step = STEP_BY_NAME["analysis"]

    class _Picky(ScriptedModel):
        def bind_tools(self, specs, **kwargs):
            if kwargs:
                raise TypeError("bind_tools() got an unexpected keyword argument")
            return super().bind_tools(specs)

    model = _Picky([call("submit", _ANALYSIS)])
    config = HarnessRunConfig(llm_factory=lambda: model)
    graph = AlignmentGraph()
    trajectory = TrajectoryLogger()
    ToolLoop(config, graph, trajectory, load_brief("minimal_brief.json"), step,
             AgenticLLM(config, trajectory, step.identity)).run()

    assert graph.element_nodes(NodeType.GAP)
    assert not any(e["action"] == "tool_binding_unavailable"
                   for e in trajectory.recovery_events)


def test_a_developer_reads_less_than_the_stage_that_dispatched_it():
    """MEASURED (run single_20260901_151738): Developers were 95 of the full
    pipeline's 146 calls, and MaterialDeveloper spent 54 on 10 work sets — only
    10 of them submits. The other 44 read topics, activities, edges and coverage
    gaps it was not assigned to act on.

    A Developer is scoped by construction: its assignment is rendered into its
    prompt. Giving it the stage's whole allowlist is not neutrality, it is a
    turn tax."""
    from alignmentgraph_isd.core import dev_plans
    from alignmentgraph_isd.core.agentic import fanout

    step = STEP_BY_NAME["content"]
    spec = fanout.SPECS["content"]
    dev = fanout.set_step(spec, dev_plans.WorkSet(set_id="MU-01"), step)

    # Not a subset — a MaterialDeveloper reads the CONTENT modules its stage
    # was busy creating — but strictly narrower, and free of the types it has
    # no assignment over.
    assert len(dev.readable_types) < len(step.readable_types)
    assert NodeType.TOPIC not in dev.readable_types
    assert NodeType.CONSTRAINT not in dev.readable_types
    assert not dev.relations, "a Developer was offered relation reads"
    assert not dev.docket, "a Developer was handed coverage gaps for other sets"
    assert budget.DEVELOPER_MAX_TURNS < ToolLoop.MAX_TURNS


def test_a_repeated_call_does_not_spend_a_turn_but_is_not_free():
    """A repeat produces no observation and no artifact, so charging a turn
    spends the budget on the model's confusion — 19 of the full pipeline's
    turns went that way. Refunded, but only up to REPEAT_ALLOWANCE: a model
    that only ever repeats has to reach the fallback."""
    step = STEP_BY_NAME["outcomes"]
    read = call("read_nodes", {"node_type": "gap"})
    # Enough repeats to exhaust the allowance, then a good submit.
    _model, config, graph, trajectory, brief = _harness(
        [read] + [read] * 6 + [call("submit", _OUTCOMES)])
    specialists.commit_analysis(graph, trajectory, _ANALYSIS)

    loop = _loop(config, graph, trajectory, brief, step)
    loop.run()

    assert loop.stats["repeated_calls"] > budget.REPEAT_ALLOWANCE
    # The refund is bounded, so the loop still terminates on its own.
    assert loop.stats["turns_used"] <= ToolLoop.MAX_TURNS + budget.REPEAT_ALLOWANCE


def test_a_developer_is_told_what_the_ids_in_its_assignment_mean():
    """MEASURED (run single_20260901_162455): the assignment gave objective IDs
    only — "ILO-01 x formative" — so four AssessmentDevelopers each issued an
    identical `read_nodes(objective)` to learn what ILO-01 says. The BFCL judge
    reads a flat call list with no notion of WHO is calling, and scored the arm
    18.0 on redundancy_avoidance against react-isd's 23.0 — the whole of its
    trajectory deficit.

    Those reads were our design, not the model's: a Developer cannot be told to
    write items for an objective and not be told what the objective says."""
    from alignmentgraph_isd.core import dev_plans
    from alignmentgraph_isd.core.agentic import fanout

    step = STEP_BY_NAME["assessment"]
    graph = AlignmentGraph()
    trajectory = TrajectoryLogger()
    specialists.commit_outcomes(graph, trajectory, _OUTCOMES)
    work_set = dev_plans.WorkSet(set_id="AS-01", objectives=("ILO-01",),
                                 pairs=(("ILO-01", "formative"),))

    without = fanout.set_step(fanout.SPECS["assessment"], work_set, step)
    with_state = fanout.set_step(fanout.SPECS["assessment"], work_set, step, graph)

    statement = _OUTCOMES["learning_objectives"][0]["statement"]
    assert statement not in without.intro
    assert statement in with_state.intro, (
        "the Developer is named an objective it is never shown")
    # An id the state does not hold resolves to nothing, not to a crash.
    missing = dev_plans.WorkSet(set_id="AS-02", objectives=("ILO-99",))
    assert fanout.set_step(fanout.SPECS["assessment"], missing, step, graph).intro


def test_a_value_that_arrived_as_text_is_reported_as_shape_not_as_content():
    """MEASURED (run single_20260901_171408): a submit arrived as
    `needs_analysis:str` and the model was told "needs_analysis.gaps must be a
    non-empty list" — an error about CONTENT for a problem of SHAPE. It
    resubmitted the same string three times, the stage fell back, and the run
    finished missing a required field.

    A value that is text cannot be judged on its contents, and telling the model
    about its contents sends it to fix the wrong thing."""
    from alignmentgraph_isd.core.agentic import tools

    step = STEP_BY_NAME["analysis"]
    params = tools.submit_parameters(step)

    errors = tools.shape_errors(params, {"needs_analysis": '{"problem_definition": "x"'})
    assert errors and "arrived as text" in errors[0]
    assert not tools.shape_errors(params, {"needs_analysis": {"problem_definition": "x"}})

    # It leads the rejection, ahead of the validator's own complaints.
    broken = {k: "not json at all" for k, _t, _r in step.submit_fields}
    _model, config, graph, trajectory, brief = _harness(
        [call("submit", broken), call("submit", _ANALYSIS)])
    _loop(config, graph, trajectory, brief, step).run()

    rejected = [e for e in trajectory.recovery_events if e["action"] == "submit_rejected"]
    assert rejected and "arrived as text" in rejected[0]["context"]["output_summary"]


def test_a_tool_call_written_as_json_in_the_content_is_recovered():
    """A third transport shape beside a parsed tool_calls entry and the
    `<function=…>` markup: MEASURED (run single_20260901_171408) the model
    answered with `{"name": "submit", "arguments": {...}}` as plain content and
    no tool call, which the loop could only read as prose — a turn spent, and a
    protocol nudge for a model that had in fact called the tool."""
    step = STEP_BY_NAME["outcomes"]
    as_json = json.dumps({"name": "submit", "arguments": _OUTCOMES}, ensure_ascii=False)
    _model, config, graph, trajectory, brief = _harness([as_json])
    specialists.commit_analysis(graph, trajectory, _ANALYSIS)

    _loop(config, graph, trajectory, brief, step).run()

    assert graph.element_nodes(NodeType.OBJECTIVE), "the recovered call never landed"
    # `agentic_gave_up`, not `agentic_fallback`: the latter has had no emitter
    # since the scripted rescue went (2026-09-01), so asserting its absence
    # asserted nothing. This one CAN fire, which is the point.
    assert not any(e["action"] == "agentic_gave_up" for e in trajectory.recovery_events)


def test_a_developer_is_told_its_assignment_is_already_complete():
    """The read tools stay — a Developer is an agent and may look at whatever it
    judges it needs. But the assignment now resolves every artifact it names, and
    a Developer that does not know that reads them anyway: MEASURED (run
    single_20260901_171408) 22 of 33 Developer calls were reads and 11 of the 67
    judge-visible calls were exact duplicates."""
    from alignmentgraph_isd.core import dev_plans
    from alignmentgraph_isd.core.agentic import fanout

    graph = AlignmentGraph()
    trajectory = TrajectoryLogger()
    specialists.commit_outcomes(graph, trajectory, _OUTCOMES)
    # `assessment` is dispatch-only now: the items come from its Developers.
    fanout.commit_sets(
        fanout.SPECS["assessment"], graph, trajectory,
        [dev_plans.WorkSet(set_id="AS-01")],
        [{"set_id": "AS-01", **_ASSESSMENT}])

    step = STEP_BY_NAME["activities"]
    # The committed id, read back rather than assumed: an artifact is named by
    # the set that wrote it (`AT-0101`), so a reference typed from the schema
    # example points at nothing. Every family that references another reads it
    # first, which is why this holds in a real run too.
    committed = graph.element_nodes(NodeType.ASSESSMENT)[0]["data"]["item_id"]
    work_set = dev_plans.WorkSet(
        set_id="AB-01", objectives=("ILO-01",),
        payload={"assessment_items": [committed]})
    intro = fanout.set_step(fanout.SPECS["activities"], work_set, step, graph).intro

    assert "do not need to look them up" in intro
    # An activity set names the items its activities prepare for, BY ID. Told to
    # prepare learners for AT-01 and not told what AT-01 asks, a Developer has
    # no choice but to go and read it.
    assert _ASSESSMENT["assessment_tools"][0]["question"] in intro
    assert _OUTCOMES["learning_objectives"][0]["statement"] in intro


def test_a_step_that_produces_nothing_says_so_instead_of_being_scripted():
    """WHY THE SCRIPTED FALLBACK WENT (2026-09-01). A scripted single-shot used
    to write the artifact whenever the loop failed, and it was writing a lot of
    them: measured across three runs, 26-35% of the full pipeline's artifacts
    and up to 76% of the prose arm's came from it rather than from any agent.

    It was also not symmetric: `ToolLoop` had the rescue and `ReactLoop` — the
    single arm — never did, so one side of the decomposition axis was caught and
    the other dropped, and part of the measured gap was that."""
    step = STEP_BY_NAME["analysis"]
    _model, config, graph, trajectory, brief = _harness(["junk"] * (ToolLoop.MAX_TURNS + 4))

    loop = _loop(config, graph, trajectory, brief, step)
    loop.run()

    assert loop.stats["gave_up"]
    assert any(e["action"] == "agentic_gave_up" for e in trajectory.to_dict()["events"])
    # Nothing was invented on the agent's behalf...
    assert not graph.element_nodes(NodeType.GAP)
    # ...and no judge-visible step claims work that was never done.
    assert not [c for c in trajectory.tool_calls if c["tool"].endswith("design_analysis")]


def test_the_models_best_attempt_is_kept_when_the_submit_budget_runs_out():
    """Giving up is not discarding: the last thing the model managed is still
    ITS work, and the deterministic repair net can mend it. What is gone is the
    script writing a different artifact and passing it off as the agent's."""
    step = STEP_BY_NAME["outcomes"]
    partial = {"course_goal": _OUTCOMES["course_goal"], "learning_objectives": []}
    _model, config, graph, trajectory, brief = _harness(
        [call("submit", partial)] * (ToolLoop.SUBMIT_BUDGET + 1))
    specialists.commit_analysis(graph, trajectory, _ANALYSIS)

    loop = _loop(config, graph, trajectory, brief, step)
    loop.run()

    assert loop.stats["gave_up"]
    assert any(e["action"] == "agentic_gave_up" for e in trajectory.to_dict()["events"])
    # The course goal the model DID write survives; nothing was fabricated for it.
    assert graph.get_node(graph.section_id(NodeType.COURSE_GOAL))["data"]


# ── analysis in instalments ─────────────────────────────────────────────────

def test_the_multi_arm_keeps_the_turn_after_a_partial_analysis_submit():
    """The stage used to end at the FIRST accepted submit, so an artifact the
    model could not fit in one call could not be finished at all. It now keeps
    the turn and is told which parts are still missing.

    MEASURED (run single_20260901_205901): `analysis` is five top-level objects
    in one call and a 2B model hit the 8192-token cap partway through the tool
    call's arguments — nine rejections, the stage gave up, three times over."""
    from alignmentgraph_isd.core.agentic.specialists import missing_parts

    step = STEP_BY_NAME["analysis"]
    parts = [{k: _ANALYSIS[k]} for k in step.submit_parts]
    _model, config, graph, trajectory, brief = _harness(
        [call("submit", part) for part in parts])

    loop = _loop(config, graph, trajectory, brief, step)
    loop.run()

    assert missing_parts(step, graph) == (), "every instalment landed"
    assert not loop.stats["gave_up"]
    assert loop.stats["submits_rejected"] == 0, "a part on its own is not an error"
    # One turn per part, and the model was told what remained after each.
    told = [m["content"] for m in loop.messages
            if isinstance(m, dict) and m.get("role") == "tool"
            and "still needs" in str(m.get("content"))]
    assert len(told) == len(parts) - 1, "told after every submit but the last"
    assert "improvement_plan" in told[0]


def test_one_whole_analysis_submit_still_ends_the_stage_in_one_turn():
    """Splitting is an ALLOWANCE, not a requirement: a model that fits the
    artifact in one call must not be made to pay four more turns for it."""
    _model, config, graph, trajectory, brief = _harness([call("submit", _ANALYSIS)])
    loop = _loop(config, graph, trajectory, brief, STEP_BY_NAME["analysis"])
    loop.run()

    assert loop.stats["turns_used"] == 1
    assert not loop.stats["gave_up"]


def test_a_step_with_no_declared_parts_returns_on_its_first_submit():
    """Every other step is unchanged — the parts path is entered only by a
    step that declares them, so the measurement surface of the rest is the
    same as before."""
    step = STEP_BY_NAME["outcomes"]
    assert step.submit_parts == ()
    _model, config, graph, trajectory, brief = _harness(
        [call("submit", _OUTCOMES), call("submit", _OUTCOMES)])
    loop = _loop(config, graph, trajectory, brief, step)
    loop.run()

    assert loop.stats["turns_used"] == 1, "a second submit was never asked for"


def test_a_stage_that_keeps_submitting_without_completing_is_stopped():
    """The cap is one turn per part plus slack. Without it, a model that
    resends the same part forever spends the whole stage on it — the same
    disagreement between validator and completeness probe that the single
    arm's SUBMIT_CAP answers."""
    step = STEP_BY_NAME["analysis"]
    one_part = {"needs_analysis": _ANALYSIS["needs_analysis"]}
    _model, config, graph, trajectory, brief = _harness(
        [call("submit", one_part)] * 20)

    loop = _loop(config, graph, trajectory, brief, step)
    loop.run()

    assert loop.stats["gave_up"]
    gave_up = [e for e in trajectory.recovery_events if e["action"] == "agentic_gave_up"]
    assert gave_up and "parts still missing" in gave_up[0]["context"]["input_summary"]
    assert loop.stats["turns_used"] <= len(step.submit_parts) + loop.PART_SUBMIT_SLACK


def test_a_stage_that_ends_owing_an_artifact_is_not_told_it_is_finished():
    """The branch above answers the model's last tool call, because the chat
    API requires every call to be answered — and it used to answer with
    `_append_committed`: "the <stage> artifact is now part of the design state.
    Move on to the next stage."

    MEASURED (run 46bd42a5, implementation): the stage ended here owing
    `dev_plan`, so the transcript closed by telling the model the stage was
    finished while `_give_up` on the very next line recorded that it was not.
    That transcript is what the judge reads, and in the single arm it is
    carried into every later stage and can come back on a repair turn."""
    step = STEP_BY_NAME["analysis"]
    one_part = {"needs_analysis": _ANALYSIS["needs_analysis"]}
    _model, config, graph, trajectory, brief = _harness([call("submit", one_part)] * 20)

    loop = _loop(config, graph, trajectory, brief, step)
    loop.run()

    closing = loop.messages[-1]["content"]
    assert "Move on to the next stage" not in closing
    assert "ENDS here without" in closing
    for part in loop_module.missing_parts(step, graph):
        assert part in closing, "it names what the stage is ending without"


def test_a_restored_contract_says_what_the_stage_already_committed():
    """MEASURED (run 46bd42a5, implementation): compaction dropped 20 turns of
    a stage that had committed six of its seven artifacts, and `restore` put
    the contract back VERBATIM — ending "This stage has 7 of them:
    instructor_orientation, system_check, ...", with nothing to say six were
    already in. The model read it as the stage starting and re-submitted the
    six, one per turn, until the ceiling ended the stage; `dev_plan`, the one
    artifact actually missing, was never written.

    The contract itself is untouched — `with_progress` is the identity function
    until something has landed, which is what keeps a stage's OPENING turn
    byte-identical for the golden fixture."""
    from alignmentgraph_isd.core.agentic.protocol import stage_brief_block, with_progress

    step = STEP_BY_NAME["analysis"]
    one_part = {"needs_analysis": _ANALYSIS["needs_analysis"]}
    _model, config, graph, trajectory, brief = _harness([call("submit", one_part)] * 20)

    contract = stage_brief_block(step)
    assert with_progress(contract, step, AlignmentGraph()) == contract, (
        "nothing committed yet: the opening turn must not change")

    loop = _loop(config, graph, trajectory, brief, step)
    loop.run()

    restored = loop._restore_brief("analysis")
    assert restored is not None and restored.startswith(contract)
    assert "Already committed: needs_analysis" in restored
    assert "still needs" in restored
    assert "do not resend those" in restored


def test_a_re_attached_contract_carries_the_progress_in_both_arms():
    """One sentence, `still_needed`, in all three places a stage is told what
    it owes: where it OPENS, where a submit is answered, and where the contract
    comes BACK. An arm that re-attached a bare contract would be arguing from a
    different set of facts than the other."""
    import inspect

    from alignmentgraph_isd.core.agentic import react

    for owner in (loop_module.ToolLoop._restore_brief, loop_module.ToolLoop._respec,
                  react.ReactLoop._restore_brief, react.ReactLoop._respec):
        assert "with_progress(" in inspect.getsource(owner), (
            "every re-attachment goes through the one implementation")


# ── a read of what the assignment already carries ───────────────────────────

def test_a_developer_reading_its_own_assignment_gets_a_pointer_not_a_second_copy():
    """The instruction not to look it up exists, is placed as well as it can be
    — first line of the Developer's intro, immediately above the data — and was
    measured to help but not to be enough: reads were 22 of 33 Developer calls
    (run 171408) and 26 of 63 after it (run f42dceff), with repeats making up
    the difference so the total stayed at 67%.

    A second sentence would not do better. The harness KNOWS what it resolved,
    so the redundant read stops being something the model must remember and
    becomes something it observes."""
    from alignmentgraph_isd.core.agentic import fanout
    from alignmentgraph_isd.core import dev_plans

    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {
        "id": "ILO-01", "statement": "List the four pillars.", "level": "remember"})
    step = STEP_BY_NAME["assessment"]
    work_set = dev_plans.WorkSet(set_id="AS-01", objectives=("ILO-01",))
    developer = fanout.set_step(fanout.SPECS["assessment"], work_set, step, graph)

    # The label the pointer names must be the heading the assignment really
    # carries — a pointer to a section that is not there is worse than none.
    assert developer.resolved_labels == {"objective": "The objectives your set names"}
    assert developer.resolved_labels["objective"] in developer.intro

    _model, config, _g, trajectory, brief = _harness([])
    loop = _loop(config, graph, trajectory, brief, developer)

    answer = loop._execute("read_nodes", {"node_type": "objective"})
    assert "already have" in answer
    assert developer.resolved_labels["objective"] in answer
    assert "statement" not in answer, "the pointer must not re-render the data"

    # A pool the assignment does NOT resolve still reads for real: the tool
    # stays bound and a Developer remains free to look at what it needs.
    real = loop._execute("read_nodes", {"node_type": "activity"})
    assert "already have" not in real


def test_a_stage_agent_reads_for_real():
    """Only a Developer is handed its artifacts. A stage agent reads live state
    it was never given, so nothing about its reads is redundant."""
    graph = AlignmentGraph()
    graph.add_element_node(NodeType.OBJECTIVE, "ILO-01", {"id": "ILO-01", "statement": "x"})
    _model, config, _g, trajectory, brief = _harness([])
    loop = _loop(config, graph, trajectory, brief, STEP_BY_NAME["assessment"])

    assert STEP_BY_NAME["assessment"].resolved_labels == {}
    assert "already have" not in loop._execute("read_nodes", {"node_type": "objective"})


def test_a_compacted_turn_is_kept_and_marked_not_dropped_from_the_record():
    """Auto-compaction takes the oldest turns out of the LIVE context to stay
    under the window. They are kept in the published transcript, marked, and
    left out of the token figures.

    The tab answers "what was this agent shown", and a transcript reduced to
    what is still being sent answers that for the last model call only —
    everything the earlier ones saw would be gone but for a number in
    `history_dropped`, which says how much was lost and nothing about what.
    """
    from alignmentgraph_isd.core.agentic.transcript import compacted_transcript, trim_history

    messages = [{"role": "system", "content": "S"}]
    messages += [{"role": "tool", "content": f"observation {i}" + "x" * 900}
                 for i in range(20)]
    messages += [{"role": "user", "content": "LIVE STAGE"}]

    live, compacted = trim_history(messages, budget=4000)
    assert compacted, "this transcript must overflow, or the test proves nothing"

    shown = compacted_transcript(live, compacted)
    assert len(shown) == len(messages), "a compacted turn is not lost"
    assert [m["content"] for m in shown] == [m["content"] for m in messages], (
        "the conversation must read in its original order")

    marked = [m for m in shown if m.get("compacted")]
    assert len(marked) == len(compacted)
    assert shown[0]["content"] == "S" and not shown[0].get("compacted"), (
        "the system turn is never compacted")
    assert not shown[-1].get("compacted"), "the live stage is never compacted"


def test_the_reasoning_channel_is_recorded_beside_the_turn_it_came_from():
    """The tab answers what this agent DID, and a model served with thinking on
    does half of it in a channel that is not `content`. Dropped, the record
    shows an empty assistant turn and nothing about why.

    Read off the message object, so there is one source: the reply carries it,
    the reply is already in the list, and nothing new is threaded through the
    loops to get it out.
    """
    from alignmentgraph_isd.core.agentic.transcript import serialize_messages
    from conftest import _Result

    thought = "  The brief asks for three objectives, so...  "
    shown = serialize_messages([
        {"role": "system", "content": "S"},
        _Result(content="", reasoning=thought),
        _Result(content="an ordinary reply"),
        {"role": "tool", "content": "COMMITTED"},
    ])

    assert shown[1]["reasoning"] == thought
    assert "reasoning" not in shown[0], "a dict turn has no reasoning channel"
    assert "reasoning" not in shown[2], "a reply that did not reason carries no key"
    assert "reasoning" not in shown[3]
    assert shown[1]["content"] == "", "the reasoning is not folded into the answer"


def test_the_reasoning_is_shown_but_never_sent_and_never_metered():
    """Two properties, and the whole feature rests on them.

    NEVER SENT: the model is handed the live message objects, and an
    ``AIMessage``'s ``additional_kwargs`` does not survive the conversion to a
    request body. That is a third-party behaviour we depend on — a version that
    started forwarding it would quietly show the model its own thinking back —
    so it is asserted rather than assumed.

    NEVER METERED: the window meter measures what is being sent, so reasoning
    has to stay outside the partition. `context_parts` summing to
    `prompt_chars` is what proves it did not sneak into the prompt.
    """
    pytest.importorskip("langchain_openai")
    from langchain_core.messages import AIMessage
    from langchain_openai.chat_models.base import _convert_message_to_dict

    from alignmentgraph_isd.core.agentic.transcript import context_parts, prompt_chars

    secret = "the model's private deliberation"
    wire = _convert_message_to_dict(
        AIMessage(content="answer", additional_kwargs={"reasoning_content": secret}))
    assert secret not in json.dumps(wire, default=str)

    messages = [
        {"role": "system", "content": "rules"},
        AIMessage(content="answer", additional_kwargs={"reasoning_content": secret}),
        {"role": "tool", "name": "submit", "content": "COMMITTED"},
    ]
    parts = context_parts(messages)
    assert sum(parts.values()) == prompt_chars(messages), (
        "reasoning was counted into the window it is not sent in")
    assert secret not in "".join(
        str(m.get("content") if isinstance(m, dict) else m.content) for m in messages)


def test_compaction_takes_the_stage_turn_and_that_is_the_design():
    """The stage turn IS droppable, deliberately — protecting it would pin a
    block at the front of the very window it has to make room in.

    What makes that safe is the rest of the design: what its task asked for is
    in the design state or listed as missing, its schema and rules were never in it
    (they are behind `stage_brief`, fetchable again for one turn), and its tool
    menu is redundant with the binding, which goes out with every request."""
    from alignmentgraph_isd.core.agentic.transcript import trim_history

    messages = [{"role": "system", "content": "S"},
                {"role": "user", "content": "STAGE TURN"}]
    messages += [{"role": "tool", "content": f"obs{i}" + "x" * 900} for i in range(20)]
    messages += [{"role": "assistant", "content": "latest"}]

    kept, dropped = trim_history(messages, budget=3000)

    assert kept[0]["content"] == "S", "the system turn is never dropped"
    assert dropped[0]["content"] == "STAGE TURN", "the oldest goes first, whatever it is"
    assert kept[-1]["content"] == "latest"


def test_the_agent_is_told_when_its_context_was_compacted():
    """Silently taking turns away leaves the model with a gap it cannot see and
    no reason to re-read what it lost.

    This is the note ALONE — the bracketed count and the way back, which cost
    nothing and are always true. A model-written summary is folded in after it
    when the compaction hook delivers one (``tests/test_compaction.py``), and
    the two are kept separable precisely so this still holds when it does not:
    v1 of that hook went out under JSON mode, came back as JSON, and was thrown
    away on every compaction of run e81b8108 after a multi-thousand-token
    completion. One implementation serves both arms and
    ``autonomy.compactions`` reports how often each reaches it."""
    from alignmentgraph_isd.core.agentic.compaction import _with_note
    from alignmentgraph_isd.core.agentic.transcript import COMPACTION_NOTE, trim_history

    messages = [{"role": "system", "content": "S"}, {"role": "user", "content": "TASK"}]
    messages += [{"role": "tool", "content": f"obs{i}" + "x" * 900} for i in range(20)]
    messages += [{"role": "assistant", "content": "latest"}]

    kept, dropped = trim_history(messages, budget=3000)
    noted = _with_note(kept, len(dropped))

    note = [m for m in noted if m.get(COMPACTION_NOTE)]
    assert len(note) == 1
    assert str(len(dropped)) in note[0]["content"]
    assert noted[1] is note[0], "the note sits where the dropped turns were"

    # It survives the next trim — the one message that says something was
    # dropped must not be the next thing dropped.
    again, more = trim_history(noted + [{"role": "tool", "content": "y" * 4000}], budget=3000)
    assert [m for m in again if m.get(COMPACTION_NOTE)], "the note was compacted away"

    # And it is never doubled: one note, rewritten.
    assert len([m for m in _with_note(again, 99) if m.get(COMPACTION_NOTE)]) == 1


def test_a_compacted_stage_brief_is_named_in_the_note():
    """MEASURED (run 2b9e911a, implementation): the contract went with the
    ninth turn's trim and the note said the dropped findings were "in the
    design state" — true of tool results, false of the contract, which is not
    in the design state at all. The model then invented `instructor_guidance`
    and a dict `session_guides`, was rejected eight times across three regens,
    and `instructor_guide` never committed, so every activity and material in
    the design was left unscheduled (14 P10/P11 gaps).

    The note is the fallback: a contract that fits is put BACK (the test below).
    This is what the model is told when it does not."""
    from alignmentgraph_isd.core.agentic.compaction import _with_note
    from alignmentgraph_isd.core.agentic.protocol import lost_briefs, stage_brief_block
    from alignmentgraph_isd.core.agentic.transcript import COMPACTION_NOTE, trim_history
    from alignmentgraph_isd.core.agentic.specialists import STEPS

    step = {s.name: s for s in STEPS}["implementation"]
    messages = [{"role": "system", "content": "S"},
                {"role": "user", "content": "TASK"},
                {"role": "tool", "name": "stage_brief",
                 "content": stage_brief_block(step)}]
    messages += [{"role": "tool", "content": f"obs{i}" + "x" * 900} for i in range(20)]
    messages += [{"role": "assistant", "content": "latest"}]

    kept, dropped = trim_history(messages, budget=3000)
    lost = lost_briefs(kept, dropped)
    assert lost == ["implementation"]

    note = [m for m in _with_note(kept, len(dropped), lost) if m.get(COMPACTION_NOTE)][0]
    assert "implementation" in note["content"]
    assert "schema" in note["content"], "and what it is that went"

    # A trim that leaves the brief alone says nothing about it: the note is
    # stage-precise so the single arm, which can lose one stage's brief while
    # another's is live, is not sent re-fetching what it still has.
    assert lost_briefs(messages, []) == []
    assert "schema" not in _with_note(kept, 3)[1]["content"]


def test_a_compacted_stage_brief_is_put_back_not_just_announced():
    """Asking the model to re-fetch costs a turn and depends on it complying;
    run 2b9e911a is three regens of a small model that did not. Re-attaching
    costs no turn and is certain. It goes at the TAIL, where it is newest and a
    trim (oldest first) will not take it again — not protected in place, which
    would pin a block at the front of the window it has to make room in."""
    from alignmentgraph_isd.core.agentic.compaction import compact
    from alignmentgraph_isd.core.agentic.protocol import brief_stages, stage_brief_block
    from alignmentgraph_isd.core.agentic.transcript import COMPACTION_NOTE, trim_history
    from alignmentgraph_isd.core.agentic.specialists import STEPS
    from alignmentgraph_isd.core.trajectory import TrajectoryLogger

    step = {s.name: s for s in STEPS}["implementation"]
    brief = stage_brief_block(step)
    messages = [{"role": "system", "content": "S"},
                {"role": "tool", "name": "stage_brief", "content": brief}]
    messages += [{"role": "tool", "content": f"obs{i}" + "x" * 900} for i in range(20)]

    kept, dropped = trim_history(messages, budget=20000)
    assert "implementation" not in brief_stages(kept), "the brief must have gone"

    stats: dict = {}
    restored = compact(kept, dropped, len(dropped), trajectory=TrajectoryLogger(),
                       stats=stats, restore=lambda _stage: brief, budget=20000)
    assert "implementation" in brief_stages(restored)
    assert restored[-1]["content"] == brief, "it goes at the tail, newest"
    note = [m for m in restored if m.get(COMPACTION_NOTE)][0]
    assert "schema" not in note["content"], (
        "the note must not report as lost what is sitting right there")

    # A brief that does not fit is named instead, so the model can still act.
    named = compact(kept, dropped, len(dropped), trajectory=TrajectoryLogger(),
                    stats=stats, restore=lambda _stage: brief, budget=len(brief))
    assert brief_stages(named) == set()
    assert "schema" in [m for m in named if m.get(COMPACTION_NOTE)][0]["content"]


def test_a_rejection_brings_the_contract_back_in_both_arms():
    """The single arm has had `_respec` since 2026-09-01; the multi arm had
    nothing, so it argued with a model that could not see the spec — that is
    what run 2b9e911a's implementation stage is. One function now, which
    NARROWS the decomposition axis rather than widening it."""
    import inspect

    from alignmentgraph_isd.core.agentic import loop as agentic_loop
    from alignmentgraph_isd.core.agentic import react
    from alignmentgraph_isd.core.agentic.protocol import respec, stage_brief_block
    from alignmentgraph_isd.core.agentic.specialists import STEPS

    step = {s.name: s for s in STEPS}["implementation"]
    brief = stage_brief_block(step)

    assert brief in respec([{"role": "system", "content": "s"}], step, brief)
    assert respec([{"role": "tool", "content": brief}], step, brief) == "", (
        "it is up to 7,400 characters; pasting it onto every rejection would "
        "push out the transcript it is meant to sit beside")

    for owner in (agentic_loop.ToolLoop._respec, react.ReactLoop._respec):
        assert "respec(" in inspect.getsource(owner), (
            "both arms must go through the one implementation")


def test_the_context_reports_every_tool_the_conversation_had():
    """A loop that continues another's messages may bind a NARROWER set — the
    replan round binds only `submit_dev_plan`, a plan being the one thing it
    asks for. Publishing just the live binding made the merged row claim the
    Designer never had `submit_assessment_plan`, which is how it wrote the plan
    in the first place."""
    from alignmentgraph_isd.core.agentic.tools import merge_specs

    first = [{"function": {"name": "read_nodes"}}, {"function": {"name": "submit_plan"}}]
    later = [{"function": {"name": "read_nodes"}}, {"function": {"name": "submit_dev_plan"}}]

    merged = merge_specs(first, later)
    assert [s["function"]["name"] for s in merged] == [
        "read_nodes", "submit_plan", "submit_dev_plan"], "first seen first, deduped"


def test_both_arms_go_through_the_same_compaction_call():
    """The asymmetry has to be MEASURED, which means it must not be designed:
    one implementation, one trigger, one budget, called identically."""
    import inspect

    from alignmentgraph_isd.core.agentic import loop, react

    for module in (loop, react):
        source = inspect.getsource(module)
        assert "self.messages = compact(" in source, (
            f"{module.__name__} never calls the shared compact(), so its loop "
            "cannot recover from a full window")
        # ...with the same hook. An arm that compacts without one gets the
        # count note while the other gets a summary, which would put a
        # difference in what the model is SHOWN onto the decomposition axis.
        assert "llm=self._summariser" in source, (
            f"{module.__name__} compacts without the summariser hook")
    # ...and both count it from the ONE stats template, which carries the
    # fold count and what the folds bought.
    for module_stats in (loop.ToolLoop, react.ReactLoop):
        assert "empty_stage_stats()" in inspect.getsource(module_stats.__init__)
    assert {"compactions", "compaction_summaries"} <= set(loop.empty_stage_stats()), (
        "the stats template counts compactions but not what they bought")


def test_a_trim_drains_to_the_low_water_mark_so_it_does_not_refire_every_turn():
    """MEASURED (run e81b8108, implementation stage): a trim that stopped just
    under the budget fired on three consecutive turns — each new observation
    put the history back over the line. Draining to the low-water mark leaves
    room for the conversation to grow before the next trim."""
    from alignmentgraph_isd.core.agentic.transcript import (
        message_size,
        trim_history,
        TRIM_LOW_WATER,
    )

    messages = [{"role": "system", "content": "S"}]
    messages += [{"role": "tool", "content": f"obs{i}" + "x" * 900} for i in range(20)]
    messages += [{"role": "user", "content": "LIVE"}]
    budget = 8000

    kept, dropped = trim_history(messages, budget=budget)
    assert dropped
    assert sum(message_size(m) for m in kept) <= budget * TRIM_LOW_WATER

    # An ordinary next observation does NOT trigger another trim.
    again, more = trim_history(kept + [{"role": "tool", "content": "y" * 900}], budget=budget)
    assert more == [], "the next turn refired — the low-water mark is not doing its job"



def test_every_call_in_a_batched_reply_runs_and_each_costs_a_turn():
    """MEASURED (run e81b8108): a model that sent `stage_brief` + `read_nodes`
    + `coverage_gaps` in one reply got the first answered and the rest
    silently dropped — unanswered ids in the history, a re-issued read, and
    an empty reply on the turn after, in five of six stages. Every call runs
    now, in order, and each is a turn."""
    step = STEP_BY_NAME["assessment"]
    model, config, graph, trajectory, brief = _harness([
        batch(call("read_nodes", {"node_type": "objective"}),
              call("coverage_gaps", {"relation_id": "C2"}),
              call("read_node", {"id": "ILO-01"})),
        batch(call("submit", _ASSESSMENT), call("submit_dev_plan", _ASSESSMENT_DEV_PLAN)),
    ])
    specialists.commit_outcomes(graph, trajectory, _OUTCOMES)

    loop = _loop(config, graph, trajectory, brief, step)
    loop.run()

    tools_used = [tc["tool"] for tc in trajectory.tool_calls]
    for label in ("tool_read_nodes_objective", "tool_coverage_gaps_C2", "tool_read_node",
                  "design_assessment_assessment_plan", "design_assessment_dev_plan"):
        assert any(label in t for t in tools_used), (label, tools_used)
    assert model.invocations == 2, "two model replies carried five calls"
    assert loop.stats["turns_used"] == 5, "one turn per executed call"
    assert loop.stats["batched_calls"] == 3
    assert not any(e["action"] == "invalid_action" for e in trajectory.recovery_events)
    # Every tool_call id the model produced has exactly one answer, in order.
    answered = [m["tool_call_id"] for m in loop.messages
                if isinstance(m, dict) and m.get("role") == "tool"]
    assert answered == ["c1.1", "c1.2", "c1.3", "c2.1", "c2.2"]
    # And the shared assistant message went in once per reply, not per call.
    assistants = [m for m in loop.messages if not isinstance(m, dict)]
    assert len(assistants) == 2
    assert graph.get_node(graph.section_id(NodeType.ASSESSMENT_PLAN))["data"]["dev_plan"]


def test_calls_the_budget_cannot_cover_are_answered_with_a_stub():
    """The chat API requires every call answered; a call past the ceiling or
    after the stage ended gets a stub that says it did not run."""
    step = STEP_BY_NAME["assessment"]
    model, config, graph, trajectory, brief = _harness([
        batch(*[call("read_node", {"id": f"ILO-0{i}"}) for i in range(1, 6)]),
    ])
    specialists.commit_outcomes(graph, trajectory, _OUTCOMES)
    # Every id must RESOLVE: a call that comes back ERROR is refunded
    # (ERROR_ALLOWANCE), so a budget test built on missing ids would measure
    # the refund instead of the ceiling.
    for i in range(2, 6):
        graph.add_element_node(NodeType.OBJECTIVE, f"ILO-0{i}",
                               {"id": f"ILO-0{i}", "statement": "S", "level": "apply"})

    loop = _loop(config, graph, trajectory, brief, step, max_turns=3)
    loop.run()

    tool_msgs = [m for m in loop.messages if isinstance(m, dict) and m.get("role") == "tool"]
    assert len(tool_msgs) == 5, "every id answered"
    assert sum("not executed" in m["content"] for m in tool_msgs) == 2
    assert loop.stats["turns_used"] == 3
    assert loop.stats["gave_up"]
    assert any(e["action"] == "calls_not_executed" for e in trajectory.recovery_events)


# ── the implementation envelope (run 24343e4d) ──────────────────────────────

def test_an_artifact_whose_inner_fields_are_wrong_keeps_its_name():
    """MEASURED (run 24343e4d). ``validate_implementation`` built ``arrived``
    from ANY non-empty key, and ``validate_section`` only emits error paths
    rooted at names it knows — so a dict of unrecognized keys validated CLEAN.
    ``unwrap_section``'s single-key branch then stripped the artifact's own
    name off a well-formed envelope whose INNER fields were wrong and committed
    the inside at the top level of the section.

    Consequences on that run: ``implementation_plan_0`` ended with 43 top-level
    keys (the graph dump is the auditability artifact, so it was corrupt),
    ``operator_manual`` was submitted three times and landed none of them, and
    the final validate reported it missing.
    """
    from alignmentgraph_isd.core.agentic.specialists import validate_implementation
    from alignmentgraph_isd.core.agentic.tools import unwrap_section

    # The exact payload from that run: a correct envelope, wrong inner fields.
    payload = {"prototype_execution": {
        "prototype_activities": ["PE-01: problem definition workshop"],
        "pilot_execution": {"duration": "4 weeks", "participants": 30}}}

    errors = validate_implementation(payload)
    assert errors, "the inner fields are wrong and must be reported"
    assert all("prototype_execution." in e for e in errors), errors

    # The inside ALONE must not validate, or unwrapping is a way past the
    # validator rather than the envelope tolerance it exists to be.
    assert validate_implementation(payload["prototype_execution"])

    section, unwrapped_errors = unwrap_section(payload, validate_implementation)
    assert unwrapped_errors == errors, "the model must be told what is wrong"
    assert set(section) == {"prototype_execution"}, "the artifact keeps its name"

    # ...and the tolerance it IS for still works: a genuinely stray wrapper.
    from conftest import _IMPLEMENTATION
    good = {"system_check": _IMPLEMENTATION["system_check"]}
    section, errors = unwrap_section({"artifact": good}, validate_implementation)
    assert errors == [] and section == good


def test_one_artifact_that_will_not_pass_does_not_cost_the_five_beside_it():
    """``SUBMIT_BUDGET`` was one counter for the whole STAGE, so three
    rejections anywhere ended it — and ending `implementation` means a
    whole-stage regen, which on run 24343e4d cost 55.6k prompt / 11.7k
    completion tokens / 122 s. ``tools.submit_specs`` already promises the
    opposite ("a rejected artifact costs that artifact"); this is that promise.
    """
    from conftest import _IMPLEMENTATION

    step = STEP_BY_NAME["implementation"]
    bad = {"prototype_execution": {"prototype_activities": ["x"]}}
    good = {k: v for k, v in _IMPLEMENTATION.items() if k != "prototype_execution"}
    script = [call("submit_prototype_execution", bad)] * (ToolLoop.SUBMIT_BUDGET + 1)
    script += [call(f"submit_{k}", {k: v}) for k, v in good.items()]
    _model, config, graph, trajectory, brief = _harness(script)

    loop = _loop(config, graph, trajectory, brief, step)
    loop.run()

    data = (graph.get_node(graph.section_id(NodeType.IMPLEMENTATION_PLAN)) or {}).get("data") or {}
    assert set(good) <= set(data), "the artifacts that were valid all landed"
    # ...and the section holds artifact NAMES only, never their inner fields.
    from alignmentgraph_isd.core.agentic.specialists import _IMPLEMENTATION_ARTIFACTS
    assert set(data) <= set(_IMPLEMENTATION_ARTIFACTS), sorted(data)


def test_a_commit_that_does_not_land_is_never_reported_as_committed():
    """The answer that hid the bug for a whole run: "COMMITTED. implementation
    still needs: <the artifact just sent>", beside a protocol saying never
    resend what is committed — an instruction no model can satisfy. It cost 11
    turns and ~10.4k completion tokens on run 24343e4d, and the trace recorded
    each one as the model's own redundancy (`duplicate_submit`)."""
    from conftest import _IMPLEMENTATION

    step = STEP_BY_NAME["implementation"]
    _model, config, graph, trajectory, brief = _harness(
        [call("submit_system_check", {"system_check": _IMPLEMENTATION["system_check"]})])
    loop = _loop(config, graph, trajectory, brief, step)
    # Make the commit a no-op, which is precisely what unwrapping did.
    loop.step = replace(step, commit=lambda *_a, **_k: None)
    loop.run()

    answers = [m["content"] for m in loop.messages
               if isinstance(m, dict) and m.get("role") == "tool"]
    assert answers and "NOT COMMITTED" in answers[0], answers
    assert "COMMITTED. " not in answers[0]
    assert any(e["action"] == "commit_did_not_land"
               for e in trajectory.to_dict()["events"])



def test_both_loops_refund_the_same_failures_with_the_same_words():
    """A refund is a harness accounting rule, so one that exists on a single
    side of the decomposition axis is a ceiling difference sitting inside the
    treatment — the same defect the scripted fallback had. Both arms go through
    one meter and are answered in one wording."""
    import inspect

    from alignmentgraph_isd.core.agentic import react

    from alignmentgraph_isd.core.agentic import turn as turn_mod

    # Structural, not a string match: the refund arithmetic is ONE
    # implementation now, so the property to hold is that both arms go through
    # it and that it reads its allowances from `budget`. Two classes each
    # carrying the same number is the shape a drift starts from.
    for source in (inspect.getsource(ToolLoop), inspect.getsource(react.ReactLoop)):
        assert "TurnMeter" in source, "an arm keeps its own turn accounting"
        assert "self._refunded" not in source and "self._turn_no" not in source, (
            "an arm kept a private copy of the meter's counters")
    meter_source = inspect.getsource(turn_mod.TurnMeter)
    for allowance in ("REPEAT_ALLOWANCE", "ERROR_ALLOWANCE"):
        assert f"budget.{allowance}" in meter_source
    # One wording and one chooser: what an empty turn is answered with is
    # `turn.nudge_for`, and neither arm decides it for itself.
    assert turn_mod.INVALID_TURN_NUDGE is protocol.INVALID_TURN_NUDGE
    for source in (inspect.getsource(ToolLoop), inspect.getsource(react.ReactLoop)):
        assert "nudge_for(" in source, "an arm chooses its own nudge"
        assert "INVALID_TURN_NUDGE" not in source


def test_a_regen_asks_only_for_what_is_still_missing():
    """A stage that gave up is re-run from a FRESH context, and its opening
    turn used to be byte-identical to the first attempt's: `_stage_message`
    never consulted the state, so it listed all six of `implementation`'s
    artifacts however many were already committed. The retry then re-fetched
    `stage_brief`, re-issued every read, and re-sent finished work — measured
    on run 24343e4d as three attempts costing 55.6k prompt / 11.7k completion
    tokens / 122 s, more than the stage's first-time work.
    """
    from conftest import _IMPLEMENTATION

    step = STEP_BY_NAME["implementation"]
    graph, trajectory = AlignmentGraph(), TrajectoryLogger()
    done = {k: v for k, v in _IMPLEMENTATION.items() if k != "operator_manual"}
    specialists.commit_implementation(graph, trajectory, done)

    config = HarnessRunConfig(llm_factory=lambda: None)
    loop = _loop(config, graph, trajectory, load_brief("minimal_brief.json"), step)
    opening = loop._stage_message(retrieval_available=False)

    assert "still needs: operator_manual" in opening
    assert "Already committed: " in opening
    for finished in done:
        assert f"submit_{finished}" not in tools.tool_names(
            tools.tool_specs(step, only=("operator_manual",))), finished

    # A FIRST attempt is unchanged — nothing has landed, so there is nothing to
    # say and the binding is the full set the golden fixture pins.
    fresh = _loop(config, AlignmentGraph(), TrajectoryLogger(),
                  load_brief("minimal_brief.json"), step)
    assert "Already committed" not in fresh._stage_message(retrieval_available=False)
    assert (tools.tool_specs(step, only=None)
            == tools.tool_specs(step)), "the default binding must not move"


# ── reading several artifacts in one turn ───────────────────────────────────

def test_read_node_takes_several_ids_in_one_turn():
    """MEASURED (run single_20260908_111232, content): the Content Designer
    spent 27 turns on 24 distinct `read_node` calls and the Material Developer
    27 on 16, each walking a list of activity ids one node per turn. At
    STAGE_MAX_TURNS 24 that exhausts the stage on reading alone, and the stage
    gave up with 5 content modules against 23 activities — C5 coverage 0.13.

    The other half of the 2026-09-06 read-cost change: `read_nodes` became a
    LISTING so a planner could see the ids it had to write, and the only way to
    then read them in full was one call per id. Scope is unchanged; turns are
    not."""
    step = STEP_BY_NAME["assessment"]
    _model, config, graph, trajectory, brief = _harness([])
    specialists.commit_outcomes(graph, trajectory, _OUTCOMES)
    loop = _loop(config, graph, trajectory, brief, step)

    ids = ["ILO-01", "ILO-02", "ILO-03"]
    for one in ids[1:]:
        graph.add_node(NodeType.OBJECTIVE, one,
                       {"statement": f"Objective {one}.", "level": "apply"})
    out = loop._execute("read_node", {"ids": ids})
    for one in ids:
        assert one in out
    assert not out.startswith("ERROR")

    assert loop._execute("read_node", {"ids": ids}).count("[OBJECTIVE:") == 3

    # The old single-id shape still works: a model that sends it has produced
    # a usable call, and refusing it would cost a turn over an envelope.
    assert ids[0] in loop._execute("read_node", {"id": ids[0]})


def test_reading_several_shares_one_budget_and_one_still_gets_all_of_it():
    """The budget is SHARED, never multiplied — a batch must not be a way to
    put N x READ_CHAR_BUDGET into one observation, which is the failure
    `render_nodes` is bounded by size to prevent. One id keeps the whole
    budget, so "in full means in full" holds exactly as it did for the call
    this replaces."""
    from alignmentgraph_isd.core.agentic import tools as tools_module

    step = STEP_BY_NAME["assessment"]
    _model, config, graph, trajectory, brief = _harness([])
    specialists.commit_outcomes(graph, trajectory, _OUTCOMES)
    loop = _loop(config, graph, trajectory, brief, step)

    ids = [f"ILO-{i:02d}" for i in range(1, 12)]
    for one in ids[1:]:
        graph.add_node(NodeType.OBJECTIVE, one,
                       {"statement": "y" * tools_module.READ_CHAR_BUDGET, "level": "apply"})
    many = loop._execute("read_node", {"ids": ids})
    assert len(many) <= tools_module.READ_CHAR_BUDGET + 200, "one shared budget"

    long_text = "x" * (tools_module.NODE_CHAR_CAP * 4)
    graph.add_node(NodeType.OBJECTIVE, "ILO-BIG", {"statement": long_text, "level": "apply"})
    alone = loop._execute("read_node", {"ids": ["ILO-BIG"]})
    assert long_text in alone, "a single read is still the whole artifact"


def test_an_unreadable_id_costs_that_id_and_says_what_may_be_read():
    """MEASURED on the same run: the Material Developer asked for 'MS-001' — a
    real media_selection node, outside its read scope — was told only "no node
    with id 'MS-001'", and asked again.

    Two rules here. One bad id must not take the batch with it, or the per-id
    turn cost this change removes comes straight back on the first typo; and
    the refusal names the readable types, because the scope IS the treatment
    and a model that cannot see it can only guess."""
    step = STEP_BY_NAME["assessment"]
    _model, config, graph, trajectory, brief = _harness([])
    specialists.commit_outcomes(graph, trajectory, _OUTCOMES)
    loop = _loop(config, graph, trajectory, brief, step)

    good = "ILO-01"
    out = loop._execute("read_node", {"ids": [good, "MS-001"]})
    assert good in out, "the readable id was still served"
    assert "MS-001" in out and "Readable types here" in out
    for readable in step.readable_types:
        assert readable in out


def test_a_read_that_came_through_the_neighbouring_door_is_still_served():
    """MEASURED (runs 53042a0d, 2559b22d): 50 of 63 ERROR observations were
    "node_type must be one of …", and most carried a perfectly good `ids`
    array — the model wanting "read these ids" and reaching for the PLURAL
    name. `read_nodes` lists a type, `read_node` reads ids; the names differ by
    one character, and since `read_node` began taking an array they no longer
    differ much in arguments either.

    Both directions are unambiguous, so both are served. Same rule as
    `_submit_alias` rescuing a bare `submit`: a call is not wrong because it
    came through the neighbouring door."""
    step = STEP_BY_NAME["assessment"]
    _model, config, graph, trajectory, brief = _harness([])
    specialists.commit_outcomes(graph, trajectory, _OUTCOMES)
    loop = _loop(config, graph, trajectory, brief, step)

    by_ids = loop._execute("read_nodes", {"ids": ["ILO-01"]})
    assert not by_ids.startswith("ERROR") and "ILO-01" in by_ids

    by_type = loop._execute("read_node", {"node_type": "objective"})
    assert not by_type.startswith("ERROR") and "ILO-01" in by_type
    assert by_type == loop._execute("read_nodes", {"node_type": "objective"})

    # A call that says neither is still an error, and now names the way out.
    empty = loop._execute("read_nodes", {})
    assert empty.startswith("ERROR") and "read_node" in empty


def test_a_turn_that_bought_no_observation_is_refunded():
    """The other half of the same family as REPEAT_ALLOWANCE.
    An ERROR carries no artifact and no fact about the design, so charging a
    turn for it spends the stage's budget on the model's confusion — measured
    at 13% of every tool result over runs 53042a0d/2559b22d, beside 84 repeat
    refusals, so 31% of turns taken bought nothing.

    Bounded, so a model that only ever errors still reaches the ceiling."""
    step = STEP_BY_NAME["assessment"]
    _model, config, graph, trajectory, brief = _harness([
        batch(*[call("read_node", {"ids": [f"NOPE-{i}"]}) for i in range(1, 9)]),
    ])
    specialists.commit_outcomes(graph, trajectory, _OUTCOMES)

    loop = _loop(config, graph, trajectory, brief, step, max_turns=4)
    loop.run()

    assert loop.stats["tool_errors"] > 0
    # Four turns of budget plus ERROR_ALLOWANCE refunds, and no more: the
    # allowance stretches the stage, it does not remove the ceiling.
    assert loop.stats["turns_used"] == 4 + budget.ERROR_ALLOWANCE


def test_both_arms_refund_a_failed_call_on_the_same_rule():
    """A refund is a harness accounting rule. One that existed on a single side
    of the decomposition axis would be a ceiling difference sitting inside the
    treatment — the defect the scripted fallback had before it was removed."""
    import inspect

    from alignmentgraph_isd.core.agentic import react

    from alignmentgraph_isd.core.agentic import turn as turn_mod

    for owner in (loop_module.ToolLoop._handle_read, react.ReactLoop._handle_read):
        source = inspect.getsource(owner)
        assert 'startswith("ERROR")' in source, owner
        assert "tool_error()" in source, f"{owner} does not refund through the meter"
    assert "budget.ERROR_ALLOWANCE" in inspect.getsource(turn_mod.TurnMeter.tool_error)



def test_a_field_the_artifact_does_not_have_is_rejected_by_name():
    """MEASURED (run 7ef3ed16): ``submit_assessment_plan`` arrived carrying
    ``pilot_data_plan`` and, beside it at the TOP level, the four fields of one
    ``anticipated_difficulties`` entry — ``area``, ``rationale``,
    ``detected_by``, ``first_revision``. The schema allowed extra keys and
    ``validate_section`` only checks the required ones, so the stray object
    went into the graph node, through the aggregator, and into
    ``addie_output.json`` for the judge.

    Naming the keys is what makes it fixable in one turn: the model wrote the
    content, it just put it one level too high."""
    step = STEP_BY_NAME["assessment"]
    difficulty = {"area": "x", "rationale": "y", "detected_by": "z", "first_revision": "w"}
    plan = {"lo_coverage_targets": {"ILO-01": ["formative"]},
            "pilot_data_plan": {"anticipated_difficulties": [difficulty]}}

    assert tools.undeclared_key_errors(step, {"assessment_plan": plan}) == []

    errors = tools.undeclared_key_errors(step, {"assessment_plan": {**plan, **difficulty}})
    assert len(errors) == 1
    # Every stray key named, and the artifact's real fields listed beside them.
    for key in difficulty:
        assert key in errors[0]
    assert "lo_coverage_targets" in errors[0] and "pilot_data_plan" in errors[0]


def test_the_undeclared_key_gate_judges_objects_only():
    """An ARRAY field's items are the Developer tier's contract
    (``fanout.output_errors``), and a stray key inside a nested object is a
    different, unmeasured failure. A gate is worth its submit budget only where
    it has been seen to fire."""
    step = STEP_BY_NAME["assessment"]
    # An array submit field, and a nested object one level down: neither judged.
    assert tools.undeclared_key_errors(
        STEP_BY_NAME["outcomes"], {"learning_objectives": [{"whatever": 1}]}) == []
    assert tools.undeclared_key_errors(step, {"assessment_plan": {
        "lo_coverage_targets": {"ILO-01": ["formative"]},
        "pilot_data_plan": {"anticipated_difficulties": [], "invented": 1}}}) == []
