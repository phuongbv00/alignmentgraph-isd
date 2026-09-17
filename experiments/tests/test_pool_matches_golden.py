"""The pooling layer must reproduce what the scripts it replaces produced.

This is the load-bearing test of the whole migration. ``results/`` is empty and
no real pooled file survives, so the oracle is a synthetic run tree (see
``factory.py``) pooled by the ORIGINAL scripts and frozen. If this passes, the
split of a 1,900-line script into five modules changed no number.

Fields excluded from the comparison, and why:

``generated_at``   a timestamp, different by construction
``config``         prose and provenance, reworded during the move
``run_dirs``/``dir``/``per_run``   absolute paths, different on every machine
``definition``     the prose description of the statistics

The frozen goldens carry the vocabulary the code uses: the LLM judge family
speaks in SCORES (``by_score``/``lead_score``/``scores``,
``interaction_by_score``), the alignment family in SIGNALS, and
``factorial.measures``, which holds both, is named after neither. Settling
that took one pass over the goldens: key names and one ``holm_family``
sentence, with the multiset of leaf VALUES asserted identical, so the oracle
is the same numbers under the names the code now uses.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from isd_experiments import paths
from isd_experiments.pool import comparison

GOLDEN = paths.exp_root() / "tests" / "fixtures" / "golden" / "pooled_comparison.json"
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
