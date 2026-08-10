"""Run execution, artifacts, cancellation and the restart sweep."""
from __future__ import annotations

import json

import pytest

from alignmentgraph_isd import AlignmentGraph
from alignmentgraph_isd.server import artifacts
from alignmentgraph_isd.server.app import sweep_interrupted_runs
from alignmentgraph_isd.server.db import session_scope
from sqlmodel import select

from alignmentgraph_isd.server.models import Run, RunStatus, Session, utcnow

def start(client, program_id):
    response = client.post(f"/api/programs/{program_id}/runs")
    assert response.status_code == 202, response.text
    return response.json()["run_id"]


# ── starting ─────────────────────────────────────────────────────────────────

def test_cannot_run_an_empty_brief(client, program):
    response = client.post(f"/api/programs/{program}/runs")
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_cannot_run_without_a_model(unconfigured_client):
    program_id = unconfigured_client.post("/api/programs", json={}).json()["program"]["id"]
    unconfigured_client.put(
        f"/api/programs/{program_id}/brief", json={"brief": {"title": "X", "domain": "Y"}}
    )
    response = unconfigured_client.post(f"/api/programs/{program_id}/runs")
    assert response.status_code == 503
    assert "AGENT_MODEL_NAME" in response.json()["detail"]


def test_a_run_produces_every_artifact(client, ready_program, settings, wait_for_terminal):
    run_id = start(client, ready_program)
    detail = wait_for_terminal(run_id)
    assert detail["run"]["status"] == "succeeded", detail["run"]["error"]

    directory = settings.data_root / artifacts.relative_run_dir(ready_program, run_id)
    for name, filename in artifacts.ARTIFACT_FILES.items():
        assert (directory / filename).exists(), f"missing {name}"
    assert (directory / artifacts.EVENTS_FILE).exists()


def test_the_saved_graph_round_trips(client, ready_program, settings, wait_for_terminal):
    """The dump the app writes must be loadable by the package that made it —
    that is what makes a run auditable after the fact."""
    run_id = start(client, ready_program)
    wait_for_terminal(run_id)

    directory = settings.data_root / artifacts.relative_run_dir(ready_program, run_id)
    payload = json.loads((directory / "graph.json").read_text(encoding="utf-8"))
    restored = AlignmentGraph.from_dict(payload)
    assert len(restored.to_dict()["nodes"]) == len(payload["nodes"])
    assert len(restored.to_dict()["edges"]) == len(payload["edges"])


def test_the_deep_trajectory_is_written_and_served(client, ready_program, wait_for_terminal):
    """The detailed record has to survive the run — a demo that can only show it
    live is no use for looking back at what an agent did."""
    run_id = start(client, ready_program)
    wait_for_terminal(run_id)

    deep = client.get(f"/api/runs/{run_id}/artifacts/trajectory_deep").json()
    assert deep["format"] == "deep"
    assert deep["summary"]["action_count"] == len(deep["actions"])

    kinds = {a["kind"] for a in deep["actions"]}
    # The work that v1 never recorded at all.
    assert "node_read" in kinds, "graph reads are missing"
    assert "edge_write" in kinds, "alignment edges are missing"
    assert "node_write" in kinds

    # And every one of them is attributed.
    assert deep["summary"]["actors"], "no agent was credited with any action"
    assert any(a["actor"] == "PedagogicalVerifierAgent" for a in deep["actions"])


def test_deep_actions_reach_the_live_stream(client, ready_program):
    """Streamed as they happen, not only readable once the run is over."""
    with client.stream("GET", f"/api/runs/{start(client, ready_program)}/events") as response:
        body = "".join(response.iter_text())
    assert "event: action" in body


def test_run_stats_describe_the_alignment(client, ready_program, wait_for_terminal):
    run_id = start(client, ready_program)
    stats = wait_for_terminal(run_id)["stats"]
    assert stats["node_count"] > 0
    assert stats["edge_count"] > 0
    assert stats["objective_count"] > 0
    assert stats["llm_calls"] > 0
    assert stats["agent_steps"] > 0


def test_one_run_at_a_time_per_program(client, ready_program, blocked_run):
    """Two runs on one program would race on the same brief and the same
    artifact directory."""
    start(client, ready_program)
    assert client.post(f"/api/programs/{ready_program}/runs").status_code == 409


def test_editing_the_brief_is_refused_mid_run(client, ready_program, blocked_run):
    start(client, ready_program)
    response = client.put(f"/api/programs/{ready_program}/brief", json={"brief": {"title": "New"}})
    assert response.status_code == 409


def test_an_unusable_model_is_refused_before_the_run_starts(client, ready_program, monkeypatch):
    """A model NAME alone yields a usable factory, so without a pre-flight check
    the run starts, every specialist fails on construction, and it "completes"
    in milliseconds with an empty graph. Better to refuse it with the reason."""
    def unusable_factory():
        raise RuntimeError("Missing credentials. Please pass an `api_key`.")

    monkeypatch.setattr(
        "alignmentgraph_isd.server.llm_settings.build_factory", lambda *a, **k: unusable_factory
    )

    response = client.post(f"/api/programs/{ready_program}/runs")
    assert response.status_code == 503
    assert "Missing credentials" in response.json()["detail"]


def test_a_run_that_produced_nothing_is_reported_as_failed():
    """The net behind the pre-flight check, for a model that passes
    construction and then fails once the run is under way.

    The harness survives a failing specialist by design, so it completes even
    when every one of them failed — leaving an empty graph under a "succeeded"
    label. Silently succeeding with no output is worse than an error.
    """
    from alignmentgraph_isd.server.runner import _barren_run_error

    barren = {
        "graph": {"nodes": [], "edges": []},
        "trajectory": {"llm_calls": 0},
        "metadata": {"errors": [f"Agent{i}: Connection refused" for i in range(6)]},
    }
    message = _barren_run_error(barren)
    assert "every specialist failed" in message
    assert "Connection refused" in message
    assert "all 6 agent attempts" in message

    # A run that produced some of the design is left alone: a partial result is
    # still worth looking at.
    partial = {
        "graph": {"nodes": [{"id": "objective_0"}]},
        "trajectory": {"llm_calls": 3},
        "metadata": {"errors": ["EvaluationRevisionAgent: timed out"]},
    }
    assert _barren_run_error(partial) == ""

    # Nothing produced and nothing to explain it.
    assert "no design output" in _barren_run_error(
        {"graph": {"nodes": []}, "trajectory": {}, "metadata": {}}
    ).lower()


def test_a_partial_run_is_still_a_success(client, ready_program, wait_for_terminal):
    """The barren check must not fire on a run that produced some of the design;
    a partial result is worth looking at."""
    run_id = start(client, ready_program)
    detail = wait_for_terminal(run_id)
    assert detail["run"]["status"] == "succeeded"
    assert detail["stats"]["node_count"] > 0


# ── reading results ──────────────────────────────────────────────────────────

def test_graph_endpoint_serves_light_and_full(client, ready_program, wait_for_terminal):
    run_id = start(client, ready_program)
    wait_for_terminal(run_id)

    light = client.get(f"/api/runs/{run_id}/graph", params={"view": "light"}).json()
    full = client.get(f"/api/runs/{run_id}/graph", params={"view": "full"}).json()
    assert len(light["nodes"]) == len(full["nodes"])
    # The point of the light view: node payloads are what makes a dump ~95 kB.
    assert all("data" not in n for n in light["nodes"])
    assert any(n.get("data") for n in full["nodes"])


def test_node_detail_is_fetched_by_id(client, ready_program, wait_for_terminal):
    run_id = start(client, ready_program)
    wait_for_terminal(run_id)

    graph = client.get(f"/api/runs/{run_id}/graph").json()
    section = next(n["id"] for n in graph["nodes"] if n["id"] == "objective_0")
    body = client.get(f"/api/runs/{run_id}/nodes/{section}").json()
    assert body["id"] == "objective_0"
    assert body["data"]["learning_objectives"]

    element = next(n["id"] for n in graph["nodes"] if n["id"].startswith("objective:"))
    assert client.get(f"/api/runs/{run_id}/nodes/{element}").json()["data"]

    assert client.get(f"/api/runs/{run_id}/nodes/nope_0").status_code == 404


def test_artifacts_are_served_by_name_only(client, ready_program, wait_for_terminal):
    run_id = start(client, ready_program)
    wait_for_terminal(run_id)

    assert client.get(f"/api/runs/{run_id}/artifacts/addie_output").json()["design"]
    assert client.get(f"/api/runs/{run_id}/artifacts/trajectory").json()["agent_steps"]
    assert "digraph" in client.get(f"/api/runs/{run_id}/artifacts/graph_dot").text

    # Not a path: an arbitrary name must not reach the filesystem.
    assert client.get(f"/api/runs/{run_id}/artifacts/secrets").status_code == 404


def test_objective_alignment_survives_to_the_api(client, ready_program, wait_for_terminal):
    """The alignment flags are the reason the graph is shown at all."""
    run_id = start(client, ready_program)
    wait_for_terminal(run_id)

    graph = client.get(f"/api/runs/{run_id}/graph").json()
    alignment = graph["objective_alignment"]
    assert alignment
    for flags in alignment.values():
        assert set(flags) >= {"measured", "supported", "evaluated", "bloom_ok", "aligned"}
    assert set(graph["relation_coverage"]) == {f"R{i}" for i in range(1, 14)}


# ── cancellation and restart ─────────────────────────────────────────────────

def test_cancelling_a_finished_run_is_a_conflict(client, ready_program, wait_for_terminal):
    run_id = start(client, ready_program)
    wait_for_terminal(run_id)
    assert client.post(f"/api/runs/{run_id}/cancel").status_code == 409


def test_cancel_is_visible_immediately(client, ready_program, blocked_run):
    """Cancelling only lands at the harness's next event, so without an event
    of its own every viewer sits on "running" and concludes the button did
    nothing."""
    run_id = start(client, ready_program)
    client.post(f"/api/runs/{run_id}/cancel")

    assert client.get(f"/api/runs/{run_id}").json()["run"]["status"] == "cancelling"

    kinds = [e["kind"] for e in _events(client, run_id)]
    assert "run_cancelling" in kinds
    # Not over yet: the stream must stay open until the run actually stops.
    assert "run_cancelled" not in kinds


def test_cancelling_twice_says_it_once(client, ready_program, blocked_run):
    run_id = start(client, ready_program)
    client.post(f"/api/runs/{run_id}/cancel")
    client.post(f"/api/runs/{run_id}/cancel")

    kinds = [e["kind"] for e in _events(client, run_id)]
    assert kinds.count("run_cancelling") == 1


def test_cancel_aborts_the_model_call_in_flight(client, ready_program, blocked_run):
    """`invoke` blocks its thread and Python cannot interrupt a thread inside a
    socket read, so the only way to stop a call already running is to close the
    transport under it. Verified here by the transport actually being closed."""
    class FakeClient:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    fake = FakeClient()
    run_id = start(client, ready_program)
    state = client.app.state.run_manager.registry.get(run_id)
    state.http_client = fake

    client.post(f"/api/runs/{run_id}/cancel")

    assert fake.closed, "the transport was not closed, so the call would run to completion"
    note = next(e for e in _events(client, run_id) if e["kind"] == "run_cancelling")
    assert note["payload"]["aborted_in_flight_call"] is True
    assert "aborted" in note["payload"]["note"]


def test_cancel_says_so_when_the_call_cannot_be_aborted(client, ready_program, blocked_run):
    """ChatAnthropic accepts no http_client, so there is nothing to close and
    the cancel has to wait for the harness's next event. Say which it was."""
    run_id = start(client, ready_program)
    client.app.state.run_manager.registry.get(run_id).http_client = None

    client.post(f"/api/runs/{run_id}/cancel")

    note = next(e for e in _events(client, run_id) if e["kind"] == "run_cancelling")
    assert note["payload"]["aborted_in_flight_call"] is False
    assert "after the current model call" in note["payload"]["note"]


def test_the_transport_is_released_when_a_run_ends(client, ready_program, blocked_run, wait_for_terminal):
    """One connection pool per run; nothing else closes it.

    The run is held at the gate first, so the transport can be observed while it
    is still assigned — otherwise the run may finish and release it before the
    assertion runs.
    """
    run_id = start(client, ready_program)
    state = client.app.state.run_manager.registry.get(run_id)
    assert state.http_client is not None, "a run should hold a transport it can abort"

    blocked_run["open"] = True
    wait_for_terminal(run_id)
    assert state.http_client is None, "the transport outlived the run"


def _events(client, run_id: str) -> list[dict]:
    """The run's events as recorded so far, from the in-memory state."""
    state = client.app.state.run_manager.registry.get(run_id)
    return [e.to_dict() for e in state.events]


def test_cancel_stops_a_run(client, ready_program, blocked_run, wait_for_terminal):
    run_id = start(client, ready_program)
    assert client.post(f"/api/runs/{run_id}/cancel").json()["status"] == "cancelling"
    blocked_run["open"] = True

    detail = wait_for_terminal(run_id)
    assert detail["run"]["status"] == "cancelled"


def test_startup_sweep_reconciles_runs_left_by_a_dead_process(client, ready_program):
    """A run lives in a worker thread; a restart kills it with no chance to
    record anything, so the row would claim `running` forever."""
    with session_scope() as db:
        session_id = db.exec(
            select(Session).where(Session.program_id == ready_program)
        ).first().id
        orphan = Run(
            program_id=ready_program,
            session_id=session_id,
            status=RunStatus.RUNNING,
            artifact_dir=f"programs/{ready_program}/runs/orphan",
            started_at=utcnow(),
        )
        db.add(orphan)
        db.commit()
        orphan_id = orphan.id

    assert sweep_interrupted_runs() == 1

    with session_scope() as db:
        assert db.get(Run, orphan_id).status == RunStatus.INTERRUPTED

    # And the program is not left blocked behind the one-active-run rule.
    assert client.post(f"/api/programs/{ready_program}/runs").status_code == 202
