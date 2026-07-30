#!/usr/bin/env bash
# Sync generated paper artifacts from the benchmark into docs/generated/.
#
#   isd-agent-benchmark/results/generated/   -->   docs/generated/
#     *.tex                                          (LaTeX \input targets)
#     stats_summary.md, stats_ablation.md,
#     stats_sensitivity.md                           (human-readable notes)
#     figures/*.{pdf,png}                            (for \includegraphics)
#
# The 09_/10_/11_/12_/14_ generator scripts write ONLY into the benchmark's
# results/generated/ (benchmark-local, gitignored); this script is the single
# copy step into docs. The paper references these via relative paths
# (e.g. ../../../generated/). Regenerate first:
#   cd isd-agent-benchmark
#   python scripts/alignmentgraph-isd-bench/09_gen_paper_tables.py
#   python scripts/alignmentgraph-isd-bench/10_gen_paper_figures.py --runs-glob 'results/test_90_benchmark_*_r*'
#   # ablation (if pooled_ablation.json exists):
#   python scripts/alignmentgraph-isd-bench/ablation/11_gen_ablation_tables.py
#   python scripts/alignmentgraph-isd-bench/ablation/12_gen_ablation_figures.py
#   # encoder sensitivity (if the pooled JSON carries alignment_sensitivity):
#   python scripts/alignmentgraph-isd-bench/14_gen_sensitivity_table.py
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"         # master-thesis/
SRC="$ROOT/isd-agent-benchmark/results/generated"
DST="$ROOT/docs/generated"

[ -d "$SRC" ] || { echo "ERROR: $SRC not found — run the generator scripts first." >&2; exit 1; }

mkdir -p "$DST/figures"
cp "$SRC"/*.tex "$SRC"/stats_summary.md "$DST"/
# Notes from pipelines that may not have run yet (ablation, encoder sweep);
# plain if-block: `[ ... ] && cp` would trip set -e when the file is absent
for note in stats_ablation.md stats_sensitivity.md bloom_validation.md \
            bloom_arms_validation.md; do
  if [ -f "$SRC/$note" ]; then
    cp "$SRC/$note" "$DST"/
  fi
done
# Per extension: a pdf-only or png-only figures dir would make the other glob
# match nothing, and an unmatched glob under set -e fails the whole script.
for ext in pdf png; do
  if compgen -G "$SRC/figures/*.$ext" > /dev/null; then
    cp "$SRC"/figures/*."$ext" "$DST/figures/"
  fi
done

echo "synced -> $DST"
ls "$DST"/*.tex "$DST"/stats_summary.md | sed "s|$ROOT/||"
echo "figures: $(ls "$DST/figures" | wc -l | tr -d ' ') files"
