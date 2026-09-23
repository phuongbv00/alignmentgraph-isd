#!/bin/bash
# ---------------------------------------------------------------------------
# launch.sh — the one launcher, driven by a profile.
#
# Replaces three near-identical scripts (the ladder comparison, the ablation,
# and the tuning launcher). The first two differed only in configuration; the
# third re-implemented ~120 lines of the shared machinery it could have sourced,
# so the two copies of slot resolution could drift apart silently.
#
# Everything that differs between experiments is a variable the caller exports,
# and `isd-exp <stage> run` is what exports them — the profile comes from
# experiment.toml, so what an official run consists of is declared rather than
# typed at a prompt.
#
# Required from the caller:
#   EXPERIMENT EXPERIMENT_TITLE DATASET CANONICAL_DATASET AGENTS
#   RATE_LIMIT _SLOTS_LIST _RUN_TAGS_LIST SESSION_PREFIX POOL_HINT
# Optional:
#   CONFIRM=0     skip the cost prompt (tuning and canary runs)
#   MANIFEST=0    skip the manifest (not an official experiment)
#   DRY_RUN=1     print the plan and exit without launching
# ---------------------------------------------------------------------------
set -u

source "$(dirname "$0")/_matrix.sh"

: "${EXPERIMENT:?launch.sh needs a profile — use \`isd-exp <stage> run\`}"
: "${DATASET:?}" "${AGENTS:?}" "${SESSION_PREFIX:?}"
CONFIRM="${CONFIRM:-1}"
MANIFEST="${MANIFEST:-1}"
DRY_RUN="${DRY_RUN:-0}"

matrix_resolve_slots
matrix_export_slots
matrix_export_keys
matrix_counts
matrix_judge_flags
matrix_serving_prefix

if [ "$DRY_RUN" = "1" ]; then
    echo "== DRY RUN — ${EXPERIMENT_TITLE:-$EXPERIMENT} =="
    echo "  dataset : $DATASET (canonical: ${CANONICAL_DATASET:-$DATASET})"
    echo "  agents  : $AGENTS"
    echo "  slots   : $_SLOTS_LIST"
    echo "  tags    : $_RUN_TAGS_LIST"
    echo "  results : $RESULTS_ROOT"
    echo "  python  : $BENCH_PYTHON"
    echo "  bench   : $BENCH_ROOT"
    echo "  env     : $ENV_FILE"
    echo "  judge   : ${JUDGE_FLAGS:-(not declared — the environment answers)}"
    echo "  serving : ${SERVING_PREFIX:-(not declared — benchmark defaults apply)}"
    echo "  pool    : ${POOL_HINT:-}"
    for slot in $_SLOTS_LIST; do
        rate_var="$(slot_upper "$slot")_RATE_LIMIT"
        echo "  peak    : ${slot} ≲ $(matrix_peak_calls "${!rate_var:-$RATE_LIMIT}") model calls in flight (rate=${!rate_var:-$RATE_LIMIT})"
    done
    echo ""
    # The command itself, for the first slot: what the flags and the prefix
    # actually come out as is not checkable from a summary of them.
    echo "  command (first slot):"
    matrix_child_command "${_SLOTS_LIST%% *}" "$RESULTS_ROOT/<slot>.log"
    echo ""
    echo ""
    echo "(nothing launched)"
    exit 0
fi

[ "$CONFIRM" = "1" ] && matrix_confirm

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_DIR="$RESULTS_ROOT/${EXPERIMENT}_${TIMESTAMP}"
mkdir -p "$LOG_DIR"

BENCH_COMMIT=$(git -C "$BENCH_ROOT" rev-parse HEAD 2>/dev/null || echo "unknown")
BENCH_DIRTY=$(git -C "$BENCH_ROOT" status --porcelain 2>/dev/null | head -1 | grep -q . && echo "true" || echo "false")
PKG_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
PKG_DIRTY=$(git status --porcelain 2>/dev/null | head -1 | grep -q . && echo "true" || echo "false")

if [ "$MANIFEST" = "1" ]; then
    matrix_write_manifest "$LOG_DIR/${EXPERIMENT}_manifest.json"
fi

matrix_launch "$LOG_DIR"
