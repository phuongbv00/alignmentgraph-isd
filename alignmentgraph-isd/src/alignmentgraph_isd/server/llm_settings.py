"""Where the model configuration comes from.

A **list of connections** in the database, exactly one of them active. That one
is what a run and the planner resolve to; the rest sit there so switching
endpoint is a click rather than three fields retyped from memory.

The database is the **only** source. The app reads no ``AGENT_MODEL_*``: the CLI
and the benchmark are configured from a shell, this is configured in its own
dialog, and mixing the two gives a run settings that appear nowhere on screen —
a connection saved with no key would quietly borrow one from the environment and
work until it was started from a different shell, where it would not. That is
why ``build_factory`` passes ``read_env=False`` and fills in every value itself,
including the ones left blank.

Client construction still goes through ``llm_factory_from_env`` in the core
package rather than being reimplemented here; the app is OpenAI-compatible only
and says so by passing ``api_spec`` explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session as DBSession
from sqlmodel import select

from ..core.llm import llm_factory_from_env
from .db import session_scope
from .models import LLMConnection, utcnow

API_SPEC = "openai_compatible"
DEFAULT_BASE_URL = "https://api.openai.com/v1"
# What a connection gets for the optional fields left blank. Resolved here
# rather than left to the core factory's own defaults, because the transcript
# budget has to be derived from the SAME cap the client is sending.
DEFAULT_TEMPERATURE = 0.0
DEFAULT_MAX_TOKENS = 4096

SOURCE_DATABASE = "database"
SOURCE_NONE = "none"


@dataclass
class ResolvedConfig:
    model_name: str = ""
    base_url: str = ""
    api_key: str = ""
    temperature: float | None = None
    max_tokens: int | None = None
    context_window: int | None = None
    disable_thinking: bool = False
    connection_id: str = ""
    name: str = ""
    source: str = SOURCE_NONE

    @property
    def completion_cap(self) -> int:
        """The cap the client sends, which is also the budget's reserve."""
        return self.max_tokens or DEFAULT_MAX_TOKENS


def config_of(row: LLMConnection) -> ResolvedConfig:
    return ResolvedConfig(
        model_name=row.model_name,
        base_url=row.base_url,
        api_key=row.api_key,
        temperature=row.temperature,
        max_tokens=row.max_tokens,
        context_window=row.context_window,
        disable_thinking=row.disable_thinking,
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

    Every field is passed explicitly and ``read_env`` is off: a value the user
    left blank has to stay blank rather than be filled in from a shell variable
    the dialog does not show.

    Pass ``http_client`` to keep a handle on the transport — see
    ``new_http_client`` for why a run wants one.
    """
    config = config or resolve()
    if not config.model_name:
        return None
    return llm_factory_from_env(
        model_name=config.model_name,
        api_spec=API_SPEC,
        base_url=config.base_url or DEFAULT_BASE_URL,
        api_key=config.api_key,
        temperature=config.temperature if config.temperature is not None else DEFAULT_TEMPERATURE,
        max_tokens=config.completion_cap,
        disable_thinking=config.disable_thinking,
        http_client=http_client,
        read_env=False,
    )


def window_settings(config: ResolvedConfig | None = None) -> dict[str, int]:
    """The transcript budget this connection implies, for ``HarnessRunConfig``.

    Without a window the harness falls back to a fixed 24,000-character budget,
    a number unrelated to whatever the connection points at — so a stage can be
    compacted repeatedly against a model whose real window was never close to
    full. The reserve is the connection's own completion cap rather than a
    second setting: what the client may answer with is exactly what has to be
    left for the answer, and two fields could disagree.
    """
    config = config or resolve()
    return {
        "llm_context_window": config.context_window or 0,
        "llm_completion_reserve": config.completion_cap,
    }


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
        return "No model configured. Add a connection in Model settings."
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
    """Write every field supplied — a present ``None`` CLEARS.

    Which fields are supplied is the caller's decision, and it is the wire
    contract: the router omits the key when the browser did not send one. A
    rule of "skip None" here instead would look the same for the key and be
    wrong for every other field, since it would make an optional number
    impossible to unset once it had a value.
    """
    for key, value in fields.items():
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
