"""Aggregate returned expert score sheets into descriptive statistics.

NOT IMPLEMENTED, on purpose. This module exists so the stage has a home and
appears in `isd-exp --help`, which is the difference between a known gap and a
forgotten one. It raises rather than returning a placeholder: a function that
produced plausible-looking agreement numbers would let the roadmap's checklist
be ticked without any expert having scored anything, and a fabricated validity
claim is far worse than a missing one.

What it has to do when implemented: read the returned sheets, report descriptive
agreement between reviewers (not a reliability claim -- the n is too small for
one), and place the expert judgement BESIDE the deterministic panel rather than
validating one against the other. The panel is a measurable-signal instrument,
not a substitute for expert judgement, and the comparison is the point.
"""

from __future__ import annotations


def aggregate(*, quiet: bool = False) -> int:
    raise SystemExit(
        "`expert aggregate` is not implemented yet.\n"
        "  It needs a rubric, score sheets and returned reviews first — "
        "see the Sprint-1 roadmap, phase 6."
    )
