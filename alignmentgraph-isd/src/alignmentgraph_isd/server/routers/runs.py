"""Starting, watching and reading runs."""
from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlmodel import Session as DBSession

from .. import artifacts, briefs, sse
from ..db import get_session
from ..models import Run, RunStatus, utcnow
from ..runner import RunManager
from ..schemas import GraphNode, RunCreated, RunDetail
from ..settings import Settings
from .deps import (
    get_app_settings,
    get_manager,
    guard_no_active_run,
    load_brief,
    load_program,
    load_run,
    parse_json,
    primary_session,
    run_summary,
)

router = APIRouter(tags=["runs"])


@router.post(
    "/programs/{program_id}/runs",
    response_model=RunCreated,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_run(
    program_id: str,
    db: DBSession = Depends(get_session),
    manager: RunManager = Depends(get_manager),
) -> RunCreated:
    program = load_program(db, program_id)
    guard_no_active_run(manager, db, program_id)

    brief = load_brief(program)
    if not briefs.is_runnable(brief):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "The design brief is empty. Describe the program in the chat or import a scenario file first.",
        )
    if not manager.has_capacity():
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"All {manager.settings.max_concurrent_runs} run slots are busy. Try again when one finishes.",
        )

    session = primary_session(db, program_id)
    run = Run(program_id=program_id, session_id=session.id, status=RunStatus.RUNNING)
    run.artifact_dir = artifacts.relative_run_dir(program_id, run.id)
    run.started_at = utcnow()
    db.add(run)

    program.latest_run_id = run.id
    program.updated_at = utcnow()
    db.add(program)
    db.commit()
    db.refresh(run)

    try:
        manager.start_run(run, brief)
    except RuntimeError as exc:
        run.status = RunStatus.FAILED
        run.error = str(exc)
        run.finished_at = utcnow()
        db.add(run)
        db.commit()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    return RunCreated(run_id=run.id, status=run.status)


@router.get("/runs/{run_id}", response_model=RunDetail)
def get_run(
    run_id: str,
    db: DBSession = Depends(get_session),
    manager: RunManager = Depends(get_manager),
    settings: Settings = Depends(get_app_settings),
) -> RunDetail:
    run = load_run(db, run_id)
    program = load_program(db, run.program_id)
    state = manager.registry.get(run_id)
    graph_available = bool(
        (state is not None and state.graph_rev)
        or (artifacts.resolve(settings, run.artifact_dir) / artifacts.ARTIFACT_FILES["graph"]).exists()
    )
    summary = run_summary(run, manager)
    return RunDetail(
        run=summary,
        stats=summary.stats,
        brief_preview=briefs.preview(load_brief(program)),
        graph_available=graph_available,
    )


@router.post("/runs/{run_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
def cancel_run(
    run_id: str,
    db: DBSession = Depends(get_session),
    manager: RunManager = Depends(get_manager),
) -> dict:
    run = load_run(db, run_id)
    if not manager.request_cancel(run_id):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Run is already {run.status}.")
    # Cancellation is cooperative — it lands at the harness's next event, so an
    # in-flight model call has to return first.
    return {"status": RunStatus.CANCELLING}


@router.get("/runs/{run_id}/events")
async def stream_events(
    run_id: str,
    request: Request,
    after: int = 0,
    db: DBSession = Depends(get_session),
    manager: RunManager = Depends(get_manager),
    settings: Settings = Depends(get_app_settings),
):
    run = load_run(db, run_id)
    cursor = sse.resume_cursor(request, after)

    state = manager.registry.get(run_id)
    if state is not None:
        wakeup = manager.wakeup_for(run_id)
        return sse.stream_response(sse.live_stream(request, state, wakeup, cursor))

    # Not in memory: a finished run from an earlier process. Replay from disk.
    directory = artifacts.resolve(settings, run.artifact_dir)
    events = artifacts.read_events(directory, after=cursor)
    summary = run_summary(run)
    status_payload = {
        "run_id": run.id,
        "program_id": run.program_id,
        "status": summary.status,
        "error": summary.error,
        "model_name": summary.model_name,
        "stats": summary.stats,
        "graph_rev": 0,
        "replay": True,
    }
    return sse.stream_response(sse.replay_stream(events, status_payload))


@router.get("/runs/{run_id}/graph")
def get_graph(
    run_id: str,
    view: str = "light",
    db: DBSession = Depends(get_session),
    manager: RunManager = Depends(get_manager),
    settings: Settings = Depends(get_app_settings),
) -> Response:
    run = load_run(db, run_id)
    state = manager.registry.get(run_id)
    if state is not None and state.graph_rev:
        # Always the cached string. The live AlignmentGraph belongs to the worker
        # thread and must never be read from here.
        return Response(state.snapshot_graph(view), media_type="application/json")

    path = artifacts.resolve(settings, run.artifact_dir) / artifacts.ARTIFACT_FILES["graph"]
    if not path.exists():
        raise HTTPException(status.HTTP_409_CONFLICT, "This run has not produced a graph yet.")
    return Response(path.read_text(encoding="utf-8"), media_type="application/json")


@router.get("/runs/{run_id}/nodes/{node_id:path}", response_model=GraphNode)
def get_graph_node(
    run_id: str,
    node_id: str,
    db: DBSession = Depends(get_session),
    manager: RunManager = Depends(get_manager),
    settings: Settings = Depends(get_app_settings),
) -> GraphNode:
    """One node's full payload, fetched on click.

    A section node such as `objective_0` carries an entire ADDIE section here,
    which is exactly why it is not shipped with every graph frame.
    """
    run = load_run(db, run_id)
    state = manager.registry.get(run_id)

    node = state.node_data(node_id) if state is not None else None
    if node is None:
        path = artifacts.resolve(settings, run.artifact_dir) / artifacts.ARTIFACT_FILES["graph"]
        if path.exists():
            graph = json.loads(path.read_text(encoding="utf-8"))
            node = next((n for n in graph.get("nodes", []) if n.get("id") == node_id), None)
    if node is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Node not found in this run's graph.")

    return GraphNode(id=node.get("id", ""), type=str(node.get("type", "")), data=node.get("data") or {})


@router.get("/runs/{run_id}/artifacts/{name}")
def get_artifact(
    run_id: str,
    name: str,
    db: DBSession = Depends(get_session),
    manager: RunManager = Depends(get_manager),
    settings: Settings = Depends(get_app_settings),
) -> Response:
    run = load_run(db, run_id)
    filename = artifacts.ARTIFACT_FILES.get(name)
    if filename is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Unknown artifact '{name}'. One of: {', '.join(sorted(artifacts.ARTIFACT_FILES))}.",
        )

    path = artifacts.resolve(settings, run.artifact_dir) / filename
    if not path.exists():
        state = manager.registry.get(run_id)
        if state is not None and not state.is_terminal:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "The run is still going; artifacts are written when it ends."
            )
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No {name} for this run.")

    text = path.read_text(encoding="utf-8")
    if name == "graph_dot":
        return PlainTextResponse(text)
    return Response(text, media_type="application/json")


@router.get("/runs/{run_id}/trajectory/export")
def export_trajectory(
    run_id: str,
    db: DBSession = Depends(get_session),
    manager: RunManager = Depends(get_manager),
    settings: Settings = Depends(get_app_settings),
) -> Response:
    """The run's TRAJECTORY as a downloadable file — and nothing else.

    Deliberately not a bundle. Metadata, the graph and the ADDIE output are
    each their own artifact with their own endpoint, and folding them in here
    would make "export trajectory" mean "export the run", so nobody could
    export the trajectory. Two files under one name is how an export format
    stops being one.

    Both halves of the trajectory travel: ``trajectory`` is the judge-visible
    trio plus the structured event log, ``trajectory_deep`` the full-fidelity
    action log. They are one record split for size, not two artifacts.

    A run still in flight exports what has been RECORDED so far, from the live
    event log, and says so. That is the moment the trace is most wanted — a run
    that looks stuck is one you want to read now — and labelling it
    ``complete: false`` costs nothing, where silently returning a partial file
    under the same shape as a finished one would be a trap.
    """
    run = load_run(db, run_id)
    directory = artifacts.resolve(settings, run.artifact_dir)

    if artifacts.has_trajectory(directory):
        payload = {
            "export_version": 1,
            "complete": True,
            "run_id": run.id,
            "trajectory": artifacts.read_json(
                directory / artifacts.ARTIFACT_FILES["trajectory"]) or {},
            "trajectory_deep": artifacts.read_json(
                directory / artifacts.ARTIFACT_FILES["trajectory_deep"]) or {},
        }
        stem = "trajectory"
    else:
        state = manager.registry.get(run_id)
        live = ([event.to_dict() for event in state.events] if state is not None
                else artifacts.read_events(directory))
        if not live:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                "This run recorded no trajectory. It failed before the harness "
                "produced one, or its artifacts were deleted.",
            )
        # NOT under the "trajectory" key: these are wire events from the live
        # stream, a different shape from the recorded trajectory, and giving
        # them that name would let a reader parse the file as if the run had
        # finished.
        payload = {
            "export_version": 1,
            "complete": False,
            "run_id": run.id,
            "live_events": live,
        }
        stem = "trajectory-partial"

    return Response(
        json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{stem}-{run.id}.json"'},
    )


@router.get("/runs/{run_id}/violations")
def get_violations(
    run_id: str,
    db: DBSession = Depends(get_session),
    manager: RunManager = Depends(get_manager),
    settings: Settings = Depends(get_app_settings),
) -> JSONResponse:
    """Every distinct finding of the run, and what became of it.

    Not the same thing as ``metadata.audit.violations``: that is the graph
    arm's residual only (the prose arm has no graph to audit), it is a snapshot
    rather than a history, and it cannot say whether a finding was repaired,
    proved unfixable, or simply ran out of budget.

    Live state first, then the persisted file — the same fallback
    ``get_contexts`` uses, for the same reason.
    """
    state = manager.registry.get(run_id)
    if state is not None and state.violations:
        return JSONResponse(list(state.violations))
    directory = artifacts.resolve(settings, load_run(db, run_id).artifact_dir)
    return JSONResponse(
        artifacts.read_json(directory / artifacts.ARTIFACT_FILES["violations"]) or [])


@router.get("/runs/{run_id}/contexts")
def get_contexts(
    run_id: str,
    context: str | None = None,
    db: DBSession = Depends(get_session),
    manager: RunManager = Depends(get_manager),
    settings: Settings = Depends(get_app_settings),
) -> JSONResponse:
    """Every agent's context: system turn, transcript, bound tool schemas.

    Live state first, then the persisted file: during a run the registry has
    the snapshots the harness has published so far, and after a restart only
    the file remains.
    """
    rows = _contexts_of(run_id, db, manager, settings)
    if context is not None:
        # ONE context, whole. What the app asks for when a reader opens a row:
        # the live stream carries the rows without their transcripts or tool
        # schemas (they are the large half and a context is republished after
        # every turn), so opening a row is where those are fetched — and
        # re-fetched as it grows, which is what makes the OPEN row live.
        rows = [row for row in rows if str(row.get("id") or "") == context]
    return JSONResponse(rows)


def _contexts_of(run_id: str, db, manager: RunManager, settings: Settings) -> list[dict]:
    """Live state first, then the persisted file: during a run the registry has
    the snapshots published so far, and after a restart only the file remains."""
    run = load_run(db, run_id)
    state = manager.registry.get(run_id)
    if state is not None and state.contexts:
        return list(state.contexts)
    directory = artifacts.resolve(settings, run.artifact_dir)
    return artifacts.read_json(directory / artifacts.ARTIFACT_FILES["contexts"]) or []


@router.get("/runs/{run_id}/transcript/export")
def export_transcript(
    run_id: str,
    context: str | None = None,
    db: DBSession = Depends(get_session),
    manager: RunManager = Depends(get_manager),
    settings: Settings = Depends(get_app_settings),
) -> Response:
    """One agent's transcript, or the whole run's, as readable Markdown.

    Markdown rather than JSON because ``/contexts`` already serves the JSON a
    tool would want, and this is the artifact a PERSON reads end to end: the
    system turn, every message in order, and the tool schemas that were bound
    alongside them.

    ``context`` picks one out of the list by its id (``core.memory.context_id``)
    — not by label, because labels repeat: a regenerated stage publishes one
    context per attempt and they share a name. Nor by position, which was the
    first answer here and is only stable while the list is: a context is
    republished after every turn now, and a link a reader kept would follow the
    ordinal rather than the conversation it was for.
    """
    contexts = _contexts_of(run_id, db, manager, settings)
    if not contexts:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "This run published no agent context. It failed before any agent "
            "finished, or its artifacts were deleted.",
        )

    stem = "transcript"
    if context is not None:
        found = [row for row in contexts if str(row.get("id") or "") == context]
        if not found:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                f"No context {context!r} in this run; it has {len(contexts)}.",
            )
        contexts = found[:1]
        # The FILENAME is still the readable half — the id identifies, the
        # label is what a reader recognises in a downloads folder.
        stem = "transcript-" + re.sub(r"[^A-Za-z0-9._-]+", "-",
                                      str(contexts[0].get("label") or context))

    return Response(
        artifacts.render_transcript(contexts),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{stem}-{run_id}.md"'},
    )


@router.get("/runs/{run_id}/stats")
def get_stats(
    run_id: str,
    db: DBSession = Depends(get_session),
    manager: RunManager = Depends(get_manager),
) -> JSONResponse:
    run = load_run(db, run_id)
    state = manager.registry.get(run_id)
    return JSONResponse(state.public_stats() if state is not None else parse_json(run.stats_json))
