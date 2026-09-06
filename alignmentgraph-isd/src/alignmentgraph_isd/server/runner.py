"""Executing harness runs off the event loop, and bridging their events.

The harness is synchronous and a real run takes minutes, so each one gets a
worker thread. The interesting part is the bridge in ``_make_consumer``, which
has three rules it must not break:

1. **Serialize on the worker thread.** ``to_full_dict`` hands back the live node
   and edge dicts, which later phases keep mutating. Holding the object and
   serializing it later in a request handler yields either a silently-changed
   "snapshot" or a dict-changed-size error mid-iteration.
2. **Never touch the database here.** A SQLAlchemy session is not thread-safe,
   and a run's progress must not depend on the database being reachable.
3. **Never block.** The consumer runs inside the agent's own tool loop; anything slow
   here slows the run itself.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from ..config import HarnessRunConfig
from ..core.brief import DesignBrief
from ..exceptions import HarnessCancelled
from . import artifacts, llm_settings
from .db import session_scope
from .events import EventKind, RunRegistry, RunState
from .models import Run, RunStatus
from .settings import Settings

logger = logging.getLogger(__name__)

# Harness event kinds forwarded to the browser as-is. Not an exhaustive mirror
# of what the harness emits: `graph_snapshot` is deliberately absent (the graph
# is carried as state, not replayed as events), and the five typed streams
# (`recovery_event`, `doc_write_event`, `reconcile_event`, `audit_event`,
# `dev_plan_event`) are absent because each of their call sites ALSO calls
# `log_action`, so their payload already reaches the browser as `action`.
_FORWARDED = frozenset({
    EventKind.ACTION,
    EventKind.PHASE_STARTED, EventKind.PHASE_FINISHED,
    EventKind.LLM_STARTED, EventKind.LLM_FINISHED,
    EventKind.AGENT_STEP, EventKind.NODE_EDIT, EventKind.LLM_CALL,
    EventKind.VALIDATION, EventKind.CHECK, EventKind.REPAIR, EventKind.RETRIEVAL,
})


class RunManager:
    """Owns the worker pool, the live registry, and the events.jsonl flusher."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.registry = RunRegistry()
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, settings.max_concurrent_runs),
            thread_name_prefix="agisd-run",
        )
        self._loop: asyncio.AbstractEventLoop | None = None
        self._flusher: asyncio.Task | None = None
        self._wakeups: dict[str, asyncio.Event] = {}
        self._lock = threading.Lock()

    # ── lifecycle ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._flusher = asyncio.create_task(self._flush_loop())

    async def stop(self) -> None:
        if self._flusher is not None:
            self._flusher.cancel()
            try:
                await self._flusher
            except asyncio.CancelledError:
                pass
        self._flush_once()
        # Do not wait: a run blocked on a model endpoint would hold shutdown for
        # minutes. The startup sweep marks whatever was left as interrupted.
        self._executor.shutdown(wait=False, cancel_futures=True)

    def wakeup_for(self, run_id: str) -> asyncio.Event:
        with self._lock:
            event = self._wakeups.get(run_id)
            if event is None:
                event = asyncio.Event()
                self._wakeups[run_id] = event
            return event

    # ── starting a run ───────────────────────────────────────────────────────

    def has_capacity(self) -> bool:
        return len(self.registry.active()) < max(1, self.settings.max_concurrent_runs)

    def start_run(self, run: Run, brief: dict) -> RunState:
        # Checked before the run rather than left to fail inside it: a model
        # that cannot be constructed produces a run that "completes" in
        # milliseconds with an empty graph and the reason buried in per-agent
        # errors.
        error = llm_settings.probe()
        if error:
            raise RuntimeError(error)
        # One transport for the whole run, held here so cancelling can close it
        # and abort a model call already in flight. Without it, a cancel has to
        # wait out the rest of that call.
        http_client = llm_settings.new_http_client()
        config = llm_settings.resolve()
        factory = llm_settings.build_factory(config, http_client=http_client)
        if factory is None:
            raise RuntimeError("No model configured.")
        # Read with the factory, from the same connection, so a run's transcript
        # budget matches the client it is actually calling — and so editing the
        # connection mid-run cannot change either one under it.
        window = llm_settings.window_settings(config)

        state = self.registry.create(run.id, run.program_id)
        state.http_client = http_client
        if self._loop is not None:
            state.attach_loop(self._loop, self.wakeup_for(run.id))
        state.append(EventKind.RUN_STARTED, {"run_id": run.id, "program_id": run.program_id})

        directory = artifacts.resolve(self.settings, run.artifact_dir)
        directory.mkdir(parents=True, exist_ok=True)
        artifacts.write_json(directory / artifacts.ARTIFACT_FILES["brief"], brief)

        self._executor.submit(
            self._execute, run.id, run.program_id, run.artifact_dir, brief, factory, window)
        return state

    def request_cancel(self, run_id: str) -> bool:
        state = self.registry.get(run_id)
        if state is None or state.is_terminal:
            return False
        if state.cancel_requested:
            return True  # already asked; nothing more to say

        state.cancel_requested = True
        state.status = RunStatus.CANCELLING

        # Break the transport so a model call already in flight fails now rather
        # than running to completion. The harness catches the resulting
        # connection error, records it as a step, and that step is an emit point
        # — which is where HarnessCancelled is raised. So the run unwinds in
        # about a second instead of a minute.
        aborted = state.abort_http()

        state.append(EventKind.RUN_CANCELLING, {
            "status": RunStatus.CANCELLING,
            "note": (
                "Stopping now — the model call in progress was aborted."
                if aborted
                else "Stopping after the current model call finishes."
            ),
            "aborted_in_flight_call": aborted,
        })
        return True

    # ── worker thread ────────────────────────────────────────────────────────

    def _make_consumer(self, state: RunState):
        def consume(kind: str, payload: dict) -> None:
            if state.cancel_requested:
                # Cooperative: takes effect at the next event, so a run stops
                # within roughly one model call rather than instantly.
                raise HarnessCancelled()

            if kind == "context_snapshot":
                # State, not a forwarded event: a transcript is large and only
                # its finished form is worth reading. Handled here on the
                # worker thread for the same reason the graph is.
                state.add_context(payload)
                return

            if kind == "graph_snapshot":
                # Serialized here, on this thread, while the payload is still
                # the state it describes. See rule 1 in the module docstring.
                state.set_graph(payload, _light_graph(payload))
                return

            if kind in _FORWARDED:
                state.append(kind, payload)

        return consume

    def _execute(
        self, run_id: str, program_id: str, artifact_dir: str, brief: dict, factory, window: dict
    ) -> None:
        state = self.registry.get(run_id)
        if state is None:
            return

        directory = artifacts.resolve(self.settings, artifact_dir)
        design_brief = DesignBrief.model_validate(brief)
        config = HarnessRunConfig(llm_factory=factory, **window)

        started = datetime.now(timezone.utc)
        status, error, stats, result = RunStatus.SUCCEEDED, "", {}, None
        try:
            from ..core.runner import MetaAgent

            result = MetaAgent(config).run(
                design_brief, on_event=self._make_consumer(state))
            # Carried on the result so `write_result` persists it with the rest:
            # a context that only existed in memory would be gone the moment the
            # process restarted, and "what did this agent see" is the question
            # you come back to a finished run with.
            #
            # The HARNESS's own list wins when it has one (core.memory keeps
            # every transcript now, whether or not anyone was watching); the
            # live one collected off the event stream is what the page shows
            # while the run is still going, and is the fallback for a result
            # produced before ``core.memory`` existed.
            result["contexts"] = result.get("contexts") or list(state.contexts)
            # The ledger only exists at the end — a finding's outcome is not
            # known until the last look has settled it — so unlike the contexts
            # there is nothing to stream progressively.
            state.set_violations(result.get("violations") or [])
            stats = _stats_from_result(result)
            # The harness is built to survive a failing specialist, so it
            # completes even when every one of them failed — leaving an empty
            # graph and an empty ADDIE output under a "succeeded" label. That
            # reads as a working run that produced nothing, which is worse than
            # an error, so it is reported as the failure it is.
            barren = _barren_run_error(result)
            if barren:
                status, error = RunStatus.FAILED, barren
        except HarnessCancelled:
            status, error = RunStatus.CANCELLED, "Cancelled by request."
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI, not swallowed
            logger.exception("run %s failed", run_id)
            status, error = RunStatus.FAILED, f"{type(exc).__name__}: {exc}"
        finally:
            # However the run ended, the transport is done with. On a cancel it
            # is already closed; this is what keeps every other path from
            # leaking a connection pool per run.
            state.release_http()

        if result is not None:
            try:
                artifacts.write_result(directory, brief, result)
            except Exception as exc:  # noqa: BLE001
                logger.warning("could not write artifacts for run %s: %s", run_id, exc)

        finished = datetime.now(timezone.utc)
        stats["duration_seconds"] = (finished - started).total_seconds()
        if result is not None:
            state.model_name = (result.get("metadata", {}).get("llm") or {}).get("model_name", "")

        # Flush what the run produced BEFORE marking it terminal. `finish`
        # closes the live stream, so a reader that was following the run
        # returns at that instant — and anything still unflushed is not on disk
        # for the replay that a restart, or a second reader, falls back to. The
        # second flush writes the terminal event itself.
        self._flush_state(state, directory)
        state.finish(status, error, stats)
        self._flush_state(state, directory)
        self._persist_terminal(run_id, state, started, finished)

    def _persist_terminal(self, run_id: str, state: RunState, started, finished) -> None:
        """Write the outcome back to the database.

        Done here, after the run, rather than from the event consumer — see rule
        2. A database failure at this point loses bookkeeping, not the run.
        """
        try:
            with session_scope() as db:
                run = db.get(Run, run_id)
                if run is None:
                    return
                run.status = state.status
                run.error = state.error
                run.model_name = state.model_name
                run.stats_json = json.dumps(state.public_stats(), ensure_ascii=False)
                run.event_count = len(state.events)
                run.started_at = started
                run.finished_at = finished
                db.add(run)
                db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not persist run %s: %s", run_id, exc)

    # ── events.jsonl flusher ─────────────────────────────────────────────────

    async def _flush_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(1.0)
                self._flush_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("event flush failed: %s", exc)

    def _flush_once(self) -> None:
        for state in self.registry.all():
            directory = self.settings.programs_dir / state.program_id / "runs" / state.run_id
            self._flush_state(state, directory)

    def _flush_state(self, state: RunState, directory) -> None:
        pending = state.drain_unflushed()
        if not pending:
            return
        try:
            directory.mkdir(parents=True, exist_ok=True)
            with (directory / artifacts.EVENTS_FILE).open("a", encoding="utf-8") as handle:
                for event in pending:
                    handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        except Exception as exc:  # noqa: BLE001 - the run matters, the log does not
            logger.warning("could not append events for run %s: %s", state.run_id, exc)


def _light_graph(full: dict) -> dict:
    """The wire version of a graph dump: same shape, no per-node `data`.

    Cuts a snapshot from ~95 KB to ~35 KB. The dropped payloads are what
    ``GET /runs/{id}/nodes/{node_id}`` serves on click.
    """
    return {
        **full,
        "nodes": [{"id": n.get("id"), "type": str(n.get("type", ""))} for n in full.get("nodes", [])],
    }


def _barren_run_error(result: dict) -> str:
    """A message when a run finished having produced nothing, else empty.

    "Nothing" means no graph nodes and no model calls: the specialists all
    failed before writing anything. A run that produced *some* of the design is
    left alone — a partial result is still worth looking at, and the per-agent
    errors travel in the metadata either way.
    """
    graph = result.get("graph") or {}
    metadata = result.get("metadata") or {}
    if graph.get("nodes") or (metadata.get("token_usage") or {}).get("llm_calls"):
        return ""

    errors = metadata.get("errors") or []
    if not errors:
        return "The run produced no design output."

    # The same failure repeats once per specialist; the first one is the cause,
    # and it is prefixed with the agent name that is not worth repeating.
    first = str(errors[0])
    detail = first.partition(": ")[2] or first
    suffix = "" if len(errors) == 1 else f" (all {len(errors)} agent attempts failed the same way)"
    return f"No design output: every specialist failed. {detail}{suffix}"


def _stats_from_result(result: dict) -> dict:
    graph = result.get("graph") or {}
    trajectory = result.get("trajectory") or {}
    metadata = result.get("metadata") or {}
    alignment = graph.get("objective_alignment") or {}
    return {
        "node_count": len(graph.get("nodes") or []),
        "edge_count": len(graph.get("edges") or []),
        "objective_count": len(alignment),
        "aligned_objective_count": sum(1 for v in alignment.values() if v.get("aligned")),
        "llm_calls": (metadata.get("token_usage") or {}).get("llm_calls", 0),
        "token_usage": metadata.get("token_usage", {}),
        "agent_steps": len(trajectory.get("tool_calls") or []),
        "check_rounds": sum(1 for e in trajectory.get("events") or []
                            if e.get("action") == "check"),
        "repair_events": sum(1 for e in trajectory.get("events") or []
                             if e.get("action") == "repair"),
        "validation_errors": len(metadata.get("validation_errors") or []),
        "model_name": (metadata.get("llm") or {}).get("model_name", ""),
    }


__all__ = ["RunManager"]
