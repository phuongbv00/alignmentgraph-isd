"""Unit tests of the tool loop (core/agentic/loop.py): act→observe over the
graph, deterministic submit validation, budgets, and what a step does when it
exhausts them."""
from __future__ import annotations

import json

from alignmentgraph_isd import HarnessRunConfig
from alignmentgraph_isd.core.agentic.loop import AgenticLLM, ToolLoop
from alignmentgraph_isd.core.agentic import specialists
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

_ASSESSMENT = {
    "assessment_plan": {
        "diagnostic": ["Pre-quiz"], "formative": ["Critique"], "summative": ["Project"],
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


def _loop(config, graph, trajectory, brief, step) -> ToolLoop:
    llm = AgenticLLM(config, trajectory, step.identity)
    return ToolLoop(config, graph, trajectory, brief, step, llm)


def test_tool_call_then_submit_commits_and_logs_the_trace():
    step = STEP_BY_NAME["assessment"]
    model, config, graph, trajectory, brief = _harness([
        call("read_nodes", {"node_type": "objective"}),
        call("coverage_gaps", {"relation_id": "C2"}),
        call("submit", _ASSESSMENT),
    ])
    specialists.commit_outcomes(graph, trajectory, _OUTCOMES)

    _loop(config, graph, trajectory, brief, step).run()

    # `assessment` is a DISPATCH stage since the Developer tier came back: one
    # submit lands the PLAN, and the items are produced per work set (fanout.py).
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
    # Four: two reads, the plan submit, and the ONE turn the stage spends
    # asking for the optional artifact it was not given (`dev_plan`). The
    # script has nothing left, so that turn ends the stage — the nudge costs a
    # call and never more than one.
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
    from alignmentgraph_isd.core.agentic.specialists import (
        commit_implementation, missing_parts, step_done, validate_implementation,
    )

    step = STEP_BY_NAME["implementation"]
    complete = {
        "instructor_orientation": {"schedule": "90m"},
        "system_check": {"checklist": ["network"]},
        "prototype_execution": {"pilot_scope": "one cohort"},
        "monitoring": {"monitoring_criteria": ["completion"]},
        "instructor_guide": {"overview": "flow"},
        "operator_manual": {"system_setup": "provision"},
    }
    # Each artifact is valid on its own — that is what one submit per artifact
    # means, and rejecting the first correct instalment would be the bug.
    for key, value in complete.items():
        assert validate_implementation({key: value}) == [], key
    assert validate_implementation({}), "an empty submit is still an error"

    graph, trajectory = AlignmentGraph(), TrajectoryLogger()
    without_guides = {k: v for k, v in complete.items()
                      if k not in ("instructor_guide", "operator_manual")}
    commit_implementation(graph, trajectory, without_guides)
    assert set(missing_parts(step, graph)) == {"instructor_guide", "operator_manual"}
    assert not step_done(step, graph)

    commit_implementation(graph, trajectory, {
        k: complete[k] for k in ("instructor_guide", "operator_manual")})
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


def test_a_value_that_is_genuinely_wrong_is_still_rejected():
    """Coercion must not paper over a real model mistake: a string that is not
    JSON stays a string, and the deterministic validator still says so."""
    step = STEP_BY_NAME["outcomes"]
    _model, config, graph, trajectory, brief = _harness([
        call("submit", {"course_goal": "not json at all",
                        "learning_objectives": "also not json"}),
        call("submit", _OUTCOMES),
    ])
    specialists.commit_analysis(graph, trajectory, _ANALYSIS)

    _loop(config, graph, trajectory, brief, step).run()

    rejected = [e for e in trajectory.recovery_events if e["action"] == "submit_rejected"]
    assert rejected, "a genuinely malformed submit must still be rejected"
    assert graph.element_nodes(NodeType.OBJECTIVE), "and the retry must still land"


def test_protocol_words_in_the_artifact_are_rejected():
    """MEASURED FAILURE (single_20260831_152628): every arm leaked tool names
    into judge-scored content — 33 occurrences in the full pipeline, including
    an assessment item asking learners to map SDLC phases to 'read_nodes' and
    'read_edges'. Same shape as the placeholder gate: rejected with an
    actionable message, not silently repaired."""
    from alignmentgraph_isd.core.agentic.loop import protocol_leak_errors

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
    from alignmentgraph_isd.core.agentic.loop import message_size, trim_history

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
    _model, config, graph, trajectory, brief = _harness([markup, call("submit", _ASSESSMENT)])
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
    assert fanout.DEVELOPER_MAX_TURNS < ToolLoop.MAX_TURNS


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

    assert loop.stats["repeated_calls"] > ToolLoop.REPEAT_ALLOWANCE
    # The refund is bounded, so the loop still terminates on its own.
    assert loop.stats["turns_used"] <= ToolLoop.MAX_TURNS + ToolLoop.REPEAT_ALLOWANCE


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
    from alignmentgraph_isd.core.agentic.loop import compacted_transcript, trim_history

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


def test_compaction_takes_the_stage_turn_and_that_is_the_design():
    """The stage turn IS droppable, deliberately — protecting it would pin a
    block at the front of the very window it has to make room in.

    What makes that safe is the rest of the design: its task survives as
    content in the compaction summary, its schema and rules were never in it
    (they are behind `stage_brief`, fetchable again for one turn), and its tool
    menu is redundant with the binding, which goes out with every request."""
    from alignmentgraph_isd.core.agentic.loop import trim_history

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
    no reason to re-read what it lost. This test covers the deterministic half:
    the note itself, which costs nothing. The rolling summary beside it IS a
    model call (``core/agentic/compaction.py``), made by the orchestrator and
    landing on `single` far more often than on `multi` — that asymmetry is the
    axis reporting its price, not a confound, which is why one implementation
    serves both arms and ``autonomy.compactions`` reports it."""
    from alignmentgraph_isd.core.agentic.loop import (
        COMPACTION_NOTE, _with_note, trim_history,
    )

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


def test_the_context_reports_every_tool_the_conversation_had():
    """A loop that continues another's messages may bind a NARROWER set — the
    replan round binds only `submit_dev_plan`, a plan being the one thing it
    asks for. Publishing just the live binding made the merged row claim the
    Designer never had `submit_assessment_plan`, which is how it wrote the plan
    in the first place."""
    from alignmentgraph_isd.core.agentic.loop import _merge_specs

    first = [{"function": {"name": "read_nodes"}}, {"function": {"name": "submit_plan"}}]
    later = [{"function": {"name": "read_nodes"}}, {"function": {"name": "submit_dev_plan"}}]

    merged = _merge_specs(first, later)
    assert [s["function"]["name"] for s in merged] == [
        "read_nodes", "submit_plan", "submit_dev_plan"], "first seen first, deduped"
