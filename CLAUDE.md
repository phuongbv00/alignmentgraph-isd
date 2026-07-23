# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Tooling

- **Prefer the `serena` MCP tools** (`find_symbol`, `find_referencing_symbols`, `replace_symbol_body`, `search_for_pattern`, etc.) over generic `Read`/`Grep`/`Edit` when navigating or editing code in `alignmentgraph-isd/` or `isd-agent-benchmark/`. Call `mcp__serena__initial_instructions` first if it hasn't been read yet this session.
- **When editing the thesis manuscript** (anything under `docs/thesis/`), always run `docs/thesis/compile.sh` afterward to confirm it still builds (`main.pdf`). Report any LaTeX errors instead of leaving them unverified.

## Repository layout

This is a master's thesis monorepo with three top-level parts:

- **`docs/`** — research documents.
  - `docs/summary.md` — RQ context (RQ1 = quality vs Qwen model scale, RQ2 = LLM-free constructive-alignment metric).
  - `docs/benchmark_guides.md` — **single source of truth for the whole benchmark workflow**: data split → RunPod/vLLM serving → tune → ladder run → audit → RQ2 scoring → pooling → paper tables, plus the full metrics reference (Appendix A). Consult it before touching anything experiment-related; it superseded and replaced the old `metrics.md`, `notes-serving-setup.md`, `results-audit-checklist.md`, and the benchmark's `scripts/README_ladder.md`.
  - `docs/paper/` — the research paper: `acm/` (ACM template; the benchmark's `scripts/8_gen_paper_tables.py` + `8_gen_paper_figures.py` write generated tables/macros/figures to the benchmark's `results/generated/`, and `docs/scripts/sync_generated.sh` copies them into `docs/generated/` (the paper \input/\includegraphics targets, via relative paths) — numbers in the paper are generated, never hand-typed), `structure-guide.md`, `refs-deployment-survey.md`.
  - `docs/refs/` — reference material pulled in from other repos.
  - `docs/thesis/` — the LaTeX thesis manuscript. `main.tex` is the entry point; `Chapter/` holds one `.tex` file per chapter; `Figure/` holds images; `glossary.tex` and `reference.bib` hold the glossary and bibliography; `compile.sh` runs `pdflatex -> bibtex -> pdflatex -> pdflatex` to produce `main.pdf`. LaTeX build artifacts and `*.pdf` are gitignored.
- **`alignmentgraph-isd/`** — the **thesis contribution**: a standalone Python package (`alignmentgraph_isd`), a LangGraph-based multi-agent ADDIE instructional-design harness. Core only — experiment harnesses live outside. Tracked directly in this repo (not a submodule).
- **`isd-agent-benchmark/`** — a **git submodule** (`git@github.com:phuongbv00/isd-agent-benchmark.git`, branch `customize`) that benchmarks ISD agents. It contains six baseline/comparison agents plus a thin wrapper that runs `alignmentgraph-isd` as a seventh agent.

The two code parts are coupled: the benchmark agent `agents/alignmentgraph-isd` is a thin adapter (`AlignmentGraphISDAgent`) whose only dependency is the top-level `alignmentgraph-isd` package. The adapter bridges the benchmark's *scenario* vocabulary to the package's *design brief* contract (`_scenario_to_design_brief`, `scenario_id` → `id`) and injects the benchmark's LLM config as a `ChatModelFactory`. See `agents/alignmentgraph-isd/README.md`.

## The `alignmentgraph-isd` package (thesis core)

Located in `alignmentgraph-isd/src/alignmentgraph_isd/`. **There is no ablation system — the full pipeline is the only pipeline** (the former `HARNESS_ABLATION` presets were removed in the 2026-07 RQ pivot; do not reintroduce them).

Public API (see the package README for details):

```python
from alignmentgraph_isd import DesignBrief, HarnessRunConfig, run_design_brief
result = run_design_brief(brief, config)   # config.llm_factory is REQUIRED — hard error, never silent empty output
# result keys: addie_output, trajectory, metadata, graph, graph_dot
```

Layout:

- **`config.py`** — `HarnessRunConfig`: `llm_factory` (any LangChain chat-model factory, required), `use_rag` + `retrieval_subagents` (RAG gate, both required to open it), `regen_budget`/`regen_backoff_seconds` (re-run a specialist whose section came back with empty required fields; the benchmark adapter sources these from `BENCHMARK_DELAY` / `HARNESS_REGEN_*` env).
- **`cli.py`** — `alignmentgraph-isd run` on a JSON file already in `DesignBrief` shape; builds a model from `--model-*` flags or `AGENT_MODEL_*` env vars.
- **`core/runner.py`** — `MetaAgent`: builds and invokes the compiled LangGraph `StateGraph` per design brief, packages output + trajectory + graph dump.
- **`core/graph.py`** — `AlignmentGraph`, the alignment-dependency graph of ISD artifacts. Edge type = human-readable relation key in `"RX-name"` form (e.g. `"R3-measures"`); 13 relations total. `to_full_dict()` / `to_dot()` produce the per-run graph dump (saved as `<agent_id>_graph.json` / `.dot` in benchmark results) — this is the auditability contribution.
- **`core/agents/`** — specialist agents, one per ISD concern (`needs_context`, `objective_design`, `assessment_design`, `activity_material`, `implementation_plan`, `evaluation_revision`), plus `pedagogical_verifier` (content-level alignment checks + LLM repair) and `addie_aggregator` (assembles final ADDIE output). All extend `core/agents/base.py` (`BaseISDAgent`).
- **`core/rag/`** — external-corpus retrieval (`agent.py`, `planner.py`, `sandbox.py`).
- **`core/`** also holds `alignment.py`, `nodes.py`, `llm.py`, `audit.py`, `trajectory.py`, `validation.py`, `viz.py`, `schema.py` + `schema/addie_output.json`.

**RAG = external-corpus retrieval only, and it is on-demand.** `use_rag` is off by default and off on the benchmark. When enabled, retrieval is NOT performed upfront: each specialist decides mid-task whether/how to retrieve (`BaseISDAgent._maybe_retrieve` → decision call → `core/rag/sandbox.py` executes single/sequential/parallel plans over `core/rag/agent.py` retrieval agents). Graph-context retrieval (the AlignmentGraph subgraph) is core, always on, and is **not** called RAG.

## The benchmark (`isd-agent-benchmark/`)

`run_benchmark.py` is the orchestrator. Key facts that aren't obvious from the README:

- **Agents run in-process, not as subprocesses.** `_get_agent_runner(agent_id, llm_config)` imports each agent's Python class directly and returns a `run(scenario) -> dict` closure. The CLI interfaces documented in `shared/interfaces/agent_interface.md` exist but the benchmark does not use them. Agent `src/` paths are added to `sys.path` at the top of `run_benchmark.py`.
- **The evaluator IS run as a subprocess** (`isd-evaluator`), with stdout streamed to parse `__EVAL_PROGRESS__` markers.
- Each agent must return `{"addie_output": ..., "trajectory": ..., "metadata": ...}`. Output schemas live in `shared/schemas/*.json`. The metadata saved in `*_trajectory.json` carries uniform `token_usage` + `execution_time_seconds` for every agent.
- **`shared/llm`** is the single source of LLM configuration. Agents must NOT read provider env vars or instantiate `ChatOpenAI`/`ChatAnthropic` directly — call `create_chat_model(llm_config)` / `llm_config_from_env()`. `LLMConfig.api_spec` is the API *contract* (`openai_compatible`/`anthropic`), distinct from `provider` (a backend preset label). Add providers via config, not agent code.
- `shared/llm/factory.py` also implements the three serving-protection env flags used for the self-hosted ladder (uniform across all agents — fairness): `AGENT_MODEL_MAX_TOKENS_CAP` (ladder value **8096** — not the 8192 some older notes claimed), `AGENT_MODEL_STREAMING=1`, `AGENT_MODEL_DISABLE_THINKING=1`.
- Agent vs. judge models are configured **separately** (`AGENT_MODEL_*` vs `JUDGE_MODEL_*`) to avoid self-preference bias. Judge config supports comma-separated lists aligned across names/providers/URLs, with `|` grouping multiple credentials per judge.
- Agent env-quads for the self-hosted Qwen pods (`QWEN{08B,2B,4B,9B}_AGENT_MODEL_*`) live in a **marker-managed block at the end of `.env`**, written by `scripts/3_sync_runpod_pods_env.py` (read-only against the RunPod API). Never hand-edit that block.
- Results land in `results/<dataset>_benchmark_<model>_<run_tag>_<ts>/` (e.g. `test_90_benchmark_Qwen3.5-2B_r1_...`) or `results/single_<ts>/` for single scenarios. Both launchers take `RUN_TAGS` (comma/space-separated, run sequentially per slot).

### Evaluator (`evaluator/`)

`isd_evaluator` package. ADDIE rubric scoring: 33 Context-Matrix sub-steps → 13 consolidated items → 5 ADDIE phases (100 pts), plus BFCL-based trajectory scoring; per-scenario canonical composite `total_score = 0.7·ADDIE + 0.3·Trajectory` (beware: the aggregate CSV "Avg" column is judge-mean and diverges when a component is missing — always use per-scenario `total_score`). Multi-judge by default (`--single-judge` to disable). Context-aware weighting in `metrics/context_weights.py`. `metrics/alignment.py` holds the **RQ2 constructive-alignment metric** (deterministic, LLM-free: Porter index, Webb range/Bloom-consistency, embedding coverage/precision) — run over a results dir via `scripts/7_score_alignment.py`. Full metric definitions: `docs/benchmark_guides.md` Appendix A.

## Common commands

All commands run from inside `isd-agent-benchmark/`. The `scripts/` number prefixes follow pipeline order; the full workflow (incl. audits and paper-table generation) is in `docs/benchmark_guides.md`.

```bash
# One-time setup: creates venv, installs base deps + every agent + evaluator (editable)
./scripts/1_setup.sh
python run_benchmark.py --install   # reinstall agent/evaluator packages (editable)
python run_benchmark.py --check     # verify all agent modules import cleanly

# Data (committed; only re-run when rebuilding from scratch, seed 42)
./scripts/2_split_data.sh                                  # 95/5 train/test split
python scripts/2_split_stratified_subset.py --source scenarios/train --target scenarios/train_30
python scripts/2_split_stratified_subset.py --source scenarios/test  --target scenarios/test_90 --per-cell 3

# Serving env: sync RunPod pod env-quads into .env (managed block)
python scripts/3_sync_runpod_pods_env.py        # --dry-run to preview

# Smoke run (1 scenario)
./scripts/3_run_benchmark_test.sh

# Tune on train_30 (one tmux session per slot; RUN_TAGS = sequential tagged runs)
DATASET=train_30 AGENT_MODEL_SLOTS=qwen2b RUN_TAGS=tune1 ./scripts/4_run_benchmark.sh

# RQ1 ladder (EXPENSIVE — 4 sizes × 3 runs × 7 agents × 90 scenarios) + audits
python scripts/5_audit_preflight.py
./scripts/5_run_ladder.sh
python scripts/6_audit_inflight.py    # every 30–60 min while running
python scripts/6_audit_postrun.py     # after runs finish

# Post-processing (local; no agent/judge calls)
python scripts/7_score_alignment.py results/test_90_benchmark_<...>   # per run dir (RQ2)
python scripts/7_pool_ladder_runs.py --auto-glob 'results/test_90_benchmark_*_r*'
python scripts/8_gen_paper_tables.py --pooled results/pooled_ladder.json   # → results/generated/
python scripts/8_gen_paper_figures.py --runs-glob 'results/test_90_benchmark_*_r*'
../docs/scripts/sync_generated.sh   # copy generated artifacts into docs/generated/

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

# Run a named dataset (scenarios/<name>/): train, test, train_30, test_90
python run_benchmark.py --dataset test_90 --agents baseline,alignmentgraph-isd
```

Default agents: `eduplanner, baseline, react-isd, addie-agent, dick-carey-agent, rpisd-agent`. **`alignmentgraph-isd` is NOT in the defaults — add it explicitly with `--agents`.**

Rate-limit presets (`-r conservative|moderate|aggressive|turbo`) set worker counts and `BENCHMARK_DELAY` together; per-slot override via `<SLOT>_RATE_LIMIT`. See the benchmark README for the full flag/env matrix.

### Tests

Each package is independently installable/testable with pytest (`requires-python >=3.11`). Run from the package directory:

```bash
cd alignmentgraph-isd && python -m pytest tests/         # package tests (network-free; fake llm_factory)
cd isd-agent-benchmark/evaluator && pytest tests/        # evaluator tests (asyncio_mode=auto)
cd isd-agent-benchmark/shared && pytest tests/           # shared model/util tests
cd isd-agent-benchmark/agents/<agent> && pytest tests/   # per-agent tests (where present)
pytest tests/test_addie_rubric_parsing.py::<name>        # single test
```

Lint (evaluator uses ruff, line-length 100, `select = E,F,I,N,W`):

```bash
cd isd-agent-benchmark/evaluator && ruff check src/
```

## Conventions

- Much of the benchmark code, docstrings, and CLI help is in **Korean** (the domain is Korean instructional-systems design). Match the surrounding language when editing a file. `docs/` (guide, summary) is Vietnamese/English.
- "Scenario" (benchmark) and "design brief" (`alignmentgraph_isd`) refer to the same input; the only translation point is `_scenario_to_design_brief` in the benchmark's `agents/alignmentgraph-isd` adapter. Prefer the "design brief" vocabulary inside the package.
- Numbers reported in the paper must come from the generated artifacts (`8_gen_paper_tables.py` output), never typed by hand.
