# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Tooling

- **Prefer the `serena` MCP tools** (`find_symbol`, `find_referencing_symbols`, `replace_symbol_body`, `search_for_pattern`, etc.) over generic `Read`/`Grep`/`Edit` when navigating or editing code in `alignmentgraph-isd/` or `isd-agent-benchmark/`. Call `mcp__serena__initial_instructions` first if it hasn't been read yet this session.
- **When editing the thesis manuscript** (anything under `docs/thesis/`), always run `docs/thesis/compile.sh` afterward to confirm it still builds (`main.pdf`). Report any LaTeX errors instead of leaving them unverified.

## Repository layout

This is a master's thesis monorepo with four top-level parts:

- **`docs/`** — research documents.
  - `docs/summary.md` — RQ context (RQ1 = quality vs Qwen model scale, RQ2 = constructive-alignment evaluation protocol, reported as a flat 7-signal panel with **no primary endpoint**) **and the canonical spec of the RQ2 protocol** (§"Alignment evaluation protocol" — the paper is updated FROM this section).
  - `docs/benchmark_guides.md` — **single source of truth for the whole benchmark workflow**: data split → RunPod/vLLM serving → tune → ladder run → audit → RQ2 scoring → pooling → paper tables, plus the full metrics reference (Appendix A). Consult it before touching anything experiment-related; it superseded and replaced the old `metrics.md`, `notes-serving-setup.md`, `results-audit-checklist.md`, and the benchmark's `scripts/README_ladder.md`.
  - `docs/paper/` — the research paper: `acm/` (ACM template; the benchmark's `scripts/alignmentgraph-isd-bench/09_gen_paper_tables.py` + `10_gen_paper_figures.py` write generated tables/macros/figures to the benchmark's `results/generated/`, and `docs/scripts/sync_generated.sh` copies them into `docs/generated/` (the paper \input/\includegraphics targets, via relative paths) — numbers in the paper are generated, never hand-typed), `structure-guide.md`, `refs-deployment-survey.md`.
  - `docs/refs/` — reference material pulled in from other repos.
  - `docs/thesis/` — the LaTeX thesis manuscript. `main.tex` is the entry point; `Chapter/` holds one `.tex` file per chapter; `Figure/` holds images; `glossary.tex` and `reference.bib` hold the glossary and bibliography; `compile.sh` runs `pdflatex -> bibtex -> pdflatex -> pdflatex` to produce `main.pdf`. LaTeX build artifacts and `*.pdf` are gitignored.
- **`alignmentgraph-isd/`** — the **thesis contribution**: a standalone Python package (`alignmentgraph_isd`), a LangGraph-based multi-agent ADDIE instructional-design harness. Core only — experiment harnesses live outside. Tracked directly in this repo (not a submodule).
- **`isd-agent-benchmark/`** — a **git submodule** (`git@github.com:phuongbv00/isd-agent-benchmark.git`, branch `customize`) that benchmarks ISD agents. It contains six baseline/comparison agents plus a thin wrapper that runs `alignmentgraph-isd` as a seventh agent.
- **`EDM2022CLO/`** — a **git submodule** (`git@github.com:phuongbv00/EDM2022CLO.git`, fork of `SteveLEEEEE/EDM2022CLO`), the released dataset + notebooks of Li et al. (2022), *Automatic Classification of Learning Objectives Based on Bloom's Taxonomy* (EDM 2022). **Reference material only — no code here imports it.** Two uses: (1) `data/sample_full.csv` (21,380 expert-labelled learning objectives, wide multi-label) is the validity-evidence corpus for the Bloom lexicon — see `scripts/alignmentgraph-isd-bench/00_validate_bloom.py`; (2) the notebooks are the published method to reproduce if the Bloom classifier is ever upgraded from the lexicon. `data/LIWC2015 Results (...).csv` is pre-extracted LIWC features: enough to reproduce the paper's SVM/RF/XGBoost numbers, but NOT usable on our own objectives (LIWC2015 is a paid tool), so only their BERT path transfers.

The two code parts are coupled: the benchmark agent `agents/alignmentgraph-isd` is a thin adapter (`AlignmentGraphISDAgent`) whose only dependency is the top-level `alignmentgraph-isd` package. The adapter bridges the benchmark's *scenario* vocabulary to the package's *design brief* contract (`_scenario_to_design_brief`, `scenario_id` → `id`) and injects the benchmark's LLM config as a `ChatModelFactory`. See `agents/alignmentgraph-isd/README.md`.

## The `alignmentgraph-isd` package (thesis core)

Located in `alignmentgraph-isd/src/alignmentgraph_isd/`. **The full pipeline is the default and only preset** (the former `HARNESS_ABLATION` preset system was removed in the 2026-07 RQ pivot; do not reintroduce it). For the defense ablation study, `HarnessRunConfig` carries exactly two boolean switches, both `True` by default: `enable_verifier` (wires the QC verify+repair nodes) and `enable_graph_context` (gates the READ side of graph-context prompt injection only — the graph is always written). They are set solely via the benchmark's per-arm agent registrations (`alignmentgraph-isd-no-verifier`, `-no-graph-ctx`, `-skeleton` in `run_benchmark.py`), and the resolved flags are recorded in `metadata.run_config`.

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
- `shared/llm/factory.py` also implements the three serving-protection env flags used for the self-hosted ladder (uniform across all agents — fairness): `AGENT_MODEL_MAX_TOKENS_CAP` (ladder value **8192**), `AGENT_MODEL_STREAMING=1`, `AGENT_MODEL_DISABLE_THINKING=1`.
- Agent vs. judge models are configured **separately** (`AGENT_MODEL_*` vs `JUDGE_MODEL_*`) to avoid self-preference bias. Judge config supports comma-separated lists aligned across names/providers/URLs, with `|` grouping multiple credentials per judge.
- Agent env-quads for the self-hosted Qwen pods (`QWEN{08B,2B,4B,9B}_AGENT_MODEL_*`) live in a **marker-managed block at the end of `.env`**, written by `scripts/3_sync_runpod_pods_env.py` (read-only against the RunPod API). Never hand-edit that block.
- Results land in `results/<dataset>_benchmark_<model>_<run_tag>_<ts>/` (e.g. `test_90_benchmark_Qwen3.5-2B_r1_...`) or `results/single_<ts>/` for single scenarios. Both launchers take `RUN_TAGS` (comma/space-separated, run sequentially per slot).

### Evaluator (`evaluator/`)

`isd_evaluator` package. ADDIE rubric scoring: 33 Context-Matrix sub-steps → 13 consolidated items → 5 ADDIE phases (100 pts), plus BFCL-based trajectory scoring; per-scenario `total_score = 0.7·ADDIE + 0.3·Trajectory` (beware: the aggregate CSV "Avg" column is judge-mean and diverges when a component is missing — always read per-scenario fields). **RQ1 reports its judge signals side by side, with no composite as headline** (`RQ1_SIGNALS` in `07_pool_ladder_runs.py`): `addie_median` is the LEAD because ADDIE measures instructional-design content quality — the construct the research question is about — while `trajectory_score` measures process conformance, a different construct, and `total_score`'s 0.7/0.3 weights come from the benchmark rather than from this study. All three get identical statistics (3 failure policies, Holm per signal×policy) under `comparisons.by_signal[<signal>]`; `total_score` is kept in full for comparability with ISD-Agent-Bench's own reporting. This endpoint choice was made **after** seeing results and must be declared post-hoc in the paper. Multi-judge by default (`--single-judge` to disable). Context-aware weighting in `metrics/context_weights.py`. `metrics/alignment.py` holds the **RQ2 constructive-alignment evaluation protocol**: deterministic, no LLM in measurement, **NO similarity threshold anywhere**, and reported as a **flat panel of 7 signals with NO primary endpoint** (`PANEL_SIGNALS`) — calling one signal "primary" is an implicit composite. Two mechanically independent instrument families, each with its own sensitivity axis: **A, textual correspondence** (`objective_{assessment,activity,evaluation}_similarity` = continuous mean-max **rectified** cosine, `max(0, cos)` on [0,1] — a scale choice, not a matching cutoff, never describe it as raw cosine; plus `assessment_objective_similarity`, the reverse direction, flagged **non-directional** — high can mean "no orphan items" or "items restate objectives"); **B, cognitive demand** (`objective_cognitive_congruence`, Porter, Webb — no similarity involved). **Naming rule**: a signal is named after the operation it computes, because names get read on figure axes and slides where a name that asserts more than the operation does the work only the validity evidence earns — so "alignment" names the protocol and the `aligned(o)` legs but never a metric, and nothing is called "precision" (that implies a retrieval frame needing a threshold this protocol lacks). Multiplicity is reported twice per size: `p_holm` within one signal (6 comparisons) and `p_holm_panel` over the whole panel×baseline family. RQ2 pooling mirrors RQ1's failure policies: the complete-case layer is over *available* outputs, never call it unconditional; `06` always records a `missing_outputs` roster and `07` always reads it to add a failure=0 pass — run over a results dir via `scripts/alignmentgraph-isd-bench/06_score_alignment.py`. Instruments are **preset-only**: encoders from `ENCODER_PRESETS` (`--encoder-preset(s)`/`--all-encoders`), Bloom classifiers from `BLOOM_PRESETS` (`--bloom-preset(s)`, `--bloom-checkpoint`); `--all-arms` runs the whole sweep. With no flag it runs the primary configuration `nemotron` + `bertbloom`. The sweep is a **star, not a grid** — each arm deviates from the primary on exactly one axis (5 arms, not 8). The primary Bloom arm `bertbloom` is a single 6-way softmax `bert-base-uncased` head fine-tuned on the EDM2022CLO corpus of Li et al. 2022 — their corpus, not their classifier design: their notebooks yield either six independent binary heads or one multi-label sigmoid head, both of which need an extra decision layer to produce the single level per text the panel requires. Measured on a held-out split it reaches kappa 0.926 vs the lexicon's 0.650, which is why it is primary; the cost, which must be declared, is that its per-case level assignment is no longer traceable to Anderson & Krathwohl and family B is no longer bit-wise deterministic (a discrete argmax, so fp noise can flip a label rather than nudge a number). **It needs a checkpoint on disk** (`evaluator/scripts/train_bloom_6way_classifier.py`, ~15 min locally), so alignment scoring is no longer zero-setup; a missing checkpoint SKIPS the arm rather than falling back to the lexicon. The `lexicon` arm is the sensitivity axis for family B (3 of the 7 signals are Bloom-derived, so without it that family is checked by no axis) and costs no GPU (`--bloom-presets lexicon --embed-cache-only`); the two arms agree at only kappa 0.665, so neither mirrors the other. Each encoder preset also pins its **backend**: only the 8B primary `nemotron` is served (`api`, endpoints from per-slot `<SLOT>_EMBED_BASE_URLS` written by `05_sync_embed_pod_env.py`, or `--embed-base-urls-for SLOT=...` — deliberately no shared endpoint/model/revision variable); `bgem3`/`granite` run `local` in-process via sentence-transformers (measured on an M4 Pro: ~44 and ~25 min for the ladder's 335k unique texts), `tfidf` is pure Python. So the pod is needed only while the primary arm is scored. Never embed one model on two backends: the cache key is `sha1(model[@revision]+text)` and does not record the backend, so mixing sources is silent. Full metric definitions: `docs/benchmark_guides.md` Appendix A.

## Common commands

All commands run from inside `isd-agent-benchmark/`. The `scripts/` number prefixes follow pipeline order; shared scripts sit in `scripts/`, the ladder pipeline in `scripts/alignmentgraph-isd-bench/`, the ablation pipeline in `scripts/alignmentgraph-isd-bench/ablation/`. The full workflow (incl. audits and paper-table generation) is in `docs/benchmark_guides.md`.

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

# RQ1 ladder + ablation arms in one go (EXPENSIVE — 4 sizes × 3 runs × 10 agents × 90 scenarios) + audits
python scripts/alignmentgraph-isd-bench/01_audit_preflight.py
./scripts/alignmentgraph-isd-bench/02_run_ladder.sh
python scripts/alignmentgraph-isd-bench/03_audit_inflight.py    # every 30–60 min while running
python scripts/alignmentgraph-isd-bench/04_audit_postrun.py     # after runs finish

# Post-processing (local; no agent/judge calls)
python scripts/alignmentgraph-isd-bench/06_score_alignment.py results/test_90_benchmark_<...>   # per run dir (RQ2; needs NEMOTRON_EMBED_BASE_URLS, see guides §7)
python scripts/alignmentgraph-isd-bench/06_score_alignment.py results/test_90_benchmark_<...> --all-arms   # + the 3-axis sensitivity star
python scripts/alignmentgraph-isd-bench/07_pool_ladder_runs.py --auto-glob 'results/test_90_benchmark_*_r*' --auto-encoders --auto-bloom
python scripts/alignmentgraph-isd-bench/09_gen_paper_tables.py --pooled results/pooled_ladder.json   # → results/generated/
python scripts/alignmentgraph-isd-bench/10_gen_paper_figures.py --runs-glob 'results/test_90_benchmark_*_r*'
python scripts/alignmentgraph-isd-bench/14_gen_sensitivity_table.py   # if pooled carries alignment_sensitivity
../docs/scripts/sync_generated.sh   # copy generated artifacts into docs/generated/
python scripts/alignmentgraph-isd-bench/99_audit_artifacts.py   # FINAL GATE — run after sync; exit 1 = something missing/stale/placeholder/unwired

# Ablation study (defense). Since 2026-07-26 the 4 arms run INSIDE the ladder
# (02_run_ladder.sh launches 10 agents), so there is no separate ablation run and
# A0 is literally the ladder's alignmentgraph-isd — no judge-drift caveat needed.
# Full pipeline: docs/benchmark_guides.md §5.4
python scripts/alignmentgraph-isd-bench/ablation/08_pool_ablation_runs.py --auto-glob 'results/test_90_benchmark_*_r[123]_*'
python scripts/alignmentgraph-isd-bench/ablation/11_gen_ablation_tables.py    # tab_ablation{,_factorial,_factorial_full}.tex + abl_macros.tex + stats_ablation.md
python scripts/alignmentgraph-isd-bench/ablation/12_gen_ablation_figures.py   # figures/fig_ablation{,_factorial,_ladder,_components}

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

Default agents: `eduplanner, baseline, react-isd, addie-agent, dick-carey-agent, rpisd-agent`. **`alignmentgraph-isd` is NOT in the defaults — add it explicitly with `--agents`.** The ablation arms (`alignmentgraph-isd-no-verifier`, `alignmentgraph-isd-no-graph-ctx`, `alignmentgraph-isd-skeleton`) are likewise registry-only: same adapter package with the flags pinned per agent_id, selected explicitly via `--agents` — they are part of `02_run_ladder.sh`'s 10-agent list.

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
- Numbers reported in the paper must come from the generated artifacts (`09_gen_paper_tables.py` output), never typed by hand.
