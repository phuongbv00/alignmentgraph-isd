# AlignmentGraph-ISD

**A graph-guided multi-agent harness for auditable Instructional Systems Design with small language models.**

This repository holds the code, experiment and manuscripts of a master's thesis at the School of
Information and Communication Technology, Hanoi University of Science and Technology.

LLM-based agents for instructional design mostly run on commercial models behind an API, while
schools and training centres often need small language models (SLMs) that run on their own
hardware. With an SLM, the *constructive alignment* between learning objectives, learning
activities and assessments is the first thing to break, and an LLM judge that scores the
finished design does not show where it broke.

AlignmentGraph-ISD is a role-decomposed multi-agent system for the ADDIE process. Its agents
share one **alignment graph**: every objective, assessment task, activity, module, material and
session guide is a node, and each relation between them (objective → assessment, objective →
activity, activity → assessment, plus secondary traceability relations) is an edge the harness
records and checks. A run returns the ADDIE design together with the graph and a ledger of every
alignment violation and what became of it, so a reviewer can audit the design rather than trust
a score.

## Repository layout

| Path | What it is |
|:---|:---|
| [`alignmentgraph-isd/`](alignmentgraph-isd/) | **The contribution.** The `alignmentgraph_isd` Python package: the multi-agent harness, the alignment graph, the checks and repairs, a CLI, and an optional demo web app (FastAPI + React). |
| [`experiments/`](experiments/) | **The experiment.** The `isd_experiments` package and its one CLI, `isd-exp`: run generation, LLM-judge and alignment scoring, statistics, pooling, and the generated tables and figures. [`experiments/experiment.toml`](experiments/experiment.toml) is the whole configuration surface. |
| [`isd-agent-benchmark/`](https://github.com/phuongbv00/isd-agent-benchmark) | Git submodule (branch `customize`). [ISD-Agent-Bench](https://github.com/phuongbv00/isd-agent-benchmark): scenarios, the six baseline agents, the rubric and the evaluator. The experiment uses these components but not the benchmark's own entry point. |
| `experiments/corpora/` | Git submodules with the labelled Bloom's-taxonomy corpora used to train and validate the Bloom classifier ([EDM2022CLO](https://github.com/SteveLEEEEE/EDM2022CLO), [bloom-classification-aied2026](https://gitlab.com/zrasoulkhani/bloom-classification-aied2026)). |
| [`docs/`](docs/) | The REV-ECIT 2026 conference paper ([`docs/paper/rev-ecit2026/`](docs/paper/rev-ecit2026/), with its built [`main.pdf`](docs/paper/rev-ecit2026/main.pdf)), the experiment and measurement guides, and supervision records. [`docs/README.md`](docs/README.md) maps which file is canonical for what. |

Dependencies point one way: `experiments/` imports the benchmark and the harness, and nothing
imports `experiments/`. The harness package runs on its own.

## How the harness works

- **Six ADDIE stages, one specialist each** — Needs Analyst, Outcome Designer, Assessment
  Designer, Activity Designer, Content Designer, Implementation Planner. The stage *order* is
  fixed; *how* each stage runs is up to the agent, which works in a native tool-calling
  act → observe loop.
- **Derived fan-out** — item-level work (assessment items, activities, materials, session
  guides) is divided into work sets derived from the design itself (one per module or per
  blueprint set) and written by Developer agents.
- **Alignment state as a tool** — an agent reads the current alignment state of its stage
  (what exists, what is missing, its own open issues) and is pointed back at it when issues
  remain after it submits.
- **Bounded, structural repair** — violations are repaired by the owning agent inside its own
  loop, or by deterministic structural fixes that never write instructional content. What
  remains is reported in the violation ledger, not hidden.
- **Auditable output** — `addie_output`, `trajectory`, `metadata`, the graph dump
  (`graph.json`) and `violations.json`.

Two ablation axes are built in: `agent_mode` (`multi` vs `single` agent) and `context_mode`
(`graph` vs a graph-free `prose` blackboard).

```python
from alignmentgraph_isd import DesignBrief, HarnessRunConfig, MetaAgent

config = HarnessRunConfig(llm_factory=my_chat_model_factory)  # any LangChain chat-model factory
result = MetaAgent(config).run(brief)                          # brief: a DesignBrief
# result keys: addie_output, trajectory, metadata, graph, violations, ...
```

See [`alignmentgraph-isd/README.md`](alignmentgraph-isd/README.md) for the package API and CLI.

## The experiment

Two experiments on the held-out scenarios of ISD-Agent-Bench, with self-hosted Qwen3.5 models
served by vLLM:

1. **Comparison** — AlignmentGraph-ISD against the benchmark's six baseline agents, all under one
   runner and one uniform model configuration.
2. **Ablation** — a 2 × 2 design over decomposition (`multi` / `single`) and substrate
   (`graph` / `prose`).

Every output is scored by two independent instruments:

- **LLM judge scores** — ISD-Agent-Bench's ADDIE rubric and trajectory score, from a roster of
  three LLM judges from different vendors (median of three).
- **Alignment signals** — a deterministic, LLM-free panel of six signals over the three edges of
  the objective–activity–assessment triad: textual correspondence (sentence-embedding
  similarity) and cognitive demand (Bloom-level congruence, Porter and Webb indices from a
  fine-tuned BERT Bloom classifier). Specified in
  [`docs/guides/alignment_protocol.md`](docs/guides/alignment_protocol.md).

The model ladder, datasets, agent rosters, ablation arms and both scoring instruments are
declared in [`experiments/experiment.toml`](experiments/experiment.toml). The end-to-end workflow
(data split → serving → run → audit → scoring → pooling → paper tables) is in
[`docs/guides/benchmark_guides.md`](docs/guides/benchmark_guides.md).

## Getting started

Requires Python ≥ 3.11 and git.

```bash
git clone --recurse-submodules <this-repo-url>
cd <repo>/experiments
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
./isd-exp doctor --fix      # installs the benchmark, agents, harness and evaluator into this venv
./isd-exp help              # every stage; `help <stage> <sub>` goes deeper
```

`experiments/.env` holds secrets only (API keys for the serving endpoints and the LLM judges);
endpoints and serving limits belong in `experiment.toml`, and `isd-exp audit preflight` refuses
them in `.env`.

Typical flow:

```bash
./isd-exp data split ablation-30            # build the evaluation split
./isd-exp run comparison --dry-run          # print the launch plan
./isd-exp run comparison --judge            # generate, then judge each run as it finishes
./isd-exp judge alignment 'results/test_30_benchmark_*'
./isd-exp pool comparison --auto-encoders --auto-bloom
./isd-exp pool ablation                     # after `run ablation --judge`
.venv/bin/python ../docs/paper/rev-ecit2026/make_tables.py   # the paper's tables and macros
```

Running the experiment calls paid or self-hosted model endpoints and can be expensive; both
`run comparison` and `run ablation` ask for confirmation first.

The alignment panel's primary Bloom arm needs a fine-tuned checkpoint in
`experiments/models/` (not tracked, ~420 MB). `./isd-exp bloom train` reproduces one from the
corpora; the cheaper `lexicon` arm needs none.

### Demo web app

```bash
cd alignmentgraph-isd
./run-app.sh
```

Watch a run live: the alignment graph as it grows, each agent's context, and the violation
ledger. Configure any OpenAI-compatible endpoint in the app's Model settings. See
[`alignmentgraph-isd/src/alignmentgraph_isd/server/README.md`](alignmentgraph-isd/src/alignmentgraph_isd/server/README.md).

### Tests

```bash
cd alignmentgraph-isd && python -m pytest tests/   # network-free, fake model
cd experiments && python -m pytest tests/          # offline
```

## Status

Work in progress. The REV-ECIT 2026 conference paper reports both experiments on one model size
(Qwen3.5-2B, 30 held-out scenarios); the full study across the model ladder is still to be run.
The paper's tables and number macros are generated from the pooled results by
[`make_tables.py`](docs/paper/rev-ecit2026/make_tables.py), never typed by hand, and are
committed in [`generated/`](docs/paper/rev-ecit2026/generated/) so the paper builds without
re-running the experiment (`docs/paper/rev-ecit2026/compile.sh`, XeLaTeX).

## Authors

- **Bùi Việt Phương** (Viet-Phuong Bui) — author
- **Phạm Văn Hải** (Van-Hai Pham) — supervisor
- **Bùi Văn Tâm** (Van-Tam Bui) — co-supervisor

School of Information and Communication Technology, Hanoi University of Science and Technology,
Hanoi, Vietnam.

## Acknowledgements

The baseline agents, scenarios, rubric and evaluator come from ISD-Agent-Bench. The Bloom
classifier is trained on the corpora of Li et al. (2022), *Automatic Classification of Learning
Objectives Based on Bloom's Taxonomy* (EDM 2022), and of *Cross-Dataset Bloom Question
Classification* (AIED 2026). Each submodule keeps its own license.
