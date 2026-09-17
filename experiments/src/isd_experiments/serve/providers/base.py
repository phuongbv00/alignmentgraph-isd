"""What a serving provider has to offer.

A provider answers one question: where are the endpoints? Everything else --
the env-quad layout, the managed `.env` block, the slot naming -- is shared,
because those are the experiment's contract with the benchmark rather than any
host's.

Two ship today:

``static``  endpoints come from ``experiment.toml`` or ``.env`` directly. Calls
            nobody's API, works with any OpenAI-compatible server, and is the
            default: a self-hosted vLLM is just a URL.
``runpod``  additionally discovers pod ids through a host API and derives base
            URLs from a template.

Adding a host is adding one file here. Nothing outside ``providers/`` may name
one -- ``tests/test_architecture.py`` enforces that.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class Endpoint:
    """One served model, and how to reach it."""

    slot: str                       # env-quad prefix, e.g. "SMALL"
    model: str                      # what the server reports serving
    base_urls: list[str] = field(default_factory=list)
    key_env: str = ""               # env var holding the bearer token
    provider: str = "static"        # label only; the API contract is api_spec

    @property
    def usable(self) -> bool:
        return bool(self.base_urls)


class Provider(Protocol):
    """Resolve the endpoints for a set of slots."""

    name: str

    def discover(self, slots: list[str]) -> list[Endpoint]:
        ...
