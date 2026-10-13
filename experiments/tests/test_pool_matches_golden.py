"""Pooling must reproduce the frozen pooled snapshots of the synthetic tree.

The oracle is a synthetic run tree (``factory.py``) pooled by the current code
and frozen under ``fixtures/golden/`` -- ``pooled_comparison.json`` and
``pooled_ablation.json``. A difference is a number that moved; a change that
moves one on purpose regenerates the snapshot and has its diff read.

Fields excluded from the comparison, and why:

``generated_at``   a timestamp, different by construction
``config``         prose and provenance (software versions among them)
``run_dirs``/``dir``/``per_run``   absolute paths, different on every machine
``definition``     the prose description of the statistics
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from isd_experiments import paths
from isd_experiments.pool import ablation, comparison

GOLDEN = paths.exp_root() / "tests" / "fixtures" / "golden" / "pooled_comparison.json"
GOLDEN_ABLATION = GOLDEN.with_name("pooled_ablation.json")
MINI = paths.exp_root() / "tests" / "fixtures" / "mini_run"

#: The roster the golden was pooled with. Stated, not inferred: the roster
#: fixes the Holm family size, so pooling the same data against a different
#: baseline list is a different (and equally correct) result.
ROSTER = ["react-isd", "baseline", "alignmentgraph-isd"]

IGNORE_TOP = {"generated_at", "config"}
SKIP_KEYS = {"run_dirs", "dir", "per_run", "definition", "source"}


def diff(a, b, path=""):
    """Every leaf disagreement, floats compared to 1e-12."""
    out = []
    if type(a) is not type(b):
        return [f"{path}: type {type(a).__name__} != {type(b).__name__}"]
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if (not path and k in IGNORE_TOP) or k in SKIP_KEYS:
                continue
            if k not in a:
                out.append(f"{path}.{k}: only in new")
            elif k not in b:
                out.append(f"{path}.{k}: only in golden")
            else:
                out += diff(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append(f"{path}: length {len(a)} != {len(b)}")
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                out += diff(x, y, f"{path}[{i}]")
    elif isinstance(a, float) and isinstance(b, float):
        if abs(a - b) > 1e-12:
            out.append(f"{path}: {a} != {b}")
    elif a != b:
        out.append(f"{path}: {a!r} != {b!r}")
    return out


@pytest.fixture(scope="module")
def repooled(tmp_path_factory):
    out = tmp_path_factory.mktemp("pool") / "pooled.json"
    comparison.run(
        experiment="comparison",
        patterns=[str(MINI / "test_90_benchmark_*_r*")],
        out=out, agents=ROSTER, quiet=True,
    )
    return json.loads(out.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def golden():
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_pooled_output_is_identical(repooled, golden):
    differences = diff(golden, repooled)
    assert differences == [], (
        f"{len(differences)} difference(s) from the frozen reference:\n  "
        + "\n  ".join(differences[:20])
    )


def test_the_ablation_pool_is_identical(tmp_path):
    out = tmp_path / "pooled_ablation.json"
    ablation.run(patterns=[str(MINI / "test_30_benchmark_*_a1_*")], out=out,
                 comparison_pooled=GOLDEN, quiet=True)
    differences = diff(json.loads(GOLDEN_ABLATION.read_text(encoding="utf-8")),
                       json.loads(out.read_text(encoding="utf-8")))
    assert differences == [], (
        f"{len(differences)} difference(s) from the frozen reference:\n  "
        + "\n  ".join(differences[:20])
    )


class TestTheGoldenActuallyExercisesTheHardParts:
    """A reference that only covers the happy path proves very little, so the
    fixture plants failures on purpose. These assert they are still there --
    otherwise the test above could pass over a corpus that tests nothing."""

    def test_a_missing_output_reaches_the_failure_layer(self, golden):
        rates = golden["failure_rates"]
        assert rates, "no failure layer in the reference"

    def test_complete_case_is_smaller_than_the_union_somewhere(self, golden):
        gaps = [(m["label"], a, row["n_scenarios_any_missing"])
                for m in golden["models"]
                for a, row in m["agents"].items()
                if row["n_scenarios_any_missing"]]
        assert gaps, "the reference has no incomplete cell, so it never tests one"

    def test_the_alignment_panel_was_pooled(self, golden):
        panel = golden["alignment"]["stats"]["per_model"][0]["panel"]
        assert len(panel) == 6, "the panel is six flat signals"

    def test_interaction_across_sizes_was_computed(self, golden):
        assert golden["interaction"], "the size axis is the point of the ladder"
