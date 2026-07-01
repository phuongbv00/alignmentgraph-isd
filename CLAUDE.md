# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository layout

This is a master's thesis monorepo with three top-level parts:

- **`docs/`** — the thesis proposal (`proposal.md` / `proposal.html`), assets, and references. LaTeX build artifacts and `*.pdf` are gitignored.
- **`alignmentgraph-isd/`** — the **thesis contribution**: a standalone Python package (`alignmentgraph_isd`), a LangGraph-based multi-agent ADDIE instructional-design system. Tracked directly in this repo (not a submodule).
- **`isd-agent-benchmark/`** — a **git submodule** (`git@github.com:phuongbv00/isd-agent-benchmark.git`, branch `customize`) that benchmarks ISD agents. It contains six baseline/comparison agents plus a thin wrapper that runs `alignmentgraph-isd` as a seventh agent.

The two code parts are coupled: the benchmark agent `agents/alignmentgraph-isd` is a thin adapter (`AlignmentGraphISDAgent`) whose only dependency is the top-level `alignmentgraph-isd` package. The adapter bridges the benchmark's *scenario* vocabulary to the package's *design brief* contract (`scenario_id` → `id`) and injects the benchmark's LLM config as a `ChatModelFactory`.

## The `alignmentgraph-isd` package (thesis core)

Located in `alignmentgraph-isd/src/alignmentgraph_isd/`. Entry point: `MetaAgent(config).run(design_brief)` in `orchestrator.py`. Pipeline:

- **`orchestrator.py`** — builds and runs a LangGraph `StateGraph` per design brief. State (`ISDState`) holds only JSON-serializable data so `MemorySaver` can checkpoint it; non-serializable objects (config, graph, trajectory, the design brief) are captured as closures at build time, never placed in state.
- **`graph.py`** — `AlignmentGraph`, the alignment-dependency graph of ISD artifacts. Nodes (`objective`, `assessment`, `activity`, `material`, `implementation_plan`, `evaluation`, `needs_context`) and typed edges (`measures`, `supports`, etc.). `IMPACT_POLICY` drives staleness propagation when a node is repaired.
- **`agents/`** — specialist agents, one per ISD concern (`needs_context`, `objective_design`, `assessment_design`, `activity_material`, `implementation_plan`, `evaluation_revision`), plus `pedagogical_verifier` (checks alignment), `addie_aggregator` (assembles final ADDIE output), and `single_agent` (used when multi-agent is ablated). All extend `agents/base.py`.
- **`planner.py`** (`ISDTaskPlanner`) — decides task order / next task. **`rag/planner.py`** (`RetrievalPlanner`) — external-corpus retrieval. **`memory.py`** (`HarnessMemory`), **`audit.py`** (`GraphAuditor`), **`trajectory.py`** (`TrajectoryLogger`).
- **`config.py`** — `HarnessRunConfig` ties together `AblationConfig`, `LLMConfig`, `MemoryConfig`, and an injectable `llm_factory`.

### Ablation presets

Set via `HARNESS_ABLATION` env var or `AblationConfig.from_key(...)`. Valid keys (see `config.py`):

`full`, `no_verifier`, `no_repair`, `single_agent`, `linear_addie_only`, `case_study`

Each toggles the flags `use_rag`, `use_verifier`, `use_repair`, `multi_agent`, `dynamic_graph`.

**RAG = external-corpus retrieval only.** `use_rag` is **off** in every benchmark preset (the benchmark runs `no_rag`); only `case_study` sets `use_rag=True`, and RAG also needs `HarnessRunConfig.retrieval_subagents` registered. Graph-context retrieval and memory retrieval are core (always on) and are **not** called RAG, so no preset disables them.

## The benchmark (`isd-agent-benchmark/`)

`run_benchmark.py` is the orchestrator. Key facts that aren't obvious from the README:

- **Agents run in-process, not as subprocesses.** `_get_agent_runner(agent_id, llm_config)` imports each agent's Python class directly and returns a `run(scenario) -> dict` closure. The CLI interfaces documented in `shared/interfaces/agent_interface.md` exist but the benchmark does not use them. Agent `src/` paths are added to `sys.path` at the top of `run_benchmark.py`.
- **The evaluator IS run as a subprocess** (`isd-evaluator`), with stdout streamed to parse `__EVAL_PROGRESS__` markers.
- Each agent must return `{"addie_output": ..., "trajectory": ..., "metadata": ...}`. Output schemas live in `shared/schemas/*.json`.
- **`shared/llm`** is the single source of LLM configuration. Agents must NOT read provider env vars or instantiate `ChatOpenAI`/`ChatAnthropic` directly — call `create_chat_model(llm_config)` / `llm_config_from_env()`. `LLMConfig.api_spec` is the API *contract* (`openai_compatible`/`anthropic`), distinct from `provider` (a backend preset label). Add providers via config, not agent code.
- Agent vs. judge models are configured **separately** (`AGENT_MODEL_*` vs `JUDGE_MODEL_*`) to avoid self-preference bias. Judge config supports comma-separated lists aligned across names/providers/URLs, with `|` grouping multiple credentials per judge.
- Results land in `results/single_<ts>/` (single scenario) or `results/benchmark_<ts>/` (dataset/variant runs).

### Evaluator (`evaluator/`)

`isd_evaluator` package. ADDIE rubric scoring: 33 Context-Matrix sub-steps → 13 consolidated items → 5 ADDIE phases (100 pts), plus BFCL-based trajectory scoring. Multi-judge by default (`--single-judge` to disable). Context-aware weighting in `metrics/context_weights.py`.

## Common commands

All commands run from inside `isd-agent-benchmark/`.

```bash
# One-time setup: creates venv, installs base deps + every agent + evaluator (editable)
./scripts/1_setup.sh

# Reinstall agent/evaluator packages in editable mode from the runner
python run_benchmark.py --install
# Verify all agent modules import cleanly
python run_benchmark.py --check

# Split scenarios into train/test
./scripts/2_split_data.sh
# Quick smoke run
./scripts/3_run_benchmark_test.sh
# Full multi-model run (one tmux session per agent-model slot)
./scripts/4_run_benchmark.sh

# Run a single scenario against chosen agents
python run_benchmark.py \
  --scenario scenarios/test/<file>.json \
  --agents baseline,alignmentgraph-isd \
  --agent-model-provider openrouter \
  --agent-model-base-url https://openrouter.ai/api/v1 \
  --agent-model-name openai/gpt-4o-mini \
  --agent-model-api-key "$OPENROUTER_API_KEY" \
  --judge-model-names google/gemini-2.5-flash-lite \
  --judge-model-api-key "$OPENROUTER_API_KEY"

# Run a named dataset (scenarios/<name>/): train, test, test_30, test_90
python run_benchmark.py --dataset test_30 --agents baseline,alignmentgraph-isd
```

Default agents: `eduplanner, baseline, react-isd, addie-agent, dick-carey-agent, rpisd-agent`. **`alignmentgraph-isd` is NOT in the defaults — add it explicitly with `--agents`.**

Rate-limit presets (`-r conservative|moderate|aggressive|turbo`) set worker counts and `BENCHMARK_DELAY` together. See the benchmark README for the full flag/env matrix.

### Tests

Each package is independently installable/testable with pytest (`requires-python >=3.11`). Run from the package directory:

```bash
cd isd-agent-benchmark/evaluator && pytest tests/        # evaluator tests (asyncio_mode=auto)
cd isd-agent-benchmark/shared && pytest tests/           # shared model/util tests
cd isd-agent-benchmark/agents/<agent> && pytest tests/   # per-agent tests (where present)
pytest tests/test_addie_rubric_parsing.py                # single test file
pytest tests/test_addie_rubric_parsing.py::<name>        # single test
```

Lint (evaluator uses ruff, line-length 100, `select = E,F,I,N,W`):

```bash
cd isd-agent-benchmark/evaluator && ruff check src/
```

## Conventions

- Much of the benchmark code, docstrings, and CLI help is in **Korean** (the domain is Korean instructional-systems design). Match the surrounding language when editing a file.
- "Scenario" (benchmark) and "design brief" (`alignmentgraph_isd`) refer to the same input; the only translation point is `_scenario_to_design_brief` in the benchmark's `agents/alignmentgraph-isd` adapter. A recent refactor replaced task-based terminology with "design briefs" — prefer that vocabulary in the package.
