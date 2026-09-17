"""Formatting rules the manuscript depends on."""

from __future__ import annotations

import math

import pytest

from isd_experiments import config, latex


class TestNumberFormatting:
    def test_decimal_point_not_comma(self):
        """`audit artifacts` fails red on a comma decimal in any artifact:
        these files are English, and a locale-dependent mark once crept in."""
        assert latex.fmt_num(87.77) == "87.77"
        assert "," not in latex.fmt_num(1234.5)

    def test_missing_is_printed_not_blank(self):
        assert latex.fmt_num(None) == "--"
        assert latex.fmt_num(float("nan")) == "--"
        assert latex.fmt_num(float("inf")) == "--"

    def test_precision_is_explicit(self):
        assert latex.fmt_num(1 / 3, 3) == "0.333"


class TestPValueFormatting:
    def test_ordinary_p_is_plain(self):
        assert latex.fmt_p(0.003) == "0.003"

    def test_small_p_is_math_mode(self):
        out = latex.fmt_p(4.4e-16)
        assert "\\times 10^{-16}" in out

    def test_zero_is_bounded_not_claimed(self):
        assert latex.fmt_p(0.0) == "<10^{-16}"

    def test_missing(self):
        assert latex.fmt_p(None) == "--"


class TestSizeParsing:
    def test_reads_a_family_it_has_never_seen(self):
        """The generators must not need to know the ladder to label an axis."""
        assert latex.size_of_label("llama-3.2-1b-instruct") == 1.0
        assert latex.size_of_label("gemma-2-27b-it") == 27.0

    def test_unparseable_is_nan(self):
        assert math.isnan(latex.size_of_label("mystery-model"))

    def test_macro_words_have_no_digits(self):
        """LaTeX forbids digits in a control sequence -- this is the whole
        reason sizes are spelled as words."""
        words = config.load().macro_words
        for i, label in enumerate(["qwen3.5-0.8b", "unknown-13b"]):
            assert not any(c.isdigit() for c in latex.size_word(label, i, words))

    def test_undeclared_sizes_do_not_collide(self):
        words = config.load().macro_words
        a = latex.size_word("mystery-7b", 0, words)
        b = latex.size_word("mystery-13b", 1, words)
        assert a != b


class TestEscaping:
    def test_escapes_an_agent_id_with_an_ampersand(self):
        assert latex.escape("Dick&Carey") == r"Dick\&Carey"

    def test_escapes_underscore(self):
        assert latex.escape("porter_mean") == r"porter\_mean"


class TestMacroRegistry:
    """Four macro files, one document, no collision check until now."""

    def test_duplicate_definition_is_refused(self):
        r = latex.MacroRegistry()
        r.add("myMacro", "1.0")
        with pytest.raises(ValueError, match="already defined"):
            r.add("myMacro", "2.0")

    def test_digits_in_a_name_are_refused(self):
        r = latex.MacroRegistry()
        with pytest.raises(ValueError, match="digits"):
            r.add("addie08B", "1.0")

    def test_renders_newcommands_with_comments(self):
        r = latex.MacroRegistry()
        r.add("meanAddieZeroEightB", "74.21", "pooled mean ADDIE at the smallest rung")
        out = r.render()
        assert "\\newcommand{\\meanAddieZeroEightB}{74.21}" in out
        assert "% pooled mean ADDIE at the smallest rung" in out


class TestHeaderComment:
    def test_names_producer_and_source_generation(self):
        head = latex.header_comment("isd-exp report tables", "LLM judge ladder table",
                                    {"generated_at": "2026-01-01T00:00:00"})
        assert "isd-exp report tables" in head
        assert "2026-01-01T00:00:00" in head
        assert head.startswith("% AUTO-GENERATED")

    def test_every_line_is_a_latex_comment(self):
        head = latex.header_comment("p", "w", {"generated_at": "x"})
        assert all(ln.startswith("%") for ln in head.strip().splitlines())
