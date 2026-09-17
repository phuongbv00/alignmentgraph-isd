"""Figures: the set, the pair, and that nothing was drawn from nothing.

Figures cannot be byte-compared against the frozen reference -- matplotlib
embeds a creation timestamp in both PDF and PNG -- so what is checked is the
contract around them: which figures exist, that each ships both formats, and
that a missing input layer produces a SKIP rather than an empty axis. An empty
axis in a paper reads as a result.
"""

from __future__ import annotations

import pytest

from isd_experiments import paths, schema
from isd_experiments.report import figures

GOLDEN = paths.exp_root() / "tests" / "fixtures" / "golden"

#: What the replaced generator produced, under the new semantic names.
EXPECTED = {
    "fig_judge_ladder", "fig_judge_delta", "fig_judge_components",
    "fig_alignment_ladder", "fig_alignment_components", "fig_alignment_forest",
    "fig_failure_rate", "fig_cost_quality",
}


@pytest.fixture(scope="module")
def drawn(tmp_path_factory):
    out = tmp_path_factory.mktemp("figs")
    written = figures.run(pooled_path=GOLDEN / "pooled_comparison.json",
                          outdir=out, quiet=True)
    return out, written


def test_the_expected_figures_are_drawn(drawn):
    out, _ = drawn
    stems = {p.stem for p in out.glob("*.pdf")}
    assert stems == EXPECTED


def test_every_figure_ships_both_formats(drawn):
    """`audit artifacts` fails a figure missing either half: the manuscript
    includes the vector form, a reader previews the raster one."""
    out, _ = drawn
    for stem in EXPECTED:
        assert (out / f"{stem}.pdf").exists(), f"{stem}: no vector form"
        assert (out / f"{stem}.png").exists(), f"{stem}: no raster form"


def test_no_figure_is_an_empty_canvas(drawn):
    """A figure drawn from a missing layer would still be a valid file."""
    out, _ = drawn
    for p in sorted(out.glob("*.pdf")):
        assert p.stat().st_size > 4000, f"{p.name} is suspiciously small"


def test_names_carry_no_question_index(drawn):
    import re
    out, _ = drawn
    assert not [p.name for p in out.iterdir() if re.search(r"(?i)rq[12]|tn[12]", p.name)]


class TestSkippingIsExplicit:
    def test_a_pooled_file_without_alignment_skips_those_figures(self, tmp_path, capsys):
        """Not an exception, and not a blank axis: a named skip."""
        pooled = schema.load(GOLDEN / "pooled_comparison.json")
        pooled["alignment"] = None
        stripped = tmp_path / "pooled.json"
        schema.write(stripped, pooled)

        out = tmp_path / "figs"
        figures.run(pooled_path=stripped, outdir=out)
        printed = capsys.readouterr().out
        assert "skipped fig_alignment_ladder" in printed
        assert not (out / "fig_alignment_ladder.pdf").exists()
        # The judge figures do not depend on that layer and must still be drawn.
        assert (out / "fig_judge_ladder.pdf").exists()

    def test_the_scatter_needs_run_dirs_and_says_so(self, tmp_path, capsys):
        """It is per-scenario, so the pooled summary cannot produce it."""
        figures.run(pooled_path=GOLDEN / "pooled_comparison.json", outdir=tmp_path / "f")
        assert "fig_alignment_vs_judge_scatter skipped" in capsys.readouterr().out
