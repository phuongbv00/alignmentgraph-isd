"""Network-free tests: run/refine contract, token accounting, unchanged short-circuit."""
from __future__ import annotations

import json

import pytest

import react_isd_baseline.agent as agent_mod
from react_isd_baseline.agent import PHASES, ReActISDBaselineAgent
from react_isd_baseline.llm import LLMSettings, TrackedChatModel

SCENARIO = {
    "scenario_id": "cs-java-oop",
    "title": "Object-Oriented Programming in Java",
    "context": {
        "target_audience": "Fresher developers",
        "learning_environment": "Hybrid",
        "duration": "3 days",
        "prior_knowledge": "Java syntax",
        "class_size": "20",
    },
    "learning_goals": ["Explain OOP pillars", "Apply inheritance"],
}

SECTION = {"placeholder": "content"}


class FakeInner:
    """Returns canned JSON with usage metadata; behavior keyed off the prompt."""

    def __init__(self, refine_changes_design: bool = False) -> None:
        self.refine_changes_design = refine_changes_design
        self.prompts: list[str] = []

    def invoke(self, prompt):
        self.prompts.append(prompt)

        class R:
            usage_metadata = {"input_tokens": 100, "output_tokens": 50}

        r = R()
        if "EDIT REQUEST" in prompt:
            if self.refine_changes_design and "D-11" in prompt:
                r.content = json.dumps({"learning_objectives": [{"id": "LO-06"}]})
            else:
                r.content = json.dumps({"unchanged": True})
        else:
            r.content = json.dumps(SECTION)
        return r


@pytest.fixture
def make_agent(monkeypatch):
    def _make(**fake_kwargs) -> tuple[ReActISDBaselineAgent, FakeInner]:
        fake = FakeInner(**fake_kwargs)
        monkeypatch.setattr(
            agent_mod, "create_chat_model",
            lambda settings, tracker: TrackedChatModel(fake, tracker),
        )
        return ReActISDBaselineAgent(LLMSettings(model_name="fake")), fake
    return _make


def test_run_contract_and_token_accounting(make_agent):
    agent, _ = make_agent()
    result = agent.run(SCENARIO)

    assert result["agent_id"] == "react-isd-baseline"
    assert set(result["addie_output"]) == set(PHASES)
    assert all(result["addie_output"][p] == SECTION for p in PHASES)
    meta = result["metadata"]
    assert meta["mode"] == "run"
    assert meta["llm_calls"] == 5
    assert meta["total_tokens"] == 5 * 150
    assert meta["token_usage"] == {"prompt_tokens": 500, "completion_tokens": 250}
    assert meta["fallbacks"] == []


def test_refine_unchanged_passthrough(make_agent):
    agent, fake = make_agent()
    previous = {p: {"old": p} for p in PHASES}
    result = agent.refine(SCENARIO, previous, "No real change needed")

    assert result["addie_output"] == previous
    meta = result["metadata"]
    assert meta["mode"] == "refine"
    assert meta["unchanged_phases"] == sorted(PHASES)
    assert meta["llm_calls"] == 5  # every phase still pays its (cheap) check call
    # Each refine prompt embeds the previous section and the edit request.
    assert all("EDIT REQUEST" in p for p in fake.prompts)
    assert any('"old": "design"' in p for p in fake.prompts)


def test_refine_changes_only_requested_phase(make_agent):
    agent, _ = make_agent(refine_changes_design=True)
    previous = {p: {"old": p} for p in PHASES}
    result = agent.refine(SCENARIO, previous, "Add objective LO-06")

    assert result["addie_output"]["design"] == {"learning_objectives": [{"id": "LO-06"}]}
    for phase in PHASES:
        if phase != "design":
            assert result["addie_output"][phase] == previous[phase]
    assert result["metadata"]["unchanged_phases"] == sorted(p for p in PHASES if p != "design")


def test_run_usage_isolated_per_call(make_agent):
    agent, _ = make_agent()
    first = agent.run(SCENARIO)
    second = agent.run(SCENARIO)
    # Per-run metadata reports the delta, not the cumulative tracker total.
    assert first["metadata"]["total_tokens"] == second["metadata"]["total_tokens"] == 750
