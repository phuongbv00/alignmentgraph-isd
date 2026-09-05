"""Server status and model connections."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session as DBSession

from .. import llm_settings, planner
from ..db import get_session
from ..models import LLMConnection
from ..runner import RunManager
from ..schemas import (
    HealthResponse,
    LLMConnectionIn,
    LLMConnectionOut,
    LLMConnectionsOut,
    ModelListOut,
)
from ..settings import Settings
from .deps import get_app_settings, get_manager

router = APIRouter(tags=["system"])

_RUN_IN_PROGRESS = "A run is in progress. Wait for it to finish before changing the model."


@router.get("/health", response_model=HealthResponse)
def health(
    manager: RunManager = Depends(get_manager),
    settings: Settings = Depends(get_app_settings),
) -> HealthResponse:
    """Whether a run can be started at all.

    The UI disables the run button on `llm_configured: false` and explains why,
    rather than letting someone fill in a whole brief and only then find out
    there is no model behind it.
    """
    error = planner.configuration_error()
    return HealthResponse(
        llm_configured=not error,
        model_name=planner.model_name(),
        model_error=error,
        active_runs=len(manager.registry.active()),
        max_concurrent_runs=settings.max_concurrent_runs,
    )


def _out(row: LLMConnection) -> LLMConnectionOut:
    return LLMConnectionOut(
        id=row.id,
        name=row.name,
        base_url=row.base_url,
        has_api_key=bool(row.api_key),
        model_name=row.model_name,
        temperature=row.temperature,
        max_tokens=row.max_tokens,
        is_active=row.is_active,
        updated_at=row.updated_at,
    )


def _current(db: DBSession) -> LLMConnectionsOut:
    """The list, plus what is wrong with the active connection if anything."""
    rows = llm_settings.list_connections(db)
    active = next((row for row in rows if row.is_active), None)
    return LLMConnectionsOut(
        connections=[_out(row) for row in rows],
        active_id=active.id if active is not None else "",
        error=llm_settings.probe(),
    )


def _guard(manager: RunManager) -> None:
    if manager.registry.active():
        raise HTTPException(status.HTTP_409_CONFLICT, _RUN_IN_PROGRESS)


def _load(db: DBSession, connection_id: str) -> LLMConnection:
    row = llm_settings.get_connection(db, connection_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such connection.")
    return row


@router.get("/connections", response_model=LLMConnectionsOut)
def get_connections(db: DBSession = Depends(get_session)) -> LLMConnectionsOut:
    """Every configured connection, and which one a run would use."""
    return _current(db)


@router.post("/connections", response_model=LLMConnectionsOut, status_code=status.HTTP_201_CREATED)
def create_connection(
    payload: LLMConnectionIn,
    db: DBSession = Depends(get_session),
    manager: RunManager = Depends(get_manager),
) -> LLMConnectionsOut:
    """Add a connection. The first one becomes active."""
    _guard(manager)
    llm_settings.create(
        db,
        name=payload.name.strip(),
        base_url=payload.base_url.strip(),
        api_key=payload.api_key,
        model_name=payload.model_name.strip(),
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
    )
    return _current(db)


@router.put("/connections/{connection_id}", response_model=LLMConnectionsOut)
def update_connection(
    connection_id: str,
    payload: LLMConnectionIn,
    db: DBSession = Depends(get_session),
    manager: RunManager = Depends(get_manager),
) -> LLMConnectionsOut:
    """Store an edited connection.

    Saving always succeeds; the response carries the probe result so a bad
    endpoint or a missing key is reported here rather than discovered when a
    run collapses in milliseconds.
    """
    _guard(manager)
    _load(db, connection_id)
    llm_settings.update(
        db,
        connection_id,
        name=payload.name.strip(),
        base_url=payload.base_url.strip(),
        api_key=payload.api_key,
        model_name=payload.model_name.strip(),
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
    )
    return _current(db)


@router.post("/connections/{connection_id}/activate", response_model=LLMConnectionsOut)
def activate_connection(
    connection_id: str,
    db: DBSession = Depends(get_session),
    manager: RunManager = Depends(get_manager),
) -> LLMConnectionsOut:
    """Make this the connection runs and the planner use."""
    _guard(manager)
    _load(db, connection_id)
    llm_settings.activate(db, connection_id)
    return _current(db)


@router.delete("/connections/{connection_id}", response_model=LLMConnectionsOut)
def delete_connection(
    connection_id: str,
    db: DBSession = Depends(get_session),
    manager: RunManager = Depends(get_manager),
) -> LLMConnectionsOut:
    """Forget a connection. Deleting the active one hands active to what is left."""
    _guard(manager)
    _load(db, connection_id)
    llm_settings.delete(db, connection_id)
    return _current(db)


@router.get("/connections/{connection_id}/models", response_model=ModelListOut)
def get_connection_models(
    connection_id: str,
    db: DBSession = Depends(get_session),
) -> ModelListOut:
    """The models this endpoint offers, read with the stored credentials.

    The key stays on the server: it is looked up from the row rather than
    travelling with the request, which is why this is addressed by connection
    id and not by a base URL and key posted from the browser.
    """
    row = _load(db, connection_id)
    models, error = llm_settings.list_models(llm_settings.config_of(row))
    return ModelListOut(models=models, error=error)
