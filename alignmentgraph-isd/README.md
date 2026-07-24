# alignmentgraph-isd

LangGraph-based multi-agent ADDIE instructional-design harness (the thesis
contribution). The package exposes a stable public API on the canonical
`DesignBrief` contract; benchmark integrations map their own scenario schema to
`DesignBrief` *outside* the harness and call the public entry point directly.

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
```

`run_design_brief` (and the CLI) fail with a clear error if `llm_factory` is not
configured — they never emit a silent empty output.

### Ablation switches

`HarnessRunConfig` carries two booleans, both `True` by default (there is no
preset system):

- `enable_verifier` — wire the per-specialist QC nodes (pedagogical verify +
  repair loop) into the workflow. Off: the generation chain runs bare; the
  aggregator safety nets and the residual graph audit still run.
- `enable_graph_context` — inject prior AlignmentGraph node data into
  specialist prompts. Off: every specialist sees only the design brief; the
  graph is still **written** in full (dumps/audit intact), i.e. it becomes
  write-only from the prompts' point of view.

The resolved flags are recorded in `result["metadata"]["run_config"]`, so every
run is self-describing. These switches exist for the thesis ablation study (the
benchmark registers one agent id per arm); production use keeps both on.

### Graph dump (explainability / auditability)

The alignment graph is the run's explicit, human-auditable alignment state, so
every run returns a **full dump as its own result keys, separate from the
trajectory**:

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
