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


class LLMSettingsOut(BaseModel):
    """What the browser is told about the model configuration.

    Never the API key itself — only whether one is set. It is stored in clear
    text in the local database and there is no reason to move it further.
    """

    model_name: str = ""
    api_spec: str = "openai_compatible"
    base_url: str = ""
    has_api_key: bool = False
    temperature: float | None = None
    max_tokens: int | None = None
    # database | environment | none — so the UI can say why a value it did not
    # set is in effect.
    source: str = "none"
    error: str = ""


class LLMSettingsIn(BaseModel):
    model_name: str = Field(min_length=1, max_length=200)
    api_spec: str = Field(default="openai_compatible", pattern="^(openai|openai_compatible|anthropic)$")
    base_url: str = Field(default="", max_length=500)
    # Omitted keeps the stored key; an empty string clears it. The browser is
    # never sent the key, so it cannot echo one back.
    api_key: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=200_000)


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
    graph_available: bool = False


class GraphNode(BaseModel):
    id: str
    type: str = ""
    data: dict[str, Any] = {}
