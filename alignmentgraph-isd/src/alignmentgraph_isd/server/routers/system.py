"""Server status and model configuration."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session as DBSession

from .. import llm_settings, planner
from ..db import get_session
from ..runner import RunManager
from ..schemas import HealthResponse, LLMSettingsIn, LLMSettingsOut
from ..settings import Settings
from .deps import get_app_settings, get_manager

router = APIRouter(tags=["system"])


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


def _current() -> LLMSettingsOut:
    config = llm_settings.resolve()
    return LLMSettingsOut(
        model_name=config.model_name,
        api_spec=config.api_spec,
        base_url=config.base_url,
        has_api_key=config.has_api_key,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        source=config.source,
        error=llm_settings.probe(config),
    )


@router.get("/settings/llm", response_model=LLMSettingsOut)
def get_llm_settings() -> LLMSettingsOut:
    """The model configuration in effect, and what is wrong with it if anything."""
    return _current()


@router.put("/settings/llm", response_model=LLMSettingsOut)
def put_llm_settings(
    payload: LLMSettingsIn,
    db: DBSession = Depends(get_session),
    manager: RunManager = Depends(get_manager),
) -> LLMSettingsOut:
    """Store the model configuration.

    Saving always succeeds; the response carries the probe result so a bad
    endpoint or a missing key is reported here rather than discovered when a
    run collapses in milliseconds.
    """
    if manager.registry.active():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "A run is in progress. Wait for it to finish before changing the model.",
        )

    llm_settings.save(
        db,
        model_name=payload.model_name.strip(),
        api_spec=payload.api_spec,
        base_url=payload.base_url.strip(),
        api_key=payload.api_key,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
    )
    return _current()


@router.delete("/settings/llm", response_model=LLMSettingsOut)
def delete_llm_settings(
    db: DBSession = Depends(get_session),
    manager: RunManager = Depends(get_manager),
) -> LLMSettingsOut:
    """Forget the stored configuration and fall back to `AGENT_MODEL_*`."""
    if manager.registry.active():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "A run is in progress. Wait for it to finish before changing the model.",
        )
    llm_settings.clear(db)
    return _current()
