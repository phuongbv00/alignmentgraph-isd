"""Elicitation loop contract: ask turns vs propose turns, brief validation."""
from __future__ import annotations

import json

import pytest

from alignmentgraph_isd import HarnessRunConfig
from alignmentgraph_isd.elicitation import BriefElicitationAgent


class _ScriptedModel:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.seen_messages: list[list[dict]] = []

    def invoke(self, messages):
        self.seen_messages.append(messages)

        class R:
            pass

        r = R()
        r.content = self._responses.pop(0)
        return r


def _config(responses: list[str]) -> tuple[HarnessRunConfig, _ScriptedModel]:
    model = _ScriptedModel(responses)
    config = HarnessRunConfig.from_ablation("case_study", memory={"enabled": False})
    config.llm_factory = lambda: model
    return config, model


def test_ask_then_propose_flow():
    config, model = _config([
        json.dumps({"action": "ask", "question": "How long should the program run?"}),
        json.dumps({
            "action": "propose",
            "summary": "Two-day OOP program for freshers.",
            "brief": {
                "title": "OOP for Freshers",
                "domain": "Software Engineering",
                "duration": "2 days",
                "target_audience": "Fresher developers",
                "learning_goals": ["Explain OOP pillars", "Apply inheritance", "Design a class hierarchy"],
            },
        }),
    ])
    agent = BriefElicitationAgent(config)

    turn1 = agent.step([], "We need OOP training for freshers")
    assert turn1.kind == "question"
    assert "How long" in turn1.message
    # System prompt is always the first message of the call.
    assert model.seen_messages[0][0]["role"] == "system"

    history = [
        {"role": "user", "content": "We need OOP training for freshers"},
        {"role": "assistant", "content": turn1.message},
    ]
    turn2 = agent.step(history, "2 days, about 20 people")
    assert turn2.kind == "draft"
    assert turn2.draft_brief.title == "OOP for Freshers"
    assert turn2.draft_brief.id.startswith("brief-")
    assert len(turn2.draft_brief.learning_goals) == 3


def test_unparseable_response_degrades_to_question():
    config, _ = _config(["this is not json at all"])
    agent = BriefElicitationAgent(config)
    turn = agent.step([], "hello")
    assert turn.kind == "question"
    assert turn.message  # generic fallback question


def test_requires_llm_factory():
    config = HarnessRunConfig.from_ablation("case_study", memory={"enabled": False})
    with pytest.raises(RuntimeError, match="llm_factory"):
        BriefElicitationAgent(config)
