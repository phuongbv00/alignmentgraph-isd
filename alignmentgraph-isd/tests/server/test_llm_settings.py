"""Configuring the model from the UI.

The point of storing it is that the demo is self-contained — no shell state to
get right before it will run. `AGENT_MODEL_*` stays as a fallback so an
existing setup keeps working.
"""
from __future__ import annotations

import pytest

from alignmentgraph_isd.server import llm_settings


# Captured at import, before any fixture patches the module. All three are
# needed: `probe` calls `build_factory`, so restoring only the first two leaves
# the fake model in place and every configuration looks valid.
_real_resolve = llm_settings.resolve
_real_probe = llm_settings.probe
_real_build_factory = llm_settings.build_factory


@pytest.fixture
def real_settings(client, monkeypatch):
    """A client whose settings routes exercise the real resolve/probe path.

    The shared `client` fixture stubs those out so every other test can run
    without a model; here they are exactly what is under test.
    """
    monkeypatch.setattr("alignmentgraph_isd.server.llm_settings.resolve", _real_resolve)
    monkeypatch.setattr("alignmentgraph_isd.server.llm_settings.probe", _real_probe)
    monkeypatch.setattr("alignmentgraph_isd.server.llm_settings.build_factory", _real_build_factory)
    for name in (
        "AGENT_MODEL_NAME", "AGENT_MODEL_BASE_URL", "AGENT_MODEL_API_KEY",
        # The provider clients fall back to these, so leaving them in place
        # would make "no credentials" pass or fail depending on whose machine
        # the suite runs on.
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    return client


def test_nothing_configured_reports_none(real_settings):
    body = real_settings.get("/api/settings/llm").json()
    assert body["source"] == "none"
    assert body["model_name"] == ""
    assert "No model configured" in body["error"]


def test_the_environment_is_the_fallback(real_settings, monkeypatch):
    """So an existing AGENT_MODEL_* setup keeps working untouched."""
    monkeypatch.setenv("AGENT_MODEL_NAME", "Qwen/Qwen3.5-4B")
    monkeypatch.setenv("AGENT_MODEL_BASE_URL", "http://localhost:8000/v1")
    body = real_settings.get("/api/settings/llm").json()
    assert body["source"] == "environment"
    assert body["model_name"] == "Qwen/Qwen3.5-4B"
    assert body["base_url"] == "http://localhost:8000/v1"


def test_saving_settings_takes_priority_over_the_environment(real_settings, monkeypatch):
    monkeypatch.setenv("AGENT_MODEL_NAME", "from-the-environment")
    real_settings.put("/api/settings/llm", json={
        "model_name": "from-the-database",
        "api_spec": "openai_compatible",
        "base_url": "http://localhost:11434/v1",
        "api_key": "sk-test",
    })
    body = real_settings.get("/api/settings/llm").json()
    assert body["source"] == "database"
    assert body["model_name"] == "from-the-database"


def test_the_api_key_is_never_sent_back(real_settings):
    """It sits in clear text in the local database; there is no reason to move
    it any further than that."""
    response = real_settings.put("/api/settings/llm", json={
        "model_name": "m", "base_url": "http://localhost:11434/v1", "api_key": "sk-secret",
    })
    assert response.status_code == 200
    body = response.json()
    assert body["has_api_key"] is True
    assert "sk-secret" not in response.text
    assert "api_key" not in body

    assert "sk-secret" not in real_settings.get("/api/settings/llm").text


def test_omitting_the_key_keeps_the_stored_one(real_settings):
    """The browser is never given the key, so it cannot echo one back; an
    absent key on save has to mean "leave it alone"."""
    real_settings.put("/api/settings/llm", json={"model_name": "m", "api_key": "sk-secret"})
    real_settings.put("/api/settings/llm", json={"model_name": "m2"})

    body = real_settings.get("/api/settings/llm").json()
    assert body["model_name"] == "m2"
    assert body["has_api_key"] is True


def test_an_empty_key_clears_it(real_settings):
    real_settings.put("/api/settings/llm", json={"model_name": "m", "api_key": "sk-secret"})
    real_settings.put("/api/settings/llm", json={"model_name": "m", "api_key": ""})
    assert real_settings.get("/api/settings/llm").json()["has_api_key"] is False


def test_saving_reports_what_is_wrong_rather_than_refusing(real_settings):
    """Saving succeeds either way; the probe result comes back with it, so a
    missing key is reported here and not when a run collapses."""
    response = real_settings.put("/api/settings/llm", json={
        "model_name": "gpt-4o-mini", "api_spec": "openai_compatible", "api_key": "",
    })
    assert response.status_code == 200
    body = response.json()
    assert body["model_name"] == "gpt-4o-mini"
    assert body["error"], "a model with no credentials should report a problem"


def test_a_working_configuration_reports_no_error(real_settings):
    body = real_settings.put("/api/settings/llm", json={
        "model_name": "qwen3.5:2b",
        "base_url": "http://localhost:11434/v1",
        "api_key": "ollama",
    }).json()
    assert body["error"] == "", body["error"]
    assert body["source"] == "database"


def test_clearing_falls_back_to_the_environment(real_settings, monkeypatch):
    real_settings.put("/api/settings/llm", json={"model_name": "stored"})
    monkeypatch.setenv("AGENT_MODEL_NAME", "from-the-environment")

    body = real_settings.delete("/api/settings/llm").json()
    assert body["source"] == "environment"
    assert body["model_name"] == "from-the-environment"


def test_settings_are_rejected_while_a_run_is_going(client, ready_program, blocked_run):
    client.post(f"/api/programs/{ready_program}/runs")
    response = client.put("/api/settings/llm", json={"model_name": "m"})
    assert response.status_code == 409


def test_an_unknown_api_spec_is_rejected(real_settings):
    response = real_settings.put("/api/settings/llm", json={
        "model_name": "m", "api_spec": "telepathy",
    })
    assert response.status_code == 422


def test_a_blank_model_name_is_rejected(real_settings):
    assert real_settings.put("/api/settings/llm", json={"model_name": ""}).status_code == 422


def test_health_follows_the_stored_settings(real_settings):
    real_settings.put("/api/settings/llm", json={
        "model_name": "qwen3.5:2b", "base_url": "http://localhost:11434/v1", "api_key": "ollama",
    })
    body = real_settings.get("/api/health").json()
    assert body["llm_configured"] is True
    assert body["model_name"] == "qwen3.5:2b"
    assert body["model_error"] == ""
