# Cost / deployability profile (generated)


Generated at: 2026-09-17T12:22:53  
Source: 2 ladder run directories, `*_trajectory.json` -> `metadata.token_usage` and `metadata.execution_time_seconds`.

## What is and is not measured

- **Tokens come only from `metadata.token_usage`.** The top-level `metadata.total_tokens` is 0 for most agents and is never read.
- **`metadata.cost_usd` is ignored.** On a self-hosted ladder there is no per-token price; one agent nonetheless writes a dollar figure from a hosted-API price list. Any dollar number below is derived here, from the labelled assumption block.
- **Wall-clock caveat.** Wall-clock is throughput under load, not latency: the ladder ran ? scenarios x ? agents concurrently (up to None in-flight designs) against 1 vLLM endpoints per size, so per-scenario seconds include queueing behind the other agents and are not a single-user response time.
- **Cost is conditional on survival.** An agent that crashes writes no trajectory, so its statistics describe only the scenarios it completed. Read every row together with its `n`.

## Concurrency provenance (measured)

- agent workers per scenario: []
- concurrent scenarios: []
- vLLM endpoints per model size: [1]
- peak in-flight designs: None

## Per agent x size (median [IQR], mean)

### Qwen3.5-0.8B

| Agent | Total tok. med [IQR] | mean | Prompt med | Compl. med | Calls med [IQR] | Wall s med [IQR] | n | cov. |
|---|---|---|---|---|---|---|---|---|
| Baseline | 11460 [11460--11460] | 11460 | 9600 | 1860 | -- [------] | 10 [9--14] | 5/6 * | 83% |
| ReAct-ISD | 22920 [22920--22920] | 22920 | 19200 | 3720 | -- [------] | 20 [16--22] | 6/6 | 100% |
| AlignmentGraph-ISD | 697150 [695240--699060] | 703517 | 584000 | 113150 | -- [------] | 356 [353--363] | 6/6 | 100% |

### Qwen3.5-4B

| Agent | Total tok. med [IQR] | mean | Prompt med | Compl. med | Calls med [IQR] | Wall s med [IQR] | n | cov. |
|---|---|---|---|---|---|---|---|---|
| Baseline | 11460 [11460--11460] | 11460 | 9600 | 1860 | -- [------] | 20 [20--20] | 5/6 * | 83% |
| ReAct-ISD | 22920 [22920--22920] | 22920 | 19200 | 3720 | -- [------] | 20 [15--22] | 6/6 | 100% |
| AlignmentGraph-ISD | 700970 [696195--705745] | 705427 | 587200 | 113770 | -- [------] | 362 [357--367] | 6/6 | 100% |

## Coverage roster and failure causes

Cells with no trajectory are crashes. `truncation` = the log ends in the per-call token-cap error (`LengthFinishReasonError`), i.e. the agent was cut off by the shared cap rather than being cheap; `other` = every other cause (schema/parse failures, connection errors).

| Size | Agent | present | missing | truncation | other | no token_usage |
|---|---|---|---|---|---|---|
| -- | -- | full coverage everywhere | 0 | 0 | 0 | 0 |

## Cost multiplier of the proposed harness over each baseline

Ratio of medians (proposed / baseline). A value above 1 means the proposed harness spends more. Baselines whose coverage is low are marked: their denominator is a survivors-only median and therefore flatters them.

### Qwen3.5-0.8B

| Baseline | tokens x | calls x | wall-clock x | baseline cov. |
|---|---|---|---|---|
| Baseline | 60.83 | -- | 37.02 | 83% * |
| ReAct-ISD | 30.42 | -- | 18.14 | 100% |

- tokens: 60.83x the cheapest baseline (Baseline, coverage 83%), 45.62x the median baseline.
  - against the cheapest baseline that actually completed the benchmark (ReAct-ISD, coverage 100%): 30.42x tokens.

### Qwen3.5-4B

| Baseline | tokens x | calls x | wall-clock x | baseline cov. |
|---|---|---|---|---|
| Baseline | 61.17 | -- | 17.95 | 83% * |
| ReAct-ISD | 30.58 | -- | 17.74 | 100% |

- tokens: 61.17x the cheapest baseline (Baseline, coverage 83%), 45.88x the median baseline.
  - against the cheapest baseline that actually completed the benchmark (ReAct-ISD, coverage 100%): 30.58x tokens.

## Serving profile and an ASSUMPTION-DERIVED dollar figure

GPU class, VRAM and hourly price are **not measured here**. Source: docs/benchmark_guides.md section 3--4 (GPU per slot, bf16, 16k context) + RunPod on-demand list price recorded at deploy time, 2026-07. Prices move; treat them as a quote.

Measured per size: total billed pod-hours over the run(s) (run wall-clock x number of endpoints, so it includes the judging phase during which the pods idle) and the number of designs those runs produced across all agents.

| Size | GPU | VRAM | USD/h (assumed) | endpoints | pod-h (meas.) | designs | USD total (assumed) | USD per design, all agents |
|---|---|---|---|---|---|---|---|---|

Per-agent attribution below splits each size's dollar total pro-rata by the agent's share of that size's total tokens. That is an **assumption** (every agent of the run shared the pods; decode time is not exactly proportional to tokens), stated so a reader can reject it and still keep the token and call columns above.

| Size | Agent | token share | USD per design (assumed) |
|---|---|---|---|

## Run provenance

| Run dir | size | elapsed | endpoints | trajectories |
|---|---|---|---|---|
| test_90_benchmark_qwen3.5-0.8b_r1_20260101_000000 | 0.8B | -- | 1 | 17 |
| test_90_benchmark_qwen3.5-4b_r1_20260101_000000 | 4B | -- | 1 | 17 |

