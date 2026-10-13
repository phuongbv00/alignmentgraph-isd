# Ladder statistics summary

Generated: 2026-10-13T10:28:49

- Proposed agent: `alignmentgraph-isd`
- Size order: qwen3.5-0.8b, qwen3.5-4b
- Pooling: mean of 1 runs per scenario; failure = 0 (a run with no scorable output counts 0) for every claim, complete-case (sensitivity) beside it
- Bootstrap: 10000 resamples, seed 42
- Holm family: 2 comparisons (proposed vs each baseline) per model size, within one score or one signal

## qwen3.5-0.8b (macro suffix: QwenZeroEightB)

- alignmentgraph-isd: ADDIE=80.8962 (LEAD signal, sdScen=1.8695), Traj=75.3905 (sdScen=2.4590), Total=79.9136 (sdScen=1.6765), n=6, nCC=6, counted 0=0
  Each sdScen is the SD across scenarios of that signal; they are not interchangeable, and none of them is a run-to-run SD — with one run per cell that quantity does not exist. Run-to-run SD of Total: n/a.

failure = 0:

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| react-isd | 6 | +9.7291 | [+7.2501, +11.1322] | 21.0 | +1.000 | 3.125e-02 | 6.250e-02 |
| baseline | 6 | +30.3416 | [+19.1244, +61.7780] | 21.0 | +1.000 | 3.125e-02 | 6.250e-02 |

complete-case (sensitivity):

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| react-isd | 6 | +9.7291 | [+7.2501, +11.1322] | 21.0 | +1.000 | 3.125e-02 | 6.250e-02 |
| baseline | 5 | +20.0790 | [+16.9991, +21.8890] | 15.0 | +1.000 | 6.250e-02 | 6.250e-02 |

## qwen3.5-4b (macro suffix: QwenFourB)

- alignmentgraph-isd: ADDIE=83.8179 (LEAD signal, sdScen=4.0369), Traj=77.1529 (sdScen=3.7873), Total=81.4284 (sdScen=3.8027), n=6, nCC=6, counted 0=0
  Each sdScen is the SD across scenarios of that signal; they are not interchangeable, and none of them is a run-to-run SD — with one run per cell that quantity does not exist. Run-to-run SD of Total: n/a.

failure = 0:

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| react-isd | 6 | +13.1431 | [+10.0417, +16.2445] | 21.0 | +1.000 | 3.125e-02 | 6.250e-02 |
| baseline | 6 | +31.8245 | [+20.0295, +64.5011] | 21.0 | +1.000 | 3.125e-02 | 6.250e-02 |

complete-case (sensitivity):

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| react-isd | 6 | +13.1431 | [+10.0417, +16.2445] | 21.0 | +1.000 | 3.125e-02 | 6.250e-02 |
| baseline | 5 | +21.2561 | [+17.7693, +25.4206] | 15.0 | +1.000 | 6.250e-02 | 6.250e-02 |

## Interaction (method x model size, DiD largest - smallest)

DiD on addie_median = mean over scenarios of [delta(largest size) - delta(smallest size)], delta = proposed - baseline per scenario (mean of runs, failure = 0); BCa bootstrap CI (10000, seed 42) resamples scenarios; positive DiD means the proposed method's advantage GROWS with model size, negative means it shrinks (i.e. the method helps small models more).

Wilcoxon p values in this section are UNCORRECTED: the DiD tests sit outside every Holm family.

- vs react-isd: n=6, DiD=+3.4140 CI[-0.4002, +8.8725] p=4.375e-01 (uncorrected); trend qwen3.5-0.8b:+9.73 qwen3.5-4b:+13.14; slope/step=+3.4140 CI[-0.4002, +8.8725]
- vs baseline: n=6, DiD=+1.4829 CI[-1.8534, +8.5597] p=1.000e+00 (uncorrected); trend qwen3.5-0.8b:+30.34 qwen3.5-4b:+31.82; slope/step=+1.4829 CI[-1.8534, +8.5597]

## Alignment metrics
Means under failure = 0 (a missing output counts 0).
### qwen3.5-0.8b
- alignmentgraph-isd: activity_assessment_similarity=0.5471 (SD 0.0235, n=6), counts.activities=2.0000 (SD 0.0000, n=6), counts.assessment_items=2.0000 (SD 0.0000, n=6), counts.objectives=2.0000 (SD 0.0000, n=6), details.sanity.bloom_vs_declared_agreement=0.7816 (SD 0.0547, n=6), objective_activity_similarity=0.5442 (SD 0.0250, n=6), objective_assessment_similarity=0.5433 (SD 0.0372, n=6), objective_cognitive_congruence=0.5233 (SD 0.0234, n=6), porter_mean=0.5542 (SD 0.0548, n=6), webb_bloom_consistency=0.5615 (SD 0.0323, n=6)
- baseline: activity_assessment_similarity=0.3676 (SD 0.1829, n=6), counts.activities=1.6667 (SD 0.8165, n=6), counts.assessment_items=1.6667 (SD 0.8165, n=6), counts.objectives=1.6667 (SD 0.8165, n=6), details.sanity.bloom_vs_declared_agreement=0.6690 (SD 0.3297, n=6), objective_activity_similarity=0.3642 (SD 0.1827, n=6), objective_assessment_similarity=0.3625 (SD 0.1829, n=6), objective_cognitive_congruence=0.3482 (SD 0.1743, n=6), porter_mean=0.3514 (SD 0.1760, n=6), webb_bloom_consistency=0.3599 (SD 0.1790, n=6)
- react-isd: activity_assessment_similarity=0.4966 (SD 0.0677, n=6), counts.activities=2.0000 (SD 0.0000, n=6), counts.assessment_items=2.0000 (SD 0.0000, n=6), counts.objectives=2.0000 (SD 0.0000, n=6), details.sanity.bloom_vs_declared_agreement=0.7986 (SD 0.0590, n=6), objective_activity_similarity=0.4517 (SD 0.0378, n=6), objective_assessment_similarity=0.4651 (SD 0.0382, n=6), objective_cognitive_congruence=0.4711 (SD 0.0320, n=6), porter_mean=0.4781 (SD 0.0147, n=6), webb_bloom_consistency=0.4578 (SD 0.0469, n=6)
### qwen3.5-4b
- alignmentgraph-isd: activity_assessment_similarity=0.5945 (SD 0.0309, n=6), counts.activities=2.0000 (SD 0.0000, n=6), counts.assessment_items=2.0000 (SD 0.0000, n=6), counts.objectives=2.0000 (SD 0.0000, n=6), details.sanity.bloom_vs_declared_agreement=0.8563 (SD 0.0387, n=6), objective_activity_similarity=0.5808 (SD 0.0519, n=6), objective_assessment_similarity=0.5912 (SD 0.0303, n=6), objective_cognitive_congruence=0.6036 (SD 0.0498, n=6), porter_mean=0.5923 (SD 0.0197, n=6), webb_bloom_consistency=0.5910 (SD 0.0593, n=6)
- baseline: activity_assessment_similarity=0.4027 (SD 0.2054, n=6), counts.activities=1.6667 (SD 0.8165, n=6), counts.assessment_items=1.6667 (SD 0.8165, n=6), counts.objectives=1.6667 (SD 0.8165, n=6), details.sanity.bloom_vs_declared_agreement=0.6801 (SD 0.3377, n=6), objective_activity_similarity=0.3896 (SD 0.1941, n=6), objective_assessment_similarity=0.4007 (SD 0.1999, n=6), objective_cognitive_congruence=0.3824 (SD 0.1898, n=6), porter_mean=0.3836 (SD 0.1900, n=6), webb_bloom_consistency=0.4122 (SD 0.2033, n=6)
- react-isd: activity_assessment_similarity=0.4947 (SD 0.0418, n=6), counts.activities=2.0000 (SD 0.0000, n=6), counts.assessment_items=2.0000 (SD 0.0000, n=6), counts.objectives=2.0000 (SD 0.0000, n=6), details.sanity.bloom_vs_declared_agreement=0.7929 (SD 0.0632, n=6), objective_activity_similarity=0.5225 (SD 0.0338, n=6), objective_assessment_similarity=0.5166 (SD 0.0451, n=6), objective_cognitive_congruence=0.4788 (SD 0.0359, n=6), porter_mean=0.4986 (SD 0.0208, n=6), webb_bloom_consistency=0.5177 (SD 0.0405, n=6)

## Alignment panel (every signal, descriptive + paired, proposed vs baselines)

No signal is primary: each is reported for every comparison, win or lose. `p_holm` corrects within one signal over the 2 baselines.

### qwen3.5-0.8b
**Missing outputs (count 0 under failure = 0; dropped by the complete-case sensitivity):** `baseline` 1 scenario(s), 1 agent-run cell(s)

#### objective_assessment_similarity [correspondence]
failure = 0 mean [BCa CI95] per agent: alignmentgraph-isd=0.543 [0.520, 0.575] (n=6), baseline=0.363 [0.140, 0.451] (n=6), react-isd=0.465 [0.443, 0.501] (n=6)
conditional (>=1 objective): alignmentgraph-isd=0.543 (n=6), baseline=0.435 (n=5), react-isd=0.465 (n=6)

failure = 0:

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| react-isd | 6 | +0.0782 | [+0.0505, +0.1247] | 21.0 | +1.000 | 3.125e-02 | 6.250e-02 |
| baseline | 6 | +0.1808 | [+0.0824, +0.3992] | 20.0 | +0.905 | 6.250e-02 | 6.250e-02 |

complete-case mean per agent: alignmentgraph-isd=0.543 (n=6), baseline=0.435 (n=5), react-isd=0.465 (n=6)

complete-case (sensitivity):

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| react-isd | 6 | +0.0782 | [+0.0505, +0.1247] | 21.0 | +1.000 | 3.125e-02 | 6.250e-02 |
| baseline | 5 | +0.1075 | [+0.0290, +0.1758] | 14.0 | +0.867 | 1.250e-01 | 1.250e-01 |

#### objective_activity_similarity [correspondence]
failure = 0 mean [BCa CI95] per agent: alignmentgraph-isd=0.544 [0.530, 0.569] (n=6), baseline=0.364 [0.135, 0.448] (n=6), react-isd=0.452 [0.424, 0.478] (n=6)
conditional (>=1 objective): alignmentgraph-isd=0.544 (n=6), baseline=0.437 (n=5), react-isd=0.452 (n=6)

failure = 0:

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| react-isd | 6 | +0.0925 | [+0.0523, +0.1333] | 21.0 | +1.000 | 3.125e-02 | 6.250e-02 |
| baseline | 6 | +0.1800 | [+0.0879, +0.4331] | 21.0 | +1.000 | 3.125e-02 | 6.250e-02 |

complete-case mean per agent: alignmentgraph-isd=0.544 (n=6), baseline=0.437 (n=5), react-isd=0.452 (n=6)

complete-case (sensitivity):

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| react-isd | 6 | +0.0925 | [+0.0523, +0.1333] | 21.0 | +1.000 | 3.125e-02 | 6.250e-02 |
| baseline | 5 | +0.0988 | [+0.0705, +0.1314] | 15.0 | +1.000 | 6.250e-02 | 6.250e-02 |

#### activity_assessment_similarity [correspondence]
failure = 0 mean [BCa CI95] per agent: alignmentgraph-isd=0.547 [0.530, 0.564] (n=6), baseline=0.368 [0.145, 0.452] (n=6), react-isd=0.497 [0.446, 0.544] (n=6)
conditional (>=1 objective): alignmentgraph-isd=0.547 (n=6), baseline=0.441 (n=5), react-isd=0.497 (n=6)

failure = 0:

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| react-isd | 6 | +0.0505 | [-0.0016, +0.0947] | 18.0 | +0.714 | 1.562e-01 | 1.562e-01 |
| baseline | 6 | +0.1796 | [+0.0967, +0.4018] | 21.0 | +1.000 | 3.125e-02 | 6.250e-02 |

complete-case mean per agent: alignmentgraph-isd=0.547 (n=6), baseline=0.441 (n=5), react-isd=0.497 (n=6)

complete-case (sensitivity):

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| react-isd | 6 | +0.0505 | [-0.0016, +0.0947] | 18.0 | +0.714 | 1.562e-01 | 1.562e-01 |
| baseline | 5 | +0.1074 | [+0.0762, +0.1341] | 15.0 | +1.000 | 6.250e-02 | 1.250e-01 |

#### objective_cognitive_congruence [cognitive]
failure = 0 mean [BCa CI95] per agent: alignmentgraph-isd=0.523 [0.501, 0.536] (n=6), baseline=0.348 [0.135, 0.429] (n=6), react-isd=0.471 [0.449, 0.496] (n=6)
conditional (>=1 objective): alignmentgraph-isd=0.523 (n=6), baseline=0.418 (n=5), react-isd=0.471 (n=6)

failure = 0:

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| react-isd | 6 | +0.0521 | [+0.0318, +0.0807] | 21.0 | +1.000 | 3.125e-02 | 6.250e-02 |
| baseline | 6 | +0.1750 | [+0.0903, +0.3956] | 21.0 | +1.000 | 3.125e-02 | 6.250e-02 |

complete-case mean per agent: alignmentgraph-isd=0.523 (n=6), baseline=0.418 (n=5), react-isd=0.471 (n=6)

complete-case (sensitivity):

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| react-isd | 6 | +0.0521 | [+0.0318, +0.0807] | 21.0 | +1.000 | 3.125e-02 | 6.250e-02 |
| baseline | 5 | +0.1045 | [+0.0644, +0.1404] | 15.0 | +1.000 | 6.250e-02 | 6.250e-02 |

#### porter_mean [cognitive]
failure = 0 mean [BCa CI95] per agent: alignmentgraph-isd=0.554 [0.519, 0.596] (n=6), baseline=0.351 [0.135, 0.433] (n=6), react-isd=0.478 [0.471, 0.494] (n=6)
conditional (>=1 objective): alignmentgraph-isd=0.554 (n=6), baseline=0.422 (n=5), react-isd=0.478 (n=6)

failure = 0:

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| react-isd | 6 | +0.0762 | [+0.0429, +0.1118] | 21.0 | +1.000 | 3.125e-02 | 6.250e-02 |
| baseline | 6 | +0.2028 | [+0.1209, +0.3913] | 21.0 | +1.000 | 3.125e-02 | 6.250e-02 |

complete-case mean per agent: alignmentgraph-isd=0.554 (n=6), baseline=0.422 (n=5), react-isd=0.478 (n=6)

complete-case (sensitivity):

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| react-isd | 6 | +0.0762 | [+0.0429, +0.1118] | 21.0 | +1.000 | 3.125e-02 | 6.250e-02 |
| baseline | 5 | +0.1429 | [+0.0988, +0.2047] | 15.0 | +1.000 | 6.250e-02 | 6.250e-02 |

#### webb_bloom_consistency [cognitive]
failure = 0 mean [BCa CI95] per agent: alignmentgraph-isd=0.561 [0.537, 0.584] (n=6), baseline=0.360 [0.135, 0.441] (n=6), react-isd=0.458 [0.428, 0.495] (n=6)
conditional (>=1 objective): alignmentgraph-isd=0.561 (n=6), baseline=0.432 (n=5), react-isd=0.458 (n=6)

failure = 0:

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| react-isd | 6 | +0.1036 | [+0.0383, +0.1404] | 20.0 | +0.905 | 6.250e-02 | 6.250e-02 |
| baseline | 6 | +0.2016 | [+0.1091, +0.4497] | 21.0 | +1.000 | 3.125e-02 | 6.250e-02 |

complete-case mean per agent: alignmentgraph-isd=0.561 (n=6), baseline=0.432 (n=5), react-isd=0.458 (n=6)

complete-case (sensitivity):

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| react-isd | 6 | +0.1036 | [+0.0383, +0.1404] | 20.0 | +0.905 | 6.250e-02 | 1.250e-01 |
| baseline | 5 | +0.1212 | [+0.0732, +0.1472] | 15.0 | +1.000 | 6.250e-02 | 1.250e-01 |

### qwen3.5-4b
**Missing outputs (count 0 under failure = 0; dropped by the complete-case sensitivity):** `baseline` 1 scenario(s), 1 agent-run cell(s)

#### objective_assessment_similarity [correspondence]
failure = 0 mean [BCa CI95] per agent: alignmentgraph-isd=0.591 [0.573, 0.618] (n=6), baseline=0.401 [0.152, 0.493] (n=6), react-isd=0.517 [0.488, 0.554] (n=6)
conditional (>=1 objective): alignmentgraph-isd=0.591 (n=6), baseline=0.481 (n=5), react-isd=0.517 (n=6)

failure = 0:

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| react-isd | 6 | +0.0746 | [+0.0261, +0.1214] | 20.0 | +0.905 | 6.250e-02 | 6.250e-02 |
| baseline | 6 | +0.1905 | [+0.0897, +0.4404] | 21.0 | +1.000 | 3.125e-02 | 6.250e-02 |

complete-case mean per agent: alignmentgraph-isd=0.591 (n=6), baseline=0.481 (n=5), react-isd=0.517 (n=6)

complete-case (sensitivity):

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| react-isd | 6 | +0.0746 | [+0.0261, +0.1214] | 20.0 | +0.905 | 6.250e-02 | 1.250e-01 |
| baseline | 5 | +0.1110 | [+0.0486, +0.1572] | 15.0 | +1.000 | 6.250e-02 | 1.250e-01 |

#### objective_activity_similarity [correspondence]
failure = 0 mean [BCa CI95] per agent: alignmentgraph-isd=0.581 [0.545, 0.621] (n=6), baseline=0.390 [0.152, 0.480] (n=6), react-isd=0.523 [0.500, 0.550] (n=6)
conditional (>=1 objective): alignmentgraph-isd=0.581 (n=6), baseline=0.467 (n=5), react-isd=0.523 (n=6)

failure = 0:

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| react-isd | 6 | +0.0583 | [+0.0056, +0.1016] | 19.0 | +0.810 | 9.375e-02 | 9.375e-02 |
| baseline | 6 | +0.1913 | [+0.1013, +0.3788] | 21.0 | +1.000 | 3.125e-02 | 6.250e-02 |

complete-case mean per agent: alignmentgraph-isd=0.581 (n=6), baseline=0.467 (n=5), react-isd=0.523 (n=6)

complete-case (sensitivity):

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| react-isd | 6 | +0.0583 | [+0.0056, +0.1016] | 19.0 | +0.810 | 9.375e-02 | 1.250e-01 |
| baseline | 5 | +0.1276 | [+0.0647, +0.1809] | 15.0 | +1.000 | 6.250e-02 | 1.250e-01 |

#### activity_assessment_similarity [correspondence]
failure = 0 mean [BCa CI95] per agent: alignmentgraph-isd=0.594 [0.569, 0.615] (n=6), baseline=0.403 [0.152, 0.504] (n=6), react-isd=0.495 [0.466, 0.535] (n=6)
conditional (>=1 objective): alignmentgraph-isd=0.594 (n=6), baseline=0.483 (n=5), react-isd=0.495 (n=6)

failure = 0:

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| react-isd | 6 | +0.0998 | [+0.0699, +0.1397] | 21.0 | +1.000 | 3.125e-02 | 6.250e-02 |
| baseline | 6 | +0.1917 | [+0.0913, +0.4652] | 21.0 | +1.000 | 3.125e-02 | 6.250e-02 |

complete-case mean per agent: alignmentgraph-isd=0.594 (n=6), baseline=0.483 (n=5), react-isd=0.495 (n=6)

complete-case (sensitivity):

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| react-isd | 6 | +0.0998 | [+0.0699, +0.1397] | 21.0 | +1.000 | 3.125e-02 | 6.250e-02 |
| baseline | 5 | +0.1046 | [+0.0613, +0.1428] | 15.0 | +1.000 | 6.250e-02 | 6.250e-02 |

#### objective_cognitive_congruence [cognitive]
failure = 0 mean [BCa CI95] per agent: alignmentgraph-isd=0.604 [0.567, 0.638] (n=6), baseline=0.382 [0.143, 0.469] (n=6), react-isd=0.479 [0.452, 0.504] (n=6)
conditional (>=1 objective): alignmentgraph-isd=0.604 (n=6), baseline=0.459 (n=5), react-isd=0.479 (n=6)

failure = 0:

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| react-isd | 6 | +0.1248 | [+0.0805, +0.1808] | 21.0 | +1.000 | 3.125e-02 | 6.250e-02 |
| baseline | 6 | +0.2212 | [+0.1218, +0.4834] | 21.0 | +1.000 | 3.125e-02 | 6.250e-02 |

complete-case mean per agent: alignmentgraph-isd=0.604 (n=6), baseline=0.459 (n=5), react-isd=0.479 (n=6)

complete-case (sensitivity):

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| react-isd | 6 | +0.1248 | [+0.0805, +0.1808] | 21.0 | +1.000 | 3.125e-02 | 6.250e-02 |
| baseline | 5 | +0.1361 | [+0.0838, +0.1681] | 15.0 | +1.000 | 6.250e-02 | 6.250e-02 |

#### porter_mean [cognitive]
failure = 0 mean [BCa CI95] per agent: alignmentgraph-isd=0.592 [0.578, 0.607] (n=6), baseline=0.384 [0.149, 0.470] (n=6), react-isd=0.499 [0.485, 0.516] (n=6)
conditional (>=1 objective): alignmentgraph-isd=0.592 (n=6), baseline=0.460 (n=5), react-isd=0.499 (n=6)

failure = 0:

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| react-isd | 6 | +0.0937 | [+0.0732, +0.1069] | 21.0 | +1.000 | 3.125e-02 | 6.250e-02 |
| baseline | 6 | +0.2087 | [+0.1278, +0.4246] | 21.0 | +1.000 | 3.125e-02 | 6.250e-02 |

complete-case mean per agent: alignmentgraph-isd=0.592 (n=6), baseline=0.460 (n=5), react-isd=0.499 (n=6)

complete-case (sensitivity):

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| react-isd | 6 | +0.0937 | [+0.0732, +0.1069] | 21.0 | +1.000 | 3.125e-02 | 6.250e-02 |
| baseline | 5 | +0.1380 | [+0.1089, +0.1629] | 15.0 | +1.000 | 6.250e-02 | 6.250e-02 |

#### webb_bloom_consistency [cognitive]
failure = 0 mean [BCa CI95] per agent: alignmentgraph-isd=0.591 [0.547, 0.633] (n=6), baseline=0.412 [0.159, 0.502] (n=6), react-isd=0.518 [0.489, 0.547] (n=6)
conditional (>=1 objective): alignmentgraph-isd=0.591 (n=6), baseline=0.495 (n=5), react-isd=0.518 (n=6)

failure = 0:

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| react-isd | 6 | +0.0733 | [+0.0158, +0.0980] | 20.0 | +0.905 | 6.250e-02 | 6.250e-02 |
| baseline | 6 | +0.1787 | [+0.0921, +0.4007] | 21.0 | +1.000 | 3.125e-02 | 6.250e-02 |

complete-case mean per agent: alignmentgraph-isd=0.591 (n=6), baseline=0.495 (n=5), react-isd=0.518 (n=6)

complete-case (sensitivity):

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| react-isd | 6 | +0.0733 | [+0.0158, +0.0980] | 20.0 | +0.905 | 6.250e-02 | 1.250e-01 |
| baseline | 5 | +0.1073 | [+0.0719, +0.1505] | 15.0 | +1.000 | 6.250e-02 | 1.250e-01 |

### Interaction (objective->assessment similarity DiD, qwen3.5-4b - qwen3.5-0.8b)
DiD on the paired objective_assessment_similarity delta (proposed - baseline): value at the largest size (qwen3.5-4b) minus the smallest (qwen3.5-0.8b), per scenario; negative = the gap narrows as the model grows (i.e. widens toward small models). BCa bootstrap CI (10000, seed 42) + Wilcoxon p on the per-scenario DiD values.
Wilcoxon p values here are UNCORRECTED: the DiD tests sit outside every Holm family.
- vs react-isd: n=6, DiD=-0.0037 CI[-0.0693, +0.0479] p=8.438e-01 (uncorrected)
- vs baseline: n=6, DiD=+0.0097 CI[-0.0621, +0.0611] p=1.000e+00 (uncorrected)

