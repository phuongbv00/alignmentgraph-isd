#!/bin/bash
# RQ2 case study - Full Run (real model, all programs/conditions)
# Refuses to run over leftover memory/results (harness conditions assert
# init->v1 per program). Pass RESET=1 to wipe them automatically first.

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BASE_DIR="$( dirname "$SCRIPT_DIR" )"   # case-study/
PY="$BASE_DIR/.venv/bin/python"

cd "$BASE_DIR"
source .env 2>/dev/null || true

PROGRAMS="${PROGRAMS:-}"           # empty = all
CONDITIONS="${CONDITIONS:-all}"
ABLATION="${ABLATION:-case_study}"

if [ -d memory ] || [ -d results ]; then
    if [ "$RESET" = "1" ]; then
        echo "RESET=1: wiping existing memory/ and results/..."
        rm -rf memory results
    else
        echo "ERROR: memory/ or results/ already exist. Harness conditions assert" >&2
        echo "init->v1, so leftover state from a previous run will fail that" >&2
        echo "assertion. Re-run with RESET=1 to wipe them, or remove manually." >&2
        exit 1
    fi
fi

echo "=========================================="
echo "  Full Run: programs=${PROGRAMS:-all} conditions=$CONDITIONS ablation=$ABLATION"
echo "  Model: ${AGENT_MODEL_NAME:-<unset, pass --model-name or set AGENT_MODEL_NAME>}"
echo "=========================================="

ARGS=(--conditions "$CONDITIONS" --ablation "$ABLATION")
if [ -n "$PROGRAMS" ]; then
    ARGS+=(--programs "$PROGRAMS")
fi

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_DIR="results_logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/run_${TIMESTAMP}.log"

"$PY" run_case_study.py "${ARGS[@]}" 2>&1 | tee "$LOG_FILE"

echo ""
echo "=========================================="
echo "  Run complete. Log: $LOG_FILE"
echo "=========================================="
echo ""
echo "Next: ./scripts/5_score_and_metrics.sh"
