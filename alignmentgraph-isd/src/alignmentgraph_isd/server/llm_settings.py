"""Where the model configuration comes from.

Two sources, in order:

1. **The database**, set from the UI. This is what makes the demo
   self-contained — no shell state to get right before it will run.
2. **`AGENT_MODEL_*`**, the same variables the CLI and the benchmark read.
   Kept as a fallback so an existing setup keeps working untouched.

Everything goes through ``llm_factory_from_env`` in the core package either
way: it takes explicit arguments that win over the environment, so the stored
settings are passed in rather than reimplementing client construction here.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from sqlmodel import Session as DBSession

from ..core.llm import llm_factory_from_env
from .db import session_scope
from .models import LLMSetting

SETTING_ID = "default"

SOURCE_DATABASE = "database"
SOURCE_ENVIRONMENT = "environment"
SOURCE_NONE = "none"


@dataclass
class ResolvedConfig:
    model_name: str = ""
    api_spec: str = "openai_compatible"
    base_url: str = ""
    api_key: str = ""
    temperature: float | None = None
    max_tokens: int | None = None
    source: str = SOURCE_NONE

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key)


def load_row(db: DBSession) -> LLMSetting | None:
    row = db.get(LLMSetting, SETTING_ID)
    return row if row is not None and row.model_name else None


def resolve() -> ResolvedConfig:
    """The configuration a run would use right now."""
    try:
        with session_scope() as db:
            row = load_row(db)
    except Exception:  # noqa: BLE001 - a missing table must not break the app
        row = None

    if row is not None:
        return ResolvedConfig(
            model_name=row.model_name,
            api_spec=row.api_spec or "openai_compatible",
            base_url=row.base_url,
            api_key=row.api_key,
            temperature=row.temperature,
            max_tokens=row.max_tokens,
            source=SOURCE_DATABASE,
        )

    env_name = os.environ.get("AGENT_MODEL_NAME", "").strip()
    if env_name:
        return ResolvedConfig(
            model_name=env_name,
            api_spec=os.environ.get("AGENT_MODEL_API_SPEC", "").strip() or "openai_compatible",
            base_url=os.environ.get("AGENT_MODEL_BASE_URL", "").strip(),
            api_key=os.environ.get("AGENT_MODEL_API_KEY", "").strip(),
            source=SOURCE_ENVIRONMENT,
        )

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
        api_spec=config.api_spec,
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

    Returns ``None`` when the configuration cannot use one (ChatAnthropic does
    not accept an ``http_client``), in which case cancellation falls back to
    landing at the harness's next event.
    """
    config = config or resolve()
    if config.api_spec not in ("openai", "openai_compatible"):
        return None
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
    if not config.model_name:
        return (
            "No model configured. Set one in Model settings, or export "
            "AGENT_MODEL_NAME before starting the server."
        )
    try:
        factory = build_factory(config)
        if factory is None:
            return "No model configured."
        factory()
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        return f"{config.model_name} could not be initialised: {exc}"
    return ""


def save(db: DBSession, **fields) -> LLMSetting:
    """Write the settings, keeping the stored key when none is supplied.

    The browser is never sent the key, so it cannot send it back; an absent key
    on save means "leave it alone", and an explicitly empty one means "clear it".
    """
    row = db.get(LLMSetting, SETTING_ID)
    if row is None:
        row = LLMSetting(id=SETTING_ID)

    for key, value in fields.items():
        if value is not None:
            setattr(row, key, value)

    from .models import utcnow

    row.updated_at = utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def clear(db: DBSession) -> None:
    """Forget the stored settings and fall back to the environment."""
    row = db.get(LLMSetting, SETTING_ID)
    if row is not None:
        db.delete(row)
        db.commit()
