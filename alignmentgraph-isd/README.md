# alignmentgraph-isd

LangGraph-based multi-agent ADDIE instructional-design harness (the thesis
contribution). The package exposes a stable public API on the canonical
`DesignBrief` contract; benchmark integrations map their own scenario schema to
`DesignBrief` *outside* the harness and call the public entry point directly.

## Mechanisms (canonical names)

The harness's behaviour decomposes into a small set of named mechanisms. These
names are canonical — paper, docs and docstrings use them, and each one is
named after the operation it performs, never after an outcome it hopes for
(the same naming rule the RQ2 protocol follows). Everything here is
deterministic unless marked as an LLM call.

- **Relation-scoped context injection** — each Designer reads a hand-curated
  list of node types from the `AlignmentGraph` before generating; nothing ever
  reads "the whole graph" (`BaseISDAgent._element_context`). Graph arm only:
  the `prose` arm replaces this channel wholesale with the blackboard's
  static document read-lists (see the ablation axes below). The graph once carried harness-side multi-hop traversal APIs
  (`neighbors`/`traverse`); a full ladder run's deep trajectory recorded
  1,179 graph reads and not one was a traversal — the graph's topology is
  shallow enough that type-scoped lists plus 1-hop ID resolution cover every
  context need — so the APIs were removed as dead code. (This is a topology
  fact about harness-side context assembly; model-driven graph querying was
  never offered, so nothing here refutes it.)
- **Relation-join context injection** — for steps that consume an evidence
  chain (Activity and Rubric Designers, and the single arm's matching
  states), the same nodes arrive pre-joined along established C2 edges: each
  objective carries the assessment items that measure it, and items no edge
  claims are surfaced under an explicit NOT-YET-LINKED header
  (`BaseISDAgent._element_context_joined`). This is generation-time work only
  the graph can do — the prose arm would have to re-derive the join, which is
  exactly the machinery the axis ablates. Prompt contexts render BARE element
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
  prompt cannot contain (`BaseISDAgent._alignment_state`). Graph arm only —
  the docket is coverage instantiated against graph state, so the `prose` arm
  keeps the LAW (system-prompt rules, shared verbatim) but never receives an
  instantiated docket. Motivating measurement: with the
  quantified rule alone, a 9B model produced 16 diagnostic / 1 summative
  items against a plan promising 1 / 5.
- **Bounded repair loop** — each Designer self-validates and repairs its own
  owned violations inline, to quiescence under an explicit
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
Designers and prompts on a graph-free blackboard, keeping only the
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
from alignmentgraph_isd import DesignBrief, HarnessRunConfig, run_design_brief

config = HarnessRunConfig()                            # defaults = the full pipeline
config.llm_factory = lambda: my_chat_model             # any LangChain chat model factory; required

brief = DesignBrief(
    id="brief-1",
    title="Object-Oriented Programming in Java",
    domain="Software Engineering",
    learning_goals=["Explain encapsulation", "Apply inheritance", "Design a class hierarchy"],
)

result = run_design_brief(brief, config)
# result == {"addie_output": {...}, "trajectory": {...}, "metadata": {...},
#            "graph": {...}, "graph_dot": "digraph alignment { ... }"}
# (the graph/graph_dot keys exist on the default graph arm only — a
#  context_mode="prose" run is graph-free and omits them)
```

`run_design_brief` (and the CLI) fail with a clear error if `llm_factory` is not
configured — they never emit a silent empty output.

### Ablation axes

`HarnessRunConfig` carries two axes, defaults = the full pipeline (there is no
preset system):

- `agent_mode` (`"multi"` default | `"single"`) — decomposition.
  `multi` is the specialist-Designer pipeline; `single` runs
  `SingleDesignerAgent`: one persona, its own state machine over artifact
  families (plan/execute pairs collapsed), importing nothing from the
  specialist agents. Both arms compose their prompts from the shared
  rulebook (`core/rulebook.py`) and dispatch into the shared repair
  toolbox (`core/repairs.py`) under the same regen/self-validation
  scaffolding, so rules and repair strength are identical by construction
  and only persona + task granularity differ
  (`tests/fixtures/golden_prompts.json` pins the composed prompts).
- `context_mode` (`"graph"` default | `"prose"`) — the alignment machinery,
  as a bundle. `graph` runs the full AlignmentGraph pipeline (every mechanism
  above). `prose` runs a **graph-free prose blackboard**
  (`core/prose_store.py::ProseStore`): each step deposits its whole parsed JSON
  under one document key, later steps read documents back verbatim by a
  static per-step read-list (the named-slice pattern non-graph baselines
  use); safeguards are limited to the within-artifact checks (bloom verbs,
  measurability, rubric consistency, evaluation quality, actionability) plus
  the shared self-repair/regen scaffolding; there is no cross-agent routing,
  no docket, no residual audit, and **no `graph`/`graph_dot` result keys**
  (its inspectability artifact is `result["prose"]` — the raw blackboard
  documents verbatim, saved by the benchmark as `<agent_id>_prose.json`; a
  content dump for debugging, not an alignment audit).
  The axis is deliberately a bundle — "what does the harness lose without its
  alignment machinery" — and is disclosed as such, never as a single isolated
  variable.

The resolved axes are recorded in `result["metadata"]["run_config"]`, so every
run is self-describing. They exist for the thesis ablation study (the
benchmark registers one agent id per arm); production use keeps the defaults.

### Graph dump (explainability / auditability)

The alignment graph is the run's explicit, human-auditable alignment state, so
every graph-arm run returns a **full dump as its own result keys, separate
from the trajectory** (a `context_mode="prose"` run has no graph and omits
both keys — a graph-free system has nothing to audit, which is the
auditability contrast the ablation reports):

- `result["graph"]` — `AlignmentGraph.to_full_dict()`: every node (id, type,
  complete data payload), every edge (source, target, relation key such as
  `"R3-measures"`, `relation_id`, `established_by`, evidence, rationale),
  per-objective / per-relation alignment annotations, and a `metadata` block
  (design brief id, UTC timestamp, node/edge counts by type). Fully
  JSON-serializable.
- `result["graph_dot"]` — `AlignmentGraph.to_dot()`: a valid Graphviz DOT
  document (node shape/colour by type and alignment state, edge labels by
  relation, DOT-escaped labels — Korean/unicode content stays valid). Render
  with `dot -Tsvg graph.dot -o graph.svg`.

Write them to files with the CLI's `--graph <stem>` flag, or set the
`ALIGNMENTGRAPH_DUMP_DIR` env var to have every run write
`<brief_id>_graph.json` + `<brief_id>_graph.dot` there automatically. The
benchmark adapter surfaces the same keys, and the benchmark runner saves them
as `<agent_id>_graph.json` / `<agent_id>_graph.dot` next to each scenario's
output.

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

### Experimental: agentic control mode (`core/agentic/`)

An opt-in, registry-only experiment — **not part of any study arm, ladder, or
paper claim**. The same 7 artifact families, but each step runs as an LLM tool
loop (act→observe over the alignment graph, JSON-action transport) instead of
the scripted call sequence: the model decides which graph reads
(`read_nodes`/`read_edges`/`coverage_gaps`), checks (`check_artifact`) or
retrievals to perform and when to `submit`. Deterministic scaffolding is kept
where SLMs measurably need it: the alignment docket up front, deterministic
submit validation, hard turn budgets with a scripted fallback, and the shared
repair toolbox (`core/repairs.py`) as the post-commit safety net. Macro
control (step order) stays fixed; there is no cross-agent routing.

Nothing in `core/` imports this subpackage. Entry points: the benchmark agent
id `alignmentgraph-isd-agentic` (select explicitly via `--agents`), or:

```python
from alignmentgraph_isd.core.agentic import run_agentic_brief
result = run_agentic_brief(config, brief)   # result-key parity with run_design_brief,
                                            # plus metadata.run_config.control_mode == "agentic"
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
python -m pytest tests/                       # all tests
python -m pytest tests/test_smoke_run.py      # public-API smoke on the fixtures
python -m pytest tests/test_full_pipeline.py  # end-to-end contract + 13-relation coverage
```
