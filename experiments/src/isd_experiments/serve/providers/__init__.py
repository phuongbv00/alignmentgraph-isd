"""Serving providers. Adding a host is adding one module here."""

from __future__ import annotations

from ...config import current as current_config
from . import static
from .base import Endpoint, Provider

__all__ = ["Endpoint", "Provider", "resolve"]


def resolve(name: str | None = None):
    """The provider module named by the config, or by `name`."""
    key = name or current_config().serving.provider
    if key == "static":
        return static
    if key == "runpod":
        from . import runpod_agents
        return runpod_agents
    raise SystemExit(
        f"Unknown serving provider {key!r}. Declared in experiment.toml "
        f"[serving].provider; known: static, runpod."
    )
