"""Draw a blinded subset of outputs for expert review.

Blinding matters more than the sampling here: an expert who can see which
system produced a design is not scoring the design. So the package must strip
the system identity from the artifacts and keep the mapping outside what the
reviewer receives.

NOT IMPLEMENTED -- see the module docstring in ``rubric.py`` for why this is
scaffolding rather than a stub that returns something.
"""

from __future__ import annotations

#: The roadmap's tiers: 3 experts is the minimum that counts as validation,
#: 5 scoring 8-12 blinded outputs each is the recommendation.
MINIMUM_EXPERTS = 3
RECOMMENDED_EXPERTS = 5
RECOMMENDED_OUTPUTS_EACH = (8, 12)


def run(*, n_experts: int = RECOMMENDED_EXPERTS, quiet: bool = False) -> int:
    raise SystemExit(
        "`expert sample` is not implemented yet.\n"
        "  Expert validation is required for the paper to be more than machine\n"
        "  self-assessment, and the roadmap places it AFTER code freeze and\n"
        "  after official outputs exist — experts must not be used to choose a\n"
        "  method or tune a prompt once results have been seen."
    )
