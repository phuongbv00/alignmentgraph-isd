# Demo web app

A web front end for the harness: describe a training program (or import a
scenario file), run the agent, and watch the alignment graph being built.

It exists to make the thesis contribution visible. The alignment graph is
otherwise only a `graph.json` on disk; here it is a thing you can look at,
filter and click through while the run is still going.

## Running it

`run-app.sh` in the package root does everything — creating the virtualenv,
installing dependencies, building the UI, starting the server. It is
idempotent, so re-running it after a `git pull` is the normal way to use it.

```bash
./run-app.sh              # one process on one URL   → http://localhost:8000
./run-app.sh --dev        # hot reload, two processes → http://localhost:5273
./run-app.sh --sync-only  # just bring dependencies up to date
```

Useful flags: `--no-sync` (fastest start), `--port N`, `--ui-port N`,
`--help`.

### Choosing a model

**From the UI** — open **Model settings** (bottom of the sidebar). It holds a
**list of connections**, one of them active: each is an endpoint (base URL and
key) plus the model picked on it, so switching between a local Ollama and a
served pod is a click rather than three fields retyped. There are presets for
Ollama, vLLM, OpenRouter and OpenAI.

Add a connection and save it, then pick the model from the dropdown: the list is
read from that endpoint's own `/v1/models`, so the id is one it actually serves.
The key never leaves the server — the browser asks for the list by connection
id, not by posting the credentials back. Saving also constructs the client and
reports what is wrong if anything is, so a missing key is caught there rather
than discovered when a run collapses.

The app speaks **OpenAI-compatible endpoints only**. The core factory still
speaks Anthropic for the CLI and the benchmark (`AGENT_MODEL_API_SPEC`); the app
does not.

The API key is held **in clear text** in the local SQLite file. It is never sent
back to the browser (only whether one is set), but use a throwaway key if that
matters to you.

**From the environment** — the same `AGENT_MODEL_*` variables the CLI and the
benchmark read. They **seed the first connection** on an empty database, so an
existing setup starts configured:

```bash
AGENT_MODEL_NAME=...        # required
AGENT_MODEL_BASE_URL=...    # for an OpenAI-compatible endpoint
AGENT_MODEL_API_KEY=...
```

Put them in `.env` (see `.env.example`) and `run-app.sh` exports them for you;
the harness reads them from the process environment, so a `.env` alone is not
enough. Seeding happens **once**, on a database with no connections in it —
after that the database is the whole story, so a connection deleted in the
dialog does not come back on the next restart.

Without a usable model the server still starts; `/api/health` reports
`llm_configured: false` with the reason, and the UI says so and offers the
settings dialog.

> A model *name* on its own is enough to build a factory but not enough to run,
> so the app constructs the client up front — both in `/api/health` and before
> starting a run. Without that check a run starts, every specialist fails on
> construction, and it "completes" in milliseconds with an empty graph and an
> empty ADDIE output under a `succeeded` label.

### By hand

```bash
pip install -e '.[server]'                          # pulls in [llm] too
cd src/alignmentgraph_isd/webapp && npm install

# development: Vite serves the UI and proxies /api, so everything is
# same-origin and no CORS configuration is involved
alignmentgraph-isd serve --reload --port 8000
cd src/alignmentgraph_isd/webapp && npm run dev      # http://localhost:5273

# demo: one process, one URL
cd src/alignmentgraph_isd/webapp && npm run build
alignmentgraph-isd serve --serve-spa --port 8000
```

Two things worth knowing:

- **Run it single-process.** Live runs and their event buffers are in-process
  state, so with two uvicorn workers half the event-stream connections would
  land on a worker that has never heard of the run. `serve` deliberately has no
  `--workers` flag.
- **The dev server is on 5273, not Vite's default 5173.** When another project
  already holds 5173 it binds IPv4 while this one gets IPv6, and since
  `localhost` resolves to IPv4 first you silently open the wrong app.
  `strictPort` is on, so a clash is an error rather than something you discover
  mid-demo.

## Configuration

All server settings are `AGISD_SERVER_*`; they are separate from
`AGENT_MODEL_*`, which configures the model the harness runs on.

| Variable | Default | Meaning |
|---|---|---|
| `AGISD_SERVER_DATA_ROOT` | `.agisd-server-data` | Database and run artifacts |
| `AGISD_SERVER_DB_URL` | a SQLite file in the data root | Override the database |
| `AGISD_SERVER_MAX_CONCURRENT_RUNS` | `2` | Worker threads for runs |
| `AGISD_SERVER_SERVE_SPA` | `0` | Serve the built UI from this app |
| `AGISD_SERVER_SPA_DIST` | `../webapp/dist` | Where the built UI is |

## How it fits together

```
webapp/  ── EventSource ──▶  /api/runs/{id}/events  ──▶  RunState (in memory)
                                                            ▲
                                       on_event callback ────┤
                                                            │
  POST /programs/{id}/runs ──▶ worker thread ──▶ MetaAgent.run(..., on_event=…)
                                     │
                                     └──▶ programs/<id>/runs/<id>/*.json
```

The harness is synchronous and a real run takes minutes, so each one gets a
worker thread and reports progress through the package's `on_event` hook.

Three rules hold that bridge together, and breaking any of them causes bugs
that only appear under load:

1. **Serialize on the worker thread.** `to_full_dict()` returns the live node
   and edge dicts, which later phases keep mutating. Keeping the object and
   serializing it later in a request handler yields either a silently-changed
   "snapshot" or a dictionary-changed-size error mid-iteration.
2. **Never touch the database from the callback.** A SQLAlchemy session is not
   thread-safe, and a run's progress must not depend on the database.
3. **Never block in the callback.** It runs inside the agent's own tool loop; anything
   slow there slows the run itself.

### Agent contexts

`GET /api/runs/{id}/contexts` returns one entry per agent — its system turn, the
whole transcript it accumulated, and the tool schemas it was bound. The harness
publishes them through `on_event` (`context_snapshot`) as each agent finishes;
they are held as run state and saved as `contexts.json`.

State rather than forwarded events, for the reason the graph is: a transcript is
large and only its finished form is worth reading. And deliberately NOT folded
into `trajectory`/`trajectory_deep` — the judge reads those and the benchmark
compares them across arms, so doubling their size to serve a viewer would change
what is measured.

### Downloading a transcript

`GET /api/runs/{id}/transcript/export` returns every agent's transcript as
Markdown — the system turn, each message in order, and the tool schemas bound
alongside them. `?index=N` picks one context out of the list.

Markdown rather than JSON because `/contexts` already serves the JSON a tool
would want, and this is the artifact a PERSON reads end to end. An INDEX rather
than a label because labels repeat: a stage that was regenerated publishes one
context per attempt, told apart by position and `attempt`, not by name.

### Exporting a run

`GET /api/runs/{id}/trajectory/export` returns the whole trace as ONE
downloadable file — `metadata` (per-stage `autonomy`, the residual audit,
repair metrics, token usage), `trajectory` (the judge-visible trio plus the
structured event log) and `trajectory_deep` (the full-fidelity action log),
under the run's identity.

The pieces are each served by `/artifacts/{name}` already, which is what the UI
reads. That is not an export: reassembling a run from four fetches is the step
someone doing it by hand gets wrong, and the four are only interpretable
together — an action log without `autonomy` cannot say whether a stage ran out
of turns, and `autonomy` without the log cannot say what it did with them.

Exporting mid-run returns what has been recorded so far, from the live event
log, under `live_events` with `complete: false`. A run that looks stuck is the
one you most want to read; giving that file the same shape as a finished one
would be a trap, so the wire events keep their own key.

### Events, and why the graph is not one

Events are a small append-only list per run, replayable by cursor. That is what
makes a page reload mid-run resume without gaps and multiple browser tabs free.
They are also flushed to `events.jsonl`, so a finished run can be replayed after
a restart.

The graph is **state**, not an event: a full dump is ~95 kB and a run produces a
dozen of them, but only the latest is ever wanted. The newest is kept and a
revision counter bumped. What goes over the wire is a light view without the
per-node payloads (~35 kB); the payloads are fetched per node on click, which
matters because a section node such as `objective_0` carries an entire ADDIE
section.

### Cancelling

Cancellation is cooperative: the callback raises `HarnessCancelled` (a
`BaseException`, so it passes through the broad `except Exception` handlers that
keep a run alive through a bad model reply) at the next event. It cannot
interrupt a model call already in flight, so a run stops within roughly one
call.

### After a restart

A run lives in a worker thread, so a restart kills it with no chance to record
anything. On startup, any row still claiming to be active is marked
`interrupted` — otherwise it would block its program forever behind the
one-active-run rule. Interrupted runs are not resumed; their partial artifacts
are kept.

## Layout

```
server/
  settings.py   AGISD_SERVER_* configuration
  db.py         SQLite engine (WAL) and sessions
  models.py     program / session / message / run / llm connection
  events.py     RunState and the in-memory registry
  runner.py     worker pool, the on_event bridge, artifact writing
  llm_settings.py  the connection list, the active one, and model discovery
  planner.py    the conversation that builds a brief
  briefs.py     scenario import, patch merging, truncation
  artifacts.py  where a run's files live
  sse.py        event-stream framing and resume
  app.py        application factory, lifespan, SPA mount
  routers/      programs · planning · runs · system
```

`Session` deserves a note: every program has exactly one, created with it, and
the UI never mentions it. It exists so a program's messages and runs are already
grouped, and a later feature can add a second one without a migration.

## Tests

```bash
pytest tests/server           # API, runs, event stream, planner
pytest tests/test_import_isolation.py   # FastAPI must not leak into the package
```

The server tests run the whole pipeline against the network-free fake model
from `tests/conftest.py`, so they need no API key and finish in seconds.
