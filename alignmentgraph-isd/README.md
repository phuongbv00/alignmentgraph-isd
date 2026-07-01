# alignmentgraph-isd

LangGraph-based multi-agent ADDIE instructional-design harness (the thesis
contribution). The package exposes a stable public API on the canonical
`DesignBrief` contract; benchmark integrations map their own scenario schema to
`DesignBrief` *outside* the harness and call the public entry point directly.

## Public API (recommended integration path)

```python
from alignmentgraph_isd import DesignBrief, HarnessRunConfig, run_design_brief

config = HarnessRunConfig.from_ablation("full")        # full | no_verifier | no_repair | single_agent | linear_addie_only | case_study
config.llm_factory = lambda: my_chat_model             # any LangChain chat model factory; required

brief = DesignBrief(
    id="brief-1",
    title="Object-Oriented Programming in Java",
    domain="Software Engineering",
    learning_goals=["Explain encapsulation", "Apply inheritance", "Design a class hierarchy"],
)

result = run_design_brief(brief, config)
# result == {"addie_output": {...}, "trajectory": {...}, "metadata": {...}}
```

`run_design_brief` (and the CLI) fail with a clear error if `llm_factory` is not
configured — they never emit a silent empty output.

### RAG (external corpus only)

In this harness **RAG means external-corpus retrieval only**. Graph-context
retrieval (the AlignmentGraph subgraph) and memory retrieval (working/episodic
memory) are core, always on, and are *not* called RAG.

- The **benchmark defaults to `no_rag`** (`use_rag=False`); RAG is never used in
  benchmark runs.
- RAG is an opt-in **case-study/app** add-on: use the `case_study` preset (or set
  `config.ablation.use_rag = True`) and register `RetrievalSubagent` instances on
  `config.retrieval_subagents`.

```python
from alignmentgraph_isd import HarnessRunConfig, LocalCorpusSubagent
config = HarnessRunConfig.from_ablation("case_study")   # use_rag=True
config.retrieval_subagents = [
    LocalCorpusSubagent("java-oop", "java_oop",
                        {"oop": ["Prefer composition over inheritance."]},
                        domains=["software engineering"], keywords=["oop", "java"]),
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
  --ablation full \
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
python -m pytest tests/test_ablations.py      # every ablation preset end-to-end
```
