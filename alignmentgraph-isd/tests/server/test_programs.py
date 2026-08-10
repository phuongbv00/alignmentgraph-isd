"""Programs, briefs and scenario import."""
from __future__ import annotations

import io
import json

import pytest

from alignmentgraph_isd.server import llm_settings


def upload(client, program_id: str, payload, filename: str = "scenario.json"):
    return client.post(
        f"/api/programs/{program_id}/brief/import",
        files={"file": (filename, io.BytesIO(json.dumps(payload).encode()), "application/json")},
    )


def test_health_reports_no_model_when_unconfigured(unconfigured_client):
    body = unconfigured_client.get("/api/health").json()
    assert body["llm_configured"] is False
    assert body["max_concurrent_runs"] >= 1


def test_health_rejects_a_model_that_cannot_be_built(client, monkeypatch):
    """A model NAME alone yields a usable factory, so a name with no endpoint or
    credentials passes a naive check and then fails on every call. Health must
    not call that configured."""
    def exploding_factory():
        raise RuntimeError("Missing credentials. Please pass an `api_key`.")

    monkeypatch.setattr(
        "alignmentgraph_isd.server.llm_settings.build_factory", lambda *a, **k: exploding_factory
    )
    monkeypatch.setattr(
        "alignmentgraph_isd.server.llm_settings.resolve",
        lambda: llm_settings.ResolvedConfig(model_name="ghost-model", source="database"),
    )
    body = client.get("/api/health").json()
    assert body["llm_configured"] is False
    assert "Missing credentials" in body["model_error"]


def test_health_reports_no_error_when_the_model_works(client):
    body = client.get("/api/health").json()
    assert body["llm_configured"] is True
    assert body["model_error"] == ""


def test_health_names_the_configured_model(client, monkeypatch):
    """Reported from the configuration, not by building a client and inspecting
    it — construction can fail for reasons unrelated to the name (missing key,
    unreachable endpoint), and the label would silently go blank."""
    monkeypatch.setattr(
        "alignmentgraph_isd.server.llm_settings.resolve",
        lambda: llm_settings.ResolvedConfig(model_name="Qwen/Qwen3.5-4B", source="database"),
    )
    body = client.get("/api/health").json()
    assert body["llm_configured"] is True
    assert body["model_name"] == "Qwen/Qwen3.5-4B"


def test_creating_a_program_creates_its_session(client):
    body = client.post("/api/programs", json={"title": "Onboarding"}).json()
    assert body["program"]["title"] == "Onboarding"
    # The session is an implementation detail the API never exposes; that it
    # exists is verified by the message endpoint working without one being made.
    assert client.get(f"/api/programs/{body['program']['id']}/messages").json() == []


def test_program_list_is_most_recently_updated_first(client):
    first = client.post("/api/programs", json={"title": "First"}).json()["program"]["id"]
    client.post("/api/programs", json={"title": "Second"})
    client.patch(f"/api/programs/{first}", json={"title": "First, renamed"})

    titles = [p["title"] for p in client.get("/api/programs").json()]
    assert titles[0] == "First, renamed"


def test_missing_program_is_404(client):
    assert client.get("/api/programs/nope").status_code == 404


# ── scenario import ──────────────────────────────────────────────────────────

def test_import_maps_scenario_id_to_brief_id(client, program, scenario_file):
    body = upload(client, program, scenario_file).json()
    assert body["brief"]["id"] == "BAL-TEEN3-0013"
    assert body["brief"]["domain"] == "Language"
    assert len(body["brief"]["learning_goals"]) == 3


def test_import_keeps_scenario_only_context_keys(client, program, scenario_file):
    """DesignBrief allows extra keys; dropping them would lose information the
    inspector shows."""
    brief = upload(client, program, scenario_file).json()["brief"]
    assert brief["context"]["additional_context"].startswith("Aims to cultivate")
    assert brief["context"]["institution_type"] == "Vocational training institution"
    assert brief["variant_type"] == "balance_teen_v3"


def test_import_drops_null_fields_and_says_so(client, program, scenario_file):
    body = upload(client, program, scenario_file).json()
    assert body["brief"]["constraints"].get("accessibility") in ("", None)
    assert any("accessibility" in w for w in body["warnings"])


def test_import_adopts_the_scenario_title(client, scenario_file):
    program_id = client.post("/api/programs", json={}).json()["program"]["id"]
    upload(client, program_id, scenario_file)
    detail = client.get(f"/api/programs/{program_id}").json()
    assert detail["program"]["title"] == scenario_file["title"]
    assert detail["program"]["source"] == "import"


def test_import_rejects_non_json_and_non_objects(client, program):
    bad_ext = client.post(
        f"/api/programs/{program}/brief/import",
        files={"file": ("scenario.txt", io.BytesIO(b"{}"), "text/plain")},
    )
    assert bad_ext.status_code == 415

    not_json = client.post(
        f"/api/programs/{program}/brief/import",
        files={"file": ("scenario.json", io.BytesIO(b"not json at all"), "application/json")},
    )
    assert not_json.status_code == 422

    assert upload(client, program, ["a", "list"]).status_code == 422


def test_brief_preview_truncates_the_goal_list(client, program, scenario_file):
    scenario_file["learning_goals"] = [f"Goal number {i}." for i in range(9)]
    preview = upload(client, program, scenario_file).json()["brief_preview"]
    assert len(preview["learning_goals"]) == 3
    assert preview["learning_goals_total"] == 9
    assert preview["is_runnable"] is True


def test_empty_brief_is_not_runnable(client, program):
    preview = client.get(f"/api/programs/{program}").json()["brief_preview"]
    assert preview["is_runnable"] is False


def test_put_brief_validates(client, program):
    ok = client.put(f"/api/programs/{program}/brief", json={"brief": {"title": "Manual", "domain": "CS"}})
    assert ok.status_code == 200
    assert ok.json()["brief"]["title"] == "Manual"

    bad = client.put(f"/api/programs/{program}/brief", json={"brief": {"learning_goals": "not a list"}})
    assert bad.status_code == 422


def test_missing_fields_guides_the_conversation(client, program):
    client.put(f"/api/programs/{program}/brief", json={"brief": {"title": "Only a title"}})
    missing = client.get(f"/api/programs/{program}").json()["missing_fields"]
    assert "domain" in missing
    assert "learning_goals" in missing
    assert "title" not in missing


# ── committing ───────────────────────────────────────────────────────────────

def test_an_imported_brief_is_committed_on_arrival(client, program, scenario_file):
    """A file arrives whole, so there is nothing to settle — it is the brief."""
    assert upload(client, program, scenario_file).json()["brief_committed_at"] is not None
    assert client.get(f"/api/programs/{program}").json()["program"]["brief_committed_at"] is not None


def test_a_new_program_has_no_committed_brief(client, program):
    assert client.get(f"/api/programs/{program}").json()["program"]["brief_committed_at"] is None


def test_committing_settles_the_draft(client, program):
    client.put(f"/api/programs/{program}/brief", json={"brief": {
        "title": "Java OOP", "domain": "Software engineering",
        "learning_goals": ["Explain encapsulation.", "Apply inheritance."],
    }})
    response = client.post(f"/api/programs/{program}/brief/commit")
    assert response.status_code == 200
    assert response.json()["brief_committed_at"] is not None


def test_an_empty_brief_cannot_be_committed(client, program):
    response = client.post(f"/api/programs/{program}/brief/commit")
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_a_later_turn_returns_the_brief_to_a_draft(client, program, scenario_file, monkeypatch):
    """Otherwise the card would keep claiming "committed" while describing
    something the designer never settled on."""
    upload(client, program, scenario_file)
    assert client.get(f"/api/programs/{program}").json()["program"]["brief_committed_at"] is not None

    class Model:
        def bind(self, **_kwargs):
            return self

        def invoke(self, _messages):
            class _Result:
                content = json.dumps({
                    "reply": "Noted.",
                    "brief_patch": {"difficulty": "Harder than it looked"},
                    "ready": False,
                })
            return _Result()

    monkeypatch.setattr(
        "alignmentgraph_isd.server.llm_settings.build_factory", lambda *a, **k: (lambda: Model())
    )
    turn = client.post(f"/api/programs/{program}/messages", json={"content": "Make it harder."}).json()
    assert turn["brief_committed_at"] is None
    assert client.get(f"/api/programs/{program}").json()["program"]["brief_committed_at"] is None


def test_a_turn_that_changes_nothing_leaves_the_commit_alone(client, program, scenario_file, monkeypatch):
    upload(client, program, scenario_file)

    class Model:
        def bind(self, **_kwargs):
            return self

        def invoke(self, _messages):
            class _Result:
                content = json.dumps({"reply": "Could you say more?", "brief_patch": {}, "ready": False})
            return _Result()

    monkeypatch.setattr(
        "alignmentgraph_isd.server.llm_settings.build_factory", lambda *a, **k: (lambda: Model())
    )
    turn = client.post(f"/api/programs/{program}/messages", json={"content": "hmm"}).json()
    assert turn["brief_committed_at"] is not None


def test_delete_removes_the_program_and_its_files(client, program, scenario_file, settings):
    upload(client, program, scenario_file)
    assert client.delete(f"/api/programs/{program}").status_code == 204
    assert client.get(f"/api/programs/{program}").status_code == 404
    assert not (settings.programs_dir / program).exists()
