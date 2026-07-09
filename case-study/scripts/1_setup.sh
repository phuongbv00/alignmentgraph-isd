#!/bin/bash
# RQ2 case study - Setup Script
# Creates case-study/.venv and installs alignmentgraph-isd + the react-isd
# baseline in editable mode (via uv, using the checked-in uv.lock).

set -e

echo "=========================================="
echo "  RQ2 Case Study Setup"
echo "=========================================="

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BASE_DIR="$( dirname "$SCRIPT_DIR" )"   # case-study/
REPO_ROOT="$( dirname "$BASE_DIR" )"

cd "$BASE_DIR"

if ! command -v uv >/dev/null 2>&1; then
    echo "ERROR: uv is required (https://docs.astral.sh/uv/). Install it and re-run." >&2
    exit 1
fi

echo "Syncing case-study/.venv (alignmentgraph-isd + react-isd-baseline, editable)..."
uv sync

echo ""
echo "Checking the benchmark venv used by score_alignment.py (step 4/5)..."
if [ -x "$REPO_ROOT/isd-agent-benchmark/venv/bin/python" ]; then
    echo "  OK: isd-agent-benchmark/venv found."
else
    echo "  WARNING: isd-agent-benchmark/venv not found."
    echo "  Run isd-agent-benchmark/scripts/1_setup.sh first if you plan to score sessions (step 5)."
fi

echo ""
echo "=========================================="
echo "  Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. (optional) create case-study/.env with AGENT_MODEL_* / JUDGE_MODEL_* for defaults/secrets"
echo "  2. Dress rehearsal (no network): ./scripts/2_rehearsal.sh"
echo "  3. Smoke test (real model, 1 program): ./scripts/3_run_case_study_test.sh"
echo "  4. Full run (real model, all programs/conditions): ./scripts/4_run_case_study.sh"
echo "  5. Score + metrics: ./scripts/5_score_and_metrics.sh"
