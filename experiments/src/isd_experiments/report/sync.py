"""Copy generated artifacts into the manuscript tree.

Driven by ``inventory``, which is also what the artifact audit reads. That
shared declaration is the point: the shell script this replaces carried a
hand-written list of which notes to copy, and the audit carried its own list of
what must exist, so the two could disagree -- and the audit's job was precisely
to notice that kind of drift.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .. import paths
from .inventory import INVENTORY


def run(*, srcdir: Path | None = None, dstdir: Path | None = None,
        quiet: bool = False) -> list[Path]:
    """Copy every declared artifact that exists. Returns what was copied."""
    src = srcdir or paths.generated_dir()
    dst = dstdir or paths.docs_generated()
    if not src.exists():
        raise SystemExit(
            f"Nothing to sync: {src} does not exist.\n"
            f"  Generate it first with:  {paths.cli()} report all --no-sync"
        )
    (dst / "figures").mkdir(parents=True, exist_ok=True)

    copied: list[Path] = []
    for spec in INVENTORY:
        for rel in spec.filenames():
            source = src / rel
            if not source.exists():
                continue          # an unrun layer; the audit reports it
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(target)
    if not quiet:
        print(f"synced {len(copied)} artifact(s) -> {dst}")
    return copied
