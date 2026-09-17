"""Configuring the model connections from the UI.

The point of storing them is that the demo is self-contained — no shell state
to get right before it will run. A *list* of connections rather than one
setting, because switching between a local Ollama and a served pod should be a
click and not three fields retyped, and the app reads no `AGENT_MODEL_*` at all:
a setting that came from a shell would be invisible in the dialog, so what the
UI shows and what a run uses could differ with nothing on screen to say so.
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from alignmentgraph_isd.server import db as server_db
from alignmentgraph_isd.server.app import create_app

_AGENT_ENV = (
    "AGENT_MODEL_NAME",
    "AGENT_MODEL_BASE_URL",
    "AGENT_MODEL_API_KEY",
    "AGENT_MODEL_API_SPEC",
    "AGENT_MODEL_TEMPERATURE",
    "AGENT_MODEL_MAX_TOKENS",
    # The provider clients fall back to these, so leaving them in place would
    # make "no credentials" pass or fail depending on whose machine the suite
    # runs on.
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
)


@contextmanager
def _serving(settings):
    """A client on the real llm_settings path.

    Built here rather than through the shared `client` fixture, which stubs
    `resolve` and `build_factory` so every other test can run without a model.
    Here those are exactly what is under test — and the app has to be created
    *after* the environment is set.
    """
    server_db.reset_engine()
    with TestClient(create_app(settings)) as client:
        yield client
    server_db.reset_engine()


@pytest.fixture
def real_settings(settings, monkeypatch):
    for name in _AGENT_ENV:
        monkeypatch.delenv(name, raising=False)
    with _serving(settings) as client:
        yield client


def _add(client, **fields):
    body = {"name": "Test", **fields}
    response = client.post("/api/connections", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _only(payload):
    assert len(payload["connections"]) == 1, payload["connections"]
    return payload["connections"][0]


def test_nothing_configured_reports_none(real_settings):
    body = real_settings.get("/api/connections").json()
    assert body["connections"] == []
    assert body["active_id"] == ""
    assert "No model configured" in body["error"]


def test_the_environment_is_never_read(settings, monkeypatch):
    """Not seeded, not a fallback, not a hole-filler.

    The whole point of configuring in the app is that the dialog shows what a
    run will use; a value arriving from a shell would be in neither place.
    """
    for name in _AGENT_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AGENT_MODEL_NAME", "from-the-environment")
    monkeypatch.setenv("AGENT_MODEL_BASE_URL", "http://from-the-environment/v1")
    monkeypatch.setenv("AGENT_MODEL_API_KEY", "sk-from-the-environment")

    with _serving(settings) as client:
        body = client.get("/api/connections").json()
        assert body["connections"] == []
        assert "No model configured" in body["error"]
        assert client.get("/api/health").json()["llm_configured"] is False


def test_a_blank_field_is_not_filled_in_from_the_environment(settings, monkeypatch):
    """A connection saved with no key must fail here rather than borrow one and
    work until it is started from a different shell."""
    for name in _AGENT_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AGENT_MODEL_API_KEY", "sk-from-the-environment")

    with _serving(settings) as client:
        body = _add(client, name="Keyless", base_url="http://localhost:11434/v1",
                    model_name="qwen3.5:2b")
        assert _only(body)["has_api_key"] is False
        assert body["error"], "a model with no credentials should report a problem"


def test_the_first_connection_becomes_active(real_settings):
    body = _add(real_settings, name="Ollama", base_url="http://localhost:11434/v1")
    assert _only(body)["is_active"] is True
    assert body["active_id"] == _only(body)["id"]


def test_a_second_connection_does_not_steal_active(real_settings):
    first = _only(_add(real_settings, name="First"))["id"]
    body = _add(real_settings, name="Second")
    assert body["active_id"] == first


def test_activating_moves_the_configuration_a_run_uses(real_settings):
    _add(real_settings, name="First", base_url="http://a/v1", api_key="k", model_name="model-a")
    body = _add(real_settings, name="Second", base_url="http://b/v1", api_key="k",
                model_name="model-b")
    second = next(c for c in body["connections"] if c["name"] == "Second")

    activated = real_settings.post(f"/api/connections/{second['id']}/activate").json()
    assert activated["active_id"] == second["id"]
    assert real_settings.get("/api/health").json()["model_name"] == "model-b"


def test_each_connection_keeps_its_own_model(real_settings):
    """A model id belongs to the endpoint that serves it, so switching back has
    to bring the model back with it."""
    body = _add(real_settings, name="First", base_url="http://a/v1", api_key="k",
                model_name="model-a")
    first = _only(body)["id"]
    body = _add(real_settings, name="Second", base_url="http://b/v1", api_key="k",
                model_name="model-b")
    second = next(c for c in body["connections"] if c["id"] != first)["id"]

    real_settings.post(f"/api/connections/{second}/activate")
    real_settings.post(f"/api/connections/{first}/activate")
    assert real_settings.get("/api/health").json()["model_name"] == "model-a"


def test_deleting_the_active_connection_hands_active_on(real_settings):
    first = _only(_add(real_settings, name="First"))["id"]
    _add(real_settings, name="Second")

    body = real_settings.delete(f"/api/connections/{first}").json()
    assert len(body["connections"]) == 1
    assert body["active_id"] == body["connections"][0]["id"]


def test_deleting_the_last_connection_leaves_nothing_active(real_settings):
    first = _only(_add(real_settings, name="First"))["id"]
    body = real_settings.delete(f"/api/connections/{first}").json()
    assert body["connections"] == []
    assert body["active_id"] == ""
    assert "No model configured" in body["error"]


def test_the_api_key_is_never_sent_back(real_settings):
    """It sits in clear text in the local database; there is no reason to move
    it any further than that."""
    response = real_settings.post("/api/connections", json={
        "name": "Ollama", "base_url": "http://localhost:11434/v1",
        "model_name": "m", "api_key": "sk-secret",
    })
    assert response.status_code == 201
    connection = _only(response.json())
    assert connection["has_api_key"] is True
    assert "sk-secret" not in response.text
    assert "api_key" not in connection

    assert "sk-secret" not in real_settings.get("/api/connections").text


def test_omitting_the_key_keeps_the_stored_one(real_settings):
    """The browser is never given the key, so it cannot echo one back; an
    absent key on save has to mean "leave it alone"."""
    connection = _only(_add(real_settings, name="Ollama", api_key="sk-secret", model_name="m"))
    body = real_settings.put(f"/api/connections/{connection['id']}", json={
        "name": "Ollama", "model_name": "m2",
    }).json()

    assert _only(body)["model_name"] == "m2"
    assert _only(body)["has_api_key"] is True


def test_an_empty_key_clears_it(real_settings):
    connection = _only(_add(real_settings, name="Ollama", api_key="sk-secret", model_name="m"))
    body = real_settings.put(f"/api/connections/{connection['id']}", json={
        "name": "Ollama", "model_name": "m", "api_key": "",
    }).json()
    assert _only(body)["has_api_key"] is False


def test_saving_reports_what_is_wrong_rather_than_refusing(real_settings):
    """Saving succeeds either way; the probe result comes back with it, so a
    missing key is reported here and not when a run collapses."""
    response = real_settings.post("/api/connections", json={
        "name": "OpenAI", "model_name": "gpt-4o-mini", "api_key": "",
    })
    assert response.status_code == 201
    body = response.json()
    assert _only(body)["model_name"] == "gpt-4o-mini"
    assert body["error"], "a model with no credentials should report a problem"


def test_a_connection_with_no_model_says_so(real_settings):
    """The normal state right after adding one: it exists, nothing is picked."""
    body = _add(real_settings, name="Ollama", base_url="http://localhost:11434/v1",
                api_key="ollama")
    assert "No model picked" in body["error"]
    assert real_settings.get("/api/health").json()["llm_configured"] is False


def test_a_working_configuration_reports_no_error(real_settings):
    body = _add(real_settings, name="Ollama", base_url="http://localhost:11434/v1",
                api_key="ollama", model_name="qwen3.5:2b")
    assert body["error"] == "", body["error"]


def test_health_follows_the_active_connection(real_settings):
    _add(real_settings, name="Ollama", base_url="http://localhost:11434/v1",
         api_key="ollama", model_name="qwen3.5:2b")
    body = real_settings.get("/api/health").json()
    assert body["llm_configured"] is True
    assert body["model_name"] == "qwen3.5:2b"
    assert body["model_error"] == ""


def test_models_are_read_from_the_endpoint(real_settings, monkeypatch):
    """The key stays on the server: the browser asks by connection id."""
    connection = _only(_add(real_settings, name="Ollama", base_url="http://localhost:11434/v1",
                            api_key="sk-secret"))
    seen = {}

    class _Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"id": "qwen3.5:4b"}, {"id": "qwen3.5:2b"}]}

    def fake_get(url, headers=None, timeout=None):
        seen["url"] = url
        seen["headers"] = headers
        return _Response()

    monkeypatch.setattr("httpx.get", fake_get)

    body = real_settings.get(f"/api/connections/{connection['id']}/models").json()
    assert body["models"] == ["qwen3.5:2b", "qwen3.5:4b"]
    assert body["error"] == ""
    assert seen["url"] == "http://localhost:11434/v1/models"
    assert seen["headers"]["Authorization"] == "Bearer sk-secret"


def test_an_unreachable_endpoint_reports_rather_than_fails(real_settings, monkeypatch):
    """A listing that cannot be had must not stop someone editing the
    connection that would fix it."""
    connection = _only(_add(real_settings, name="Ollama", base_url="http://localhost:11434/v1"))

    def fake_get(url, headers=None, timeout=None):
        raise OSError("connection refused")

    monkeypatch.setattr("httpx.get", fake_get)

    response = real_settings.get(f"/api/connections/{connection['id']}/models")
    assert response.status_code == 200
    body = response.json()
    assert body["models"] == []
    assert "connection refused" in body["error"]


def test_the_window_and_the_cap_are_stored_per_connection(real_settings):
    body = _add(real_settings, name="RunPod 4B", base_url="http://pod/v1", api_key="k",
                model_name="Qwen/Qwen3.5-4B", context_window=16384, max_tokens=8192)
    connection = _only(body)
    assert connection["context_window"] == 16384
    assert connection["max_tokens"] == 8192


def test_the_window_reaches_the_run_config(real_settings):
    """The transcript budget is derived from the connection, not from a shell
    variable — and the reserve is the same cap the client is sending, so the
    two cannot disagree."""
    from alignmentgraph_isd.server import llm_settings

    _add(real_settings, name="RunPod 4B", base_url="http://pod/v1", api_key="k",
         model_name="Qwen/Qwen3.5-4B", context_window=16384, max_tokens=8192)

    assert llm_settings.window_settings() == {
        "llm_context_window": 16384,
        "llm_completion_reserve": 8192,
    }


def test_an_unset_window_keeps_the_harness_default(real_settings):
    from alignmentgraph_isd.server import llm_settings

    _add(real_settings, name="Ollama", base_url="http://localhost:11434/v1",
         api_key="ollama", model_name="qwen3.5:2b")

    settings = llm_settings.window_settings()
    assert settings["llm_context_window"] == 0, "0 means the historical constant"
    assert settings["llm_completion_reserve"] == llm_settings.DEFAULT_MAX_TOKENS


def test_an_explicit_null_clears_an_optional_number(real_settings):
    """Otherwise a token cap could be set but never unset, since the browser
    sends every field on every save."""
    connection = _only(_add(real_settings, name="Ollama", max_tokens=8192,
                            context_window=16384))
    body = real_settings.put(f"/api/connections/{connection['id']}", json={
        "name": "Ollama", "max_tokens": None, "context_window": None,
    }).json()
    assert _only(body)["max_tokens"] is None
    assert _only(body)["context_window"] is None


def test_a_window_below_the_floor_is_rejected(real_settings):
    response = real_settings.post("/api/connections", json={"name": "x", "context_window": 12})
    assert response.status_code == 422


def test_an_unknown_connection_is_a_404(real_settings):
    assert real_settings.get("/api/connections/nope/models").status_code == 404
    assert real_settings.put("/api/connections/nope", json={"name": "x"}).status_code == 404
    assert real_settings.delete("/api/connections/nope").status_code == 404
    assert real_settings.post("/api/connections/nope/activate").status_code == 404


def test_connections_are_locked_while_a_run_is_going(client, ready_program, blocked_run):
    client.post(f"/api/programs/{ready_program}/runs")
    assert client.post("/api/connections", json={"name": "x"}).status_code == 409
    assert client.put("/api/connections/any", json={"name": "x"}).status_code == 409
    assert client.delete("/api/connections/any").status_code == 409
    assert client.post("/api/connections/any/activate").status_code == 409


def test_a_name_that_is_too_long_is_rejected(real_settings):
    response = real_settings.post("/api/connections", json={"name": "x" * 101})
    assert response.status_code == 422
