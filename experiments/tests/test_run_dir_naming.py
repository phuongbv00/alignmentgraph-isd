"""Run-dir names must parse for every tag namespace, not just one.

This is a regression guard for a real defect in the code being replaced. The
old grammar pinned the tag to `r\\d+`:

    (?P<model>.+?)(?:_(?P<tag>r\\d+))?_(?P<ts>\\d{8}_\\d{6})

The tag group is optional, so a run tagged anything else did not fail to
parse -- it parsed WRONG, folding the tag into the model label
(`qwen3.5-4b_a1`). The ablation uses its own tag namespace deliberately, so
every ablation run was mislabelled, and the reference-drift gauge -- which
bounds how much of an arm delta could be session effect -- looks its sizes up
in the comparison pool by exact label. Every lookup missed, and it reported
"size ... not found in ladder pooled JSON" for every row instead of a number.

A wrong answer that looks like a missing input is the worst failure mode
available, so the grammar accepts any alphabetic tag and the drift gauge is
asserted to produce numbers.
"""

from __future__ import annotations

import json
import re

import pytest

from isd_experiments import paths, runs

#: The grammar the replaced script used.
OLD_RE = re.compile(
    r"^(?P<dataset>.+)_benchmark_(?P<model>.+?)(?:_(?P<tag>r\d+))?_(?P<ts>\d{8}_\d{6})$"
)

GOLDEN = paths.exp_root() / "tests" / "fixtures" / "golden"


@pytest.mark.parametrize("tag", ["r1", "c1", "a1", "tune1", "canary"])
def test_every_tag_namespace_parses_to_the_same_model_label(tag):
    name = f"test_90_benchmark_qwen3.5-4b_{tag}_20260101_000000"
    parsed = runs.parse_run_dir_name(name)
    assert parsed is not None, name
    assert parsed["model"] == "qwen3.5-4b", f"tag {tag!r} leaked into the model label"
    assert parsed["tag"] == tag


def test_the_old_grammar_really_did_mislabel_non_r_tags():
    """Pins the defect, so the guard above cannot be mistaken for decoration."""
    name = "test_30_benchmark_qwen3.5-4b_a1_20260101_000000"
    assert OLD_RE.match(name).group("model") == "qwen3.5-4b_a1"
    assert runs.parse_run_dir_name(name)["model"] == "qwen3.5-4b"


def test_a_name_without_a_tag_still_parses():
    parsed = runs.parse_run_dir_name("test_90_benchmark_qwen3.5-4b_20260101_000000")
    assert parsed["model"] == "qwen3.5-4b" and not parsed["tag"]


def test_a_name_that_is_not_a_run_dir_returns_none():
    assert runs.parse_run_dir_name("generated") is None
    assert runs.parse_run_dir_name("pooled_comparison.json") is None


class TestDriftGaugeProducesNumbers:
    """The consequence of the fix, asserted on the outcome rather than the regex."""

    @staticmethod
    @pytest.fixture(scope="class")
    def pooled(tmp_path_factory):
        from isd_experiments.pool import ablation
        out = tmp_path_factory.mktemp("abl") / "pooled_ablation.json"
        import os
        old = os.environ.get("RESULTS_DIR")
        os.environ["RESULTS_DIR"] = str(paths.exp_root() / "tests" / "fixtures" / "mini_run")
        try:
            ablation.run(patterns=["test_30_benchmark_*_a*"],
                         comparison_pooled=GOLDEN / "pooled_comparison.json",
                         out=out, quiet=True)
        finally:
            if old is None:
                os.environ.pop("RESULTS_DIR", None)
            else:
                os.environ["RESULTS_DIR"] = old
        return json.loads(out.read_text(encoding="utf-8"))

    def test_labels_match_the_comparison_pool(self, pooled):
        comparison = json.loads((GOLDEN / "pooled_comparison.json").read_text())
        assert {m["label"] for m in pooled["models"]} == {m["label"] for m in comparison["models"]}

    def test_every_row_carries_a_delta_not_a_not_found_note(self, pooled):
        rows = pooled["reference_drift"]["per_model"]
        assert rows, "the drift gauge produced no rows at all"
        for row in rows:
            assert "note" not in row, f"{row.get('label')}: {row.get('note')}"
            assert isinstance(row["delta"], float)
