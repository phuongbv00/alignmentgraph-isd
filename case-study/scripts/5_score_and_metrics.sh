#!/bin/bash
# RQ2 case study - Judge Scoring + Metrics
# Scores every session with the benchmark's LLM-judge evaluator (needs the
# isd-agent-benchmark venv + judge credentials), then recomputes metrics.

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BASE_DIR="$( dirname "$SCRIPT_DIR" )"   # case-study/
REPO_ROOT="$( dirname "$BASE_DIR" )"
BENCH_PY="$REPO_ROOT/isd-agent-benchmark/venv/bin/python"
PY="$BASE_DIR/.venv/bin/python"

cd "$REPO_ROOT"
source case-study/.env 2>/dev/null || true

if [ ! -x "$BENCH_PY" ]; then
    echo "ERROR: $BENCH_PY not found. Run isd-agent-benchmark/scripts/1_setup.sh first." >&2
    exit 1
fi

FORCE_FLAG=""
if [ "$FORCE" = "1" ]; then
    FORCE_FLAG="--force"
fi

echo "=========================================="
echo "  Judge Scoring (benchmark venv)"
echo "  Judge: ${JUDGE_MODEL_NAMES:-${JUDGE_MODEL_NAME:-<unset, evaluator defaults apply>}}"
echo "=========================================="

"$BENCH_PY" case-study/score_alignment.py $FORCE_FLAG

echo ""
echo "=========================================="
echo "  Metrics"
echo "=========================================="

"$PY" case-study/compute_metrics.py

echo ""
echo "Done. See case-study/results/metrics.{csv,md}."
