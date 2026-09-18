"""Server-sent events for a live run.

Hand-rolled rather than pulled from a library: the framing is a dozen lines and
the lifecycle rules below are the whole substance of it.

A stream always opens the same way — `hello`, then the current graph, then any
events the client has not seen — so a first connection and a reconnection after
a reload take the identical path. The client's position comes from the
`Last-Event-ID` header that ``EventSource`` resends automatically, or from
``?after=`` when a caller is driving it by hand.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import Request
from fastapi.responses import StreamingResponse

from .events import EventKind, RunState, terminal_kind

HEARTBEAT_SECONDS = 15.0

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    # Nginx and friends buffer text/event-stream by default, which turns a live
    # stream into one delivery at the end.
    "X-Accel-Buffering": "no",
}


def frame(kind: str, data: dict, seq: int | None = None) -> str:
    parts = []
    if seq is not None:
        parts.append(f"id: {seq}")
    parts.append(f"event: {kind}")
    parts.append(f"data: {json.dumps(data, ensure_ascii=False)}")
    return "\n".join(parts) + "\n\n"


def resume_cursor(request: Request, after: int = 0) -> int:
    """Where to resume from. The header wins: the browser sets it on reconnect
    without the client code being involved, so it is the more trustworthy of the
    two."""
    header = request.headers.get("last-event-id")
    if header:
        try:
            return int(header)
        except ValueError:
            pass
    return max(0, after)


def hello_payload(state: RunState) -> dict:
    return {
        "run_id": state.run_id,
        "program_id": state.program_id,
        "status": state.status,
        "error": state.error,
        "model_name": state.model_name,
        "stats": state.public_stats(),
    }


async def live_stream(
    request: Request, state: RunState, wakeup: asyncio.Event, after: int = 0
) -> AsyncIterator[str]:
    """Replay from `after`, then follow the run to its end."""
    yield frame("hello", hello_payload(state))

    sent_graph_rev = 0
    if state.graph_rev:
        sent_graph_rev = state.graph_rev
        yield _graph_frame(state)

    sent_contexts_rev = 0
    if state.contexts_rev:
        sent_contexts_rev = state.contexts_rev
        yield _contexts_frame(state)

    sent_violations_rev = 0
    if state.violations_rev:
        sent_violations_rev = state.violations_rev
        yield _violations_frame(state)

    cursor = after
    while True:
        # Cleared BEFORE the scan, so a wakeup that lands while a frame is being
        # yielded is kept for the wait below instead of erased by a clear after it.
        wakeup.clear()
        if await request.is_disconnected():
            return

        # This round's events are CAPTURED first and sent last, with the state
        # frames in between. State frames are the latest state rather than
        # history, so going out ahead of the events that led to them loses
        # nothing; sent after them, a `violations` frame lands behind the
        # terminal event whenever the run's last ledger write and its finish
        # arrive in one wakeup, and the terminal event is what a client closes
        # on. Capturing before reading the state is what makes the order safe
        # the other way too: every state write that precedes a captured event
        # is already in the frames below, so the last one is never left unsent.
        pending = state.events_after(cursor)

        if state.graph_rev > sent_graph_rev:
            sent_graph_rev = state.graph_rev
            yield _graph_frame(state)

        if state.contexts_rev > sent_contexts_rev:
            sent_contexts_rev = state.contexts_rev
            yield _contexts_frame(state)

        if state.violations_rev > sent_violations_rev:
            sent_violations_rev = state.violations_rev
            yield _violations_frame(state)

        for event in pending:
            cursor = event.seq
            yield frame(event.kind, event.to_dict(), seq=event.seq)

        if state.is_terminal and not state.events_after(cursor):
            # The terminal event has already gone out above; closing here is what
            # stops EventSource reconnecting forever. The client closes on its side.
            return

        try:
            await asyncio.wait_for(wakeup.wait(), timeout=HEARTBEAT_SECONDS)
        except asyncio.TimeoutError:
            yield ": heartbeat\n\n"


async def replay_stream(events: list[dict], status: dict) -> AsyncIterator[str]:
    """A finished run whose state is no longer in memory: replay from disk and close.

    There are usually NO events to replay. The wire log is deleted once a run
    has a result (``artifacts.discard_events``), because the result's own
    artifacts carry every frame of it, so what a reader gets is ``hello`` — the
    `Run` row: status, error, stats — and the closing frame below. The page
    fetches the trace itself, as it already does for the graph, the contexts
    and the ledger.

    Events ARE replayed for a run that ended with no result, which is the case
    the log exists for: cancelled, failed, or interrupted with the process.
    """
    yield frame("hello", status)
    for event in events:
        yield frame(event.get("kind", "event"), event, seq=event.get("seq"))
    if not any(e.get("kind") in EventKind.TERMINAL for e in events):
        # Nothing on disk says how this ended — either the log is gone because
        # the run has a result, or the process died before writing its terminal
        # event. Either way the `Run` row knows, and the client stops listening
        # only on a terminal frame, so one is synthesized rather than left for
        # a reader that would wait forever. Named through the same mapping the
        # live stream closes with: a run must not replay under a different
        # terminal name than it finished under.
        yield frame(terminal_kind(str(status.get("status") or "")),
                    {"status": status.get("status"), "error": status.get("error", ""),
                     "stats": status.get("stats") or {}})


def stream_response(generator: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(generator, media_type="text/event-stream", headers=SSE_HEADERS)


def _violations_frame(state: RunState) -> str:
    """The run's ledger: every distinct finding and what became of it.

    Sent whole — a finding is a row, not a transcript — and whenever the
    revision moves, which is throughout the run: the harness publishes the
    ledger as it writes it, so the tab fills in the way the Context tab does.
    An outcome stays provisional until the final look settles it, and a
    finding with no `open_reason` yet is precisely one that has not been."""
    rows = json.dumps(state.violations, ensure_ascii=False)
    return f"event: violations\ndata: {rows}\n\n"


def _contexts_frame(state: RunState) -> str:
    """The context ROWS, without their transcripts.

    Same protocol as the graph — a revision counter, pushed only when it moves
    — and the same reason for sending a reduced payload: a loop republishes its
    context after every turn, so the full transcripts would go over the wire
    tens of times per run. The rows carry who is speaking, in which phase, and
    how much of the window they are using, which is the whole of the list view;
    the transcript is fetched from /contexts when a row is opened.
    """
    rows = json.dumps(state.contexts_light(), ensure_ascii=False)
    return f"event: contexts\ndata: {rows}\n\n"


def _graph_frame(state: RunState) -> str:
    # Assembled as text: the payload is already a JSON string and re-parsing it
    # only to re-serialize would be wasted work on every tick.
    return f"event: graph\ndata: {state.snapshot_graph('light') or '{}'}\n\n"
