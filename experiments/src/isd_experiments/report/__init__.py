"""Generated artifacts for the manuscript, and the order they must run in.

The order is a real constraint, declared here rather than left to a comment:

1. tables, cost, sensitivity, ablation tables  -- write the ``*_macros.tex``
2. figures, ablation figures                   -- independent of those
3. facts                                       -- READS the macro files, so it
                                                  must come after step 1
4. sync                                        -- copies into the manuscript tree
5. audit                                       -- checks what sync produced

A step whose input layer is absent SKIPS with a message naming the command
that would produce it. It never emits a placeholder: an artifact that exists
but means nothing is worse than one that is missing, because only the missing
one gets noticed.
"""

from __future__ import annotations

from pathlib import Path

from . import (
    ablation_figures,
    ablation_tables,
    cost,
    facts,
    figures,
    sensitivity,
    sync,
    tables,
)

__all__ = ["run_all", "tables", "figures", "cost", "sensitivity",
           "ablation_tables", "ablation_figures", "facts", "sync"]


def run_all(*, comparison_pooled: Path | None = None,
            ablation_pooled: Path | None = None,
            outdir: Path | None = None,
            runs_glob: str | None = None,
            do_sync: bool = True,
            quiet: bool = False) -> list[Path]:
    """Run every generator in dependency order. Returns everything written."""
    written: list[Path] = []
    figdir = (outdir / "figures") if outdir else None

    written += tables.run(pooled_path=comparison_pooled, outdir=outdir, quiet=quiet)
    written += cost.run(runs_glob=runs_glob, outdir=outdir, quiet=quiet)
    written += sensitivity.run(pooled_path=comparison_pooled, outdir=outdir, quiet=quiet)
    written += ablation_tables.run(pooled_path=ablation_pooled, outdir=outdir, quiet=quiet)

    written += figures.run(pooled_path=comparison_pooled, outdir=figdir,
                           runs_glob=runs_glob, quiet=quiet)
    written += ablation_figures.run(pooled_path=ablation_pooled, outdir=figdir, quiet=quiet)

    # After the macro files exist: this reads them back.
    sheet = facts.run(comparison_pooled=comparison_pooled, ablation_pooled=ablation_pooled,
                      outdir=outdir, quiet=quiet)
    if sheet:
        written.append(sheet)

    if do_sync:
        written += sync.run(srcdir=outdir, quiet=quiet)
    return written
