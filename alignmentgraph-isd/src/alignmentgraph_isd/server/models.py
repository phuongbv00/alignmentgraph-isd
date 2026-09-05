"""Database tables.

Only small, queryable facts live here. The bulky per-run artifacts (the graph
dump alone is ~100 KB) are files on disk; a row stores the directory holding
them, relative to the configured data root.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RunStatus:
    RUNNING = "running"
    CANCELLING = "cancelling"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    # A run whose worker thread died with the process. Set by the startup sweep,
    # never by the run itself — by definition nothing was left to set it.
    INTERRUPTED = "interrupted"

    ACTIVE = (RUNNING, CANCELLING)
    TERMINAL = (SUCCEEDED, FAILED, CANCELLED, INTERRUPTED)


class Program(SQLModel, table=True):
    """A training program: one design brief and the runs made from it."""

    id: str = Field(default_factory=new_id, primary_key=True)
    title: str = Field(default="Untitled program", index=True)
    source: str = "freeform"  # freeform | import
    brief_json: str = "{}"
    brief_committed_at: datetime | None = None
    latest_run_id: str | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Session(SQLModel, table=True):
    """A working session within a program.

    Every program has exactly one today, created with it. The table exists so
    that the messages and runs of a program are already grouped by session, and
    a later feature can add a second one without a migration.
    """

    id: str = Field(default_factory=new_id, primary_key=True)
    program_id: str = Field(foreign_key="program.id", index=True)
    index: int = 0
    kind: str = "initial"
    created_at: datetime = Field(default_factory=utcnow)


class Message(SQLModel, table=True):
    """One turn of the planning conversation."""

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="session.id", index=True)
    seq: int = 0
    role: str = "user"  # user | assistant
    content: str = ""
    # The assistant's structured side-channel: brief_patch, missing_fields,
    # ready, warnings. Kept out of `content`, which is what the UI renders.
    payload_json: str = "{}"
    created_at: datetime = Field(default_factory=utcnow)


class LLMConnection(SQLModel, table=True):
    """One endpoint the app can talk to, and the model picked on it.

    A list rather than a single setting: switching between a local Ollama and a
    served pod is choosing a row, not retyping a base URL and a key. Exactly one
    row carries ``is_active`` — that is the connection a run and the planner use.

    The model belongs to the connection because it only means anything there:
    an id from one endpoint's ``/v1/models`` is not offered by another, so a
    connection remembers its own model, temperature and token cap.

    OpenAI-compatible only. There is no ``api_spec``; the core factory still
    speaks Anthropic for the CLI and the benchmark, the app does not.

    The API key is held in clear text in the local SQLite file. That is a
    deliberate limit of a local demo tool — it is never returned to the browser
    (only whether one is set), and the UI says where it lives.
    """

    id: str = Field(default_factory=new_id, primary_key=True)
    name: str = ""
    base_url: str = ""  # empty falls back to the OpenAI default in the client
    api_key: str = ""
    model_name: str = ""  # empty until one is picked from the endpoint's list
    temperature: float | None = None
    max_tokens: int | None = None
    is_active: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Run(SQLModel, table=True):
    """One execution of the harness over a program's brief."""

    id: str = Field(default_factory=new_id, primary_key=True)
    program_id: str = Field(foreign_key="program.id", index=True)
    session_id: str = Field(foreign_key="session.id", index=True)
    status: str = Field(default=RunStatus.RUNNING, index=True)
    artifact_dir: str = ""  # relative to settings.data_root
    model_name: str = ""
    error: str = ""
    stats_json: str = "{}"
    event_count: int = 0
    created_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None
