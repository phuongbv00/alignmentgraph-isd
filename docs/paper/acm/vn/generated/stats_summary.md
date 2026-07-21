# Ladder statistics summary

Generated: 2026-07-21T02:19:17  
**TBD-DEMO: every value below is a fake placeholder.**

- Proposed agent: `alignmentgraph-isd`
- Size order: qwen3.5-0.8b, qwen3.5-2b, qwen3.5-4b, qwen3.5-9b
- Pooling: mean of 3 runs per scenario; primary policy complete-case
- Bootstrap: 10000 resamples, seed 42
- Holm family: 6 comparisons (proposed vs each baseline) per model size

## qwen3.5-0.8b (macro suffix: ZeroEightB)

- alignmentgraph-isd: Total=46.0000, runSD=0.4000, nCC=90, missing=0

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| baseline | 90 | +6.0000 | [+5.0000, +7.0000] | 4000.0 | +0.900 | 1.000e-09 | 6.000e-09 |
| eduplanner | 90 | +14.0000 | [+13.0000, +15.0000] | 4000.0 | +0.900 | 1.000e-09 | 6.000e-09 |
| addie-agent | 90 | +5.0000 | [+4.0000, +6.0000] | 4000.0 | +0.900 | 1.000e-09 | 6.000e-09 |
| rpisd-agent | 90 | +7.0000 | [+6.0000, +8.0000] | 4000.0 | +0.900 | 1.000e-09 | 6.000e-09 |
| dick-carey-agent | 90 | +4.0000 | [+3.0000, +5.0000] | 4000.0 | +0.900 | 1.000e-09 | 6.000e-09 |
| react-isd | 90 | +4.5000 | [+3.5000, +5.5000] | 4000.0 | +0.900 | 1.000e-09 | 6.000e-09 |

Sensitivity (mean diff under imputation policies):
- zero: baseline=+6.00, eduplanner=+14.00, addie-agent=+5.00, rpisd-agent=+7.00, dick-carey-agent=+4.00, react-isd=+4.50
- min_score: baseline=+6.00, eduplanner=+14.00, addie-agent=+5.00, rpisd-agent=+7.00, dick-carey-agent=+4.00, react-isd=+4.50

## qwen3.5-2b (macro suffix: TwoB)

- alignmentgraph-isd: Total=61.0000, runSD=0.4000, nCC=90, missing=0

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| baseline | 90 | +6.0000 | [+5.0000, +7.0000] | 4000.0 | +0.900 | 1.000e-09 | 6.000e-09 |
| eduplanner | 90 | +14.0000 | [+13.0000, +15.0000] | 4000.0 | +0.900 | 1.000e-09 | 6.000e-09 |
| addie-agent | 90 | +5.0000 | [+4.0000, +6.0000] | 4000.0 | +0.900 | 1.000e-09 | 6.000e-09 |
| rpisd-agent | 90 | +7.0000 | [+6.0000, +8.0000] | 4000.0 | +0.900 | 1.000e-09 | 6.000e-09 |
| dick-carey-agent | 90 | +4.0000 | [+3.0000, +5.0000] | 4000.0 | +0.900 | 1.000e-09 | 6.000e-09 |
| react-isd | 90 | +4.5000 | [+3.5000, +5.5000] | 4000.0 | +0.900 | 1.000e-09 | 6.000e-09 |

Sensitivity (mean diff under imputation policies):
- zero: baseline=+6.00, eduplanner=+14.00, addie-agent=+5.00, rpisd-agent=+7.00, dick-carey-agent=+4.00, react-isd=+4.50
- min_score: baseline=+6.00, eduplanner=+14.00, addie-agent=+5.00, rpisd-agent=+7.00, dick-carey-agent=+4.00, react-isd=+4.50

## qwen3.5-4b (macro suffix: FourB)

- alignmentgraph-isd: Total=71.0000, runSD=0.4000, nCC=90, missing=0

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| baseline | 90 | +6.0000 | [+5.0000, +7.0000] | 4000.0 | +0.900 | 1.000e-09 | 6.000e-09 |
| eduplanner | 90 | +14.0000 | [+13.0000, +15.0000] | 4000.0 | +0.900 | 1.000e-09 | 6.000e-09 |
| addie-agent | 90 | +5.0000 | [+4.0000, +6.0000] | 4000.0 | +0.900 | 1.000e-09 | 6.000e-09 |
| rpisd-agent | 90 | +7.0000 | [+6.0000, +8.0000] | 4000.0 | +0.900 | 1.000e-09 | 6.000e-09 |
| dick-carey-agent | 90 | +4.0000 | [+3.0000, +5.0000] | 4000.0 | +0.900 | 1.000e-09 | 6.000e-09 |
| react-isd | 90 | +4.5000 | [+3.5000, +5.5000] | 4000.0 | +0.900 | 1.000e-09 | 6.000e-09 |

Sensitivity (mean diff under imputation policies):
- zero: baseline=+6.00, eduplanner=+14.00, addie-agent=+5.00, rpisd-agent=+7.00, dick-carey-agent=+4.00, react-isd=+4.50
- min_score: baseline=+6.00, eduplanner=+14.00, addie-agent=+5.00, rpisd-agent=+7.00, dick-carey-agent=+4.00, react-isd=+4.50

## qwen3.5-9b (macro suffix: NineB)

- alignmentgraph-isd: Total=81.0000, runSD=0.4000, nCC=90, missing=0

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| baseline | 90 | +6.0000 | [+5.0000, +7.0000] | 4000.0 | +0.900 | 1.000e-09 | 6.000e-09 |
| eduplanner | 90 | +14.0000 | [+13.0000, +15.0000] | 4000.0 | +0.900 | 1.000e-09 | 6.000e-09 |
| addie-agent | 90 | +5.0000 | [+4.0000, +6.0000] | 4000.0 | +0.900 | 1.000e-09 | 6.000e-09 |
| rpisd-agent | 90 | +7.0000 | [+6.0000, +8.0000] | 4000.0 | +0.900 | 1.000e-09 | 6.000e-09 |
| dick-carey-agent | 90 | +4.0000 | [+3.0000, +5.0000] | 4000.0 | +0.900 | 1.000e-09 | 6.000e-09 |
| react-isd | 90 | +4.5000 | [+3.5000, +5.5000] | 4000.0 | +0.900 | 1.000e-09 | 6.000e-09 |

Sensitivity (mean diff under imputation policies):
- zero: baseline=+6.00, eduplanner=+14.00, addie-agent=+5.00, rpisd-agent=+7.00, dick-carey-agent=+4.00, react-isd=+4.50
- min_score: baseline=+6.00, eduplanner=+14.00, addie-agent=+5.00, rpisd-agent=+7.00, dick-carey-agent=+4.00, react-isd=+4.50

## Interaction (method x model size, DiD largest - smallest)

TBD-DEMO

- vs baseline: n=90, DiD=-2.0000 CI[-3.0000, -1.0000] p=1.000e-02; trend qwen3.5-0.8b:+8.00 qwen3.5-2b:+7.34 qwen3.5-4b:+6.68 qwen3.5-9b:+6.02; slope/step=-0.6600 CI[-1.0000, -0.3000]
- vs eduplanner: n=90, DiD=-2.0000 CI[-3.0000, -1.0000] p=1.000e-02; trend qwen3.5-0.8b:+16.00 qwen3.5-2b:+15.34 qwen3.5-4b:+14.68 qwen3.5-9b:+14.02; slope/step=-0.6600 CI[-1.0000, -0.3000]
- vs addie-agent: n=90, DiD=-2.0000 CI[-3.0000, -1.0000] p=1.000e-02; trend qwen3.5-0.8b:+7.00 qwen3.5-2b:+6.34 qwen3.5-4b:+5.68 qwen3.5-9b:+5.02; slope/step=-0.6600 CI[-1.0000, -0.3000]
- vs rpisd-agent: n=90, DiD=-2.0000 CI[-3.0000, -1.0000] p=1.000e-02; trend qwen3.5-0.8b:+9.00 qwen3.5-2b:+8.34 qwen3.5-4b:+7.68 qwen3.5-9b:+7.02; slope/step=-0.6600 CI[-1.0000, -0.3000]
- vs dick-carey-agent: n=90, DiD=-2.0000 CI[-3.0000, -1.0000] p=1.000e-02; trend qwen3.5-0.8b:+6.00 qwen3.5-2b:+5.34 qwen3.5-4b:+4.68 qwen3.5-9b:+4.02; slope/step=-0.6600 CI[-1.0000, -0.3000]
- vs react-isd: n=90, DiD=-2.0000 CI[-3.0000, -1.0000] p=1.000e-02; trend qwen3.5-0.8b:+6.50 qwen3.5-2b:+5.84 qwen3.5-4b:+5.18 qwen3.5-9b:+4.52; slope/step=-0.6600 CI[-1.0000, -0.3000]

## Alignment metrics (RQ2)
### qwen3.5-0.8b
- baseline: porter_alignment=0.5000 (SD 0.1000, n=90), webb_consistency=0.6000 (SD 0.1000, n=90), coverage=0.7000 (SD 0.1000, n=90)
- eduplanner: porter_alignment=0.4200 (SD 0.1000, n=90), webb_consistency=0.5200 (SD 0.1000, n=90), coverage=0.6200 (SD 0.1000, n=90)
- addie-agent: porter_alignment=0.5100 (SD 0.1000, n=90), webb_consistency=0.6100 (SD 0.1000, n=90), coverage=0.7100 (SD 0.1000, n=90)
- rpisd-agent: porter_alignment=0.4900 (SD 0.1000, n=90), webb_consistency=0.5900 (SD 0.1000, n=90), coverage=0.6900 (SD 0.1000, n=90)
- dick-carey-agent: porter_alignment=0.5200 (SD 0.1000, n=90), webb_consistency=0.6200 (SD 0.1000, n=90), coverage=0.7200 (SD 0.1000, n=90)
- react-isd: porter_alignment=0.5150 (SD 0.1000, n=90), webb_consistency=0.6150 (SD 0.1000, n=90), coverage=0.7150 (SD 0.1000, n=90)
- alignmentgraph-isd: porter_alignment=0.5600 (SD 0.1000, n=90), webb_consistency=0.6600 (SD 0.1000, n=90), coverage=0.7600 (SD 0.1000, n=90)
### qwen3.5-2b
- baseline: porter_alignment=0.5000 (SD 0.1000, n=90), webb_consistency=0.6000 (SD 0.1000, n=90), coverage=0.7000 (SD 0.1000, n=90)
- eduplanner: porter_alignment=0.4200 (SD 0.1000, n=90), webb_consistency=0.5200 (SD 0.1000, n=90), coverage=0.6200 (SD 0.1000, n=90)
- addie-agent: porter_alignment=0.5100 (SD 0.1000, n=90), webb_consistency=0.6100 (SD 0.1000, n=90), coverage=0.7100 (SD 0.1000, n=90)
- rpisd-agent: porter_alignment=0.4900 (SD 0.1000, n=90), webb_consistency=0.5900 (SD 0.1000, n=90), coverage=0.6900 (SD 0.1000, n=90)
- dick-carey-agent: porter_alignment=0.5200 (SD 0.1000, n=90), webb_consistency=0.6200 (SD 0.1000, n=90), coverage=0.7200 (SD 0.1000, n=90)
- react-isd: porter_alignment=0.5150 (SD 0.1000, n=90), webb_consistency=0.6150 (SD 0.1000, n=90), coverage=0.7150 (SD 0.1000, n=90)
- alignmentgraph-isd: porter_alignment=0.5600 (SD 0.1000, n=90), webb_consistency=0.6600 (SD 0.1000, n=90), coverage=0.7600 (SD 0.1000, n=90)
### qwen3.5-4b
- baseline: porter_alignment=0.5000 (SD 0.1000, n=90), webb_consistency=0.6000 (SD 0.1000, n=90), coverage=0.7000 (SD 0.1000, n=90)
- eduplanner: porter_alignment=0.4200 (SD 0.1000, n=90), webb_consistency=0.5200 (SD 0.1000, n=90), coverage=0.6200 (SD 0.1000, n=90)
- addie-agent: porter_alignment=0.5100 (SD 0.1000, n=90), webb_consistency=0.6100 (SD 0.1000, n=90), coverage=0.7100 (SD 0.1000, n=90)
- rpisd-agent: porter_alignment=0.4900 (SD 0.1000, n=90), webb_consistency=0.5900 (SD 0.1000, n=90), coverage=0.6900 (SD 0.1000, n=90)
- dick-carey-agent: porter_alignment=0.5200 (SD 0.1000, n=90), webb_consistency=0.6200 (SD 0.1000, n=90), coverage=0.7200 (SD 0.1000, n=90)
- react-isd: porter_alignment=0.5150 (SD 0.1000, n=90), webb_consistency=0.6150 (SD 0.1000, n=90), coverage=0.7150 (SD 0.1000, n=90)
- alignmentgraph-isd: porter_alignment=0.5600 (SD 0.1000, n=90), webb_consistency=0.6600 (SD 0.1000, n=90), coverage=0.7600 (SD 0.1000, n=90)
### qwen3.5-9b
- baseline: porter_alignment=0.5000 (SD 0.1000, n=90), webb_consistency=0.6000 (SD 0.1000, n=90), coverage=0.7000 (SD 0.1000, n=90)
- eduplanner: porter_alignment=0.4200 (SD 0.1000, n=90), webb_consistency=0.5200 (SD 0.1000, n=90), coverage=0.6200 (SD 0.1000, n=90)
- addie-agent: porter_alignment=0.5100 (SD 0.1000, n=90), webb_consistency=0.6100 (SD 0.1000, n=90), coverage=0.7100 (SD 0.1000, n=90)
- rpisd-agent: porter_alignment=0.4900 (SD 0.1000, n=90), webb_consistency=0.5900 (SD 0.1000, n=90), coverage=0.6900 (SD 0.1000, n=90)
- dick-carey-agent: porter_alignment=0.5200 (SD 0.1000, n=90), webb_consistency=0.6200 (SD 0.1000, n=90), coverage=0.7200 (SD 0.1000, n=90)
- react-isd: porter_alignment=0.5150 (SD 0.1000, n=90), webb_consistency=0.6150 (SD 0.1000, n=90), coverage=0.7150 (SD 0.1000, n=90)
- alignmentgraph-isd: porter_alignment=0.5600 (SD 0.1000, n=90), webb_consistency=0.6600 (SD 0.1000, n=90), coverage=0.7600 (SD 0.1000, n=90)

