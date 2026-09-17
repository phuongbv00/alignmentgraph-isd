"""A split named for a size must have that size, and down-sampling must spread.

Regression guard for a real defect. ``PRESETS["tune-30"]`` was
``("train", "train_30", 3, [])`` -- 3 per cell over a 30-cell grid -- so the
directory named ``train_30`` held **90** scenarios. Nothing caught it: the
module docstring said 30, the usage example said 30, the workflow guide said
30, and the only thing that knew otherwise was the filesystem. Every cost
estimate taken off the tuning stage inherited the error threefold, and the
tuning split was the one split with no distribution report to contradict it.

So the trailing number in a preset name is treated as a claim about the split,
and checked against the arithmetic that actually produces it.
"""

from __future__ import annotations

import random
import re

import pytest

from isd_experiments.data import sample

CELLS = len(sample.DOMAINS) * len(sample.DIFFICULTY_ORDER)


def _declared_size(per_cell: int, max_total: int | None) -> int:
    """What the preset will actually write, assuming a source that can fill it."""
    full = per_cell * CELLS
    return min(full, max_total) if max_total is not None else full


@pytest.mark.parametrize("name", sorted(sample.PRESETS))
def test_a_presets_name_matches_the_size_it_produces(name):
    _src, dst, per_cell, _disjoint, max_total = sample.PRESETS[name]
    claimed = re.search(r"(\d+)$", name)
    assert claimed, f"preset {name!r} has no size in its name"
    assert _declared_size(per_cell, max_total) == int(claimed.group(1)), (
        f"{name!r} writes {_declared_size(per_cell, max_total)} scenarios"
    )
    assert dst.endswith("_" + claimed.group(1)), (
        f"preset {name!r} writes into {dst!r}, whose name claims a different size"
    )


def test_every_preset_target_is_named_once():
    targets = [spec[1] for spec in sample.PRESETS.values()]
    assert len(targets) == len(set(targets)), (
        "two presets write the same directory; build_subset clears its target, "
        "so whichever runs second would silently wipe the other"
    )


def test_a_split_is_never_carved_out_of_a_directory_no_preset_builds():
    """Sources are either the corpus splits or another preset's target."""
    corpus = {"train", "test"}
    targets = {spec[1] for spec in sample.PRESETS.values()}
    for name, (src, *_rest) in sample.PRESETS.items():
        assert src in corpus | targets, f"{name!r} reads {src!r}, which nothing builds"


def test_downsample_spreads_across_cells_rather_than_truncating():
    """The failure this rules out: taking the first N of a flat list walks
    DOMAINS in declaration order, so 10 of 30 would be three whole domains."""
    picked = {(d, f): [f"{d}|{f}"] for d in sample.DOMAINS
              for f in sample.DIFFICULTY_ORDER}
    kept = sample._downsample(picked, 10, random.Random(42))
    assert len(kept) == 10
    assert len(set(kept)) == 10
    assert len({name.split("|")[0] for name in kept}) >= 8, (
        "a 10-of-30 cut landed in fewer than 8 domains"
    )


def test_downsample_is_deterministic_under_the_seed():
    picked = {(d, f): [f"{d}|{f}"] for d in sample.DOMAINS
              for f in sample.DIFFICULTY_ORDER}
    a = sample._downsample(picked, 10, random.Random(42))
    b = sample._downsample(picked, 10, random.Random(42))
    assert a == b


def test_downsample_returns_everything_when_the_cap_is_not_binding():
    picked = {(d, f): [f"{d}|{f}"] for d in sample.DOMAINS
              for f in sample.DIFFICULTY_ORDER}
    kept = sample._downsample(picked, 999, random.Random(42))
    assert len(kept) == CELLS
