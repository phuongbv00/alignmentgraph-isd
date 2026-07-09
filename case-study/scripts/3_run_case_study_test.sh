#!/bin/bash
# RQ2 case study - Smoke Test (real model, small scope)
# Runs one program (smallest: git-agile, 2 rounds) for one round, across all
# four conditions, against a real model. Use this to validate credentials and
# end-to-end wiring before committing to the full run.

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BASE_DIR="$( dirname "$SCRIPT_DIR" )"   # case-study/
PY="$BASE_DIR/.venv/bin/python"

cd "$BASE_DIR"
source .env 2>/dev/null || true

PROGRAM="${PROGRAM:-git-agile}"
CONDITIONS="${CONDITIONS:-all}"
ROUNDS_LIMIT="${ROUNDS_LIMIT:-1}"

if [ -d memory ] || [ -d results ]; then
    echo "ERROR: memory/ or results/ already exist. Harness conditions assert" >&2
    echo "init->v1, so leftover state from a previous run will fail. Remove" >&2
    echo "them first (rm -rf memory results) if you're OK discarding that run." >&2
    exit 1
fi

echo "=========================================="
echo "  Smoke Test: program=$PROGRAM conditions=$CONDITIONS rounds-limit=$ROUNDS_LIMIT"
echo "  Model: ${AGENT_MODEL_NAME:-<unset, pass --model-name or set AGENT_MODEL_NAME>}"
echo "=========================================="

"$PY" run_case_study.py \
  --programs "$PROGRAM" \
  --conditions "$CONDITIONS" \
  --rounds-limit "$ROUNDS_LIMIT"

"$PY" compute_metrics.py

echo ""
echo "Smoke test complete. Inspect results/ and results/metrics.md."
echo "Remove memory/ and results/ before running ./scripts/4_run_case_study.sh."
