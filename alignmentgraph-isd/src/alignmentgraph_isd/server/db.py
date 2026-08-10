"""SQLite engine and session plumbing."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import event
from sqlmodel import Session as DBSession
from sqlmodel import SQLModel, create_engine

from .settings import Settings, get_settings

_engine = None


def get_engine(settings: Settings | None = None):
    global _engine
    if _engine is not None:
        return _engine
    settings = settings or get_settings()
    settings.data_root.mkdir(parents=True, exist_ok=True)
    _engine = create_engine(
        settings.resolved_db_url,
        # Runs execute on worker threads; the request that started one may be
        # served by a different thread than the one that finishes it.
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(_engine, "connect")
    def _set_pragmas(dbapi_connection, _record):
        # WAL so a long-lived read (an open SSE stream that also queries) does
        # not block the writer finishing a run.
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return _engine


def reset_engine() -> None:
    """Drop the cached engine. Tests point the settings at a tmp dir per case."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def init_db(settings: Settings | None = None) -> None:
    SQLModel.metadata.create_all(get_engine(settings))


def get_session() -> Iterator[DBSession]:
    with DBSession(get_engine()) as session:
        yield session


def session_scope() -> DBSession:
    """A session for code outside the request cycle (startup, worker threads)."""
    return DBSession(get_engine())
