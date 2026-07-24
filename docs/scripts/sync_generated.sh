#!/usr/bin/env bash
# Sync generated paper artifacts from the benchmark into docs/generated/.
#
#   isd-agent-benchmark/results/generated/   -->   docs/generated/
#     *.tex, stats_summary.md, stats_ablation.md     (LaTeX \input targets + notes)
#     figures/*.{pdf,png}                            (for \includegraphics)
#
# The 8_* generator scripts write ONLY into the benchmark's results/generated/
# (benchmark-local, gitignored); this script is the single copy step into docs.
# The paper references these via relative paths (e.g. ../../../generated/).
# Regenerate first:
#   cd isd-agent-benchmark
#   python scripts/alignmentgraph-isd-bench/8_gen_paper_tables.py
#   python scripts/alignmentgraph-isd-bench/8_gen_paper_figures.py --runs-glob 'results/test_90_benchmark_*_r*'
#   # ablation (if pooled_ablation.json exists):
#   python scripts/alignmentgraph-isd-bench/ablation/8_gen_ablation_tables.py
#   python scripts/alignmentgraph-isd-bench/ablation/8_gen_ablation_figures.py
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"         # master-thesis/
SRC="$ROOT/isd-agent-benchmark/results/generated"
DST="$ROOT/docs/generated"

[ -d "$SRC" ] || { echo "ERROR: $SRC not found — run the 8_* generator scripts first." >&2; exit 1; }

mkdir -p "$DST/figures"
cp "$SRC"/*.tex "$SRC"/stats_summary.md "$DST"/
# ablation stats notes (only exists after the ablation pipeline has run);
# plain if-block: `[ ... ] && cp` would trip set -e when the file is absent
if [ -f "$SRC/stats_ablation.md" ]; then
  cp "$SRC/stats_ablation.md" "$DST"/
fi
if compgen -G "$SRC/figures/*" > /dev/null; then
  cp "$SRC"/figures/*.pdf "$SRC"/figures/*.png "$DST/figures/"
fi

echo "synced -> $DST"
ls "$DST"/*.tex "$DST"/stats_summary.md | sed "s|$ROOT/||"
echo "figures: $(ls "$DST/figures" | wc -l | tr -d ' ') files"
