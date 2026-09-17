# ---------------------------------------------------------------------------
# _matrix.sh — the machinery every launch shares.
#
# Sourced by launch.sh, which is the single launcher for every profile:
# comparison, ablation, tune and canary. Those were three separate scripts, two
# of which differed only in configuration while the third re-implemented ~120
# lines of this file rather than sourcing it — so the two copies of slot
# resolution could drift apart with nothing to notice.
#
# What differs between profiles is exported by `isd-exp <stage> run` from
# experiment.toml, which is also what removed a real hazard: this file used to
# source .env and let it override an experiment's own identity, so a stray
# DATASET=train_30 from a tuning session would silently run an official
# experiment on the wrong split.
#
# Caller contract — set these before calling, then call the functions in order:
#   EXPERIMENT        profile name, goes in the manifest and the run dir
#   EXPERIMENT_TITLE  banner line
#   DATASET           scenarios/<DATASET>
#   AGENTS            comma-separated agent ids
#   RATE_LIMIT        global default preset; <SLOT>_RATE_LIMIT overrides per slot
#   _SLOTS_LIST       space-separated model slots
#   _RUN_TAGS_LIST    space-separated run tags (one tag = one run per cell)
#   SESSION_PREFIX    tmux session name prefix
#   POOL_HINT         the pooling command to print when the launch finishes
#
# SOURCE THIS FIRST, before the caller's own config block. It cd's to the repo
# root and sources .env, and .env is allowed to override an experiment's
# defaults — so the caller's `${DATASET:-test_90}` has to be evaluated AFTER
# .env has been read, not before. Sourcing it last inverts that and silently
# runs an official experiment on whatever dataset a tuning session left behind.
#
#   matrix_resolve_slots   fold *_BASE_URLS into *_BASE_URL, fail on missing
#   matrix_export_keys     export every API key env the slots/judge reference
#   matrix_confirm         cost banner + "type yes"
#   matrix_write_manifest  <path>
#   matrix_launch          <log_dir>   one tmux session per slot
# ---------------------------------------------------------------------------

# Anchors, resolved from THIS file so every caller agrees regardless of depth.
EXP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BENCH_ROOT="${ISD_BENCH_ROOT:-$(cd "$EXP_ROOT/../isd-agent-benchmark" && pwd)}"
RESULTS_ROOT="${RESULTS_DIR:-$EXP_ROOT/results}"
# The interpreter that can import the seven agents. `isd-exp` runs in a lighter
# venv with no inference stack, so a bare `python run_benchmark.py` would
# inherit the wrong one and fail deep inside an agent registry -- which reads
# like an agent bug rather than a venv bug.
BENCH_PYTHON="${ISD_BENCH_PYTHON:-$BENCH_ROOT/venv/bin/python}"
[ -x "$BENCH_PYTHON" ] || BENCH_PYTHON="$BENCH_ROOT/.venv/bin/python"
[ -x "$BENCH_PYTHON" ] || { echo "No benchmark interpreter at $BENCH_PYTHON" >&2; exit 1; }
cd "$EXP_ROOT" || exit 1

# .env is the right place for CREDENTIALS and pod endpoints, and the wrong place
# to decide WHAT an official experiment runs. A tuning session leaves
# DATASET=train_30, AGENTS=<two agents>, RUN_TAGS=tune1 sitting in .env, and
# with a plain `source .env` those silently win over the experiment's own
# defaults -- the ablation would launch on the tuning split with its arms
# missing, and nothing would say so except a banner line nobody re-reads.
#
# So: an override typed for THIS invocation (`DATASET=x ./script`) wins, and a
# leftover in .env does not. Snapshot the caller's environment first, source
# .env for everything else, then put the snapshot back -- unsetting the ones
# that were not set inline, so the caller's `${VAR:-default}` sees its default.
_MATRIX_INLINE_VARS="DATASET AGENTS RUN_TAGS RATE_LIMIT LADDER_SLOTS ABLATION_SLOTS"
for _v in $_MATRIX_INLINE_VARS; do
    eval "_MATRIX_PRE_${_v}=\"\${${_v}:-}\""
done
ENV_FILE="$EXP_ROOT/.env"
[ -f "$ENV_FILE" ] || ENV_FILE="$BENCH_ROOT/.env"
source "$ENV_FILE" 2>/dev/null || true
for _v in $_MATRIX_INLINE_VARS; do
    eval "_pre=\"\${_MATRIX_PRE_${_v}}\""
    if [[ -n "$_pre" ]]; then
        eval "${_v}=\"\$_pre\""
    else
        unset "$_v"
    fi
done
unset _v _pre

# Per-slot defaults come from experiment.toml, exported by `isd-exp <stage>
# run` before this file is sourced. Nothing about the ladder is written here:
# the rungs, their model ids and their API-key env names are configuration, so
# running a different ladder is a config edit rather than a patch to this file.
# The managed block in .env (written by `isd-exp serve sync-agents`) then
# overrides the BASE_URLs with what each endpoint actually serves.

slot_upper() {
    echo "$1" | tr '[:lower:]-' '[:upper:]_'
}

# A slot may be served by SEVERAL pods of the same model: set
# <SLOT>_AGENT_MODEL_BASE_URLS to a comma-separated list and the agents
# round-robin across them (shared/llm/config.py::resolve_base_url), the same
# way <SLOT>_EMBED_BASE_URLS works for the encoder. Fold the plural into the
# singular here so everything downstream stays unchanged, and strip whitespace:
# the value is interpolated unquoted into the tmux command string below, so a
# space would split it into two arguments.
matrix_resolve_slots() {
    for slot in $_SLOTS_LIST; do
        upper=$(slot_upper "$slot")
        plural_var="${upper}_AGENT_MODEL_BASE_URLS"
        single_var="${upper}_AGENT_MODEL_BASE_URL"
        _urls="${!plural_var:-${!single_var:-}}"
        printf -v "$single_var" '%s' "${_urls//[[:space:]]/}"
    done

    # Fail fast: an empty *_BASE_URL would otherwise vanish from the unquoted
    # run_benchmark.py invocation below (bash drops empty unquoted expansions),
    # silently shifting --agent-model-base-url's value onto the next flag.
    _missing_base_url=""
    for slot in $_SLOTS_LIST; do
        upper=$(slot_upper "$slot")
        base_url_var="${upper}_AGENT_MODEL_BASE_URL"
        if [[ -z "${!base_url_var:-}" ]]; then
            _missing_base_url="${_missing_base_url} ${slot}"
        fi
    done
    if [[ -n "$_missing_base_url" ]]; then
        echo "ERROR: no serving BASE_URL set for slot(s):${_missing_base_url}" >&2
        echo "Bring the endpoints up (see docs/benchmark_guides.md), then write them into .env." >&2
        echo "With provider=\"static\" a base_url in experiment.toml is enough. Or sync them:" >&2
        echo "  ./isd-exp serve sync-agents   (from $EXP_ROOT)" >&2
        exit 1
    fi
}

# Export every API key env referenced by any slot or the judge config so child
# tmux sessions inherit them.
# NOTE: no associative arrays here -- macOS ships bash 3.2 as /bin/bash (no
# `declare -A`), which combined with `set -u` turns a silently-broken assoc
# array into a hard "unbound variable" crash (see git history for details).
_exported_keys_list=""
register_key_envs() {
    local IFS=','
    for env_name in $1; do
        env_name="${env_name// /}"
        case " $_exported_keys_list " in
            *" $env_name "*) ;;
            *)
                if [[ -n "$env_name" ]]; then
                    export "$env_name"
                    _exported_keys_list="$_exported_keys_list $env_name"
                fi
                ;;
        esac
    done
}

matrix_export_keys() {
    for slot in $_SLOTS_LIST; do
        upper=$(slot_upper "$slot")
        key_envs_var="${upper}_AGENT_MODEL_API_KEY_ENVS"
        register_key_envs "${!key_envs_var:-}"
    done
    register_key_envs "${JUDGE_MODEL_API_KEY_ENV:-}"
}

matrix_confirm() {
    NUM_SLOTS=$(echo "$_SLOTS_LIST" | wc -w | tr -d ' ')
    NUM_RUNS=$(echo "$_RUN_TAGS_LIST" | wc -w | tr -d ' ')
    NUM_AGENTS=$(echo "${AGENTS//,/ }" | wc -w | tr -d ' ')
    NUM_SCENARIOS=$(ls "scenarios/${DATASET}"/*.json 2>/dev/null | wc -l | tr -d ' ')
    [[ -z "$NUM_SCENARIOS" || "$NUM_SCENARIOS" == "0" ]] && {
        echo "ERROR: no scenarios in scenarios/${DATASET}/" >&2; exit 1; }

    echo "=============================================================="
    echo "  ${EXPERIMENT_TITLE}"
    echo "=============================================================="
    echo "  Dataset:    $DATASET ($NUM_SCENARIOS scenarios)"
    # .env may legitimately override DATASET for a smoke run, so this is a
    # warning rather than a hard stop -- but an official experiment reported in
    # the paper runs on its canonical split, and a stale export is exactly how
    # that goes wrong without anyone noticing.
    if [[ -n "${CANONICAL_DATASET:-}" && "$DATASET" != "$CANONICAL_DATASET" ]]; then
        echo "  !! NOTE: ${EXPERIMENT} is defined on '${CANONICAL_DATASET}', not '${DATASET}'."
        echo "  !! Results from this launch are NOT the official ${EXPERIMENT}."
    fi
    echo "  Agents ($NUM_AGENTS): $AGENTS"
    echo "  Runs/cell:  $NUM_RUNS (tags: $_RUN_TAGS_LIST)"
    echo "  Rate limit: $RATE_LIMIT (global default; per-slot <SLOT>_RATE_LIMIT overrides)"
    echo "  Model slots ($NUM_SLOTS):"
    for slot in $_SLOTS_LIST; do
        upper=$(slot_upper "$slot")
        name_var="${upper}_AGENT_MODEL_NAME"
        provider_var="${upper}_AGENT_MODEL_PROVIDER"
        rate_var="${upper}_RATE_LIMIT"
        echo "    - ${slot}: ${!name_var} (provider=${!provider_var}, rate=${!rate_var:-$RATE_LIMIT})"
    done
    echo ""
    echo "  !! WARNING: this launches ~$((NUM_SLOTS * NUM_RUNS)) full benchmark runs"
    echo "  !! (~$((NUM_SLOTS * NUM_RUNS * NUM_AGENTS * NUM_SCENARIOS)) agent generations, plus judge calls)."
    echo "  !! This costs REAL MONEY and takes MANY HOURS."
    echo "  !! Also billing GPU time per endpoint on top of this."
    echo "=============================================================="
    read -r -p "Type 'yes' to launch: " CONFIRM
    if [[ "$CONFIRM" != "yes" ]]; then
        echo "Aborted. Nothing launched."
        exit 1
    fi

    # Export slot env quads (+ optional per-slot rate) so both the manifest
    # python and the tmux child shells see them (they may only be defined by
    # this file's defaults, not by .env, so they are plain shell vars).
    for slot in $_SLOTS_LIST; do
        upper=$(slot_upper "$slot")
        for suffix in PROVIDER BASE_URL NAME API_KEY_ENVS; do
            export "${upper}_AGENT_MODEL_${suffix}"
        done
        export "${upper}_RATE_LIMIT"
    done
}

# Manifest (M8 reproducibility): exact model IDs, dataset, agents, run tags,
# git commits of benchmark + alignmentgraph-isd package. This is the file the
# paper's reproducibility subsection promises, so it records the EXPERIMENT id
# too — each experiment is answered from its own manifest.
matrix_write_manifest() {
    local manifest="$1"
    MATRIX_TS="$TIMESTAMP" EXPERIMENT="$EXPERIMENT" DATASET="$DATASET" \
    AGENTS="$AGENTS" RUN_TAGS="$_RUN_TAGS_LIST" \
    RATE_LIMIT="$RATE_LIMIT" SLOTS="$_SLOTS_LIST" \
    BENCH_COMMIT="$BENCH_COMMIT" BENCH_DIRTY="$BENCH_DIRTY" \
    PKG_COMMIT="$PKG_COMMIT" PKG_DIRTY="$PKG_DIRTY" \
    JUDGE_MODEL_NAMES="${JUDGE_MODEL_NAMES:-}" JUDGE_MODEL_PROVIDER="${JUDGE_MODEL_PROVIDER:-}" \
    python3 - "$manifest" <<'PYEOF'
import json, os, sys

slots = []
for slot in os.environ["SLOTS"].split():
    upper = slot.upper().replace("-", "_")
    slots.append({
        "slot": slot,
        "model": os.environ.get(f"{upper}_AGENT_MODEL_NAME", ""),
        "provider": os.environ.get(f"{upper}_AGENT_MODEL_PROVIDER", ""),
        "base_url": os.environ.get(f"{upper}_AGENT_MODEL_BASE_URL", ""),
        "api_key_envs": os.environ.get(f"{upper}_AGENT_MODEL_API_KEY_ENVS", ""),
        "rate_limit": os.environ.get(f"{upper}_RATE_LIMIT") or os.environ["RATE_LIMIT"],
    })

manifest = {
    "experiment": os.environ["EXPERIMENT"],
    "timestamp": os.environ["MATRIX_TS"],
    "dataset": os.environ["DATASET"],
    "agents": os.environ["AGENTS"].split(","),
    "run_tags": os.environ["RUN_TAGS"].split(),
    "rate_limit": os.environ["RATE_LIMIT"],
    "model_slots": slots,
    "judge_models": [m for m in os.environ.get("JUDGE_MODEL_NAMES", "").split(",") if m],
    "judge_provider": os.environ.get("JUDGE_MODEL_PROVIDER", ""),
    "git": {
        "isd_agent_benchmark_commit": os.environ["BENCH_COMMIT"],
        "isd_agent_benchmark_dirty": os.environ["BENCH_DIRTY"] == "true",
        "master_thesis_commit": os.environ["PKG_COMMIT"],
        "master_thesis_dirty": os.environ["PKG_DIRTY"] == "true",
        "note": "master_thesis_commit covers the alignmentgraph-isd package "
                "(tracked directly in the parent monorepo).",
    },
    "run_dir_pattern": "results/{dataset}_benchmark_{model_safe}_{run_tag}_{timestamp}",
}
with open(sys.argv[1], "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2, ensure_ascii=False)
print(f"Manifest written: {sys.argv[1]}")
PYEOF
}

# One tmux session per model slot; slots run in PARALLEL, the run tags of a slot
# run SEQUENTIALLY inside its session (safe w.r.t. per-key rate limits).
matrix_launch() {
    local log_dir="$1"        # absolute: the child cd's elsewhere
    local i=0

    for slot in $_SLOTS_LIST; do
        tmux kill-session -t "${SESSION_PREFIX}-${slot}" 2>/dev/null
    done

    for slot in $_SLOTS_LIST; do
        i=$((i + 1))
        upper=$(slot_upper "$slot")
        provider_var="${upper}_AGENT_MODEL_PROVIDER"
        base_url_var="${upper}_AGENT_MODEL_BASE_URL"
        name_var="${upper}_AGENT_MODEL_NAME"
        key_envs_var="${upper}_AGENT_MODEL_API_KEY_ENVS"
        rate_var="${upper}_RATE_LIMIT"
        slot_rate="${!rate_var:-$RATE_LIMIT}"

        session="${SESSION_PREFIX}-${slot}"
        log_file="$log_dir/${slot}.log"

        echo "[${i}/${NUM_SLOTS}] ${slot}: ${!name_var} (rate=$slot_rate) x runs [$_RUN_TAGS_LIST]..."

        # The child runs in the BENCHMARK tree (run_benchmark.py lives there),
        # with the experiment's .env and results dir handed over explicitly.
        tmux new-session -d -s "$session" \
"cd '$BENCH_ROOT' || exit 1; \
source '$ENV_FILE' 2>/dev/null || true; \
export RESULTS_DIR='$RESULTS_ROOT'; \
for tag in $_RUN_TAGS_LIST; do \
    echo \"=== ${slot} run \$tag starting: \$(date) ===\"; \
    '$BENCH_PYTHON' run_benchmark.py \
        --dataset $DATASET \
        --agents $AGENTS \
        --rate-limit $slot_rate \
        --agent-model-provider ${!provider_var} \
        --agent-model-base-url ${!base_url_var} \
        --agent-model-name ${!name_var} \
        --agent-model-api-key-envs ${!key_envs_var} \
        --run-tag \$tag \
        2>&1 | tee -a $log_file; \
    echo \"=== ${slot} run \$tag finished: \$(date) ===\"; \
done; echo 'Slot done!'; read"
    done

    echo ""
    echo "=============================================================="
    echo "  ${NUM_SLOTS} ${SESSION_PREFIX} tmux sessions running (${NUM_RUNS} sequential run(s) each)"
    echo "=============================================================="
    echo ""
    echo "Attach:"
    for slot in $_SLOTS_LIST; do
        echo "  tmux attach -t ${SESSION_PREFIX}-${slot}"
    done
    echo ""
    echo "Logs:"
    for slot in $_SLOTS_LIST; do
        echo "  tail -f $log_dir/${slot}.log"
    done
    echo ""
    echo "Stop everything: tmux kill-server"
    echo ""
    echo "After all runs finish, pool with:"
    echo "  $POOL_HINT"
}
