"""In-memory state for runs that are in flight.

Design notes worth keeping in mind when changing this:

* **Events are a cursor-replayable list, not a queue.** One shared list per run
  serves any number of readers, each holding its own offset. That is what makes
  a page reload mid-run resumable and multiple browser tabs free.
* **The graph is state, not an event.** A full graph dump is ~95 KB; a run
  produces a dozen-odd of them, and only the latest is ever wanted. Storing the
  newest and bumping a revision beats replaying stale copies.
* **Everything is stored pre-serialized.** The harness hands us live dicts from
  inside the running graph, which later phases keep mutating. Serializing on the
  worker thread at the moment of the event is what makes a snapshot a snapshot.
"""
from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .models import RunStatus


class EventKind:
    """Wire names for the SSE `event:` field."""

    RUN_STARTED = "run_started"
    PHASE_STARTED = "phase_started"
    PHASE_FINISHED = "phase_finished"
    LLM_STARTED = "llm_started"
    LLM_FINISHED = "llm_finished"
    # One entry of the deep trajectory: a graph read, a node
    # write, an alignment edge, a model call, a check, a repair.
    ACTION = "action"
    AGENT_STEP = "agent_step"
    NODE_EDIT = "node_edit"
    LLM_CALL = "llm_call"
    VALIDATION = "validation_event"
    CHECK = "check_event"
    REPAIR = "repair_event"
    RETRIEVAL = "retrieval_event"
    # Not terminal: the request has been accepted but the run is still winding
    # down. Emitted so every open viewer sees the button take effect instead of
    # watching "running" for the ~50 s an in-flight model call can still take.
    RUN_CANCELLING = "run_cancelling"
    RUN_FINISHED = "run_finished"
    RUN_FAILED = "run_failed"
    RUN_CANCELLED = "run_cancelled"

    TERMINAL = (RUN_FINISHED, RUN_FAILED, RUN_CANCELLED)


@dataclass(frozen=True)
class Event:
    seq: int
    kind: str
    ts: str
    payload: dict[str, Any]

    def to_dict(self) -> dict:
        return {"seq": self.seq, "kind": self.kind, "ts": self.ts, "payload": self.payload}


@dataclass
class RunState:
    """Live state of one run. Mutated from the worker thread, read from the loop."""

    run_id: str
    program_id: str
    status: str = RunStatus.RUNNING
    error: str = ""
    model_name: str = ""

    events: list[Event] = field(default_factory=list)
    # Latest graph only, pre-serialized. `light` drops the per-node `data`
    # payloads (~95 KB -> ~35 KB) and is what goes over the wire; `full` backs
    # the on-demand node-detail endpoint.
    graph_light_json: str = ""
    graph_full_json: str = ""
    graph_rev: int = 0
    # One entry per agent context published by the harness: the system turn,
    # the whole transcript, and the tool schemas that were bound. State, not
    # events, for the same reason the graph is: a transcript is large and only
    # its latest form is worth reading, so replaying every version to every
    # viewer would be paying repeatedly for something nobody reads twice.
    contexts: list[dict] = field(default_factory=list)
    #: Where each context sits in `contexts`, by identity, so a mid-run
    #: snapshot replaces the one before it instead of piling up.
    context_index: dict[str, int] = field(default_factory=dict)
    #: Bumped on every context change, so the stream can push only when there
    #: is something new — the same protocol `graph_rev` uses.
    contexts_rev: int = 0
    #: Every distinct finding of the run, latest state, in first-seen order.
    #: Published whole rather than incrementally: unlike a transcript a finding
    #: is small, and unlike the graph it is a list the tab renders directly.
    violations: list[dict] = field(default_factory=list)
    violations_rev: int = 0

    stats: dict[str, Any] = field(default_factory=dict)
    cancel_requested: bool = False
    # The run's HTTP transport, when the configured provider allowed one. Held
    # so cancelling can close it and break a model call already in flight; see
    # `abort_http`.
    http_client: Any = None

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _loop: asyncio.AbstractEventLoop | None = field(default=None, repr=False)
    _wakeup: asyncio.Event | None = field(default=None, repr=False)
    # Events not yet written to events.jsonl. Drained by the flusher task.
    _unflushed: list[Event] = field(default_factory=list, repr=False)

    # ── producer side (worker thread) ────────────────────────────────────────

    def attach_loop(self, loop: asyncio.AbstractEventLoop, wakeup: asyncio.Event) -> None:
        self._loop = loop
        self._wakeup = wakeup

    def append(self, kind: str, payload: dict) -> Event:
        with self._lock:
            event = Event(
                seq=len(self.events) + 1,
                kind=kind,
                ts=datetime.now(timezone.utc).isoformat(),
                payload=payload,
            )
            self.events.append(event)
            self._unflushed.append(event)
        self._notify()
        return event

    def add_context(self, payload: dict) -> None:
        """Record one agent's context, replacing the last snapshot of it.

        A loop publishes after every turn now, so the same conversation arrives
        many times, each one longer than the last. Appending would make the tab
        a list of prefixes of itself.

        The payload already holds copies (``loop.serialize_messages``), which
        matters: the live transcript is appended to, trimmed, and rewritten in
        place by the single arm's compaction, so holding the harness's own
        lists would be reading state that changes underneath.
        """
        # `id` comes from the harness (core.memory.new_agent_run_id) so this side
        # never has to know what a context's identity is made of.
        key = str(payload.get("id") or "")
        with self._lock:
            position = self.context_index.get(key)
            if position is None:
                self.context_index[key] = len(self.contexts)
                self.contexts.append(payload)
            else:
                self.contexts[position] = payload
            self.contexts_rev += 1
        # Deliberately no `_notify()`. A context is republished after EVERY
        # turn, and waking the stream that often drains it far ahead of the
        # events.jsonl flusher — which turned a rare disk-replay race into a
        # reliable one. The frame rides out with the next event's wakeup or the
        # heartbeat, and there is always one close behind: `llm_started` and
        # `llm_finished` bracket every model call, which is what the turns are.

    def set_violations(self, findings: list[dict]) -> None:
        """Replace the ledger. Like `add_context`, deliberately WITHOUT a
        `_notify()`: the frame rides the next event's wakeup, and waking the
        stream on its own drains it ahead of the events.jsonl flusher."""
        with self._lock:
            self.violations = list(findings)
            self.violations_rev += 1

    def contexts_light(self) -> list[dict]:
        """The contexts without their transcripts.

        What the live stream carries. The rows are what the tab's LIST shows —
        who is speaking, in which phase, how much of the window they are using
        — and they are small enough to push on every turn. The transcript is
        the large half and is fetched when a row is opened, so watching a run
        costs one small frame per turn instead of every transcript re-sent."""
        heavy = ("messages", "tools")
        with self._lock:
            return [
                {**{k: v for k, v in context.items() if k not in heavy},
                 "turns": len(context.get("messages") or [])}
                for context in self.contexts
            ]

    def set_graph(self, full_payload: dict, light_payload: dict) -> None:
        full = json.dumps(full_payload, ensure_ascii=False)
        light = json.dumps(light_payload, ensure_ascii=False)
        with self._lock:
            self.graph_full_json = full
            self.graph_light_json = light
            self.graph_rev += 1
        self._notify()

    def abort_http(self) -> bool:
        """Close the run's transport, aborting any model call in flight.

        The only lever available: ``invoke`` blocks its thread and Python cannot
        interrupt a thread inside a socket read, so the call has to be broken
        from underneath. Returns whether there was a transport to close — with
        a provider that would not accept one, cancellation falls back to landing
        at the harness's next event.
        """
        client = self.http_client
        if client is None:
            return False
        try:
            client.close()
        except Exception:  # noqa: BLE001 - a failed close must not block cancelling
            return False
        return True

    def release_http(self) -> None:
        """Close the transport at the end of a run, so sockets are not leaked."""
        client, self.http_client = self.http_client, None
        if client is None:
            return
        try:
            client.close()
        except Exception:  # noqa: BLE001
            pass

    def finish(self, status: str, error: str = "", stats: dict | None = None) -> None:
        with self._lock:
            self.status = status
            self.error = error
            if stats:
                self.stats = stats
        kind = {
            RunStatus.SUCCEEDED: EventKind.RUN_FINISHED,
            RunStatus.CANCELLED: EventKind.RUN_CANCELLED,
        }.get(status, EventKind.RUN_FAILED)
        self.append(kind, {"status": status, "error": error, "stats": self.stats})

    def _notify(self) -> None:
        """Wake any SSE reader. Called from the worker thread, so it must not
        block and must survive the loop already being gone at shutdown."""
        loop, wakeup = self._loop, self._wakeup
        if loop is None or wakeup is None:
            return
        try:
            loop.call_soon_threadsafe(wakeup.set)
        except RuntimeError:
            pass  # loop closed; nothing is listening anyway

    # ── consumer side (event loop) ───────────────────────────────────────────

    def events_after(self, seq: int) -> list[Event]:
        with self._lock:
            return [e for e in self.events if e.seq > seq]

    def snapshot_graph(self, view: str = "light") -> str:
        with self._lock:
            return self.graph_full_json if view == "full" else self.graph_light_json

    def node_data(self, node_id: str) -> dict | None:
        """Full `data` payload for one graph node, from the cached dump.

        The section nodes carry an entire ADDIE section here, which is why the
        UI fetches this on click rather than shipping it with every snapshot.
        """
        with self._lock:
            raw = self.graph_full_json
        if not raw:
            return None
        for node in json.loads(raw).get("nodes", []):
            if node.get("id") == node_id:
                return node
        return None

    def drain_unflushed(self) -> list[Event]:
        with self._lock:
            pending, self._unflushed = self._unflushed, []
            return pending

    @property
    def is_terminal(self) -> bool:
        return self.status in RunStatus.TERMINAL

    def public_stats(self) -> dict:
        with self._lock:
            return {**self.stats, "event_count": len(self.events), "graph_rev": self.graph_rev}


class RunRegistry:
    """Every run this process knows about, live or recently finished.

    Finished runs stay so a viewer who reconnects right after completion still
    gets the tail from memory rather than falling back to disk.
    """

    def __init__(self) -> None:
        self._runs: dict[str, RunState] = {}
        self._lock = threading.Lock()

    def create(self, run_id: str, program_id: str) -> RunState:
        state = RunState(run_id=run_id, program_id=program_id)
        with self._lock:
            self._runs[run_id] = state
        return state

    def get(self, run_id: str) -> RunState | None:
        with self._lock:
            return self._runs.get(run_id)

    def active_for_program(self, program_id: str) -> RunState | None:
        with self._lock:
            for state in self._runs.values():
                if state.program_id == program_id and not state.is_terminal:
                    return state
        return None

    def active(self) -> list[RunState]:
        with self._lock:
            return [s for s in self._runs.values() if not s.is_terminal]

    def all(self) -> list[RunState]:
        with self._lock:
            return list(self._runs.values())
