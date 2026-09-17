#!/usr/bin/env python3
"""In-flight audit while the ladder is running (guide section 7.2).

Prints, per slot log in the slot logs under the launch dir (newest ladder dir by
default), the red-flag counters that must all stay at 0:

  524   proxy timeout came back (streaming not effective?)      -> stop, investigate
  400   max-context rejection (token cap not applied?)          -> check MAX_TOKENS_CAP
  empty model returned empty content ('응답 길이: 0')            -> thinking overflow?
  stub  baseline wrote default output ('기본 출력 반환')          -> that scenario's data is junk

plus ok/fail tallies and progress-log freshness (stale > --stale-min minutes
-> warning). Run it every 30-60 minutes during the ladder, e.g.:

  ./isd-exp audit inflight            # newest ladder dir
  ./isd-exp audit inflight --ladder-dir results/ladder_20260722_200348
  watch -n 300 ./isd-exp audit inflight

Exit code 0 = clean, 1 = at least one red flag > 0.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .. import paths


RED_FLAGS = {
    "524": "Error code: 524",
    "400": "Error code: 400",
    "empty": "응답 길이: 0",
    "stub": "기본 출력 반환",
}
TALLIES = {"ok": "✅", "fail": "❌"}


def run(*, experiment: str | None = None, ladder_dir=None, stale_minutes: int = 45) -> int:

    ladder_dir = ladder_dir
    if ladder_dir is None:
        candidates = sorted((paths.results_root()).glob("ladder_*"))
        if not candidates:
            print("No results/ladder_* dir found.", file=sys.stderr)
            return 1
        ladder_dir = candidates[-1]

    print(f"== In-flight audit (guide 7.2) — {ladder_dir} ==\n")
    red = 0

    logs = sorted(ladder_dir.glob("*.log"))
    if not logs:
        print(f"  no *.log files in {ladder_dir}", file=sys.stderr)
        return 1
    header = f"  {'log':14s}" + "".join(f"{k:>7s}" for k in RED_FLAGS) \
        + "".join(f"{k:>7s}" for k in TALLIES)
    print(header)
    for log in logs:
        text = log.read_text(encoding="utf-8", errors="replace")
        counts = {k: text.count(pat) for k, pat in RED_FLAGS.items()}
        tallies = {k: text.count(pat) for k, pat in TALLIES.items()}
        red += sum(counts.values())
        row = f"  {log.stem:14s}" + "".join(f"{counts[k]:7d}" for k in RED_FLAGS) \
            + "".join(f"{tallies[k]:7d}" for k in TALLIES)
        print(row)
    if red:
        print("\n  !! red flags nonzero — see guide 7.7 for the action per flag")

    # progress freshness: newest benchmark_progress.log across current runs
    print("\n-- progress freshness")
    prog = sorted((paths.results_root()).glob("*_benchmark_*/benchmark_progress.log"),
                  key=lambda p: p.stat().st_mtime)
    if not prog:
        print("  no benchmark_progress.log found")
    else:
        now = time.time()
        for p in prog[-4:]:
            age_min = (now - p.stat().st_mtime) / 60
            flag = "" if age_min <= stale_minutes else \
                f"  <-- stale (> {stale_minutes:.0f}m): run may be stuck or finished"
            print(f"  {p.parent.name}: last write {age_min:5.1f}m ago{flag}")

    print(f"\n== {'CLEAN' if red == 0 else f'{red} red-flag hit(s)'} ==")
    return 0 if red == 0 else 1
