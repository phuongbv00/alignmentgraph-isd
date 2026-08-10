"""Starting, watching and reading runs."""
from __future__ import annotations

import json

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


@router.get("/runs/{run_id}/stats")
def get_stats(
    run_id: str,
    db: DBSession = Depends(get_session),
    manager: RunManager = Depends(get_manager),
) -> JSONResponse:
    run = load_run(db, run_id)
    state = manager.registry.get(run_id)
    return JSONResponse(state.public_stats() if state is not None else parse_json(run.stats_json))
