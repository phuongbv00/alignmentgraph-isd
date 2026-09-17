"""What the report pipeline produces, declared once.

Two consumers read this: ``sync`` (what to copy into the manuscript tree) and
``audit.artifacts`` (what must exist, be fresh, and be referenced). They used
to carry separate lists -- the sync script a hand-written set of notes, the
audit its own inventory -- so the two could disagree about what the pipeline
produces, which is exactly the drift the audit exists to catch.

``producer`` is a MODULE, not a path string. The replaced audit grepped the
generator's source text for filename literals, so moving a write call into a
shared helper silently disabled the drift check. Naming the module lets the
audit ask it what it writes.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Spec:
    """One declared artifact.

    ``name`` carries the extension for tables and notes, and is a bare stem for
    figures, which always ship as a .pdf/.png pair.

    ``need`` says what has to have happened for this to exist:
      always       the core pipeline produced it
      ablation     the ablation was pooled
      sensitivity  the pooled file carries the instrument sweep
      bloom        a Bloom checkpoint was trained and validated
    A missing "always" artifact is an error; the others are states to report.
    """

    name: str
    producer: str        # the `isd-exp` command that writes it
    kind: str            # "tex" | "note" | "figure"
    need: str            # "always" | "ablation" | "sensitivity" | "bloom"

    def filenames(self) -> list[str]:
        """Paths relative to the generated directory."""
        if self.kind == "figure":
            return [f"figures/{self.name}.pdf", f"figures/{self.name}.png"]
        return [self.name]


TABLES = "report tables"
FIGURES = "report figures"
COST = "report cost"
SENSITIVITY = "report sensitivity"
ABL_TABLES = "report ablation-tables"
ABL_FIGURES = "report ablation-figures"
BLOOM = "bloom validate"

#: The declared inventory, held honest against the generators in both
#: directions, so a new output cannot quietly go unnoticed.
INVENTORY: list[Spec] = [
    # LLM judge and alignment tables, plus the prose macros. The LLM judge
    # tables lead
    # on ADDIE and report Total and Trajectory alongside; the alignment side
    # leads on one signal and carries the whole flat panel. Each is a separate
    # \input target.
    Spec("tab_llm_judge_addie.tex", TABLES, "tex", "always"),
    Spec("tab_llm_judge_total.tex", TABLES, "tex", "always"),
    Spec("tab_llm_judge_trajectory.tex", TABLES, "tex", "always"),
    Spec("tab_alignment.tex", TABLES, "tex", "always"),
    Spec("tab_alignment_panel.tex", TABLES, "tex", "always"),
    Spec("stats_macros.tex", TABLES, "tex", "always"),
    Spec("stats_summary.md", TABLES, "note", "always"),
    # Figures.
    Spec("fig_llm_judge_ladder", FIGURES, "figure", "always"),
    Spec("fig_llm_judge_delta", FIGURES, "figure", "always"),
    Spec("fig_llm_judge_components", FIGURES, "figure", "always"),
    Spec("fig_alignment_ladder", FIGURES, "figure", "always"),
    Spec("fig_alignment_components", FIGURES, "figure", "always"),
    Spec("fig_alignment_forest", FIGURES, "figure", "always"),
    Spec("fig_alignment_vs_llm_judge_scatter", FIGURES, "figure", "always"),
    Spec("fig_failure_rate", FIGURES, "figure", "always"),
    Spec("fig_cost_quality", FIGURES, "figure", "always"),
    # Cost. "always" because these read the run dirs directly rather than a
    # pooled layer: if there is a run at all there is a cost table, and a
    # missing one means the deployability claim has no number under it.
    Spec("tab_cost.tex", COST, "tex", "always"),
    Spec("cost_macros.tex", COST, "tex", "always"),
    Spec("stats_cost.md", COST, "note", "always"),
    # Ablation, once its pooled file exists.
    Spec("tab_ablation.tex", ABL_TABLES, "tex", "ablation"),
    Spec("tab_ablation_factorial.tex", ABL_TABLES, "tex", "ablation"),
    Spec("tab_ablation_factorial_full.tex", ABL_TABLES, "tex", "ablation"),
    Spec("abl_macros.tex", ABL_TABLES, "tex", "ablation"),
    Spec("stats_ablation.md", ABL_TABLES, "note", "ablation"),
    Spec("fig_ablation", ABL_FIGURES, "figure", "ablation"),
    Spec("fig_ablation_ladder", ABL_FIGURES, "figure", "ablation"),
    Spec("fig_ablation_components", ABL_FIGURES, "figure", "ablation"),
    Spec("fig_ablation_factorial", ABL_FIGURES, "figure", "ablation"),
    # Instrument sensitivity, once the pooled file carries the sweep.
    Spec("tab_sensitivity.tex", SENSITIVITY, "tex", "sensitivity"),
    Spec("sens_macros.tex", SENSITIVITY, "tex", "sensitivity"),
    Spec("stats_sensitivity.md", SENSITIVITY, "note", "sensitivity"),
    # Bloom validity evidence. Needs a hand-trained checkpoint, so its absence
    # is a warning rather than a pipeline failure.
    Spec("bloom_validation.md", BLOOM, "note", "bloom"),
    Spec("bloom_arms_validation.md", BLOOM, "note", "bloom"),
]


def by_need(need: str) -> list[Spec]:
    return [s for s in INVENTORY if s.need == need]


def required() -> list[Spec]:
    return by_need("always")


def producers() -> dict[str, list[Spec]]:
    out: dict[str, list[Spec]] = {}
    for spec in INVENTORY:
        out.setdefault(spec.producer, []).append(spec)
    return out
