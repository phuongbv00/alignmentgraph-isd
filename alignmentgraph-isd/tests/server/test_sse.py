"""The live event stream.

The invariant that matters: whatever a client does — connect late, reload
mid-run, reconnect after the run finished — the events it ends up with must be
the complete sequence, with no gaps and no duplicates.
"""
from __future__ import annotations

import json

def parse_stream(text: str) -> list[dict]:
    """Split an SSE body into {event, data} records, ignoring heartbeats."""
    records = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block or block.startswith(":"):
            continue
        event, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                data = line[6:]
        if event is not None:
            records.append({"event": event, "data": json.loads(data) if data else {}})
    return records


def read_stream(client, run_id: str, headers=None, params=None) -> list[dict]:
    with client.stream(
        "GET", f"/api/runs/{run_id}/events", headers=headers or {}, params=params or {}
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        return parse_stream("".join(response.iter_text()))


def start(client, program_id):
    return client.post(f"/api/programs/{program_id}/runs").json()["run_id"]


def test_stream_opens_with_hello_and_ends_terminal(client, ready_program):
    run_id = start(client, ready_program)
    records = read_stream(client, run_id)

    assert records[0]["event"] == "hello"
    assert records[0]["data"]["run_id"] == run_id
    assert records[-1]["event"] in ("run_finished", "run_failed", "run_cancelled")


def test_sequence_numbers_have_no_gaps_or_duplicates(client, ready_program):
    run_id = start(client, ready_program)
    records = read_stream(client, run_id)

    seqs = [r["data"]["seq"] for r in records if "seq" in r.get("data", {})]
    assert seqs == list(range(1, len(seqs) + 1)), "event sequence is not contiguous"


def test_progress_events_reach_the_client(client, ready_program):
    """Without these the UI has nothing to show for minutes at a time."""
    run_id = start(client, ready_program)
    kinds = {r["event"] for r in read_stream(client, run_id)}

    assert "run_started" in kinds
    assert "phase_started" in kinds and "phase_finished" in kinds
    assert "llm_started" in kinds and "llm_finished" in kinds
    assert "agent_step" in kinds and "node_edit" in kinds
    assert "graph" in kinds


def test_the_graph_arrives_as_state_not_as_replayed_events(client, ready_program):
    """Graph frames carry no seq: they are the latest state, not history."""
    run_id = start(client, ready_program)
    graph_frames = [r for r in read_stream(client, run_id) if r["event"] == "graph"]

    assert graph_frames
    last = graph_frames[-1]["data"]
    assert last["nodes"] and last["edges"]
    assert all("data" not in n for n in last["nodes"]), "wire frames must be the light view"
    # ...and the light view must still be drawable: `data` is the only thing
    # dropped, so every display field is on the wire.
    assert all(n["label"] and n["kind"] for n in last["nodes"]), \
        "the light frame must still carry what a renderer draws from"
    assert last["legend"]["nodes"], "the legend rides with the graph it explains"

    counts = [len(f["data"]["nodes"]) for f in graph_frames]
    assert counts == sorted(counts), "the live graph shrank between frames"


def test_resuming_with_a_cursor_skips_what_was_seen(client, ready_program):
    run_id = start(client, ready_program)
    everything = read_stream(client, run_id)
    all_seqs = [r["data"]["seq"] for r in everything if "seq" in r.get("data", {})]
    midpoint = all_seqs[len(all_seqs) // 2]

    resumed = read_stream(client, run_id, params={"after": midpoint})
    resumed_seqs = [r["data"]["seq"] for r in resumed if "seq" in r.get("data", {})]

    assert resumed_seqs, "resuming returned nothing"
    assert min(resumed_seqs) > midpoint, "resume replayed events the client already had"
    assert resumed_seqs == sorted(set(resumed_seqs)), "resume produced duplicates"
    # Together the two reads cover the run exactly once.
    assert set(all_seqs[: all_seqs.index(midpoint) + 1]) | set(resumed_seqs) == set(all_seqs)


def test_last_event_id_header_takes_priority_over_the_query(client, ready_program):
    """The browser sets this header on reconnect without the client's help, so
    it is the more trustworthy cursor of the two."""
    run_id = start(client, ready_program)
    everything = read_stream(client, run_id)
    all_seqs = [r["data"]["seq"] for r in everything if "seq" in r.get("data", {})]
    cursor = all_seqs[len(all_seqs) // 2]

    resumed = read_stream(client, run_id, headers={"Last-Event-ID": str(cursor)}, params={"after": 0})
    seqs = [r["data"]["seq"] for r in resumed if "seq" in r.get("data", {})]
    assert min(seqs) > cursor


def test_a_finished_run_replays_as_its_outcome_and_closes(client, ready_program, wait_for_terminal):
    """After a restart the run is gone from memory — and so is its wire log.

    A run with a result has the log deleted (`artifacts.discard_events`)
    because its artifacts carry every frame of it, so the replay is `hello`
    (the `Run` row) plus a synthesized closing frame, and the page fetches the
    trace itself — the same division the graph, the contexts and the ledger
    already live under.

    The closing frame is the part that has to be right. The client stops
    listening on the terminal NAME, so a synthesized one that said
    `run_failed` for a run that succeeded would both leave the browser
    reconnecting and show the wrong outcome. It comes from the one mapping the
    live stream closes with (`events.terminal_kind`).
    """
    run_id = start(client, ready_program)
    wait_for_terminal(run_id)

    live = read_stream(client, run_id)
    assert live[-1]["event"] == "run_finished"

    # Drop the in-memory state, exactly as a restart would.
    client.app.state.run_manager.registry._runs.clear()

    replayed = read_stream(client, run_id)
    assert replayed[0]["event"] == "hello"
    assert replayed[0]["data"]["replay"] is True
    assert replayed[-1]["event"] == "run_finished", "a replayed run closed under another name"
    assert replayed[-1]["data"]["status"] == "succeeded"
    # Nothing in between: the artifacts are the record now.
    assert len(replayed) == 2


def test_a_run_with_no_result_replays_its_whole_log():
    """The case the wire log exists for.

    A run that ends without a result writes no artifacts, so its log is kept
    whole — actions included — and replaying it is the only way to see what
    happened. (That the log SURVIVES such a run is
    `test_a_run_that_wrote_no_result_keeps_its_whole_wire_log`; this is the
    other half: what the replay does with it.)

    Its closing frame is synthesized too, through the same mapping, and
    `interrupted` is not a status the live stream can ever emit — nothing was
    left running to emit it — so this is the one terminal frame that only ever
    exists here.
    """
    import asyncio

    from alignmentgraph_isd.server import sse

    events = [{"seq": 1, "kind": "action", "payload": {"action": "node_read"}},
              {"seq": 2, "kind": "llm_started", "payload": {}}]
    status = {"run_id": "r", "status": "interrupted", "error": "the process died",
              "stats": {}, "replay": True}

    async def collect():
        return [chunk async for chunk in sse.replay_stream(events, status)]

    records = parse_stream("".join(asyncio.run(collect())))
    assert [r["event"] for r in records] == ["hello", "action", "llm_started", "run_failed"]
    assert records[1]["data"]["payload"]["action"] == "node_read"
    assert records[-1]["data"]["error"] == "the process died"


def test_streaming_an_unknown_run_is_404(client):
    assert client.get("/api/runs/nope/events").status_code == 404


def test_the_ledger_streams_live_and_replaces_rather_than_piles_up():
    """The Violations tab is live too: the harness republishes the whole ledger
    whenever it writes a finding, so a viewer watches problems appear and move
    from open to repaired instead of seeing only the settled result.

    Sent WHOLE, unlike the contexts, because a finding is a row rather than a
    transcript — there is no heavy half to leave behind and fetch per row.

    And, like `add_context`, deliberately without a `_notify()`: waking the
    stream every time a finding is written would drain it far ahead of the
    events.jsonl flusher. The frame rides the next event's wakeup, and there is
    always one close behind — the producer only emits from inside the consumer
    chain, so an event has just gone through.
    """
    from alignmentgraph_isd.server.events import RunState

    state = RunState(run_id="r", program_id="p")
    state.set_violations([{"key": "a", "outcome": "open", "open_reason": ""}])
    state.set_violations([{"key": "a", "outcome": "open", "open_reason": ""},
                          {"key": "b", "outcome": "open", "open_reason": ""}])
    state.set_violations([{"key": "a", "outcome": "repaired_by_harness", "open_reason": ""},
                          {"key": "b", "outcome": "open", "open_reason": "converged"}])

    assert [f["key"] for f in state.violations] == ["a", "b"], (
        "each publish replaces the ledger; appending would pile up prefixes")
    assert state.violations[0]["outcome"] == "repaired_by_harness", "the latest wins"
    assert state.violations_rev == 3, "every change is a revision the stream can follow"
    assert state._unflushed == [], (
        "the ledger is state, not an event — nothing here belongs in events.jsonl")


def test_contexts_stream_live_and_replace_rather_than_pile_up():
    """The Context tab is live now: a loop republishes its context after every
    turn, so a viewer watches the transcript grow instead of seeing it appear
    only once its agent has finished.

    Two things make that affordable. The frame carries the ROWS without their
    transcripts — the whole of the list view, small enough to push per turn —
    and each republish REPLACES the snapshot before it, or the tab would be a
    list of prefixes of itself.

    What "the same context" means is decided ONCE, by the harness
    (``core.memory.context_id``), and travels in the payload as ``id``: this
    side never has to know what that identity is made of.
    """
    from alignmentgraph_isd.server.events import RunState

    state = RunState(run_id="r", program_id="p")
    first = {"id": "aaaaaaaaaaaa",
             "agent": "OutcomeDesignerAgent", "phase": "outcomes", "label": "outcomes",
             "attempt": 1, "messages": [{"role": "system", "content": "x"}],
             "tools": [{"function": {"name": "submit_learning_objectives"}}],
             "total_tokens": 300, "token_budget": 8000}
    state.add_context(first)
    state.add_context({**first, "messages": first["messages"] * 4, "total_tokens": 900})
    state.add_context({**first, "id": "bbbbbbbbbbbb", "attempt": 2, "total_tokens": 120})

    assert len(state.contexts) == 2, "a republished context replaced the one before it"
    assert state.contexts[0]["total_tokens"] == 900, "the latest snapshot wins"
    assert state.contexts_rev == 3, "every change is a revision the stream can follow"

    rows = state.contexts_light()
    assert [r["turns"] for r in rows] == [4, 1], "the row says how far the agent has got"
    assert all("messages" not in r and "tools" not in r for r in rows), (
        "the live frame must not carry the transcripts — they are the large half")
    assert rows[0]["total_tokens"] == 900 and rows[0]["token_budget"] == 8000, (
        "the meter is drawn from the row, so it has to carry the numbers")
