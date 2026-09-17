#!/usr/bin/env python3
"""Create a stratified scenario subset (domain × difficulty, N per cell).

Reproduces how scenarios/train_30, test_90 and test_30 were built, as a
repeatable script rather than an ad-hoc step. Two jobs it is used for: carving a
small TUNING/dev set out of the TRAIN split so prompt and budget tuning never
touches the test set, and carving the smaller experiment splits out of a larger
one.

Default: 1 scenario per (domain × difficulty) cell = 10 domains × 3 levels = 30.

``--disjoint-from`` is the guard the experiment design asks for: it fails if the
subset just written shares a scenario with the given directory. Pass the tuning
split whenever you build a split that experiments report on, so "tuned on
train_30, reported on test" is checked rather than assumed.

See also (different jobs, both also called "stratified"):
  - split_train_test.py: one-time 95/5 split of the raw dataset, stratified on
    domain|difficulty|learning_environment.
  - sampling_strategy.py (StratifiedScenarioSampler): runtime n-sample selection
    inside run_benchmark.py, stratified on 4 separate imbalance axes and may
    duplicate items (oversample strategy).
This script instead copies a fixed N-per-cell subset to disk, no duplicates.

Examples:
  # 30-scenario tuning set from train (proper ML hygiene: tune on train, report on test)
  python scripts/2_split_stratified_subset.py --source scenarios/train --target scenarios/train_30
  # 90-scenario test set, 3 per cell
  python scripts/2_split_stratified_subset.py --source scenarios/test --target scenarios/test_90 --per-cell 3
  # ablation's 30-scenario ablation set: one per cell OUT OF test_90, so the whole
  # study draws on one held-out pool and ablation's A0 can be read against comparison's on
  # the same scenarios (the arms are still compared only within ablation).
  python scripts/2_split_stratified_subset.py --source scenarios/test_90 --target scenarios/test_30 \
      --per-cell 1 --disjoint-from scenarios/train_30 --disjoint-from scenarios/train
"""
from __future__ import annotations

import argparse
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


def build_subset(source: Path, target: Path, *, per_cell: int = 3,
                 disjoint_from=None, seed: int = 42) -> int:
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
    selected: list[str] = []
    matrix: dict[str, dict[str, int]] = {}
    missing: list[str] = []
    for domain in DOMAINS:
        matrix[domain] = {}
        for difficulty in DIFFICULTY_ORDER:
            pool = cells.get((domain, difficulty), [])
            take = min(per_cell, len(pool))
            picked = rng.sample(pool, take) if take else []
            matrix[domain][difficulty] = len(picked)
            selected.extend(picked)
            if len(picked) < per_cell:
                missing.append(f"{domain} / {difficulty} (had {len(pool)})")

    target.mkdir(parents=True, exist_ok=True)
    # Start clean so re-running is deterministic, not additive.
    for old in target.glob("*.json"):
        old.unlink()
    for name in selected:
        shutil.copy2(source / name, target / name)

    metadata = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_dir": str(source),
        "source_note": f"Stratified subset ({per_cell} per domain×difficulty cell) for tuning.",
        "target_dir": str(target),
        "source_count": sum(len(v) for v in cells.values()),
        "selected_count": len(selected),
        "seed": seed,
        "sampling_unit": "domain × difficulty",
        "samples_per_cell": per_cell,
        "domains": DOMAINS,
        "difficulty_order": DIFFICULTY_ORDER,
        "matrix": matrix,
        "selected_files": sorted(selected),
    }
    meta_path = target.parent / f"{target.name}_metadata.json"
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {len(selected)} scenarios to {target}")
    print(f"Metadata: {meta_path}")
    if missing:
        print(f"WARNING: {len(missing)} cell(s) under-filled:")
        for m in missing:
            print(f"  - {m}")

    # Checked AFTER writing, and loudly: a split that overlaps the tuning set is
    # worth discovering with the offending file names in hand.
    chosen = set(selected)
    overlaps = False
    for other in disjoint_from:
        if not other.is_dir():
            print(f"ERROR: --disjoint-from directory not found: {other}")
            overlaps = True
            continue
        shared = sorted(chosen & {p.name for p in other.glob("*.json")})
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
#: remembered flag combinations. Each is (source, target, per-cell, disjoint).
PRESETS = {
    "test-90":     ("test", "test_90", 3, []),
    "tune-30":     ("train", "train_30", 3, []),
    # The ablation split must not overlap the tuning split: tuning results
    # never enter the paper, and a scenario seen during tuning is no longer
    # held out.
    "ablation-30": ("test_90", "test_30", 1, ["train_30", "train"]),
}


def run(*, preset: str | None = None, source=None, target=None,
        per_cell: int = 3, disjoint_from=None, seed: int = 42) -> int:
    """Carve a stratified subset of the scenario corpus."""
    from .. import paths

    scen = paths.scenarios_dir()
    if preset:
        if preset not in PRESETS:
            raise SystemExit(f"Unknown split {preset!r}. Known: {', '.join(PRESETS)}")
        src_name, dst_name, cells, disjoint = PRESETS[preset]
        source = scen / src_name
        target = scen / dst_name
        per_cell = cells
        disjoint_from = [scen / d for d in disjoint]
    elif not (source and target):
        raise SystemExit(
            "Give a named split (" + ", ".join(PRESETS) + ") or both --source and --target."
        )
    else:
        disjoint_from = [Path(d) for d in (disjoint_from or [])]

    build_subset(Path(source), Path(target), per_cell=per_cell,
                 disjoint_from=disjoint_from, seed=seed)
    return 0
