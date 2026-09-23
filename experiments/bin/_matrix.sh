# ---------------------------------------------------------------------------
# _matrix.sh — the machinery every launch shares.
#
# Sourced by launch.sh, which is the single launcher for every profile:
# comparison, ablation, tune and canary. Those were three separate scripts, two
# of which differed only in configuration while the third re-implemented ~120
# lines of this file rather than sourcing it — so the two copies of slot
# resolution could drift apart with nothing to notice.
#
# What differs between profiles is exported by `isd-exp run <experiment>` from
# experiment.toml, which is also what removed a real hazard: this file used to
# source .env and let it override an experiment's own identity, so a stray
# DATASET=train_10 from a tuning session would silently run an official
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
#   JUDGE_AFTER_RUN        1 = each run is judged (LLM judge + alignment) once generated
#   _ISD_EXPERIMENT_CONFIG  the declaration the child re-reads
#   _ALIGNMENT_JUDGE_ARM_LIST  the declared alignment arms, for the plan
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
# The interpreter every run is generated in. ONE environment holds both sides
# -- isd-exp and the seven agents -- so this is the same one `isd-exp` itself
# runs in, and `bench.bench_python()` resolves to the same place. A bare
# `python` would instead inherit whichever interpreter happens to be active,
# and when that is the wrong one the failure is an ImportError deep inside an
# agent registry, which reads like an agent bug rather than an install one.
BENCH_PYTHON="${ISD_BENCH_PYTHON:-$EXP_ROOT/.venv/bin/python}"
[ -x "$BENCH_PYTHON" ] || {
    echo "No interpreter at $BENCH_PYTHON" >&2
    echo "  Create it:  python3 -m venv $EXP_ROOT/.venv" >&2
    echo "              $EXP_ROOT/.venv/bin/pip install -e '$EXP_ROOT[dev]'" >&2
    echo "              $EXP_ROOT/isd-exp doctor --fix" >&2
    exit 1
}
cd "$EXP_ROOT" || exit 1

# .env is the right place for CREDENTIALS and pod endpoints, and the wrong place
# to decide WHAT an official experiment runs. A tuning session leaves
# DATASET=train_10, AGENTS=<two agents>, RUN_TAGS=tune1 sitting in .env, and
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

# Per-slot defaults come from experiment.toml, exported by `isd-exp run
# <experiment>` before this file is sourced. Nothing about the ladder is written here:
# the rungs, their model ids and their API-key env names are configuration, so
# running a different ladder is a config edit rather than a patch to this file.
# That includes the endpoints: `base_urls` on the rung is where a slot's URLs
# are written, and the launcher exports them under the plural name below.

slot_upper() {
    echo "$1" | tr '[:lower:]-' '[:upper:]_'
}

# A slot may be served by SEVERAL endpoints of the same model: `base_urls` on
# the rung takes a list and the agents round-robin across them
# (shared/llm/config.py::resolve_base_url).
#
# _<SLOT>_AGENT_MODEL_BASE_URLS is what `isd-exp run <experiment>` exports out of
# experiment.toml, and it is read FIRST: the underscore is what puts it out of
# reach of the `source .env` above. A stale endpoint line in .env -- especially
# an EMPTY one left behind by an earlier tool -- would otherwise take back the
# declared URL and send the rung nowhere, with nothing but an empty flag in the
# printed command to show for it. The plain names are still honoured for a slot
# the declaration says nothing about.
#
# Fold whatever won into the singular so everything downstream stays unchanged,
# and strip whitespace: the value is interpolated unquoted into the tmux command
# string below, so a space would split it into two arguments.
matrix_resolve_slots() {
    for slot in $_SLOTS_LIST; do
        upper=$(slot_upper "$slot")

        # API_SPEC / NAME / API_KEY_ENVS: the declaration wins outright. A
        # leftover NAME in .env would otherwise run the ladder under a model
        # experiment.toml never named, and the freeze manifest -- which hashes
        # experiment.toml -- would attest to a model that never ran.
        for _suffix in API_SPEC NAME API_KEY_ENVS; do
            declared_var="_${upper}_AGENT_MODEL_${_suffix}"
            plain_var="${upper}_AGENT_MODEL_${_suffix}"
            if [[ -n "${!declared_var:-}" ]]; then
                printf -v "$plain_var" '%s' "${!declared_var}"
            fi
        done

        declared_var="_${upper}_AGENT_MODEL_BASE_URLS"
        plural_var="${upper}_AGENT_MODEL_BASE_URLS"
        single_var="${upper}_AGENT_MODEL_BASE_URL"
        _urls="${!declared_var:-${!plural_var:-${!single_var:-}}}"
        printf -v "$single_var" '%s' "${_urls//[[:space:]]/}"
    done
    unset _suffix

    # Fail fast: a slot with no endpoint would launch a session whose every
    # model call fails, and report hours later as a run of agent failures.
    _missing_base_url=""
    for slot in $_SLOTS_LIST; do
        upper=$(slot_upper "$slot")
        base_url_var="${upper}_AGENT_MODEL_BASE_URL"
        if [[ -z "${!base_url_var:-}" ]]; then
            _missing_base_url="${_missing_base_url} ${slot}"
        fi
    done
    if [[ -n "$_missing_base_url" ]]; then
        # A dry run assembles the command and prints it; there is no invocation
        # for an empty expansion to corrupt, and the plan is worth seeing before
        # the endpoints are up. Every other path stops here.
        if [[ "${DRY_RUN:-0}" == "1" ]]; then
            echo "NOTE: no serving BASE_URL yet for slot(s):${_missing_base_url}" >&2
            return 0
        fi
        echo "ERROR: no serving BASE_URL set for slot(s):${_missing_base_url}" >&2
        echo "Bring the endpoints up (see docs/guides/benchmark_guides.md), then declare them" >&2
        echo "as base_urls on the matching [[serving.slots]] table in experiment.toml." >&2
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
    # The evaluator separates the credentials of ONE judge with `|` inside a
    # `,`-separated list of judges. Both are just separators here: every name in
    # the value has to reach the child, whichever judge it belongs to.
    local IFS=','
    for env_name in ${1//|/,}; do
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
    register_key_envs "${JUDGE_MODEL_API_KEY_ENVS:-}"
    # The declared roster, which travels under an underscored name so .env
    # cannot take it back.
    register_key_envs "${_JUDGE_MODEL_API_KEY_ENV:-}"
    register_key_envs "${_JUDGE_MODEL_API_KEY_ENVS:-}"
}


# Export the slot env vars so the manifest's python sees them: a rung's model
# and api_spec may come from experiment.toml alone, in which case they are plain
# shell variables in THIS process and nothing below inherits them.
matrix_export_slots() {
    for slot in $_SLOTS_LIST; do
        upper=$(slot_upper "$slot")
        for suffix in API_SPEC BASE_URL NAME API_KEY_ENVS; do
            export "${upper}_AGENT_MODEL_${suffix}"
        done
        export "${upper}_RATE_LIMIT"
    done
}


# What the run costs, in the units the banner and the manifest both count in.
# Computed unconditionally: a profile that skips the cost prompt still launches
# through matrix_launch, which prints these.
matrix_counts() {
    NUM_SLOTS=$(echo "$_SLOTS_LIST" | wc -w | tr -d ' ')
    NUM_RUNS=$(echo "$_RUN_TAGS_LIST" | wc -w | tr -d ' ')
    NUM_AGENTS=$(echo "${AGENTS//,/ }" | wc -w | tr -d ' ')
    # The splits live in the BENCHMARK tree -- paths.scenarios_dir() says so.
    # This file cd's to EXP_ROOT, so the path has to be absolute: a bare
    # "scenarios/..." counts zero here and stops every real launch.
    _scenario_dir="$BENCH_ROOT/scenarios/${DATASET}"
    NUM_SCENARIOS=$(ls "$_scenario_dir"/*.json 2>/dev/null | wc -l | tr -d ' ')
    if [[ -z "$NUM_SCENARIOS" || "$NUM_SCENARIOS" == "0" ]]; then
        # Same rule as a missing BASE_URL: a dry run reports it and carries on,
        # because nothing is about to read the split.
        if [[ "${DRY_RUN:-0}" == "1" ]]; then
            echo "NOTE: no scenarios in ${_scenario_dir}/ yet" >&2
            NUM_SCENARIOS=0
            return 0
        fi
        echo "ERROR: no scenarios in ${_scenario_dir}/" >&2
        exit 1
    fi
}


# An UPPER BOUND on one slot's concurrent model calls, which is what its
# endpoint has to absorb: scenarios at once x agents at once x the proposed
# system's Developers at once. Every agent is counted as fanning out, so the
# bound is loose when most of the roster is a baseline. The three tables are
# copies: scenarios and agents from runner/llm.py::RATE_PRESETS, the Developer
# gate from the adapter's LLM_CONCURRENCY_BY_RATE_LIMIT. They are
# printed for sizing, never enforced, so a drift misstates a number on screen
# and changes nothing that runs.
matrix_peak_calls() {
    local scen agents gate
    case "$1" in
        conservative) scen=2;  agents=2;  gate=2 ;;
        moderate)     scen=4;  agents=3;  gate=3 ;;
        aggressive)   scen=8;  agents=7;  gate=4 ;;
        turbo)        scen=15; agents=10; gate=6 ;;
        *) echo "?"; return 0 ;;
    esac
    (( agents > NUM_AGENTS )) && agents=$NUM_AGENTS
    (( scen > NUM_SCENARIOS )) && scen=$NUM_SCENARIOS
    local workers="${_HARNESS_FANOUT_WORKERS:-1}"
    (( workers > gate )) && workers=$gate
    echo $(( scen * agents * workers ))
}

matrix_confirm() {
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
        rate_var="${upper}_RATE_LIMIT"
        echo "    - ${slot}: ${!name_var} (rate=${!rate_var:-$RATE_LIMIT}," \
             "peak ≲ $(matrix_peak_calls "${!rate_var:-$RATE_LIMIT}") calls in flight)"
    done
    echo "  Developer workers: ${_HARNESS_FANOUT_WORKERS:-unset (1)} ([harness].fanout_workers)"
    echo "  Development:       ${_HARNESS_DEVELOPMENT_MODE:-unset (light)} ([harness].development_mode)"
    echo ""
    echo "  !! WARNING: this launches ~$((NUM_SLOTS * NUM_RUNS)) full benchmark runs"
    if [[ "${JUDGE_AFTER_RUN:-0}" == "1" ]]; then
        echo "  !! (~$((NUM_SLOTS * NUM_RUNS * NUM_AGENTS * NUM_SCENARIOS)) agent generations, then LLM judge calls)."
    else
        echo "  !! (~$((NUM_SLOTS * NUM_RUNS * NUM_AGENTS * NUM_SCENARIOS)) agent generations; judging is a later step)."
    fi
    echo "  !! This costs REAL MONEY and takes MANY HOURS."
    echo "  !! Also billing GPU time per endpoint on top of this."
    echo "=============================================================="
    read -r -p "Type 'yes' to launch: " CONFIRM
    if [[ "$CONFIRM" != "yes" ]]; then
        echo "Aborted. Nothing launched."
        exit 1
    fi
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
    JUDGE_DECLARED="${_JUDGE_MODEL_NAMES:+1}" \
    JUDGE_MODEL_NAMES="${_JUDGE_MODEL_NAMES:-${JUDGE_MODEL_NAMES:-}}" \
    JUDGE_MODEL_PROVIDER="${_JUDGE_MODEL_PROVIDER:-${JUDGE_MODEL_PROVIDER:-}}" \
    JUDGE_MODEL_PROVIDERS="${_JUDGE_MODEL_PROVIDERS:-${JUDGE_MODEL_PROVIDERS:-}}" \
    JUDGE_MODEL_BASE_URLS="${_JUDGE_MODEL_BASE_URLS:-${JUDGE_MODEL_BASE_URLS:-}}" \
    JUDGE_MODEL_API_KEY_ENVS="${_JUDGE_MODEL_API_KEY_ENVS:-${JUDGE_MODEL_API_KEY_ENVS:-}}" \
    AGENT_MODEL_CONTEXT_WINDOW="${_AGENT_MODEL_CONTEXT_WINDOW:-}" \
    AGENT_MODEL_MAX_OUTPUT_TOKENS="${_AGENT_MODEL_MAX_OUTPUT_TOKENS:-}" \
    AGENT_MODEL_STREAMING="${_AGENT_MODEL_STREAMING:-}" \
    AGENT_MODEL_THINKING_BUDGET="${_AGENT_MODEL_THINKING_BUDGET:-}" \
    AGENT_MODEL_TEMPERATURE="${_AGENT_MODEL_TEMPERATURE:-}" \
    HARNESS_FANOUT_WORKERS="${_HARNESS_FANOUT_WORKERS:-}" \
    HARNESS_DEVELOPMENT_MODE="${_HARNESS_DEVELOPMENT_MODE:-}" \
    python3 - "$manifest" <<'PYEOF'
import json, os, sys


def _judge_models():
    """The roster, index-aligned exactly as the evaluator reads it."""
    names = [m for m in os.environ.get("JUDGE_MODEL_NAMES", "").split(",") if m]
    def at(var, idx):
        parts = os.environ.get(var, "").split(",")
        return parts[idx] if idx < len(parts) else ""
    return [
        {
            "name": name,
            # Blank when the roster names no per-judge provider: the evaluator
            # then derives each label from the model slug, and filling the
            # profile in here would record one no report carries.
            "provider": at("JUDGE_MODEL_PROVIDERS", i),
            "base_url": at("JUDGE_MODEL_BASE_URLS", i),
            "api_key_envs": at("JUDGE_MODEL_API_KEY_ENVS", i),
        }
        for i, name in enumerate(names)
    ]


slots = []
for slot in os.environ["SLOTS"].split():
    upper = slot.upper().replace("-", "_")
    slots.append({
        "slot": slot,
        "model": os.environ.get(f"{upper}_AGENT_MODEL_NAME", ""),
        "api_spec": os.environ.get(f"{upper}_AGENT_MODEL_API_SPEC", ""),
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
    # Which judge scored this run, in enough detail to answer the question
    # without re-reading a config that may have moved on. `declared_in_config`
    # separates a roster the experiment declared from one the environment
    # happened to be carrying -- only the first is fingerprinted.
    "judge": {
        "declared_in_config": bool(os.environ.get("JUDGE_DECLARED")),
        "provider": os.environ.get("JUDGE_MODEL_PROVIDER", ""),
        "models": _judge_models(),
    },
    "serving": {
        "context_window": os.environ.get("AGENT_MODEL_CONTEXT_WINDOW", ""),
    },
    "generation": {
        "max_output_tokens": os.environ.get("AGENT_MODEL_MAX_OUTPUT_TOKENS", ""),
        "streaming": os.environ.get("AGENT_MODEL_STREAMING", ""),
        "thinking_budget": os.environ.get("AGENT_MODEL_THINKING_BUDGET", ""),
        "temperature": os.environ.get("AGENT_MODEL_TEMPERATURE", ""),
    },
    "harness": {
        "fanout_workers": os.environ.get("HARNESS_FANOUT_WORKERS", ""),
        "development_mode": os.environ.get("HARNESS_DEVELOPMENT_MODE", ""),
    },
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

# The command one slot's tmux session runs: `isd-exp run <experiment>
# --foreground` once per run tag, for this slot. The run reads the declaration
# itself -- the rung's model and endpoints, the serving limits, the judge
# roster -- so none of them travels through this string. What does is only what
# a launch may override for this invocation: the slot, the tag, the roster, the
# rate preset, and whether to judge.
#
# Every value below is expanded by THIS shell and single-quoted, so an empty
# one becomes a present-but-empty argument instead of disappearing and shifting
# the next flag's value onto the wrong flag. The declaration's path is an
# assignment prefix rather than an export: a tmux server that is already
# running gives a new session its own environment, not this one.
#
# Built here rather than inline in matrix_launch so a dry run can print the
# command that would actually run.
matrix_child_command() {
    local slot="$1" log_file="$2"
    local upper rate_var slot_rate judge_flag=""
    upper=$(slot_upper "$slot")
    rate_var="${upper}_RATE_LIMIT"
    slot_rate="${!rate_var:-$RATE_LIMIT}"
    [[ "${JUDGE_AFTER_RUN:-0}" == "1" ]] && judge_flag=" --judge"

    # Real newlines and backslash continuations, not one line joined by `;`:
    # the dry run prints this string as it is, and tmux hands the same string
    # to `sh -c`, which reads it the same way. What a reader checks is what runs.
    printf '%s' "cd '$EXP_ROOT' || exit 1
source '$ENV_FILE' 2>/dev/null || true
export RESULTS_DIR='$RESULTS_ROOT'
for tag in $_RUN_TAGS_LIST; do
    echo \"=== ${slot} run \$tag starting: \$(date) ===\"
    ISD_EXPERIMENT_CONFIG='$_ISD_EXPERIMENT_CONFIG' \\
    '$BENCH_PYTHON' -m isd_experiments.cli \\
        run '$EXPERIMENT' --foreground \\
        --slots '$slot' \\
        --tags \"\$tag\" \\
        --agents '$AGENTS' \\
        --rate-limit '$slot_rate'$judge_flag \\
        2>&1 | tee -a '$log_file'
    echo \"=== ${slot} run \$tag finished: \$(date) ===\"
done
echo 'Slot done!'
read"
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
        name_var="${upper}_AGENT_MODEL_NAME"
        rate_var="${upper}_RATE_LIMIT"
        slot_rate="${!rate_var:-$RATE_LIMIT}"

        session="${SESSION_PREFIX}-${slot}"
        log_file="$log_dir/${slot}.log"

        echo "[${i}/${NUM_SLOTS}] ${slot}: ${!name_var} (rate=$slot_rate) x runs [$_RUN_TAGS_LIST]..."

        tmux new-session -d -s "$session" "$(matrix_child_command "$slot" "$log_file")"
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
    if [[ -n "${POOL_HINT:-}" ]]; then
        echo "After all runs finish, pool with:"
        echo "  $POOL_HINT"
    fi
}
