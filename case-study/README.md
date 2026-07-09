# Case study: RQ2 refinement-session experiment (IT/Software Engineering)

Measures the four process metrics from the thesis/paper over multi-session
refinement of three training programs, under **four conditions** that receive
the same information (prior design + cumulative brief + edit request) and
differ only in the refinement mechanism:

| Condition | Agent | Mechanism |
|---|---|---|
| `harness_targeted_refine` | AlignmentGraph-ISD | refinement request → IMPACT_POLICY cascade → targeted repair (proposed) |
| `harness_full_regen` | AlignmentGraph-ISD | `scope="regenerate_all"` — isolates the scoping mechanism |
| `react_full_regen` | `baselines/react-isd` | full `run()` on the cumulative scenario — dilemma horn 1 |
| `react_targeted_refine` | `baselines/react-isd` `refine()` | previous output + edit request, no alignment control — dilemma horn 2 |

React round 0 (full generation of the base brief) runs once per program and is
shared by both react chains.

## Layout

- `briefs/`, `agents/`, `scenarios/` — programs, retrieval agent specs, per-program scenario files (8 refinement rounds spanning the IMPACT_POLICY spectrum).
- `baselines/react-isd/` — English-prompt clone of the benchmark's `react-isd` agent with token accounting and `refine()` (targeted refinement without alignment control).
- `run_case_study.py` — session runner for all four conditions.
- `score_alignment.py` — LLM-judge scoring (evaluator ADDIE + Design alignment
  item D1) for every session: the shared cross-agent alignment instrument.
  Runs in the **benchmark venv** (needs `isd_evaluator` + judge credentials).
- `compute_metrics.py` — network-free; merges judge scores when present →
  `results/metrics.{csv,md}`.
- `elicit_brief.py` — interactive brief-elicitation demo (motivation
  illustration; no metrics claim).
- `memory/` — graph versions per harness program; `results/` — session JSONs,
  `manifest.json`, `scores/`, metrics.

## Run

```bash
# From the repo root (uses the core package's venv):
PY=case-study/.venv/bin/python

# 1. Dress rehearsal, no network:
$PY case-study/run_case_study.py --conditions all --fake-llm
$PY case-study/compute_metrics.py
rm -rf case-study/memory case-study/results          # reset before real runs

# 2. Real run (SLM via AGENT_MODEL_* env or flags):
export AGENT_MODEL_NAME=... AGENT_MODEL_API_KEY=... AGENT_MODEL_BASE_URL=...
$PY case-study/run_case_study.py --conditions all

# 3. Judge scoring (benchmark venv, judge credentials in env):
isd-agent-benchmark/venv/bin/python case-study/score_alignment.py

# 4. Metrics:
$PY case-study/compute_metrics.py
```

Useful flags: `--programs java-oop`, `--conditions harness_targeted_refine,react_targeted_refine`,
`--rounds-limit 1`, `--ablation full` (RAG off), `--dry-run`.

**Reset semantics:** harness conditions assert `init` → v1 then `refinement` → vN+1;
a program with existing committed versions fails that assertion, so wipe
`memory/` and `results/` (or use fresh program ids) before repeating a run.
`score_alignment.py` skips already-scored sessions unless `--force`.

## Metrics

| Metric | Instrument | Conditions |
|---|---|---|
| cascade_scope | `refinement_request:*` cascade event / nodes in base graph version | harness only |
| output_locality | changed `addie_output` subsections (sha256 per phase.sub_key) between consecutive rounds of a chain | all |
| graph_locality / touched_locality | graph-node hash diff between committed versions / `node_edits` | harness only |
| cost per round | tokens, llm_calls, latency (unified across result formats) + ratio vs own init | all |
| alignment preservation | judge: evaluator ADDIE score + Design alignment item D1 (`results/scores/`) | all |
| alignment preservation (internal) | audit coverage M/S/E, residual verifier violations | harness only |

## Caveats

- With `--fake-llm`, tokens read 0 and hash-based localities read 0.0 (canned
  identical payloads); use cascade scope, `touched_locality` and
  `unchanged_phases` to check mechanisms in rehearsals.
- Node totals include objective element nodes (`objective:LO-xx`).
- If a refinement round changes the LO id set, a stale element node can linger and
  depress harness coverage; inspect the session JSON if metric 4 drops.
- The react baseline uses English-translated prompts (original is Korean) and
  an author-written refinement prompt — both disclosed as threats to validity; the
  `unchanged` short-circuit deliberately favors the baseline on cost.
