"""Unit tests of the agentic arm's tool loop (core/agentic/loop.py):
act→observe over the graph, deterministic submit validation, budgets and the
scripted fallback."""
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
    def __init__(self, content: str) -> None:
        self.content = content
        self.usage_metadata = None


class ScriptedModel:
    """Returns a fixed sequence of responses, shared across factory calls."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.invocations = 0

    def bind(self, **_kwargs) -> "ScriptedModel":
        return self

    def invoke(self, _messages) -> _Result:
        self.invocations += 1
        return _Result(self._responses.pop(0) if self._responses else "{}")


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
        json.dumps({"action": "read_nodes", "args": {"node_type": "objective"}}),
        json.dumps({"action": "coverage_gaps", "args": {"relation_id": "C2"}}),
        json.dumps({"action": "submit", "args": _ASSESSMENT}),
    ])
    specialists.commit_outcomes(graph, trajectory, _OUTCOMES)

    _loop(config, graph, trajectory, brief, step).run()

    assert graph.element_nodes(NodeType.ASSESSMENT)
    assert graph.get_edges(relation_id="C2")  # AT-01 -> ILO-01 established by the shared matcher
    tools_used = [tc["tool"] for tc in trajectory.tool_calls]
    # Tool labels carry their scoping argument so the judge-visible trace
    # distinguishes reads of different targets.
    assert f"{step.identity}.tool_read_nodes_objective" in tools_used
    assert f"{step.identity}.tool_coverage_gaps_C2" in tools_used
    assert f"{step.identity}.design_assessment" in tools_used
    assert model.invocations == 3


def test_rejected_submit_returns_errors_and_second_submit_lands():
    step = STEP_BY_NAME["outcomes"]
    _model, config, graph, trajectory, brief = _harness([
        json.dumps({"action": "submit", "args": {"learning_objectives": []}}),
        json.dumps({"action": "submit", "args": _OUTCOMES}),
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


def test_turn_budget_exhausted_falls_back_to_scripted_single_shot():
    step = STEP_BY_NAME["analysis"]
    junk = [json.dumps({"noise": i}) for i in range(ToolLoop.MAX_TURNS)]
    _model, config, graph, trajectory, brief = _harness(junk + [json.dumps(_ANALYSIS)])

    _loop(config, graph, trajectory, brief, step).run()

    assert graph.element_nodes(NodeType.GAP)
    assert any(e["action"] == "agentic_fallback" for e in trajectory.recovery_events)
    assert any(tc["tool"].endswith("design_analysis_fallback") for tc in trajectory.tool_calls)


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
        json.dumps({"action": "submit", "args": {"artifact": _OUTCOMES}}),
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


def test_invalid_final_submit_is_rescued_by_the_scripted_fallback():
    """Regression for the measured 2B failure: a truncated submit that kept
    only part of the artifact must not be committed as-is — the scripted
    single-shot (which works on the same model in the classic arms) gets one
    rescue attempt first."""
    step = STEP_BY_NAME["outcomes"]
    bad = json.dumps({"action": "submit", "args": {"learning_objectives": []}})
    _model, config, graph, trajectory, brief = _harness([bad, bad, bad, json.dumps(_OUTCOMES)])
    specialists.commit_analysis(graph, trajectory, _ANALYSIS)

    _loop(config, graph, trajectory, brief, step).run()

    assert graph.element_nodes(NodeType.OBJECTIVE)
    assert any(e["action"] == "submit_invalid_final" for e in trajectory.recovery_events)
    assert any(tc["tool"].endswith("design_outcomes_fallback") for tc in trajectory.tool_calls)


def test_invalid_commit_on_spent_budget_is_recovery_not_a_judge_visible_step():
    step = STEP_BY_NAME["outcomes"]
    bad = json.dumps({"action": "submit", "args": {"learning_objectives": []}})
    # Three invalid submits AND an invalid fallback: nothing valid ever shows
    # up, so the commit is recovery plumbing, never a judge-visible step.
    _model, config, graph, trajectory, brief = _harness([bad, bad, bad, "{}"])
    specialists.commit_analysis(graph, trajectory, _ANALYSIS)

    _loop(config, graph, trajectory, brief, step).run()

    assert not any("design_outcomes" in tc["tool"] for tc in trajectory.tool_calls)
    assert any(e["action"] == "commit_invalid_section" for e in trajectory.recovery_events)


def test_repeated_identical_tool_call_is_not_reanswered():
    """Measured 2B failure: six identical read_nodes calls burned the whole
    turn budget. A repeat gets a nudge instead of a second answer, and never
    shows up as a judge-visible tool call."""
    step = STEP_BY_NAME["assessment"]
    read = json.dumps({"action": "read_nodes", "args": {"node_type": "objective"}})
    _model, config, graph, trajectory, brief = _harness([
        read, read, read,
        json.dumps({"action": "submit", "args": _ASSESSMENT}),
    ])
    specialists.commit_outcomes(graph, trajectory, _OUTCOMES)

    _loop(config, graph, trajectory, brief, step).run()

    assert graph.element_nodes(NodeType.ASSESSMENT)
    reads = [tc for tc in trajectory.tool_calls if "tool_read_nodes" in tc["tool"]]
    assert len(reads) == 1  # answered once, repeats are recovery plumbing
    repeats = [e for e in trajectory.recovery_events if e["action"] == "repeated_tool_call"]
    assert len(repeats) == 2


def test_analysis_submit_requires_the_improvement_plan():
    """Measured 2B failure: after a truncation rejection the model trimmed
    improvement_plan away entirely; nothing required it, so the run shipped
    zero IMPROVEMENT nodes and the program-improvement rubric item scored 0."""
    from alignmentgraph_isd.core.agentic.specialists import validate_analysis

    assert validate_analysis(_ANALYSIS) == []
    trimmed = {k: v for k, v in _ANALYSIS.items() if k != "improvement_plan"}
    assert any("improvement_plan.improvements" in e for e in validate_analysis(trimmed))


def test_implementation_submit_requires_the_guides():
    """instructor_guide/operator_manual are required by the shared section
    schema and scored by two rubric items — a submit without them must be
    rejected (measured: both scored 0 when a 2B model economized them away)."""
    from alignmentgraph_isd.core.agentic.specialists import validate_implementation

    complete = {
        "instructor_orientation": {"schedule": "90m"},
        "system_check": {"checklist": ["network"]},
        "prototype_execution": {"pilot_scope": "one cohort"},
        "monitoring": {"monitoring_criteria": ["completion"]},
        "instructor_guide": {"overview": "flow"},
        "operator_manual": {"system_setup": "provision"},
    }
    assert validate_implementation(complete) == []
    without_guides = {k: v for k, v in complete.items()
                      if k not in ("instructor_guide", "operator_manual")}
    errors = validate_implementation(without_guides)
    assert any("instructor_guide" in e for e in errors)
    assert any("operator_manual" in e for e in errors)


def test_unknown_tool_and_disallowed_type_come_back_as_error_observations():
    step = STEP_BY_NAME["assessment"]
    _model, config, graph, trajectory, brief = _harness([
        json.dumps({"action": "read_nodes", "args": {"node_type": "rubric"}}),  # not readable here
        json.dumps({"action": "frobnicate", "args": {}}),
        json.dumps({"action": "submit", "args": _ASSESSMENT}),
    ])
    specialists.commit_outcomes(graph, trajectory, _OUTCOMES)

    loop = _loop(config, graph, trajectory, brief, step)
    assert loop._execute("read_nodes", {"node_type": "rubric"}).startswith("ERROR")
    assert loop._execute("frobnicate", {}).startswith("ERROR")
    loop.run()
    assert graph.element_nodes(NodeType.ASSESSMENT)
