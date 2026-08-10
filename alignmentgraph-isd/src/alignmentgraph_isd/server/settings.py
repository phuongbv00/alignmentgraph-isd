"""Server configuration, all via ``AGISD_SERVER_*`` env vars.

Deliberately separate from ``AGENT_MODEL_*``: those configure the model the
harness runs on and are read by ``llm_factory_from_env`` in the core package,
shared with the CLI and the benchmark. Nothing here touches them.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGISD_SERVER_", env_file=".env", extra="ignore")

    # Run artifacts (graph.json, trajectory.json, events.jsonl, ...) live under
    # here; the database only stores paths relative to it, so moving the
    # directory does not invalidate rows.
    data_root: Path = Path(".agisd-server-data")

    # Empty means "a SQLite file inside data_root".
    db_url: str = ""

    # Runs are I/O-bound (waiting on a model endpoint), so threads are the right
    # tool. Kept small: each concurrent run is a full ADDIE pipeline.
    max_concurrent_runs: int = 2

    # Serve the built SPA from this app, so a demo is one process on one URL.
    # Off in development, where Vite serves it and proxies /api here.
    serve_spa: bool = False
    spa_dist: Path = _PACKAGE_ROOT / "webapp" / "dist"

    @property
    def resolved_db_url(self) -> str:
        if self.db_url:
            return self.db_url
        return f"sqlite:///{(self.data_root / 'demo.db').resolve()}"

    @property
    def programs_dir(self) -> Path:
        return self.data_root / "programs"


@lru_cache
def get_settings() -> Settings:
    return Settings()
