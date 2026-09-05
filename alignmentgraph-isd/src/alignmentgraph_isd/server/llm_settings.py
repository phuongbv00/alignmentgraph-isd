"""Where the model configuration comes from.

A **list of connections** in the database, exactly one of them active. That one
is what a run and the planner resolve to; the rest sit there so switching
endpoint is a click rather than three fields retyped from memory.

``AGENT_MODEL_*`` — the same variables the CLI and the benchmark read — seeds
the first connection on an empty database (``seed_from_environment``). It is a
starting point, not a live fallback: once a row exists the database is the only
source, so what the UI shows is what a run will use.

Everything goes through ``llm_factory_from_env`` in the core package: it takes
explicit arguments that win over the environment, so the stored connection is
passed in rather than reimplementing client construction here. The app is
OpenAI-compatible only and says so by passing ``api_spec`` explicitly — leaving
it out would let ``AGENT_MODEL_API_SPEC`` reach in and change the client under a
connection the user configured here.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

from sqlmodel import Session as DBSession
from sqlmodel import select

from ..core.llm import llm_factory_from_env
from .db import session_scope
from .models import LLMConnection, utcnow

API_SPEC = "openai_compatible"
DEFAULT_BASE_URL = "https://api.openai.com/v1"

SOURCE_DATABASE = "database"
SOURCE_NONE = "none"


@dataclass
class ResolvedConfig:
    model_name: str = ""
    base_url: str = ""
    api_key: str = ""
    temperature: float | None = None
    max_tokens: int | None = None
    connection_id: str = ""
    name: str = ""
    source: str = SOURCE_NONE

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key)


def config_of(row: LLMConnection) -> ResolvedConfig:
    return ResolvedConfig(
        model_name=row.model_name,
        base_url=row.base_url,
        api_key=row.api_key,
        temperature=row.temperature,
        max_tokens=row.max_tokens,
        connection_id=row.id,
        name=row.name,
        source=SOURCE_DATABASE,
    )


def list_connections(db: DBSession) -> list[LLMConnection]:
    return list(db.exec(select(LLMConnection).order_by(LLMConnection.created_at)).all())


def get_connection(db: DBSession, connection_id: str) -> LLMConnection | None:
    return db.get(LLMConnection, connection_id)


def active_connection(db: DBSession) -> LLMConnection | None:
    return db.exec(select(LLMConnection).where(LLMConnection.is_active)).first()


def resolve() -> ResolvedConfig:
    """The configuration a run would use right now."""
    try:
        with session_scope() as db:
            row = active_connection(db)
            return config_of(row) if row is not None else ResolvedConfig()
    except Exception:  # noqa: BLE001 - a missing table must not break the app
        return ResolvedConfig()


def build_factory(config: ResolvedConfig | None = None, *, http_client=None):
    """A chat-model factory for the resolved configuration, or None.

    The values are captured now, so the factory a run holds cannot change under
    it if someone edits the settings mid-run.

    Pass ``http_client`` to keep a handle on the transport — see
    ``new_http_client`` for why a run wants one.
    """
    config = config or resolve()
    if not config.model_name:
        return None
    return llm_factory_from_env(
        model_name=config.model_name,
        api_spec=API_SPEC,
        base_url=config.base_url,
        api_key=config.api_key,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        http_client=http_client,
    )


def new_http_client(config: ResolvedConfig | None = None):
    """A transport the caller owns, so a call in flight can be aborted.

    ``invoke`` blocks its whole thread and Python cannot interrupt a thread
    sitting in a socket read, so closing this from another thread is the only
    way to stop a model call that has already started — measured at about a
    second, versus waiting out the rest of the call.
    """
    try:
        import httpx
    except ImportError:  # pragma: no cover - httpx ships with the openai client
        return None
    return httpx.Client()


def probe(config: ResolvedConfig | None = None) -> str:
    """Why a run cannot start, in a sentence, or empty if it can.

    Constructing the client is the check: a model *name* alone yields a usable
    factory, so without this the UI would invite a run that dies instantly with
    the reason buried in per-agent errors. This does not call the endpoint —
    that only happens once a run starts.
    """
    config = config or resolve()
    if config.source == SOURCE_NONE:
        return (
            "No model configured. Add a connection in Model settings, or export "
            "AGENT_MODEL_NAME before starting the server."
        )
    if not config.model_name:
        # The normal state right after a connection is created: it exists, it
        # just has no model picked off its /models list yet.
        return f"No model picked for {config.name or 'this connection'}."
    try:
        factory = build_factory(config)
        if factory is None:
            return "No model configured."
        factory()
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        return f"{config.model_name} could not be initialised: {exc}"
    return ""


def list_models(config: ResolvedConfig) -> tuple[list[str], str]:
    """The model ids the endpoint offers, or an empty list and why not.

    Reported rather than raised, like ``probe``: an endpoint that will not list
    its models is worth saying out loud, but it must not stop someone editing
    the connection that would fix it.
    """
    try:
        import httpx
    except ImportError:  # pragma: no cover - httpx ships with the openai client
        return [], "httpx is not installed."

    base = (config.base_url or DEFAULT_BASE_URL).rstrip("/")
    headers = {"Authorization": f"Bearer {config.api_key}"} if config.api_key else {}
    try:
        response = httpx.get(f"{base}/models", headers=headers, timeout=15.0)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        return [], f"Could not list models from {base}: {exc}"

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return [], f"{base}/models did not answer with an OpenAI-shaped model list."
    ids = {str(item["id"]) for item in data if isinstance(item, dict) and item.get("id")}
    if not ids:
        return [], f"{base} reports no models."
    return sorted(ids), ""


def _apply(row: LLMConnection, fields: dict) -> LLMConnection:
    for key, value in fields.items():
        if value is not None:
            setattr(row, key, value)
    row.updated_at = utcnow()
    return row


def create(db: DBSession, **fields) -> LLMConnection:
    """Add a connection. The first one is active, since nothing else could be."""
    row = _apply(LLMConnection(), fields)
    row.is_active = active_connection(db) is None
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update(db: DBSession, connection_id: str, **fields) -> LLMConnection | None:
    """Edit a connection, keeping the stored key when none is supplied.

    The browser is never sent the key, so it cannot send it back; an absent key
    on save means "leave it alone", and an explicitly empty one means "clear it".
    """
    row = db.get(LLMConnection, connection_id)
    if row is None:
        return None
    db.add(_apply(row, fields))
    db.commit()
    db.refresh(row)
    return row


def activate(db: DBSession, connection_id: str) -> LLMConnection | None:
    row = db.get(LLMConnection, connection_id)
    if row is None:
        return None
    for other in list_connections(db):
        other.is_active = other.id == connection_id
        db.add(other)
    db.commit()
    db.refresh(row)
    return row


def delete(db: DBSession, connection_id: str) -> bool:
    """Remove a connection, handing active to whatever is left."""
    row = db.get(LLMConnection, connection_id)
    if row is None:
        return False
    was_active = row.is_active
    db.delete(row)
    db.commit()
    if was_active:
        remaining = list_connections(db)
        if remaining:
            remaining[0].is_active = True
            db.add(remaining[0])
            db.commit()
    return True


def seed_from_environment() -> LLMConnection | None:
    """Turn `AGENT_MODEL_*` into the first connection, once.

    Only on an empty table: after that the database is the whole truth, so a
    connection someone deleted here does not come back on the next restart.
    """
    name = os.environ.get("AGENT_MODEL_NAME", "").strip()
    if not name:
        return None
    if os.environ.get("AGENT_MODEL_API_SPEC", "").strip().lower() == "anthropic":
        # The app is OpenAI-compatible only; seeding this would produce a
        # connection that quietly points an OpenAI client at Anthropic.
        return None

    try:
        with session_scope() as db:
            if list_connections(db):
                return None
            base_url = os.environ.get("AGENT_MODEL_BASE_URL", "").strip()
            return create(
                db,
                name=_label_for(base_url),
                base_url=base_url,
                api_key=os.environ.get("AGENT_MODEL_API_KEY", "").strip(),
                model_name=name,
                temperature=_env_float("AGENT_MODEL_TEMPERATURE"),
                max_tokens=_env_int("AGENT_MODEL_MAX_TOKENS"),
            )
    except Exception:  # noqa: BLE001 - seeding must never block startup
        return None


def _label_for(base_url: str) -> str:
    host = urlparse(base_url).hostname if base_url else ""
    return f"{host} (from AGENT_MODEL_*)" if host else "AGENT_MODEL_*"


def _env_float(key: str) -> float | None:
    try:
        return float(os.environ[key])
    except (KeyError, ValueError):
        return None


def _env_int(key: str) -> int | None:
    try:
        return int(os.environ[key])
    except (KeyError, ValueError):
        return None
