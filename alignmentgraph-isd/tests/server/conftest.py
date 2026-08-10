"""Server test fixtures.

Every test gets its own data root and database, and a fake model injected via
``llm_factory_from_env`` so the whole run pipeline executes without a network.
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi", reason="needs the [server] extra")

from fastapi.testclient import TestClient  # noqa: E402

from alignmentgraph_isd.server import db as server_db  # noqa: E402
from alignmentgraph_isd.server import llm_settings  # noqa: E402
from alignmentgraph_isd.server.app import create_app  # noqa: E402
from alignmentgraph_isd.server.settings import Settings  # noqa: E402

# `fake_llm_factory` comes from tests/conftest.py — pytest makes a parent
# conftest's fixtures available here, which avoids importing it as a module
# (both files are named `conftest`, so a direct import resolves to this one).


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        data_root=tmp_path / "data",
        db_url=f"sqlite:///{tmp_path / 'test.db'}",
        max_concurrent_runs=2,
        serve_spa=False,
    )


@pytest.fixture
def fake_model(monkeypatch, fake_llm_factory):
    """Point the harness and the planner at the network-free fake model.

    Patched at `llm_settings`, the single place both the runner and the planner
    resolve a model through.
    """
    # `probe` is deliberately NOT stubbed: it is the pre-flight check that
    # decides whether a run may start, so tests should exercise the real one.
    # It calls build_factory, which is what the fake replaces.
    monkeypatch.setattr(
        "alignmentgraph_isd.server.llm_settings.build_factory", lambda *a, **k: fake_llm_factory
    )
    monkeypatch.setattr(
        "alignmentgraph_isd.server.llm_settings.resolve",
        lambda: llm_settings.ResolvedConfig(
            model_name="fake-model", source=llm_settings.SOURCE_ENVIRONMENT
        ),
    )
    return fake_llm_factory


@pytest.fixture
def client(settings, fake_model):
    server_db.reset_engine()
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client
    server_db.reset_engine()


@pytest.fixture
def unconfigured_client(settings, monkeypatch):
    """No model available — the state a fresh checkout starts in."""
    monkeypatch.delenv("AGENT_MODEL_NAME", raising=False)
    monkeypatch.setattr(
        "alignmentgraph_isd.server.llm_settings.resolve", lambda: llm_settings.ResolvedConfig()
    )
    monkeypatch.setattr("alignmentgraph_isd.server.llm_settings.build_factory", lambda *a, **k: None)
    server_db.reset_engine()
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client
    server_db.reset_engine()


@pytest.fixture
def program(client) -> str:
    response = client.post("/api/programs", json={"title": "Test program"})
    assert response.status_code == 201
    return response.json()["program"]["id"]


@pytest.fixture
def ready_program(client, program) -> str:
    """A program with a brief complete enough to run."""
    client.put(
        f"/api/programs/{program}/brief",
        json={"brief": {
            "title": "Java OOP",
            "domain": "Software engineering",
            "learning_goals": ["Explain encapsulation.", "Apply inheritance."],
        }},
    )
    return program


@pytest.fixture
def wait_for_terminal(client):
    """Poll a run to completion. Fast, because the fake model returns instantly."""
    import time

    def wait(run_id: str, timeout: float = 60.0) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            payload = client.get(f"/api/runs/{run_id}").json()
            if payload["run"]["status"] in ("succeeded", "failed", "cancelled", "interrupted"):
                return payload
            time.sleep(0.05)
        raise AssertionError(f"run {run_id} did not finish within {timeout}s")

    return wait


@pytest.fixture
def blocked_run(monkeypatch):
    """Hold a run's worker at the gate so mid-run behaviour can be exercised."""
    import alignmentgraph_isd.server.runner as server_runner

    original = server_runner.RunManager._execute
    gate = {"open": False}

    def gated(self, *args, **kwargs):
        import time
        while not gate["open"]:
            time.sleep(0.01)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(server_runner.RunManager, "_execute", gated)
    try:
        yield gate
    finally:
        gate["open"] = True


@pytest.fixture
def scenario_file() -> dict:
    """A realistic benchmark scenario, including the keys DesignBrief has no
    field for and the null one that gets stripped."""
    return {
        "scenario_id": "BAL-TEEN3-0013",
        "variant_type": "balance_teen_v3",
        "title": "Virtual Platform Microlearning Course for Arabic Beginners",
        "context": {
            "prior_knowledge": "Elementary Arabic script and greeting-level proficiency",
            "duration": "Short-term intensive (within 1 week)",
            "learning_environment": "Mobile microlearning",
            "class_size": "Large (30+ learners)",
            "additional_context": "Aims to cultivate basic Arabic communication skills",
            "institution_type": "Vocational training institution",
            "learner_age": "Teens (13-19)",
            "learner_education": "Middle school",
            "learner_role": "Office worker (administrative/management)",
            "domain_expertise": "Beginner",
        },
        "learning_goals": [
            "Demonstrate everyday Arabic greetings with 80% accuracy.",
            "Handwrite basic Arabic script (alphabet) with 90% accuracy.",
            "Perform language exchange activities with peer learners over three times.",
        ],
        "constraints": {
            "budget": "medium",
            "resources": ["Mobile-Compatible Virtual Learning Platform", "Interactive Quiz Template"],
            "accessibility": None,
            "language": "en",
            "tech_requirements": "Bring Your Own Device (BYOD)",
            "assessment_type": "Formative assessment-focused",
        },
        "difficulty": "Easy - Simple structure with minimal constraints",
        "domain": "Language",
    }
