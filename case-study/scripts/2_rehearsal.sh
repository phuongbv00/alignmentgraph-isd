#!/bin/bash
# RQ2 case study - Dress Rehearsal (no network)
# Runs all four conditions with canned fake models to sanity-check the
# harness/react mechanics, prints metrics, then wipes the fake artifacts so
# a subsequent real run starts clean (harness conditions assert init->v1,
# so leftover memory/ from a fake run would fail that assertion).

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BASE_DIR="$( dirname "$SCRIPT_DIR" )"   # case-study/
PY="$BASE_DIR/.venv/bin/python"

cd "$BASE_DIR"

echo "=========================================="
echo "  Dress Rehearsal (--fake-llm, no network)"
echo "=========================================="

"$PY" run_case_study.py --conditions all --fake-llm
"$PY" compute_metrics.py

echo ""
echo "Rehearsal metrics written to results/metrics.{csv,md} (tokens/hash-based"
echo "localities read 0 with --fake-llm; check cascade_scope, touched_locality,"
echo "unchanged_phases instead)."
echo ""
echo "Wiping fake-run artifacts (memory/, results/) so a real run starts clean..."
rm -rf memory results

echo "Done. Ready for ./scripts/3_run_case_study_test.sh or ./scripts/4_run_case_study.sh"
