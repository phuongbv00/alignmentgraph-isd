"""End-to-end tests of the agentic arm (core/agentic/run.py): full run over
the canned fixture payloads, result-contract parity with the scripted runner,
and graph parity with the single arm (whose commit bodies the agentic steps
are copies of)."""
from __future__ import annotations

import json

from alignmentgraph_isd import HarnessRunConfig, run_design_brief
from alignmentgraph_isd.core.agentic import run_agentic_brief
from alignmentgraph_isd.core.agentic.specialists import STEPS
from alignmentgraph_isd.core.alignment_graph import NodeType

from conftest import events_of, FakeChatModel, load_brief


class _Result:
    def __init__(self, content: str) -> None:
        self.content = content
        self.usage_metadata = None


class SubmitWrappingModel(FakeChatModel):
    """The conftest fake, speaking the agentic JSON-action protocol: the same
    canned schema-keyed payload, wrapped as a submit action."""

    def invoke(self, messages) -> _Result:
        payload = json.loads(super().invoke(messages).content)
        return _Result(json.dumps({"action": "submit", "args": payload}, ensure_ascii=False))


def _agentic_result():
    config = HarnessRunConfig(llm_factory=lambda: SubmitWrappingModel())
    return run_agentic_brief(config, load_brief("minimal_brief.json"))


def test_end_to_end_result_contract_and_every_step_produced():
    result = _agentic_result()

    assert {"addie_output", "trajectory", "trajectory_deep", "metadata",
            "graph", "graph_dot"} <= set(result)
    run_config = result["metadata"]["run_config"]
    assert run_config["control_mode"] == "agentic"
    assert run_config["agent_mode"] == "multi"
    assert run_config["context_mode"] == "graph"
    # Schema-valid canned payloads must aggregate to a valid ADDIE output.
    assert result["metadata"]["validation_errors"] == []

    nodes_by_id = {n["id"]: n for n in result["graph"]["nodes"]}
    for element_type in (NodeType.GAP, NodeType.OBJECTIVE, NodeType.ASSESSMENT,
                         NodeType.ACTIVITY, NodeType.MATERIAL, NodeType.RUBRIC):
        assert any(n["type"] == element_type and ":" in n["id"]
                   for n in nodes_by_id.values()), f"no {element_type} elements"
    assert nodes_by_id.get("implementation_plan_0", {}).get("data")

    # One submit-wrapped call per step — no hidden extra turns in the loop.
    # A repair that hands missing content back to the model spends a call of
    # its own (batched, so at most one per repair event), which is why the
    # budget is a range and not an equality.
    calls = result["metadata"]["token_usage"]["llm_calls"]
    repair_events = result["metadata"]["repair_metrics"]["repair_events"]
    assert len(STEPS) <= calls <= len(STEPS) + repair_events
    # The judge-visible trace carries the per-step design actions.
    design_actions = {tc["tool"].split(".", 1)[1] for tc in result["trajectory"]["tool_calls"]}
    assert {f"design_{step.name}" for step in STEPS} <= design_actions


def test_graph_parity_with_the_single_arm_commits():
    """The agentic commits are copies of SingleDesignerAgent's; on identical
    payloads the two arms must ship the same graph for the families where
    that copy relationship still holds — the copy discipline's regression
    guard.

    2026-08-28 scope note: the dev-plan fan-out gave SingleDesignerAgent's
    assessment/activities/content/rubrics states a dispatch+per-set-call
    structure (different work-set ids, e.g. "AT-F-ILO-01"/"AB-03") that
    core/agentic/specialists.py deliberately was NOT converted to (see
    CLAUDE.md's "Agentic experimental arm" note — it stays a manual copy of
    the PRE-fan-out monolithic-per-family shape). Full graph identity across
    those four families is no longer meaningful; this test now checks it
    only for the three families the fan-out never touched (analysis/
    outcomes/implementation), where the copy relationship is exact."""
    agentic = _agentic_result()
    single = run_design_brief(
        load_brief("minimal_brief.json"),
        HarnessRunConfig(llm_factory=lambda: FakeChatModel(), agent_mode="single"),
    )

    unconverted_types = {
        NodeType.GAP, NodeType.TOPIC, NodeType.CONSTRAINT, NodeType.IMPROVEMENT,
        NodeType.LEARNER_PROFILE, NodeType.COURSE_GOAL, NodeType.OBJECTIVE,
        NodeType.IMPLEMENTATION_PLAN,
    }

    def node_ids(result, types):
        return {n["id"] for n in result["graph"]["nodes"] if n["type"] in types}

    assert node_ids(agentic, unconverted_types) == node_ids(single, unconverted_types)

    def edge_set(result, types):
        # BOTH endpoints, not either: an objective (unconverted) is also the
        # SOURCE of C2/C7 edges into assessment/rubric elements (converted),
        # whose ids differ by construction now (see the docstring above) —
        # counting a one-sided edge would leak that expected variance back in.
        ids = node_ids(result, types)
        return {
            (e["type"], e["source"], e["target"]) for e in result["graph"]["edges"]
            if e["source"] in ids and e["target"] in ids
        }

    assert edge_set(agentic, unconverted_types) == edge_set(single, unconverted_types)


def test_agentic_run_records_phases_and_repair_scaffolding():
    result = _agentic_result()
    deep = result["trajectory_deep"]
    phases = [a["context"]["phase"] for a in deep["actions"] if a["action"] == "phase_started"]
    assert phases == [step.name for step in STEPS] + ["aggregate"]
    # The deterministic self-validation ran for every step (check_events
    # populated even when nothing was owned — same instrumentation parity rule
    # the scripted arms follow).
    assert len(events_of(result["trajectory"], "check")) >= len(STEPS)
