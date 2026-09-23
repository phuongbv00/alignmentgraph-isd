"""SQLite engine and session plumbing."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import event, inspect, text
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
    engine = get_engine(settings)
    SQLModel.metadata.create_all(engine)
    _add_missing_columns(engine)


def _add_missing_columns(engine) -> None:
    """Add columns a model declares that an existing table does not have.

    ``create_all`` creates a missing TABLE and never a missing COLUMN, so every
    field added to a model after someone's database exists is invisible to
    SQLAlchemy's DDL and fatal to its SELECT: the query names the column and
    SQLite answers ``no such column``. MEASURED: adding one boolean to
    ``LLMConnection`` took every connection endpoint down with a 500 until the
    file was deleted.

    ADDITIVE ONLY, which is what makes this safe without a migration tool. It
    adds; it never drops, renames, retypes or reorders, so it cannot destroy a
    column whose model has moved on — a table that has fields this code does
    not know about keeps them. A column that can be neither NULL nor defaulted
    is skipped rather than guessed at: SQLite cannot add one to a populated
    table, and inventing a value would be writing data.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    models = {mapper.local_table.name: mapper.class_
              for mapper in SQLModel._sa_registry.mappers if mapper.local_table is not None}
    for table in SQLModel.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue        # create_all just made it, with every column
        have = {column["name"] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in have or column.primary_key:
                continue
            default = _literal_default(column, models.get(table.name))
            if default is None and not column.nullable:
                continue
            kind = column.type.compile(engine.dialect)
            clause = f"{column.name} {kind}"
            if default is not None:
                clause += f" DEFAULT {default}"
                if not column.nullable:
                    clause += " NOT NULL"
            with engine.begin() as connection:
                connection.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {clause}"))


def _literal_default(column, model=None) -> str | None:
    """The column's default as SQL text, or None when it has none.

    Read from the MODEL FIELD when the column carries no SQL default, which is
    the normal case here: a SQLModel field's ``= False`` is a Pydantic default
    applied when an object is built, and never reaches the DDL. Without this
    the one shape that matters — a new non-nullable column with a default —
    looks to SQLAlchemy exactly like one that can neither be null nor filled,
    and is skipped.

    Only a plain Python scalar: a callable default (``default_factory``) is the
    application's to run per row and has no meaning as a table default.
    """
    default = getattr(column.default, "arg", None) if column.default is not None else None
    if default is None and model is not None:
        field = getattr(model, "model_fields", {}).get(column.name)
        default = getattr(field, "default", None) if field is not None else None
        if default is not None and type(default).__name__ == "PydanticUndefinedType":
            default = None
    if default is None or callable(default):
        return None
    if isinstance(default, bool):
        return "1" if default else "0"
    if isinstance(default, (int, float)):
        return str(default)
    return "'" + str(default).replace("'", "''") + "'"


def get_session() -> Iterator[DBSession]:
    with DBSession(get_engine()) as session:
        yield session


def session_scope() -> DBSession:
    """A session for code outside the request cycle (startup, worker threads)."""
    return DBSession(get_engine())
