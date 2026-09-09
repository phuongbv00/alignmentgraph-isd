"""Request and response bodies.

Separate from ``models.py``: those are rows, these are the wire contract. The
brief itself travels as a plain ``dict`` rather than a typed model — it is a
``DesignBrief`` dump and re-declaring its shape here would give two definitions
that could drift.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    llm_configured: bool
    model_name: str = ""
    # Why the model is unusable, when it is. Shown verbatim in the UI banner:
    # "no model configured" and "the endpoint rejected the credentials" need
    # very different fixes.
    model_error: str = ""
    active_runs: int = 0
    max_concurrent_runs: int = 0


class LLMConnectionOut(BaseModel):
    """What the browser is told about one connection.

    Never the API key itself — only whether one is set. It is stored in clear
    text in the local database and there is no reason to move it further.
    """

    id: str
    name: str = ""
    base_url: str = ""
    has_api_key: bool = False
    model_name: str = ""
    temperature: float | None = None
    max_tokens: int | None = None
    context_window: int | None = None
    disable_thinking: bool = False
    is_active: bool = False
    updated_at: datetime | None = None


class LLMConnectionsOut(BaseModel):
    """The whole picture, returned by every connection endpoint.

    One shape for read and write so the UI has a single source of state rather
    than patching a list from per-row responses.
    """

    connections: list[LLMConnectionOut] = []
    active_id: str = ""
    # Why the active connection is unusable, when it is.
    error: str = ""


class LLMConnectionIn(BaseModel):
    name: str = Field(default="", max_length=100)
    base_url: str = Field(default="", max_length=500)
    # Omitted keeps the stored key; an empty string clears it. The browser is
    # never sent the key, so it cannot echo one back.
    api_key: str | None = None
    # Allowed to be empty: a connection is saved first, and only then can its
    # /models list be read to pick one.
    model_name: str = Field(default="", max_length=200)
    temperature: float | None = Field(default=None, ge=0, le=2)
    # The completion cap, which doubles as the transcript budget's reserve.
    max_tokens: int | None = Field(default=None, ge=1, le=200_000)
    # The window the endpoint serves. Every one of these is nullable and a null
    # that is actually SENT clears the stored value; only `api_key` is kept when
    # omitted, because the browser is never given it to send back.
    context_window: int | None = Field(default=None, ge=256, le=10_000_000)
    disable_thinking: bool = False


class ModelListOut(BaseModel):
    models: list[str] = []
    # Why the list is empty, when it is. Reported, not raised.
    error: str = ""


class ProgramCreate(BaseModel):
    title: str = Field(default="", max_length=200)


class ProgramUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class RunSummary(BaseModel):
    id: str
    status: str
    error: str = ""
    model_name: str = ""
    stats: dict[str, Any] = {}
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ProgramSummary(BaseModel):
    id: str
    title: str
    source: str
    created_at: datetime
    updated_at: datetime
    # Set when the brief was settled — on import, or when the designer commits
    # one built through the conversation. Cleared again if a later turn changes
    # it, so "committed" always describes the brief as it stands.
    brief_committed_at: datetime | None = None
    brief_preview: dict[str, Any] = {}
    latest_run: RunSummary | None = None


class MessageOut(BaseModel):
    id: int | None = None
    seq: int
    role: str
    content: str
    payload: dict[str, Any] = {}
    created_at: datetime | None = None


class ProgramDetail(BaseModel):
    program: ProgramSummary
    brief: dict[str, Any] = {}
    brief_preview: dict[str, Any] = {}
    messages: list[MessageOut] = []
    missing_fields: list[str] = []
    runs: list[RunSummary] = []


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


class PlanTurnResponse(BaseModel):
    user_message: MessageOut
    assistant_message: MessageOut
    brief: dict[str, Any]
    brief_preview: dict[str, Any]
    missing_fields: list[str] = []
    ready: bool = False
    warnings: list[str] = []
    # Null once a turn has moved the brief: the conversation produces a draft
    # until the designer commits it.
    brief_committed_at: datetime | None = None


class BriefUpdate(BaseModel):
    brief: dict[str, Any]


class BriefResponse(BaseModel):
    brief: dict[str, Any]
    brief_preview: dict[str, Any]
    missing_fields: list[str] = []
    warnings: list[str] = []
    brief_committed_at: datetime | None = None


class RunCreated(BaseModel):
    run_id: str
    status: str


class RunDetail(BaseModel):
    run: RunSummary
    stats: dict[str, Any] = {}
    brief_preview: dict[str, Any] = {}


class GraphNode(BaseModel):
    id: str
    type: str = ""
    data: dict[str, Any] = {}
