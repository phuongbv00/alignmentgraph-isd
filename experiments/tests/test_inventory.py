"""The inventory must agree with what the generators actually write.

This is the drift check the replaced audit did by grepping generator source
text for filename literals -- a method that silently stopped working whenever a
write call moved into a shared helper, which is precisely what this migration
did. Asking the modules instead means the check survives refactoring.
"""

from __future__ import annotations

import re

import pytest

from isd_experiments import paths, schema
from isd_experiments.report import (
    ablation_tables,
    inventory,
    tables,
)

GOLDEN = paths.exp_root() / "tests" / "fixtures" / "golden"


class TestDeclarationMatchesProduction:
    """Both directions: nothing undeclared, nothing declared-but-unwritten."""

    def test_every_table_written_is_declared(self):
        pooled = schema.load(GOLDEN / "pooled_comparison.json")
        written = set(tables.build(pooled))
        declared = {s.name for s in inventory.INVENTORY if s.producer == inventory.TABLES}
        assert written == declared, (
            f"only written: {sorted(written - declared)}\n"
            f"only declared: {sorted(declared - written)}"
        )

    def test_every_ablation_table_written_is_declared(self):
        pooled = schema.load(GOLDEN / "pooled_ablation.json")
        written = set(ablation_tables.build(pooled))
        declared = {s.name for s in inventory.INVENTORY if s.producer == inventory.ABL_TABLES}
        assert written == declared

    def test_every_figure_declared_is_actually_drawn(self, tmp_path):
        from isd_experiments.report import figures
        figures.run(pooled_path=GOLDEN / "pooled_comparison.json",
                    outdir=tmp_path, quiet=True)
        drawn = {p.stem for p in tmp_path.glob("*.pdf")}
        declared = {s.name for s in inventory.INVENTORY if s.producer == inventory.FIGURES}
        # The scatter needs per-scenario run dirs, which this call does not give
        # it, so it is expected to be absent here.
        assert declared - drawn == {"fig_alignment_vs_judge_scatter"}
        assert drawn - declared == set()


class TestInventoryHygiene:
    def test_names_are_unique(self):
        names = [s.name for s in inventory.INVENTORY]
        assert len(names) == len(set(names))

    def test_every_producer_is_a_real_command(self):
        """A producer names the `isd-exp` subcommand that writes it, so a
        reader who sees a missing artifact knows what to run."""
        valid = {inventory.TABLES, inventory.FIGURES, inventory.COST,
                 inventory.SENSITIVITY, inventory.ABL_TABLES,
                 inventory.ABL_FIGURES, inventory.BLOOM}
        assert {s.producer for s in inventory.INVENTORY} <= valid

    def test_figures_expand_to_both_formats(self):
        for spec in inventory.INVENTORY:
            if spec.kind == "figure":
                assert sorted(spec.filenames()) == [
                    f"figures/{spec.name}.pdf", f"figures/{spec.name}.png"]

    def test_no_artifact_indexes_a_question_number(self):
        assert not [s.name for s in inventory.INVENTORY
                    if re.search(r"(?i)rq[12]|tn[12]", s.name)]

    @pytest.mark.parametrize("need", ["always", "ablation", "sensitivity", "bloom"])
    def test_every_need_tier_is_populated(self, need):
        """An empty tier means a layer lost its artifacts without anyone
        noticing -- the drift this file exists to prevent."""
        assert inventory.by_need(need), f"no artifact declared for need={need!r}"
