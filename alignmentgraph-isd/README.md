# alignmentgraph-isd

Multi-agent ADDIE instructional-design harness (the thesis contribution). Each
of the six ADDIE stages is a native tool-calling act→observe loop; the stage
ORDER is instructed and fixed. The package exposes a stable public API on the canonical
`DesignBrief` contract; benchmark integrations map their own scenario schema to
`DesignBrief` *outside* the harness and call the public entry point directly.

## Mechanisms (canonical names)

The harness's behaviour decomposes into a small set of named mechanisms. These
names are canonical — paper, docs and docstrings use them, and each one is
named after the operation it performs, never after an outcome it hopes for
(the same naming rule the RQ2 protocol follows). Everything here is
deterministic unless marked as an LLM call.

- **Relation-scoped context reads** — an agent reads the `AlignmentGraph`
  through tools it chooses to call (`read_nodes`, `read_node`, `read_edges`,
  `coverage_gaps` in `core/agentic/tools.py`), each scoped to a hand-curated
  list of node types for that stage; nothing ever reads "the whole graph".
  Graph arm only:
  the `prose` arm replaces this channel wholesale with the blackboard's
  static document read-lists (see the ablation axes below). The graph once carried harness-side multi-hop traversal APIs
  (`neighbors`/`traverse`); a full ladder run's deep trajectory recorded
  1,179 graph reads and not one was a traversal — the graph's topology is
  shallow enough that type-scoped lists plus 1-hop ID resolution cover every
  context need — so the APIs were removed as dead code. (This is a topology
  fact about harness-side context assembly; model-driven graph querying was
  never offered, so nothing here refutes it.)
- **Bare element ids** — prompt contexts render BARE element
  ids only (`[OBJECTIVE:ILO-01]`, never `objective:ILO-01`): namespaced ids
  leaked into model reference fields and broke the bare-id matchers, and
  `alignment.bare_ref` normalizes any that still arrive.
- **Alignment-state scaffolding** — generation context carries, besides the
  artifact nodes, the graph's CURRENT alignment state: established edges for
  the relations in the agent's scope, coverage obligations instantiated
  against that state ("ILO-03 has no assessed_by link yet" — an enumerated
  checklist, not a quantified rule), and the plan-promised (objective x
  category) pairs no item yet realises. Rules stay in the system prompt
  (static, stated once); this block carries only per-run state the system
  prompt cannot contain (`tools.alignment_docket`, injected up front by both
  loops rather than fetched). Graph arm only —
  the docket is coverage instantiated against graph state, so the `prose` arm
  keeps the LAW (system-prompt rules, shared verbatim) but never receives an
  instantiated docket. Motivating measurement: with the
  quantified rule alone, a 9B model produced 16 diagnostic / 1 summative
  items against a plan promising 1 / 5.
- **Bounded repair loop** — each stage self-validates and repairs its own
  owned violations as a repair turn inside its own tool loop
  (`ToolLoop._own_violations`, bounded by `REPAIR_TURNS`), and cross-family
  residuals are reconciled once after the last stage under an explicit
  `SELF_VALIDATION_BUDGET`. Deliberately *bounded*, not run-to-convergence:
  the budget is the termination guarantee, and residual violations are
  reported in the audit rather than silently iterated away.
- **Judge-visible / recovery split** — one `tool_call` per real, purposeful
  model call; retries, empty-output regeneration and truncation salvage are
  recorded in `recovery_events`, which keeps the trajectory honest about
  effort without conflating recovery plumbing with agent actions
  (`TrajectoryLogger.log_step` vs `log_recovery_event`).

The two experimental axes are `agent_mode` (multi vs. single — decomposition)
and `context_mode` (graph vs. prose — the alignment machinery as a bundle).
Every mechanism above belongs to the graph arm; the `prose` arm runs the same
stages and prompts on a graph-free blackboard, keeping only the
within-artifact safeguards and the shared regen/repair scaffolding (see the
ablation axes section below). Per-run mechanism activity (verifier/repair/
recovery event counts) is reported observationally from the trajectory.

An earlier version of this harness also had 3 "validate" checkpoints and a
deterministic cross-agent router that could send a Designer back for a
narrow revision when a downstream check traced a gap to an earlier
Designer's output. Removed 2026-08-28: it was structurally almost always a
no-op — every violation type it could route was either already self-repaired
inline by the exact owning Designer moments before the checkpoint ran, or
excluded by the router's own valid-targets rule. Nothing a Designer's inline
repair genuinely can't fix goes unreported: it still surfaces in the final
`GraphAuditor` residual at aggregation.

## Public API (recommended integration path)

```python
from alignmentgraph_isd import DesignBrief, HarnessRunConfig, MetaAgent

config = HarnessRunConfig()                            # defaults = the full pipeline
config.llm_factory = lambda: my_chat_model             # any LangChain chat model factory; required

brief = DesignBrief(
    id="brief-1",
    title="Object-Oriented Programming in Java",
    domain="Software Engineering",
    learning_goals=["Explain encapsulation", "Apply inheritance", "Design a class hierarchy"],
)

result = MetaAgent(config).run(brief)
# result == {"addie_output": {...}, "trajectory": {...}, "metadata": {...},
#            "graph": {...}}
# (the graph key exists on the default graph arm only — a
#  context_mode="prose" run is graph-free and omits it)
```

`MetaAgent.run` (and the CLI) fails with a clear error if `llm_factory` is not
configured — it never emits a silent empty output. The guard is on `run`
itself, so every caller gets it; the `run_design_brief` wrapper that used to
hold it was removed 2026-09-05.

### Ablation axes

`HarnessRunConfig` carries two axes, defaults = the full pipeline (there is no
preset system):

- `agent_mode` (`"multi"` default | `"single"`) — decomposition, and
  deliberately a BUNDLE, disclosed exactly as `context_mode` is: it varies the
  context boundary, who walks the stages, how many personas, and whether work
  is delegated. `multi` starts each stage in a fresh context under that stage's
  specialist identity; `single` carries ONE context across all six under
  `SingleDesignerAgent`. Both arms compose their prompts from the shared
  rulebook (`core/rulebook.py`) and dispatch into the shared repair
  toolbox (`core/repairs.py`) under the same regen/self-validation
  scaffolding (`tests/fixtures/golden_prompts.json` pins the composed prompts
  and the bound tool schemas). Equal model effort is NOT the parity
  requirement: an agent that plans its own order and writes its own item
  batches cannot spend the same number of calls as a harness walking a fixed
  plan with Developers. What is checkable is that neither arm was CUT by its
  turn budget — while that holds, an outcome difference cannot be blamed on
  the ceiling.
- `context_mode` (`"graph"` default | `"prose"`) — the alignment machinery,
  as a bundle. `graph` runs the full AlignmentGraph pipeline (every mechanism
  above). `prose` runs a **graph-free prose blackboard**
  (`core/prose_store.py::ProseStore`): each step deposits its whole parsed JSON
  under one document key, later steps read documents back verbatim by a
  static per-step read-list (the named-slice pattern non-graph baselines
  use); safeguards are limited to the within-artifact checks (bloom verbs,
  measurability, rubric consistency, evaluation quality, actionability) plus
  the shared self-repair/regen scaffolding; there is no cross-agent routing,
  no docket, no residual audit, and **no `graph` result key**
  (its inspectability artifact is `result["prose"]` — the raw blackboard
  documents verbatim, saved by the benchmark as `<agent_id>_prose.json`; a
  content dump for debugging, not an alignment audit).
  The axis is deliberately a bundle — "what does the harness lose without its
  alignment machinery" — and is disclosed as such, never as a single isolated
  variable.

The resolved axes are recorded in `result["metadata"]["run_config"]`, so every
run is self-describing.

`development_mode` (`"light"` | `"full"`, default `"light"`) sits beside them
and is NOT an axis. A design is always PLANNED at full scale — the assessment
blueprint says a module's quiz has 40 items — and this setting decides how much
of it the Developers write out: `light` a typical, reviewable slice (one item per
objective × timing at the objective's own Bloom level, one activity per objective,
two outlined materials per module — `core/dev_plans.py`'s `LIGHT_*` quotas and
the table at the head of its development-mode section), `full` all of it,
batched, with complete learner-ready materials. It changes numbers and a derived
assignment in a work set and one note in its assignment, never a rule block, and
the output states the scale it was written at (`development.development_scope`,
plus `items_written` on every task). Every arm of one experiment runs under the
same value. They exist for the thesis ablation study (the
benchmark registers one agent id per arm); production use keeps the defaults.

### Graph dump (explainability / auditability)

The alignment graph is the run's explicit, human-auditable alignment state, so
every graph-arm run returns a **full dump as its own result keys, separate
from the trajectory** (a `context_mode="prose"` run has no graph and omits
both keys — a graph-free system has nothing to audit, which is the
auditability contrast the ablation reports):

- `result["graph"]` — `AlignmentGraph.to_full_dict()`: every node (id, type,
  complete data payload), every edge (source, target, relation key such as
  `"C2-assessed_by"`, `relation_id`, `established_by`, evidence, rationale),
  per-objective / per-relation alignment annotations, and a `metadata` block
  (design brief id, UTC timestamp, node/edge counts by type). Fully
  JSON-serializable.

  It also carries the **display semantics** — a node's `label` and `kind`, an
  edge's `id`, `layer`, `tier` and `invalid` flag, an objective's ordered
  alignment `legs`, the graph's `legend` — so it is the single thing every
  renderer reads. Colour and shape are all a renderer still decides.

Write it to a file with the CLI's `--graph <stem>` flag, or set the
`ALIGNMENTGRAPH_DUMP_DIR` env var to have every run write
`<brief_id>_graph.json` there automatically. The benchmark adapter surfaces
the same key, and the benchmark runner saves it as `<agent_id>_graph.json`
next to each scenario's output.

There is no `.dot` artifact: GraphViz DOT is a RENDERING of that payload,
reproducible from it byte-for-byte, so it is produced on demand rather than
kept in step as a second file.

```bash
alignmentgraph-isd dot graph.json -o graph.dot
dot -Tsvg graph.dot -o graph.svg
```

### RAG (external corpus only)

In this harness **RAG means external-corpus retrieval only**. Graph-context
retrieval (the AlignmentGraph subgraph) is core, always on, and is *not*
called RAG.

RAG is off by default (`use_rag=False`) and is an opt-in add-on: set
`use_rag=True` **and** register retrieval agents on
`config.retrieval_subagents` — both are required for the gate to open.

```python
from alignmentgraph_isd import HarnessRunConfig, RetrievalAgent, RetrievalTool
config = HarnessRunConfig(use_rag=True)
config.retrieval_subagents = [
    RetrievalAgent(
        "java-oop-corpus", "java_oop",
        tools=[RetrievalTool("search_corpus", "Search OOP corpus",
                             lambda query="": ["Prefer composition over inheritance."])],
        domains=["software engineering"], keywords=["oop", "java"],
    ),
]
```

### The executor (`core/agentic/`)

The 7 artifact families, each produced by a native tool-calling act→observe
loop: the model decides which graph reads
(`read_nodes`/`read_edges`/`coverage_gaps`) or retrievals to perform and when
to `submit`. Deterministic scaffolding is kept where SLMs measurably need it:
the alignment docket up front, deterministic submit validation, hard turn
budgets, and the shared repair toolbox (`core/repairs.py`) as the post-commit safety net. The ADDIE
stage ORDER stays instructed in both decomposition arms — the agents are
autonomous in HOW a stage is executed, never in what order the stages run.
Cross-family violations still outstanding after the last stage are reconciled
once, routed to the family that owns them (`agent_mode="multi"`) or repaired in
place by the one agent (`"single"`).

There is one executor; `MetaAgent.run` dispatches straight to it.

```python
from alignmentgraph_isd import HarnessRunConfig, MetaAgent
result = MetaAgent(HarnessRunConfig(llm_factory=...)).run(brief)
# metadata.run_config records agent_mode/context_mode;
# metadata.autonomy records per-stage context_len, turns, fallbacks.
```

## CLI (developer smoke / manual runs)

The CLI takes a JSON file already in `DesignBrief` shape (not a raw benchmark
scenario). It builds a chat model from `--model-*` flags (or `AGENT_MODEL_*`
env vars), so install the provider clients first:

```bash
pip install -e '.[llm]'    # langchain-openai + langchain-anthropic

# OpenAI-compatible backend (e.g. OpenRouter):
AGENT_MODEL_API_KEY="$OPENROUTER_API_KEY" alignmentgraph-isd run \
  --input tests/fixtures/minimal_brief.json \
  --output result.json \
  --trajectory trajectory.json \
  --graph graph \
  --model-name openai/gpt-4o-mini \
  --base-url https://openrouter.ai/api/v1

# Anthropic:
ANTHROPIC=... alignmentgraph-isd run --input brief.json --output result.json \
  --api-spec anthropic --model-name claude-opus-4-8 --api-key "$ANTHROPIC_API_KEY"
```

Flags fall back to env vars: `AGENT_MODEL_NAME`, `AGENT_MODEL_API_SPEC`
(default `openai_compatible`), `AGENT_MODEL_BASE_URL`, `AGENT_MODEL_API_KEY`,
`AGENT_MODEL_TEMPERATURE`, `AGENT_MODEL_MAX_TOKENS`. Without a resolvable model
the CLI exits 2 with a message instead of emitting empty output.

## Tests

Network-free; a fake `llm_factory` drives the whole pipeline (see
`tests/conftest.py`). From this package directory:

```bash
pip install -e '.[server]'                    # REQUIRED: see below
python -m pytest tests/                       # all tests
python -m pytest tests/test_smoke_run.py      # public-API smoke on the fixtures
python -m pytest tests/test_full_pipeline.py  # end-to-end contract + 18-relation coverage
```

**Install the `[server]` extra in every dev and CI environment.** `tests/server/`
is ~100 tests and `tests/server/conftest.py` skips the whole package when
FastAPI is absent — so without the extra the suite reports a healthy pass count
while nothing under `src/alignmentgraph_isd/server/` is guarded at all. The
extra is a test-environment requirement only; the package itself must stay
importable without it (`tests/test_import_isolation.py` is that guard).
