"""Write the embedding endpoints for the alignment panel into `.env`.

Only a SERVED encoder arm needs one. Local and lexical arms are always listed
anyway, so the sensitivity sweep can run whatever the endpoint situation is --
those are precisely the arms that should still be scorable when nothing is
served.
"""

from __future__ import annotations

import os

from .. import paths
from ..alignment.presets import current as arms
from . import env_block

BLOCK = "embedding endpoints"


def run(*, dry_run: bool = False, quiet: bool = False) -> int:
    registry = arms()
    served, offline = [], []
    lines = []
    for key, arm in registry.encoders.items():
        slot = arm.env_slot
        if not arm.needs_endpoint:
            offline.append(key)
            lines += [f"{slot}_EMBED_MODEL={arm.model}", ""]
            continue
        urls = os.environ.get(f"{slot}_EMBED_BASE_URLS", "")
        served.append(key)
        lines += [
            f"{slot}_EMBED_BASE_URLS={urls}",
            f"{slot}_EMBED_MODEL={arm.model}",
            f"{slot}_EMBED_API_KEY_ENV={os.environ.get(f'{slot}_EMBED_API_KEY_ENV', 'LLM_API_KEY')}",
            "",
        ]
    lines.insert(0, f"EMBED_SLOTS={','.join(sorted(registry.encoders))}")
    block = "\n".join(lines).rstrip() + "\n"

    if dry_run:
        print(block)
        return 0

    env_block.write(paths.env_file(), BLOCK, block)
    if not quiet:
        print(f"wrote the {BLOCK!r} block into {paths.env_file()}")
        print(f"  served arms  : {', '.join(served) or 'none'}")
        print(f"  offline arms : {', '.join(offline) or 'none'} (no endpoint needed)")
    return 0
