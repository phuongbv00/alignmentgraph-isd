"""The planning conversation, and its tolerance for badly-formed model output.

A small self-hosted model asked for JSON will regularly not return JSON. Every
shape below was chosen because it is something models actually emit. None of
them may raise: the person is mid-sentence.
"""
from __future__ import annotations

import json

import pytest

from alignmentgraph_isd.server import llm_settings, planner

WELL_FORMED = {
    "reply": "What subject does this program cover?",
    "brief_patch": {"title": "Intro to Arabic"},
    "missing_fields": ["domain"],
    "ready": False,
}


class ScriptedModel:
    """Returns canned responses in order, recording what it was asked."""

    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)
        self.calls: list[list[dict]] = []

    def bind(self, **_kwargs):
        return self

    def invoke(self, messages):
        self.calls.append(messages)
        content = self.responses.pop(0) if self.responses else ""

        class _Result:
            def __init__(self, text):
                self.content = text

        return _Result(content)


@pytest.fixture
def scripted(monkeypatch):
    def install(*responses: str) -> ScriptedModel:
        model = ScriptedModel(*responses)
        monkeypatch.setattr(
            "alignmentgraph_isd.server.llm_settings.build_factory", lambda *a, **k: (lambda: model)
        )
        monkeypatch.setattr(
            "alignmentgraph_isd.server.llm_settings.resolve",
            lambda: llm_settings.ResolvedConfig(model_name="scripted", source="database"),
        )
        return model

    return install


def turn(user_message: str = "It is an Arabic course.", brief: dict | None = None) -> dict:
    return planner.plan_turn([], brief or {}, user_message)


# ── the parse ladder ─────────────────────────────────────────────────────────

def test_clean_json_is_used_as_is(scripted):
    scripted(json.dumps(WELL_FORMED))
    result = turn()
    assert result["reply"] == WELL_FORMED["reply"]
    assert result["brief"]["title"] == "Intro to Arabic"


def test_json_inside_markdown_fences(scripted):
    scripted("```json\n" + json.dumps(WELL_FORMED) + "\n```")
    assert turn()["brief"]["title"] == "Intro to Arabic"


def test_json_with_prose_wrapped_around_it(scripted):
    scripted("Sure! Here is the update:\n" + json.dumps(WELL_FORMED) + "\nLet me know if that works.")
    assert turn()["brief"]["title"] == "Intro to Arabic"


def test_a_top_level_array_wrapping_the_object(scripted):
    scripted(json.dumps([WELL_FORMED]))
    assert turn()["brief"]["title"] == "Intro to Arabic"


def test_a_truncated_object_is_repaired(scripted):
    truncated = '{"reply": "What subject?", "brief_patch": {"title": "Intro to Arabic"'
    scripted(truncated)
    result = turn()
    assert result["reply"]
    assert result["brief"]["title"] == "Intro to Arabic"


def test_plain_prose_triggers_a_correction_turn(scripted):
    model = scripted("I think we should start with the basics.", json.dumps(WELL_FORMED))
    result = turn()
    assert len(model.calls) == 2, "the model was not asked to correct itself"
    assert result["brief"]["title"] == "Intro to Arabic"


def test_two_bad_replies_still_produce_a_usable_turn(scripted):
    """The last rung: show the designer what the model said rather than an error."""
    scripted("Let us begin with greetings.", "Still not JSON, sorry.")
    result = turn()
    assert result["reply"]
    assert result["brief_patch"] == {}
    assert result["ready"] is False


def test_an_empty_response_falls_back_without_raising(scripted):
    scripted("", "")
    result = turn()
    assert result["reply"]
    # The brief comes back as a fully-defaulted DesignBrief, so what matters is
    # that nothing was invented into it.
    assert result["brief_patch"] == {}
    assert not result["brief"]["title"]
    assert result["brief"]["learning_goals"] == []


def test_a_model_that_raises_does_not_break_the_turn(scripted, monkeypatch):
    class Exploding:
        def bind(self, **_kwargs):
            return self

        def invoke(self, messages):
            raise RuntimeError("endpoint is down")

    # Installed through `scripted` so the pre-flight probe still passes: the
    # case under test is an endpoint that dies mid-conversation, not one the
    # configuration check would have caught.
    scripted()
    monkeypatch.setattr(
        "alignmentgraph_isd.server.llm_settings.build_factory", lambda *a, **k: (lambda: Exploding())
    )
    result = turn()
    assert result["reply"]
    assert result["brief_patch"] == {}


# ── patch application ────────────────────────────────────────────────────────

def test_invented_fields_are_rejected(scripted):
    """DesignBrief allows extra keys, so validation will not catch this — the
    whitelist has to."""
    scripted(json.dumps({
        "reply": "ok",
        "brief_patch": {"title": "Kept", "sneaky_field": "dropped", "context": {"nonsense": "dropped"}},
        "missing_fields": [],
        "ready": False,
    }))
    result = turn()
    assert result["brief"]["title"] == "Kept"
    assert "sneaky_field" not in result["brief"]
    assert "nonsense" not in result["brief"].get("context", {})
    assert any("sneaky_field" in w for w in result["warnings"])


def test_the_model_cannot_overwrite_the_brief_id(scripted):
    scripted(json.dumps({"reply": "ok", "brief_patch": {"id": "hijacked"}, "ready": False}))
    result = turn(brief={"id": "ORIGINAL-01"})
    assert result["brief"]["id"] == "ORIGINAL-01"


def test_nested_sections_merge_rather_than_replace(scripted):
    """A turn about the audience must not erase the constraints."""
    scripted(json.dumps({
        "reply": "ok",
        "brief_patch": {"context": {"class_size": "Large (30+ learners)"}},
        "ready": False,
    }))
    existing = {"context": {"learner_age": "Teens (13-19)"}, "constraints": {"budget": "medium"}}
    result = turn(brief=existing)
    assert result["brief"]["context"]["class_size"] == "Large (30+ learners)"
    assert result["brief"]["context"]["learner_age"] == "Teens (13-19)"
    assert result["brief"]["constraints"]["budget"] == "medium"


def test_scenario_only_context_keys_are_still_writable(scripted):
    scripted(json.dumps({
        "reply": "ok",
        "brief_patch": {"context": {"additional_context": "Mobile-first cohort"}},
        "ready": False,
    }))
    assert turn()["brief"]["context"]["additional_context"] == "Mobile-first cohort"


def test_ready_needs_a_brief_worth_running(scripted):
    """`ready` is the model's opinion; it is checked against the brief before
    the UI is told anything."""
    scripted(json.dumps({"reply": "All set!", "brief_patch": {}, "ready": True}))
    assert turn()["ready"] is False

    scripted(json.dumps({
        "reply": "All set!",
        "brief_patch": {"title": "T", "domain": "D", "learning_goals": ["A.", "B."]},
        "ready": True,
    }))
    assert turn()["ready"] is True


def test_missing_fields_are_computed_not_taken_from_the_model(scripted):
    scripted(json.dumps({
        "reply": "ok",
        "brief_patch": {"title": "T"},
        "missing_fields": ["nothing at all"],
        "ready": True,
    }))
    missing = turn()["missing_fields"]
    assert "domain" in missing
    assert "nothing at all" not in missing


# ── the endpoint ─────────────────────────────────────────────────────────────

def test_posting_a_message_records_both_turns(client, program, scripted):
    scripted(json.dumps(WELL_FORMED))
    body = client.post(f"/api/programs/{program}/messages", json={"content": "An Arabic course."}).json()

    assert body["user_message"]["role"] == "user"
    assert body["assistant_message"]["role"] == "assistant"
    assert body["assistant_message"]["seq"] == body["user_message"]["seq"] + 1
    assert body["brief"]["title"] == "Intro to Arabic"

    history = client.get(f"/api/programs/{program}/messages").json()
    assert [m["role"] for m in history] == ["user", "assistant"]


def test_the_program_adopts_the_title_from_the_conversation(client, program, scripted):
    scripted(json.dumps(WELL_FORMED))
    client.post(f"/api/programs/{program}/messages", json={"content": "An Arabic course."})
    # The fixture program is named "Test program", so it keeps its name.
    fresh = client.post("/api/programs", json={}).json()["program"]["id"]
    scripted(json.dumps(WELL_FORMED))
    client.post(f"/api/programs/{fresh}/messages", json={"content": "An Arabic course."})
    assert client.get(f"/api/programs/{fresh}").json()["program"]["title"] == "Intro to Arabic"


def test_planning_without_a_model_is_503(unconfigured_client):
    program_id = unconfigured_client.post("/api/programs", json={}).json()["program"]["id"]
    response = unconfigured_client.post(f"/api/programs/{program_id}/messages", json={"content": "hi"})
    assert response.status_code == 503
    # Points at the dialog, which is the only place a model can come from:
    # the app reads no AGENT_MODEL_* at all.
    assert "Model settings" in response.json()["detail"]


def test_an_empty_message_is_rejected(client, program):
    assert client.post(f"/api/programs/{program}/messages", json={"content": ""}).status_code == 422
