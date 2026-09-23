# experiments

The thesis experiment. One entry point, `isd-exp`; everything else here serves it.

This exists so the benchmark can be a **tool** again. The study uses ISD-Agent-Bench's
components -- its scenarios, its six baseline agents, `shared/llm`, its rubric and its evaluator --
and none of its entry points: the orchestration (`runner/`) and the scoring steps (`judge/`) are
this package's own.

Generating and scoring are separate steps. `isd-exp run <experiment>` generates;
`isd-exp judge llm` and `isd-exp judge alignment` score a finished run and never regenerate it;
`run --judge` chains them.

## Layout

```
experiment.toml        the whole configuration surface — edit this, not code
bin/                   tmux launchers (shell, because tmux orchestration is shell-shaped)
models/                Bloom checkpoint (gitignored; moved between machines, never retrained)
results/               run dirs, pooled JSON, generated/ (gitignored)
src/isd_experiments/
  paths.py bench.py    where things are; how the benchmark's components are reached
  config.py            experiment.toml -> typed objects
  stats.py             hand-rolled inferential statistics, stdlib only
  runs.py schema.py    run-dir discovery; the pooled-JSON contract
  latex.py plots.py    shared formatting and figure style
  runner/              generate one run: agents, the uniform model config, the run dir
  judge/               score finished runs: llm (the benchmark's evaluator), alignment
  alignment/           the constructive-alignment instruments (protocol, presets, Bloom)
  pool/                LLM judge and panel pooling, per experiment
  report/              tables, figures, notes, the facts sheet, sync
  audit/               preflight, inflight, postrun, repair, artifacts
  serve/ data/ freeze/ endpoints, splits, the code-freeze manifest
  expert/ trajectory   roadmap stages with a home but no implementation yet
tests/                 217 tests; see the four guards below
```

## Three rules the tests enforce

**Dependency runs one way.** `experiments/` imports the benchmark and the harness package.
Nothing imports `isd_experiments`. Delete this directory and both other trees still run; the
reverse is not true.

**No vendor lock-in.** The model ladder, the serving host, the datasets, the rosters, the
ablation arms and the alignment instruments are all declared in `experiment.toml`. No module
in `src/` names a vendor or a model family. Running a two-rung Llama+Gemma ladder on localhost
is a config edit.

**Names say what a thing is.** No `rq1`/`rq2`/`tn1`/`tn2` in modules, constants, artifacts,
tags or log dirs. The measurement families are `llm_judge` and `alignment`; the experiments are
`comparison` and `ablation`.

## Getting started

`./isd-exp` is a wrapper that finds the `.venv` beside it and execs the CLI there. Nothing
needs activating, nothing goes on `PATH`.

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"   # once
./isd-exp doctor --fix
./isd-exp help                # subcommands read down the roadmap's six phases
./isd-exp help run comparison # or any stage; `help <stage> <sub>` goes deeper
```

If you would rather have a real command, `pip install -e .` into any environment puts
`isd-exp` on that environment's PATH; the wrapper then becomes redundant.

Full workflow: `docs/guides/benchmark_guides.md`. Measurement protocol:
`docs/guides/alignment_protocol.md`. Experiment design: `docs/supervision/feedbacks/sprint1_20260828_0908/`.

## Not implemented

Two roadmap stages have a home and a contract but no implementation, and they raise rather
than returning anything — a function producing plausible numbers would let the roadmap's
checklist be ticked without the work being done:

- `isd-exp trajectory rescore` — the diagnostic trajectory layer at a higher tool-call cap.
  Must be settled **before** the official comparison run; the cap cannot change once results
  are seen.
- `isd-exp expert sample` / `aggregate` — expert validation. Comes after code freeze and after
  official outputs exist.
