"""The FastAPI application.

Run it single-process. Live runs and their event buffers are in-process state,
so with two uvicorn workers half the SSE connections would land on the worker
that has never heard of the run. ``alignmentgraph-isd serve`` deliberately does
not expose a ``--workers`` flag.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import select

from . import llm_settings
from .db import init_db, session_scope
from .models import Run, RunStatus, utcnow
from .routers import planning, programs, runs, system
from .runner import RunManager
from .settings import Settings, get_settings

logger = logging.getLogger(__name__)


def sweep_interrupted_runs() -> int:
    """Reconcile runs the previous process was in the middle of.

    A run lives in a worker thread, so a restart kills it with no chance to
    record anything. Any row still claiming to be active at startup therefore
    belongs to a process that is gone; leaving it would block its program
    forever behind the one-active-run rule.
    """
    with session_scope() as db:
        stale = db.exec(select(Run).where(Run.status.in_(RunStatus.ACTIVE))).all()
        for run in stale:
            run.status = RunStatus.INTERRUPTED
            run.error = "Interrupted by a server restart."
            run.finished_at = run.finished_at or utcnow()
            db.add(run)
        if stale:
            db.commit()
            logger.info("marked %d interrupted run(s) from a previous process", len(stale))
        return len(stale)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings.data_root.mkdir(parents=True, exist_ok=True)
        init_db(settings)
        # Turns AGENT_MODEL_* into the first connection on an empty database,
        # so an existing shell setup still starts configured.
        llm_settings.seed_from_environment()
        sweep_interrupted_runs()
        manager = RunManager(settings)
        await manager.start()
        app.state.run_manager = manager
        app.state.settings = settings
        try:
            yield
        finally:
            await manager.stop()

    app = FastAPI(
        title="AlignmentGraph-ISD",
        description="Demo app for the AlignmentGraph-ISD instructional-design harness.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = settings

    # No CORS middleware and no GZip: in development Vite proxies /api here so
    # requests are same-origin, and GZip buffers text/event-stream, which would
    # turn the live run stream into a single delivery at the end.
    api_routers = [system.router, programs.router, planning.router, runs.router]
    for router in api_routers:
        app.include_router(router, prefix="/api")

    if settings.serve_spa:
        _mount_spa(app, settings)

    return app


def _mount_spa(app: FastAPI, settings: Settings) -> None:
    """Serve the built SPA, so a demo is one process on one URL.

    Mounted after the API routers: a mount at "/" matches everything, so
    ordering is what keeps /api reachable.
    """
    dist = settings.spa_dist
    index = dist / "index.html"
    if not index.exists():
        logger.warning(
            "AGISD_SERVER_SERVE_SPA is on but %s does not exist. "
            "Build it first: cd %s && npm install && npm run build",
            index,
            dist.parent,
        )
        return

    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        # Client-side routing: unknown paths render the app, except under /api,
        # where a miss is a genuine 404 and should say so as JSON.
        if full_path.startswith("api/"):
            return JSONResponse({"detail": "Not found."}, status_code=404)
        candidate = dist / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)


app = None


def get_app() -> FastAPI:
    """Lazy singleton for `uvicorn alignmentgraph_isd.server.app:get_app --factory`."""
    global app
    if app is None:
        app = create_app()
    return app
