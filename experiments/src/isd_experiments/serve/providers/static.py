"""Endpoints read straight from configuration. The default.

Calls no API. Works with any OpenAI-compatible server -- a self-hosted vLLM, a
local llama.cpp, a hosted inference provider -- because at this layer an
endpoint is a URL and a key, and nothing more.
"""

from __future__ import annotations

import os

from ...config import current as current_config
from .base import Endpoint

name = "static"


def discover(slots: list[str]) -> list[Endpoint]:
    """One endpoint per requested slot, from experiment.toml or the environment.

    The environment wins over the declared `base_url`, so a machine can point
    at a different server without editing the declaration.
    """
    cfg = current_config()
    out = []
    for slot in slots:
        rung = cfg.rung(slot)
        prefix = rung.env_prefix
        from_env = os.environ.get(f"{prefix}_AGENT_MODEL_BASE_URLS") or \
            os.environ.get(f"{prefix}_AGENT_MODEL_BASE_URL") or ""
        urls = [u.strip() for u in from_env.split(",") if u.strip()]
        if not urls and rung.base_url:
            urls = [rung.base_url]
        out.append(Endpoint(slot=prefix, model=rung.model, base_urls=urls,
                            key_env=cfg.serving.key_env))
    return out
