"""Run execution, artifacts, cancellation and the restart sweep."""
from __future__ import annotations

import csv
import io
import json


from alignmentgraph_isd import AlignmentGraph, HarnessRunConfig
from alignmentgraph_isd.server import artifacts
from alignmentgraph_isd.server.app import sweep_interrupted_runs
from alignmentgraph_isd.server.db import session_scope
from sqlmodel import select

from alignmentgraph_isd.server.models import Run, RunStatus, Session, utcnow

def start(client, program_id, **arm):
    """Start a run, under the default arm unless one is named.

    No body at all when no arm is given — that is the path the Run button takes,
    and the one that leaves the choice to `HarnessRunConfig`.
    """
    response = client.post(f"/api/programs/{program_id}/runs", json=arm or None)
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
    # Points at the dialog, which is the only place a model can come from:
    # the app reads no AGENT_MODEL_* at all.
    assert "Model settings" in response.json()["detail"]


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

    kinds = {a["action"] for a in deep["actions"]}
    # The work that v1 never recorded at all.
    assert "node_read" in kinds, "graph reads are missing"
    assert "edge_write" in kinds, "alignment edges are missing"
    assert "node_write" in kinds

    # And every one of them is attributed — every action has a real agent
    # (2026-08-27: PedagogicalVerifierAgent was retired; self-validation now
    # runs inline under each specialist's own identity, never blank).
    assert deep["summary"]["agents"], "no agent was credited with any action"
    assert all(a["agent"] for a in deep["actions"]), "an action was credited to nobody"

    check_actions = [a for a in deep["actions"] if a["action"] == "check"]
    assert check_actions and all(a["agent"] for a in check_actions)


def test_the_work_set_plans_are_written_and_served(client, ready_program, wait_for_terminal):
    """How the work was divided has to survive the run too.

    The `dev_plan` trajectory event keeps a summary of the same decision, which
    is what the timeline reads; the plan itself carries the work set each
    Developer was handed — its obligations, its theme, the count it was asked
    for — and that reached the harness result and then nowhere, so it was gone
    the moment the run ended.
    """
    run_id = start(client, ready_program)
    wait_for_terminal(run_id)

    plans = client.get(f"/api/runs/{run_id}/artifacts/plans").json()
    assert plans, "the run divided no family into work sets"
    # Written from the result, not defaulted to an empty list on the way out.
    assert any(plan["work_sets"] for plan in plans)
    for plan in plans:
        assert plan["family"] and plan["stage"]
        # The honest field: whether the Designer's own division was used, or
        # the deterministic split had to carry it.
        assert plan["source"] in {"llm", "fallback", "deterministic"}

    # The join the trajectory inspector depends on: a `dev_plan` beat resolves
    # to its plan by SET IDS, because the event does not record its round and a
    # replan round's ids carry it (`AS-01R1`) — matching on family alone would
    # file round 0's sets under round 1's beat.
    deep = client.get(f"/api/runs/{run_id}/artifacts/trajectory_deep").json()
    events = [a for a in deep["actions"] if a["action"] == "dev_plan"]
    assert events, "the run dispatched no work sets"
    for event in events:
        ids = {entry["set_id"] for entry in event["context"]["sets"]}
        matched = [p for p in plans if {ws["set_id"] for ws in p["work_sets"]} & ids]
        assert len(matched) == 1, f"{ids} matched {len(matched)} plans"


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
        "trajectory": {},
        "metadata": {"token_usage": {"llm_calls": 0},
                     "errors": [f"Agent{i}: Connection refused" for i in range(6)]},
    }
    message = _barren_run_error(barren)
    assert "every specialist failed" in message
    assert "Connection refused" in message
    assert "all 6 agent attempts" in message

    # A run that produced some of the design is left alone: a partial result is
    # still worth looking at.
    partial = {
        "graph": {"nodes": [{"id": "objective_0"}]},
        "trajectory": {},
        "metadata": {"token_usage": {"llm_calls": 3},
                     "errors": ["EvaluationRevisionAgent: timed out"]},
    }
    assert _barren_run_error(partial) == ""

    # Nothing produced and nothing to explain it.
    assert "no design output" in _barren_run_error(
        {"graph": {"nodes": []}, "trajectory": {}, "metadata": {}}
    ).lower()


def test_a_complete_run_reports_succeeded_with_stats(client, ready_program, wait_for_terminal):
    """Renamed 2026-09-04: it was called `test_a_partial_run_is_still_a_success`
    but never built a partial run — the fake model completes every stage, so it
    asserted the happy path twice over. The partial-vs-barren boundary it
    claimed to guard is asserted directly on `_barren_run_error` above."""
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
    # The point of the light view: node payloads are most of a dump's size.
    assert all("data" not in n for n in light["nodes"])
    assert any(n.get("data") for n in full["nodes"])

    # And the point of the light view being a CUT and not a rebuild: it drops
    # `data` and keeps everything a renderer draws from. It used to whitelist
    # `{id, type}`, which would take the display fields out with it and leave
    # the browser to work them out again — the arrangement this replaced.
    assert all(n["label"] and n["kind"] for n in light["nodes"])
    for lit, fat in zip(light["nodes"], full["nodes"]):
        assert set(fat) - set(lit) == {"data"}
    assert light["edges"] == full["edges"]
    assert light["legend"] == full["legend"]


def test_node_detail_is_fetched_by_id(client, ready_program, wait_for_terminal):
    run_id = start(client, ready_program)
    wait_for_terminal(run_id)

    graph = client.get(f"/api/runs/{run_id}/graph").json()
    # objective has no section node any more — element nodes are the single
    # source of truth for the LO list (2026-08-27) — so the "fetch a section"
    # half uses implementation_plan, one of the few types still singleton.
    section = next(n["id"] for n in graph["nodes"] if n["id"] == "implementation_plan_0")
    body = client.get(f"/api/runs/{run_id}/nodes/{section}").json()
    assert body["id"] == "implementation_plan_0"
    assert body["data"]["instructor_orientation"]

    element = next(n["id"] for n in graph["nodes"] if n["id"].startswith("objective:"))
    assert client.get(f"/api/runs/{run_id}/nodes/{element}").json()["data"]

    assert client.get(f"/api/runs/{run_id}/nodes/nope_0").status_code == 404


def test_artifacts_are_served_by_name_only(client, ready_program, wait_for_terminal):
    run_id = start(client, ready_program)
    wait_for_terminal(run_id)

    assert client.get(f"/api/runs/{run_id}/artifacts/addie_output").json()["design"]
    assert client.get(f"/api/runs/{run_id}/artifacts/trajectory").json()["tool_calls"]
    assert client.get(f"/api/runs/{run_id}/artifacts/graph").json()["nodes"]

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
        assert set(flags) >= {"assessed_by", "practiced_by", "prepares_for", "bloom_ok", "aligned"}
    # 16 relations total: 5 core (C1-C5) + 11 secondary (P1-P11) — see
    # alignment.py::REGISTRY (renamed from the old R1..R13 scheme).
    from alignmentgraph_isd.core.alignment_graph import alignment as alignment_module
    assert set(graph["relation_coverage"]) == set(alignment_module.MATRIX)
    assert len(alignment_module.MATRIX) == 16   # C6/C7 went with the rubric node type


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


# ── trajectory export ───────────────────────────────────────────────────────

def test_export_carries_the_trajectory_and_only_the_trajectory(
    client, ready_program, wait_for_terminal,
):
    """Both halves of the trace — the judge-visible trio plus event log, and the
    full-fidelity action log — are one record split for size, so both travel.

    Nothing else does. Metadata, the graph and the ADDIE output are each their
    own artifact with their own endpoint; folding them in would make "export
    trajectory" mean "export the run", and then nobody could export the
    trajectory."""
    run_id = start(client, ready_program)
    wait_for_terminal(run_id)

    response = client.get(f"/api/runs/{run_id}/trajectory/export")
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    assert f"trajectory-{run_id}.json" in response.headers["content-disposition"]

    payload = response.json()
    assert payload["complete"] is True
    assert payload["run_id"] == run_id
    assert payload["trajectory"]["tool_calls"]
    assert payload["trajectory"]["events"]
    assert payload["trajectory_deep"]["actions"]

    assert set(payload) == {"export_version", "complete", "run_id",
                            "trajectory", "trajectory_deep"}
    assert json.loads(response.text) == payload


def test_exporting_mid_run_gives_what_was_recorded_and_says_it_is_partial(
    client, ready_program, blocked_run, wait_for_terminal,
):
    """The moment the trace is most wanted is while a run looks stuck. Returning
    a partial file under the same shape as a finished one would be a trap, so
    the live wire events travel under their own key and `complete` is false."""
    run_id = start(client, ready_program)

    response = client.get(f"/api/runs/{run_id}/trajectory/export")
    assert response.status_code == 200
    payload = response.json()
    assert payload["complete"] is False
    assert payload["run_id"] == run_id
    assert "trajectory" not in payload
    assert "live_events" in payload
    assert f"trajectory-partial-{run_id}.json" in response.headers["content-disposition"]

    blocked_run["open"] = True
    wait_for_terminal(run_id)
    assert client.get(f"/api/runs/{run_id}/trajectory/export").json()["complete"] is True


def test_exporting_an_unknown_run_is_a_404(client):
    assert client.get("/api/runs/does-not-exist/trajectory/export").status_code == 404


# ── agent contexts ──────────────────────────────────────────────────────────

def test_every_agent_context_is_recorded_with_its_transcript_and_tools(
    client, ready_program, wait_for_terminal,
):
    """What an agent was SHOWN is the first question about why it produced what
    it did, and until now nothing recorded it: `autonomy` had `context_len`, a
    number, and the transcript itself lived only in the loop's memory.

    Under native tool calling the SCHEMAS are half of what the model sees, so a
    context without them is half a context."""
    run_id = start(client, ready_program)
    wait_for_terminal(run_id)

    contexts = client.get(f"/api/runs/{run_id}/contexts").json()
    assert contexts, "no agent context was published"

    for entry in contexts:
        assert entry["agent"] and entry["label"]
        assert entry["messages"], f"{entry['label']} recorded no transcript"
        assert entry["messages"][0]["role"] == "system"
        assert entry["chars"] > 0
        # JSON-safe: the transcript is MIXED — the tool-call round trip leaves
        # the model's own message objects in it — so anything not serialized
        # here would have failed to reach disk at all.
        assert json.dumps(entry)

    labelled = {entry["label"] for entry in contexts}
    assert "analysis" in labelled and "outcomes" in labelled
    # A Developer's context is its own, separate from the stage that dispatched
    # it: that is the fan-out at its second scale, and merging them would hide
    # the tier the multi-agent claim rests on.
    assert any(":" in label for label in labelled), labelled


def test_the_context_survives_the_run_and_is_served_from_disk(
    client, ready_program, settings, wait_for_terminal,
):
    run_id = start(client, ready_program)
    wait_for_terminal(run_id)

    directory = settings.data_root / artifacts.relative_run_dir(ready_program, run_id)
    saved = json.loads((directory / "contexts.json").read_text(encoding="utf-8"))
    assert saved
    assert client.get(f"/api/runs/{run_id}/contexts").json() == saved


def test_a_run_with_no_context_yet_serves_an_empty_list(client, ready_program, blocked_run):
    run_id = start(client, ready_program)
    assert client.get(f"/api/runs/{run_id}/contexts").json() == []


# ── transcript export ───────────────────────────────────────────────────────

def test_the_transcript_downloads_as_readable_markdown(
    client, ready_program, wait_for_terminal,
):
    """Markdown, not JSON: `/contexts` already serves the JSON a tool would
    want, and this is the one artifact a PERSON reads end to end. A 27-message
    conversation as a JSON array is not that."""
    run_id = start(client, ready_program)
    wait_for_terminal(run_id)

    response = client.get(f"/api/runs/{run_id}/transcript/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert f"transcript-{run_id}.md" in response.headers["content-disposition"]

    body = response.text
    contexts = client.get(f"/api/runs/{run_id}/contexts").json()
    # Every agent is in it, and every message: the point of downloading a
    # transcript is to read exactly what the model was shown.
    for entry in contexts:
        assert f"## {entry['agent']} — {entry['label']}" in body
    total_messages = sum(len(c["messages"]) for c in contexts)
    assert body.count("\n### ") >= total_messages


def test_one_agent_can_be_exported_by_its_context_id(client, ready_program, wait_for_terminal):
    """By ID, not by label and not by position.

    Not by label because a regenerated stage publishes one context per attempt
    and they share a name. Not by position — which is what this addressed
    first — because a context is republished after every turn now, so the list
    is only stable once the run is over, and a link a reader kept would follow
    the ordinal rather than the conversation it was for."""
    run_id = start(client, ready_program)
    wait_for_terminal(run_id)

    contexts = client.get(f"/api/runs/{run_id}/contexts").json()
    assert len(contexts) > 1
    wanted = contexts[1]
    assert wanted["id"], "the harness names every context it publishes"

    response = client.get(f"/api/runs/{run_id}/transcript/export?context={wanted['id']}")
    assert response.status_code == 200
    assert wanted["agent"] in response.text
    # Only that one.
    assert response.text.count("\n---\n") == 1
    # The id identifies; the LABEL is what a reader recognises in a downloads
    # folder, so that is what the filename carries.
    assert wanted["label"].replace(":", "-") in response.headers["content-disposition"]

    assert client.get(
        f"/api/runs/{run_id}/transcript/export?context=nope").status_code == 404


def test_exporting_a_transcript_that_was_never_recorded_is_a_404(
    client, ready_program, blocked_run,
):
    """``blocked_run`` holds the worker at the gate, so the condition in the
    name is actually forced. Without it the run may well have finished and
    published contexts, and the assertion had to accept 200 as well as 404 —
    which made it a check that the route does not crash, nothing more."""
    run_id = start(client, ready_program)
    assert client.get(f"/api/runs/{run_id}/transcript/export").status_code == 404


def test_one_context_can_be_fetched_whole_while_the_run_is_live(
    client, ready_program, wait_for_terminal,
):
    """The row a reader OPENS is where the transcript and the tool schemas are
    fetched.

    The live stream carries the rows without either — they are the large half
    and a context is republished after every turn — so a row that is merely
    listed costs almost nothing, and the one being looked at is re-fetched as
    it grows. Regression: when live rows first landed, the Tool schemas section
    rendered empty, because the row it was reading has no schemas by design."""
    run_id = start(client, ready_program)
    wait_for_terminal(run_id)

    rows = client.get(f"/api/runs/{run_id}/contexts").json()
    assert rows
    wanted = rows[0]["id"]

    one = client.get(f"/api/runs/{run_id}/contexts?context={wanted}").json()
    assert len(one) == 1 and one[0]["id"] == wanted
    assert one[0]["tools"], "the schemas are half of what the model sees"
    assert one[0]["messages"]

    assert client.get(f"/api/runs/{run_id}/contexts?context=nope").json() == []


def test_the_violation_ledger_is_served_and_survives_the_run(
    client, ready_program, settings, wait_for_terminal,
):
    """What the app needed and never had: a violation's own words.

    Every view in the app was built from counters on the event stream — a
    reader could see that four `C2` violations were found in round 2, never
    which node, what the message said, or what the hint told the agent to do.
    That text existed only inside trajectory_deep.json, which the app fetches
    and renders through the timeline reducers.
    """
    run_id = start(client, ready_program)
    wait_for_terminal(run_id)

    served = client.get(f"/api/runs/{run_id}/violations").json()
    directory = settings.data_root / artifacts.relative_run_dir(ready_program, run_id)
    saved = json.loads((directory / "violations.json").read_text(encoding="utf-8"))
    assert served == saved

    for finding in served:
        assert finding["key"] and finding["messages"]
        assert finding["outcome"] in (
            "open", "repaired_by_harness", "repaired_by_agent")
        if finding["outcome"] == "open":
            # The distinction the ledger exists for: "the model could not fix
            # this" and "we did not give it another turn" are different
            # results, and only the second is ours to change.
            assert finding["open_reason"]


def test_the_violation_ledger_downloads_as_csv(client, ready_program, wait_for_terminal):
    """CSV, not JSON: `/violations` already serves the JSON a tool would want,
    and the ledger is a TABLE — what is still open, why, who owns it, which
    check said so. Those are spreadsheet questions."""
    run_id = start(client, ready_program)
    wait_for_terminal(run_id)

    response = client.get(f"/api/runs/{run_id}/violations/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert f"violations-{run_id}.csv" in response.headers["content-disposition"]

    rows = list(csv.DictReader(io.StringIO(response.text)))
    served = client.get(f"/api/runs/{run_id}/violations").json()
    assert served, "the fixture run finds violations; without them this proves nothing"
    assert len(rows) == len(served)
    assert list(rows[0]) == list(artifacts.VIOLATION_COLUMNS)

    by_key = {finding["key"]: finding for finding in served}
    for row in rows:
        finding = by_key[row["key"]]
        assert row["type"] == finding["type"]
        assert row["outcome"] == finding["outcome"]
        # Both halves of the ledger's point survive the flattening: WHY a
        # finding is still open, and WHICH item it is about.
        assert row["open_reason"] == finding["open_reason"]
        assert json.loads(row["metadata"]) == finding["metadata"]
        assert row["messages"] == "\n".join(finding["messages"])


def test_a_clean_run_exports_a_header_and_no_rows(client, ready_program, blocked_run):
    """An empty ledger is a RESULT, not an absence — a run whose checks all came
    back clean is exactly what the design is aiming at, and answering it with a
    404 would make the successful case the one you cannot download."""
    run_id = start(client, ready_program)

    response = client.get(f"/api/runs/{run_id}/violations/export")
    assert response.status_code == 200
    assert list(csv.DictReader(io.StringIO(response.text))) == []
    assert response.text.splitlines()[0].count(",") == len(artifacts.VIOLATION_COLUMNS) - 1
    # Still going, so the file says which file it is, as the trajectory export
    # says `complete: false`.
    assert f"violations-partial-{run_id}.csv" in response.headers["content-disposition"]


def test_the_consumer_turns_a_ledger_snapshot_into_state_not_an_event(settings, tmp_path):
    """The ledger is STATE, the way a context and the graph are: republished
    whole whenever a finding is written, and only its latest form is worth
    reading. Appending it to the timeline instead would put a hundred-odd
    `violations_snapshot` actions in front of a reader looking for what the
    agents did."""
    from alignmentgraph_isd.server.events import RunState
    from alignmentgraph_isd.server.runner import RunManager

    state = RunState(run_id="r", program_id="p")
    consume = RunManager(settings)._make_consumer(state)

    consume("violations_snapshot", {"findings": [{"key": "a", "outcome": "open"}]})
    consume("violations_snapshot", {"findings": [
        {"key": "a", "outcome": "repaired_by_harness"}, {"key": "b", "outcome": "open"}]})

    assert [f["key"] for f in state.violations] == ["a", "b"], "replaced, not piled up"
    assert state.violations[0]["outcome"] == "repaired_by_harness", "the latest wins"
    assert state.violations_rev == 2, "every change is a revision the stream can follow"
    assert state.events == [], "state, never an action on the timeline"


def test_a_run_in_flight_exports_the_findings_so_far(client, ready_program, blocked_run):
    """The partial export finally has something to export.

    `/violations/export` has always named its file `violations-partial-` for a
    run still going, but until the ledger streamed there were never any rows
    behind that name — the findings did not exist outside the harness until it
    returned."""
    run_id = start(client, ready_program)
    state = client.app.state.run_manager.registry.get(run_id)
    assert state is not None, "the run must still be in the registry to be live"

    state.set_violations([{
        "key": "C2|objective:ILO-01", "type": "C2", "node_id": "objective:ILO-01",
        "edge_type": "", "severity": "high", "outcome": "open", "open_reason": "",
        "repair_hint": "write an item for it", "metadata": {"lo_id": "ILO-01"},
        "target_designer": "assessment_designer", "messages": ["not assessed"],
        "first_round": 1, "first_phase": "assessment", "first_family": "assessment_designer",
        "last_round": 1, "sightings": 1, "shown_to_agent": 0, "report_only": False,
        "repaired_by": "", "repaired_at_round": 0, "converged_at_round": 0,
    }])

    assert client.get(f"/api/runs/{run_id}/violations").json(), (
        "the endpoint answers from live state while the run is in the registry")

    response = client.get(f"/api/runs/{run_id}/violations/export")
    assert f"violations-partial-{run_id}.csv" in response.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert [row["key"] for row in rows] == ["C2|objective:ILO-01"]


def test_exporting_violations_of_a_run_that_does_not_exist_is_a_404(client):
    assert client.get("/api/runs/does-not-exist/violations/export").status_code == 404


def test_the_graph_marks_every_node_that_carries_a_violation(
    client, ready_program, wait_for_terminal,
):
    """`objective_alignment` is built by walking the OBJECTIVE nodes, so an
    activity linked to no objective, a material whose module does not exist and
    an item with no answer key had no signal on the graph at all — the first
    place a reader looks said nothing about them."""
    run_id = start(client, ready_program)
    wait_for_terminal(run_id)

    graph = client.get(f"/api/runs/{run_id}/graph?detail=full").json()
    marks = graph["node_violations"]
    assert isinstance(marks, dict)
    for node_id, types in marks.items():
        assert types and sorted(types) == types, node_id


# ── the ablation arm ─────────────────────────────────────────────────────────

def test_a_run_with_no_arm_takes_the_harness_default(client, ready_program, wait_for_terminal):
    """The app names no arm, so the harness decides which one it is.

    Asserted against `HarnessRunConfig`'s own fields rather than against the
    literals "multi"/"graph": those defaults live in exactly one place, and a
    test that copied them here would be the second.
    """
    default = HarnessRunConfig()
    response = client.post(f"/api/programs/{ready_program}/runs")
    assert response.status_code == 202, response.text
    assert response.json()["agent_mode"] == default.agent_mode
    assert response.json()["context_mode"] == default.context_mode

    stats = wait_for_terminal(response.json()["run_id"])["stats"]
    assert stats["agent_mode"] == default.agent_mode
    assert stats["context_mode"] == default.context_mode


def test_a_run_can_be_started_under_another_arm(
    client, ready_program, settings, wait_for_terminal
):
    run_id = start(client, ready_program, agent_mode="single", context_mode="prose")
    detail = wait_for_terminal(run_id)
    assert detail["run"]["status"] == "succeeded", detail["run"]["error"]
    assert detail["stats"]["agent_mode"] == "single"
    assert detail["stats"]["context_mode"] == "prose"

    # What the run itself recorded has to agree with what the row reports: both
    # are read off the same config object, and a disagreement would mean the
    # badge in the app names an arm the harness did not run.
    directory = settings.data_root / artifacts.relative_run_dir(ready_program, run_id)
    run_config = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))["run_config"]
    assert run_config["agent_mode"] == "single"
    assert run_config["context_mode"] == "prose"


def test_a_prose_run_ships_no_graph(client, ready_program, settings, wait_for_terminal):
    """The absent graph IS the treatment — this pins what the app has to explain."""
    run_id = start(client, ready_program, agent_mode="single", context_mode="prose")
    wait_for_terminal(run_id)

    directory = settings.data_root / artifacts.relative_run_dir(ready_program, run_id)
    assert json.loads((directory / "graph.json").read_text(encoding="utf-8")) == {}
    assert client.get(f"/api/runs/{run_id}/graph").json().get("nodes") == []


def test_an_unknown_arm_is_refused_before_a_run_row_exists(client, ready_program):
    response = client.post(f"/api/programs/{ready_program}/runs", json={"agent_mode": "duo"})
    assert response.status_code == 422, response.text
    assert client.get(f"/api/programs/{ready_program}").json()["runs"] == []


def test_the_closing_frame_still_names_the_arm(client, ready_program, wait_for_terminal):
    """A watcher that stays to the end must not be left with less than a reader
    who fetches the run afterwards.

    The arm is carried beside `stats` rather than inside it, and the terminal
    frame used to publish the raw dict the run's own counters replace — so the
    badge showed all run and vanished at the last frame.
    """
    run_id = start(client, ready_program, agent_mode="single", context_mode="graph")
    wait_for_terminal(run_id)

    frames = [json.loads(line[len("data: "):])
              for line in client.get(f"/api/runs/{run_id}/events?after=0").text.splitlines()
              if line.startswith("data: ")]
    terminal = [frame for frame in frames
                if isinstance(frame, dict) and frame.get("kind") == "run_finished"]
    assert terminal, "the stream never carried a terminal frame"
    assert terminal[-1]["payload"]["stats"]["agent_mode"] == "single"
    assert terminal[-1]["payload"]["stats"]["context_mode"] == "graph"


def test_the_arm_is_known_before_the_run_starts(
    client, ready_program, blocked_run, wait_for_terminal
):
    """Resolved on the request thread, not the worker.

    The browser opens the event stream as soon as it has the run id, and the
    opening frame is the only one carrying `stats` — an arm settled later would
    reach a watcher only on reload.
    """
    run_id = start(client, ready_program, agent_mode="multi", context_mode="prose")
    stats = client.get(f"/api/runs/{run_id}").json()["stats"]
    assert (stats["agent_mode"], stats["context_mode"]) == ("multi", "prose")

    blocked_run["open"] = True
    wait_for_terminal(run_id)
