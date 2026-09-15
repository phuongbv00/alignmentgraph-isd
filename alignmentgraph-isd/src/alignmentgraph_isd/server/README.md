# Demo web app

A web front end for the harness: describe a training program (or import a
scenario file), run the agent, and watch the alignment graph being built.

It exists to make the thesis contribution visible. The alignment graph is
otherwise only a `graph.json` on disk; here it is a thing you can look at,
filter and click through while the run is still going. The app decides nothing
about that graph: what a node is called, which layer an edge is on and which
edges are marked bad all come from the payload, and the only thing this front
end still owns is colour and shape.

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

Two more fields decide how much of the conversation the harness may keep:

| Field | What it is | Blank means |
|---|---|---|
| **Max output tokens** | the cap on one reply, sent to the client | 4096 |
| **Context window** | everything the endpoint serves — prompt and reply together | a fixed 24,000-character budget |

The window sizes the transcript budget, and the output cap is what has to be
left in it for the answer — one number for both, so they cannot disagree. Leave the window
blank and the harness falls back to a constant unrelated to whatever the
connection points at: measured on run e81b8108, a stage compacted three times
under that budget against a model whose real window was never close to full.

**Disable thinking mode** is a third field, off by default. It sends
`chat_template_kwargs: {enable_thinking: false}` in the request body — the same
mechanism as the benchmark's `AGENT_MODEL_DISABLE_THINKING`, which cannot reach
this app (see below). Turn it on for small Qwen3 models: left thinking, they
spend the whole output cap inside `reasoning_content`, which arrives with empty
content, no tool call and `finish_reason: "stop"` — so truncation salvage cannot
see it either. The loop reads that as a turn the model wasted. Measured on run
24343e4d: 12 of 78 calls, 47-405 billed completion tokens each, one stage turn
gone every time.

> **There are no migrations** — `init_db` is `create_all`, so a column added to
> a connection is not added to a `demo.db` that already exists, and the first
> query raises `no such column`. Delete the local database, or add the column by
> hand, after pulling a change that adds one.

**Nothing else configures the model.** The app reads no `AGENT_MODEL_*` — not as
a fallback, not as a seed, not to fill in a field left blank. Those variables
belong to the CLI and the benchmark, which are configured from a shell; this is
configured in its own dialog, and a value arriving from the environment would be
visible in neither place. A connection saved with no key therefore fails here
rather than borrowing `AGENT_MODEL_API_KEY` and working until it is started from
a different shell. (`AGISD_SERVER_*`, below, is unaffected: those are server
settings — port, data root — not model configuration.)

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

All server settings are `AGISD_SERVER_*`, and they are the only environment the
app reads. The model is not here: it lives in Model settings and its database
(see above). `AGENT_MODEL_*` configures the CLI and the benchmark and has no
effect on the app.

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

### Work-set plans

`GET /api/runs/{id}/artifacts/plans` returns how each family was divided into
work sets, round by round: the stage and family, whether the Designer's own dev
plan was used or the deterministic split had to carry it, and the whole work set
each Developer was handed — its obligations, its theme, the count it was asked
for.

The `dev_plan` trajectory event carries a SUMMARY of the same decision (set ids
and their objectives, the source, what the harness dropped, duplicated or split)
and that is what the timeline reads. The plan itself is the payload behind it,
and nothing else on disk holds it, so without this file "what exactly was this
Developer asked for" could only be answered while the run was still alive.

### Downloading a transcript

`GET /api/runs/{id}/transcript/export` returns every agent's transcript as
Markdown — the system turn, each message in order, and the tool schemas bound
alongside them. `?context=<id>` picks one context out of the list.

Markdown rather than JSON because `/contexts` already serves the JSON a tool
would want, and this is the artifact a PERSON reads end to end. By ID
(`core.memory.new_agent_run_id`) rather than by label, because labels repeat: a stage
that was regenerated publishes one context per attempt and they share a name.
And rather than by position, which is what this addressed first: a context is
republished after every turn now, so the list is only stable once the run is
over, and a link a reader kept would follow the ordinal rather than the
conversation it was for.

### Exporting the trajectory

`GET /api/runs/{id}/trajectory/export` returns the run's TRAJECTORY as one
downloadable file — `trajectory` (the judge-visible trio plus the structured
event log) and `trajectory_deep` (the full-fidelity action log), under the
run's identity.

Both halves travel because they are one record split for size, not two
artifacts. Nothing else does: `metadata`, the graph and the ADDIE output are
each their own artifact with their own endpoint, and folding them in here would
make "export trajectory" mean "export the run", so nobody could export the
trajectory. Two files under one name is how an export format stops being one.

Exporting mid-run returns what has been recorded so far, from the live event
log, under `live_events` with `complete: false`. A run that looks stuck is the
one you most want to read; giving that file the same shape as a finished one
would be a trap, so the wire events keep their own key.

### Exporting the violation ledger

`GET /api/runs/{id}/violations/export` returns every distinct finding of the run
as CSV, one row per finding: the check that fired, the node, the outcome, why it
is still open, who owns it, and the metadata that says which item or objective
it is about.

CSV rather than JSON because `/violations` already serves the JSON a tool would
want, and the ledger is a TABLE — how many are still open, by reason, by owner,
by check are each one column, and rebuilding that from a nested array by hand is
the work this removes. `messages` travels newline-joined inside its cell and
`metadata` as compact JSON, so a row can still be traced back to the design.

An empty ledger is a RESULT, not an absence: a run whose checks all came back
clean gets a header row and no rows. Exporting mid-run gives what has been found
so far under a `violations-partial` filename — an outcome column read off a live
run is provisional in a way a finished one is not, and the name says which file
it is, as `complete: false` does for the trajectory.

### Events, and why the graph is not one

Events are a small append-only list per run, replayable by cursor. That is what
makes a page reload mid-run resume without gaps and multiple browser tabs free.
They are also flushed to `events.jsonl`, so a finished run can be replayed after
a restart.

The graph is **state**, not an event: a full dump runs ~170 kB at the median
and ~880 kB at the worst measured, and a run produces a dozen of them, but only
the latest is ever wanted. The newest is kept and a revision counter bumped.

What goes over the wire is a light view: the same payload with each node's
`data` dropped and **nothing else** (~92 kB at the median). Those payloads are
fetched per node on click, which matters because a section node such as
`objective_0` carries an entire ADDIE section.

That cut is safe because of a rule the payload keeps: it carries every display
semantic as its own field — a node's `label` and `kind`, an edge's `id`,
`layer`, `tier` and whether it is `invalid`, an objective's ordered alignment
`legs`, and the graph's `legend` — and **nothing reads `data` to draw**. So the
light frame is a complete picture, not a stub. The cut is made by
`viz.without_node_data`, not by a shape this server invents: it used to rebuild
each node as `{id, type}`, which is the same thing only while a node carries
nothing else worth keeping.

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
