#!/usr/bin/env python3
"""Create a stratified scenario subset (domain × difficulty, N per cell).

Reproduces how train_10, test_90 and test_30 were built, as a repeatable script
rather than an ad-hoc step. Two jobs it is used for: carving a small TUNING/dev
set out of the TRAIN split so prompt and budget tuning never touches the test
set, and carving the smaller experiment splits out of a larger one.

The grid is 10 domains × 3 difficulty levels = 30 cells, so ``per_cell`` alone
cannot produce a subset smaller than 30. ``max_total`` is the second knob: it
down-samples the filled cells round-robin, in a seeded cell order, so the
survivors spread across distinct cells instead of piling into a few domains.
A subset built that way covers only part of the grid and is therefore NOT a
stratified sample of the corpus -- it is a cost-calibration set, and the
metadata sidecar says so in ``source_note``.

``--disjoint-from`` is the guard the experiment design asks for: it fails if the
subset just written shares a scenario with the given directory. Pass the tuning
split whenever you build a split that experiments report on, so "tuned on
train_10, reported on test" is checked rather than assumed.

See also (different jobs, both also called "stratified"):
  - split_train_test.py: one-time 95/5 split of the raw dataset, stratified on
    domain|difficulty|learning_environment.
  - sampling_strategy.py (StratifiedScenarioSampler): runtime n-sample selection
    inside the benchmark's own runner, stratified on 4 separate imbalance axes and may
    duplicate items (oversample strategy).
This script instead copies a fixed subset to disk, no duplicates.

Examples:
  # 10-scenario tuning set from train (proper ML hygiene: tune on train, report on test)
  isd-exp data split --source scenarios/train --target scenarios/train_10 \
      --per-cell 1 --max-total 10
  # 90-scenario test set, 3 per cell
  isd-exp data split --source scenarios/test --target scenarios/test_90 --per-cell 3
  # ablation's 30-scenario set: one per cell OUT OF test_90, so the whole study
  # draws on one held-out pool and ablation's A0 can be read against comparison's
  # on the same scenarios (the arms are still compared only within ablation).
  isd-exp data split --source scenarios/test_90 --target scenarios/test_30 \
      --per-cell 1 --disjoint-from scenarios/train_10 --disjoint-from scenarios/train
"""
from __future__ import annotations

import json
import random
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# The stratification cells, matching scenarios/test_30_metadata.json exactly.
DOMAINS = [
    "AI", "Business/HR/Admin Support", "Education (Teaching & Learning)", "Language",
    "Mathematics", "Medical/Nursing", "Science", "Service/Customer Support",
    "Social Studies", "Software Development/IT",
]
DIFFICULTY_ORDER = [
    "Easy - Simple structure with minimal constraints",
    "Moderate - Standard complexity with some constraints",
    "Hard - Complex requirements with multiple constraints",
]


def _index_by_cell(source: Path) -> dict[tuple[str, str], list[str]]:
    """(domain, difficulty) -> sorted list of file names present in source."""
    cells: dict[tuple[str, str], list[str]] = defaultdict(list)
    for path in sorted(source.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        cells[(data.get("domain"), data.get("difficulty"))].append(path.name)
    return cells


def _downsample(picked: dict[tuple[str, str], list[str]], max_total: int,
                rng: random.Random) -> list[str]:
    """Keep ``max_total`` of what the cells yielded, one pass per cell at a time.

    Round-robin over a shuffled cell order rather than truncating the flat list:
    truncation walks DOMAINS in declaration order, so a 10-of-30 cut would take
    the first three domains entire and leave seven domains unrepresented.
    """
    order = [key for key in picked if picked[key]]
    rng.shuffle(order)
    kept: list[str] = []
    depth = 0
    while len(kept) < max_total:
        progressed = False
        for key in order:
            if depth >= len(picked[key]):
                continue
            kept.append(picked[key][depth])
            progressed = True
            if len(kept) == max_total:
                return kept
        if not progressed:
            break
        depth += 1
    return kept


def build_subset(source: Path, target: Path, *, per_cell: int = 3,
                 disjoint_from=None, seed: int = 42,
                 max_total: int | None = None) -> int:
    """Carve a stratified subset, writing a metadata sidecar beside it.

    Deterministic under a seed, and destructive on the target so re-running
    reproduces rather than accumulates -- an additive re-run would make the
    split depend on how many times it had been built.
    """
    disjoint_from = list(disjoint_from or [])

    if not source.is_dir():
        print(f"Source not found: {source}")
        return 1
    print(f"Indexing {source} by (domain × difficulty) ...")
    cells = _index_by_cell(source)

    rng = random.Random(seed)
    picked: dict[tuple[str, str], list[str]] = {}
    missing: list[str] = []
    for domain in DOMAINS:
        for difficulty in DIFFICULTY_ORDER:
            pool = cells.get((domain, difficulty), [])
            take = min(per_cell, len(pool))
            chosen_cell = rng.sample(pool, take) if take else []
            picked[(domain, difficulty)] = chosen_cell
            # A shortage of SOURCE scenarios, which is a data problem. Cells
            # dropped by max_total below are a deliberate cut and not reported
            # here, or the two would read as the same kind of event.
            if len(chosen_cell) < per_cell:
                missing.append(f"{domain} / {difficulty} (had {len(pool)})")

    if max_total is not None and sum(len(v) for v in picked.values()) > max_total:
        selected = _downsample(picked, max_total, rng)
    else:
        selected = [name for key in picked for name in picked[key]]

    # The matrix must describe what was KEPT. Built from `picked` it would keep
    # claiming full coverage after a down-sample -- the sidecar's own version of
    # a directory named for a size it does not have.
    kept = set(selected)
    matrix: dict[str, dict[str, int]] = {}
    for domain in DOMAINS:
        matrix[domain] = {
            difficulty: sum(1 for n in picked[(domain, difficulty)] if n in kept)
            for difficulty in DIFFICULTY_ORDER
        }
    cells_covered = sum(1 for row in matrix.values() for v in row.values() if v)
    cells_total = len(DOMAINS) * len(DIFFICULTY_ORDER)

    target.mkdir(parents=True, exist_ok=True)
    # Start clean so re-running is deterministic, not additive.
    for old in target.glob("*.json"):
        old.unlink()
    for name in selected:
        shutil.copy2(source / name, target / name)

    if max_total is None:
        note = f"Stratified subset ({per_cell} per domain×difficulty cell)."
    else:
        note = (f"Cost-calibration subset: {per_cell} per domain×difficulty cell, "
                f"then down-sampled to {max_total}, covering {cells_covered} of "
                f"{cells_total} cells. NOT a stratified sample of the corpus.")
    metadata = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_dir": str(source),
        "source_note": note,
        "target_dir": str(target),
        "source_count": sum(len(v) for v in cells.values()),
        "selected_count": len(selected),
        "seed": seed,
        "sampling_unit": "domain × difficulty",
        "samples_per_cell": per_cell,
        "max_total": max_total,
        "cells_covered": cells_covered,
        "cells_total": cells_total,
        "domains": DOMAINS,
        "difficulty_order": DIFFICULTY_ORDER,
        "matrix": matrix,
        "selected_files": sorted(selected),
    }
    meta_path = target.parent / f"{target.name}_metadata.json"
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {len(selected)} scenarios to {target}")
    print(f"Metadata: {meta_path}")
    if max_total is not None:
        print(f"Down-sampled to {max_total}: covers {cells_covered} of {cells_total} cells.")
    if missing:
        print(f"WARNING: {len(missing)} cell(s) under-filled:")
        for m in missing:
            print(f"  - {m}")

    # Checked AFTER writing, and loudly: a split that overlaps the tuning set is
    # worth discovering with the offending file names in hand.
    overlaps = False
    for other in disjoint_from:
        if not other.is_dir():
            print(f"ERROR: --disjoint-from directory not found: {other}")
            overlaps = True
            continue
        shared = sorted(kept & {p.name for p in other.glob("*.json")})
        if shared:
            overlaps = True
            print(f"ERROR: {len(shared)} scenario(s) also in {other}:")
            for name in shared[:10]:
                print(f"  - {name}")
            if len(shared) > 10:
                print(f"  ... and {len(shared) - 10} more")
        else:
            print(f"Disjoint from {other}: OK")
    if overlaps:
        return 1
    return 0


#: Named splits, so the three the study uses are commands rather than
#: remembered flag combinations. Each is (source, target, per-cell, disjoint,
#: max-total). The trailing number in a name is the scenario count the split
#: actually writes, and tests/test_splits.py holds it to that: a directory whose
#: name disagrees with its size is inherited by every cost estimate taken off it.
PRESETS = {
    "test-90":     ("test", "test_90", 3, [], None),
    # 10 of the 30 cells, one scenario each. Cost and budget calibration only --
    # its results never enter the paper, and at n=10 no panel comparison could
    # reach significance under the Holm family anyway.
    "tune-10":     ("train", "train_10", 1, [], 10),
    # The ablation split must not overlap the tuning split: tuning results
    # never enter the paper, and a scenario seen during tuning is no longer
    # held out.
    "ablation-30": ("test_90", "test_30", 1, ["train_10", "train"], None),
}


def run(*, preset: str | None = None, source=None, target=None,
        per_cell: int = 3, disjoint_from=None, seed: int = 42,
        max_total: int | None = None) -> int:
    """Carve a stratified subset of the scenario corpus."""
    from .. import paths

    scen = paths.scenarios_dir()
    if preset:
        if preset not in PRESETS:
            raise SystemExit(f"Unknown split {preset!r}. Known: {', '.join(PRESETS)}")
        src_name, dst_name, cells, disjoint, cap = PRESETS[preset]
        source = scen / src_name
        target = scen / dst_name
        per_cell = cells
        max_total = cap
        disjoint_from = [scen / d for d in disjoint]
    elif not (source and target):
        raise SystemExit(
            "Give a named split (" + ", ".join(PRESETS) + ") or both --source and --target."
        )
    else:
        disjoint_from = [Path(d) for d in (disjoint_from or [])]

    # Propagated, not discarded: the disjointness guard is the reason this
    # command exists, and swallowing its exit code made it unable to fail.
    return build_subset(Path(source), Path(target), per_cell=per_cell,
                        disjoint_from=disjoint_from, seed=seed, max_total=max_total)
