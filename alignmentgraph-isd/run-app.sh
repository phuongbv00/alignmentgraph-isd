#!/usr/bin/env bash
#
# Run the demo web app: sync dependencies, build the UI, serve it.
#
#   ./run-app.sh                one process on one URL (for a demo)
#   ./run-app.sh --dev          two processes with hot reload (for development)
#   ./run-app.sh --sync-only    just bring the environment up to date
#
# Everything is idempotent, so re-running after a pull is the normal way to use
# it. See src/alignmentgraph_isd/server/README.md for the app itself.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

VENV=".venv"
WEBAPP="src/alignmentgraph_isd/webapp"
PORT=8000
# Not Vite's default 5173, which tends to already be taken by another project;
# a clash there is silent and sends you to the wrong app. See vite.config.ts.
UI_PORT=5273
MODE="demo"
SYNC=1

usage() {
    sed -n '3,11p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    cat <<'EOF'

Options:
  --dev          Backend with --reload plus the Vite dev server on :5173.
  --sync-only    Install/update dependencies and stop.
  --no-sync      Skip dependency installation (fastest start).
  --port N       Backend port (default 8000).
  --ui-port N    Vite dev-server port, --dev only (default 5273).
  -h, --help     This message.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dev) MODE="dev"; shift ;;
        --sync-only) MODE="sync"; shift ;;
        --no-sync) SYNC=0; shift ;;
        --port) PORT="$2"; shift 2 ;;
        --ui-port) UI_PORT="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

step() { printf '\n\033[1;34m==>\033[0m \033[1m%s\033[0m\n' "$1"; }
note() { printf '    %s\n' "$1"; }
fail() { printf '\n\033[1;31mError:\033[0m %s\n' "$1" >&2; exit 1; }

# ── Python environment ───────────────────────────────────────────────────────
# uv when it is available (it created this venv and is much faster); otherwise
# the venv's own pip. Note the venv uv builds has no pip in it, so the two are
# not interchangeable once one has been chosen.

sync_python() {
    step "Python environment"

    if [[ ! -d "$VENV" ]]; then
        note "Creating $VENV"
        if command -v uv >/dev/null 2>&1; then
            uv venv "$VENV"
        else
            python3 -m venv "$VENV"
        fi
    fi

    note "Installing alignmentgraph-isd[server]"
    if command -v uv >/dev/null 2>&1; then
        VIRTUAL_ENV="$PWD/$VENV" uv pip install --quiet -e ".[server]"
    elif [[ -x "$VENV/bin/pip" ]]; then
        "$VENV/bin/pip" install --quiet --upgrade -e ".[server]"
    else
        fail "$VENV has no pip and uv is not installed.
    Install uv (https://docs.astral.sh/uv/) or recreate the venv with:
        rm -rf $VENV && python3 -m venv $VENV"
    fi

    "$VENV/bin/python" -c 'import fastapi, sqlmodel, uvicorn' \
        || fail "the [server] extra did not install correctly"
    note "OK"
}

# ── Node environment ─────────────────────────────────────────────────────────
# npm install only when the manifest is newer than what was installed; it is
# slow enough to be worth skipping, unlike the Python side.

sync_node() {
    step "Web UI dependencies"
    command -v npm >/dev/null 2>&1 || fail "npm is not installed (Node 18 or newer is required)."

    local stamp="$WEBAPP/node_modules/.install-stamp"
    if [[ -f "$stamp" && "$stamp" -nt "$WEBAPP/package.json" ]]; then
        note "Up to date"
        return
    fi

    ( cd "$WEBAPP" && npm install --no-fund --no-audit )
    touch "$stamp"
    note "OK"
}

build_ui() {
    step "Building the web UI"
    ( cd "$WEBAPP" && npm run build )
}

# ── Model configuration ──────────────────────────────────────────────────────
# AGENT_MODEL_* is read straight from the process environment by the harness
# (core/llm.py), so a .env has to be exported here — only AGISD_SERVER_* is
# picked up from the file automatically.

load_env() {
    [[ -f .env ]] || return 0
    step "Loading .env"
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
    note "OK"
}

check_model() {
    if [[ -z "${AGENT_MODEL_NAME:-}" ]]; then
        printf '\n\033[1;33mNote:\033[0m AGENT_MODEL_NAME is not set.\n'
        printf '    The app will start, but runs and the planning conversation are\n'
        printf '    unavailable and the UI will say so. Set it (plus AGENT_MODEL_BASE_URL\n'
        printf '    and AGENT_MODEL_API_KEY as your endpoint needs) in .env — see\n'
        printf '    .env.example — or export it before running this script.\n'
    else
        note "Model: $AGENT_MODEL_NAME"
    fi
}

# ── Run ──────────────────────────────────────────────────────────────────────

load_env

if [[ $SYNC -eq 1 ]]; then
    sync_python
    sync_node
fi

if [[ "$MODE" == "sync" ]]; then
    step "Done"
    note "Start the app with: ./run-app.sh"
    exit 0
fi

check_model

if [[ "$MODE" == "dev" ]]; then
    step "Starting in development mode"
    note "UI:  http://localhost:$UI_PORT   ← open this one; it proxies /api"
    note "API: http://localhost:$PORT"
    printf '\n'

    # Both ports are passed to Vite, so --port is honoured on both sides and the
    # UI URL printed above is the one it actually binds (strictPort makes a
    # clash fail loudly rather than drift to another port).
    export AGISD_API_PORT="$PORT"
    export AGISD_UI_PORT="$UI_PORT"

    # Job control, so each background job leads its own process group. Both
    # children spawn grandchildren — uvicorn --reload forks a worker, npm forks
    # vite — and killing only the job leaves those orphaned, still holding the
    # ports. Killing the group takes the whole tree.
    set -m

    "$VENV/bin/alignmentgraph-isd" serve --reload --port "$PORT" &
    backend=$!
    ( cd "$WEBAPP" && exec npm run dev ) &
    frontend=$!

    stop() {
        trap - INT TERM EXIT
        kill -TERM -- "-$backend" "-$frontend" 2>/dev/null || true
        # Anything ignoring TERM gets one grace period, then SIGKILL.
        sleep 1
        kill -KILL -- "-$backend" "-$frontend" 2>/dev/null || true
    }
    trap 'stop' INT TERM EXIT

    # Stop as soon as either one dies, rather than leaving half the app running.
    # Polled rather than `wait -n`, which needs bash 4.3 — macOS ships 3.2.
    while kill -0 "$backend" 2>/dev/null && kill -0 "$frontend" 2>/dev/null; do
        sleep 1
    done
    printf '\n'
    stop
    exit 1
fi

build_ui

step "Starting the app"
note "http://localhost:$PORT"
printf '\n'
# Single process by design: live runs and their event buffers are in-process
# state, so a second worker would not find them.
exec "$VENV/bin/alignmentgraph-isd" serve --serve-spa --port "$PORT"
