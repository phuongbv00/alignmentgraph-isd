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

from .events import EventKind, RunState

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
        "graph_rev": state.graph_rev,
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

    cursor = after
    while True:
        if await request.is_disconnected():
            return

        for event in state.events_after(cursor):
            cursor = event.seq
            yield frame(event.kind, event.to_dict(), seq=event.seq)

        if state.graph_rev > sent_graph_rev:
            sent_graph_rev = state.graph_rev
            yield _graph_frame(state)

        if state.is_terminal and not state.events_after(cursor):
            # The terminal event has already gone out above; closing here is what
            # stops EventSource reconnecting forever. The client closes on its side.
            return

        wakeup.clear()
        try:
            await asyncio.wait_for(wakeup.wait(), timeout=HEARTBEAT_SECONDS)
        except asyncio.TimeoutError:
            yield ": heartbeat\n\n"


async def replay_stream(events: list[dict], status: dict) -> AsyncIterator[str]:
    """A finished run whose state is no longer in memory: replay from disk and close."""
    yield frame("hello", status)
    for event in events:
        yield frame(event.get("kind", "event"), event, seq=event.get("seq"))
    if not any(e.get("kind") in EventKind.TERMINAL for e in events):
        # The process died before writing a terminal event; say so explicitly so
        # the client stops waiting for one that will never arrive.
        yield frame(EventKind.RUN_FAILED, {"status": status.get("status"), "error": status.get("error", "")})


def stream_response(generator: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(generator, media_type="text/event-stream", headers=SSE_HEADERS)


def _graph_frame(state: RunState) -> str:
    # Assembled as text: the payload is already a JSON string and re-parsing it
    # only to re-serialize would be wasted work on every tick.
    return f"event: graph\ndata: {state.snapshot_graph('light') or '{}'}\n\n"
