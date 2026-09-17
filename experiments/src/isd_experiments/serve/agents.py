"""Write the agent-model endpoints into the managed `.env` block.

Provider-agnostic: WHERE the endpoints come from is the provider's business
(see ``providers/``), and what gets written is the same env-quad contract
``shared/llm`` speaks regardless.
"""

from __future__ import annotations

from .. import paths
from ..config import current as current_config
from . import env_block
from .providers import resolve

#: Delimiters of the block this command owns. Everything outside them is the
#: user's and is never touched; re-running replaces the block rather than
#: appending a second one.
BLOCK = "agent model endpoints"


def run(*, dry_run: bool = False, quiet: bool = False) -> int:
    cfg = current_config()
    provider = resolve()
    slots = [r.slot for r in cfg.ladder]
    endpoints = provider.discover(slots)

    lines = []
    for ep in endpoints:
        lines += [
            f"{ep.slot}_AGENT_MODEL_BASE_URLS={','.join(ep.base_urls)}",
            f"{ep.slot}_AGENT_MODEL_NAME={ep.model}",
            f"{ep.slot}_AGENT_MODEL_API_KEY_ENVS={ep.key_env}",
            "",
        ]
    block = "\n".join(lines).rstrip() + "\n"

    unusable = [e.slot for e in endpoints if not e.usable]
    if dry_run:
        print(block)
        if unusable and not quiet:
            print(f"# no base URL for: {', '.join(unusable)}")
        return 0

    env_block.write(paths.env_file(), BLOCK, block)
    if not quiet:
        print(f"wrote the {BLOCK!r} block into {paths.env_file()} "
              f"({len(endpoints)} slot(s), provider={provider.name})")
        if unusable:
            print(f"! no base URL for: {', '.join(unusable)} — those slots cannot run")
    return 1 if unusable else 0
