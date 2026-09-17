# Ladder statistics summary


- Proposed agent: `alignmentgraph-isd`
- Size order: qwen3.5-0.8b, qwen3.5-4b
- Pooling: mean of 1 runs per scenario; primary policy complete-case
- Bootstrap: 10000 resamples, seed 42
- Holm family: 6 comparisons (proposed vs each baseline) per model size

## qwen3.5-0.8b (macro suffix: ZeroEightB)

- alignmentgraph-isd: ADDIE=80.8962 (LEAD signal, sdScen=1.8695), Traj=75.3905 (sdScen=2.4590), Total=79.9136 (sdScen=1.6765), nCC=6, missing=0
  Each sdScen is the SD across scenarios of that signal; they are not interchangeable, and none of them is a run-to-run SD — with one run per cell that quantity does not exist. Run-to-run SD of Total: n/a.

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| react-isd | 5 | +10.6244 | [+9.7436, +11.7298] | 15.0 | +1.000 | 6.250e-02 | 1.250e-01 |
| baseline | 5 | +20.0790 | [+17.4054, +22.1513] | 15.0 | +1.000 | 6.250e-02 | 1.250e-01 |

Sensitivity (mean diff under imputation policies):
- zero: react-isd=+22.28, baseline=+30.34
- min_score: react-isd=+12.83, baseline=+20.90

## qwen3.5-4b (macro suffix: FourB)

- alignmentgraph-isd: ADDIE=83.8179 (LEAD signal, sdScen=4.0369), Traj=77.1529 (sdScen=3.7873), Total=81.4284 (sdScen=3.8027), nCC=6, missing=0
  Each sdScen is the SD across scenarios of that signal; they are not interchangeable, and none of them is a run-to-run SD — with one run per cell that quantity does not exist. Run-to-run SD of Total: n/a.

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| react-isd | 5 | +12.0425 | [+9.2643, +14.8206] | 15.0 | +1.000 | 6.250e-02 | 1.250e-01 |
| baseline | 5 | +21.2561 | [+17.7058, +25.2044] | 15.0 | +1.000 | 6.250e-02 | 1.250e-01 |

Sensitivity (mean diff under imputation policies):
- zero: react-isd=+25.27, baseline=+31.82
- min_score: react-isd=+15.38, baseline=+21.94

## Interaction (method x model size, DiD largest - smallest)

DiD on addie_median = mean over scenarios of [delta(largest size) - delta(smallest size)], delta = proposed - baseline per scenario (mean of runs, complete-case); bootstrap CI (10k, seed 42) resamples scenarios; positive DiD means the proposed method's advantage GROWS with model size, negative means it shrinks (i.e. the method helps small models more).

- vs react-isd: n=5, DiD=+1.4181 CI[-1.9344, +4.7540] p=8.125e-01; trend qwen3.5-0.8b:+10.62 qwen3.5-4b:+12.04; slope/step=+1.4181 CI[-1.9179, +4.7540]
- vs baseline: n=5, DiD=+1.1771 CI[-3.1083, +7.2693] p=8.125e-01; trend qwen3.5-0.8b:+20.08 qwen3.5-4b:+21.26; slope/step=+1.1771 CI[-3.0114, +7.2693]

## Alignment metrics
### qwen3.5-0.8b
- alignmentgraph-isd: activity_assessment_similarity=0.5471 (SD 0.0235, n=6), counts.activities=2.0000 (SD 0.0000, n=6), counts.assessment_items=2.0000 (SD 0.0000, n=6), counts.objectives=2.0000 (SD 0.0000, n=6), details.sanity.bloom_vs_declared_agreement=0.7816 (SD 0.0547, n=6), objective_activity_similarity=0.5442 (SD 0.0250, n=6), objective_assessment_similarity=0.5433 (SD 0.0372, n=6), objective_cognitive_congruence=0.5233 (SD 0.0234, n=6), porter_mean=0.5542 (SD 0.0548, n=6), webb_bloom_consistency=0.5615 (SD 0.0323, n=6)
- baseline: activity_assessment_similarity=0.4411 (SD 0.0361, n=5), counts.activities=2.0000 (SD 0.0000, n=5), counts.assessment_items=2.0000 (SD 0.0000, n=5), counts.objectives=2.0000 (SD 0.0000, n=5), details.sanity.bloom_vs_declared_agreement=0.8028 (SD 0.0403, n=5), objective_activity_similarity=0.4370 (SD 0.0439, n=5), objective_assessment_similarity=0.4350 (SD 0.0489, n=5), objective_cognitive_congruence=0.4179 (SD 0.0400, n=5), porter_mean=0.4217 (SD 0.0406, n=5), webb_bloom_consistency=0.4319 (SD 0.0343, n=5)
- react-isd: activity_assessment_similarity=0.4966 (SD 0.0677, n=6), counts.activities=2.0000 (SD 0.0000, n=6), counts.assessment_items=2.0000 (SD 0.0000, n=6), counts.objectives=2.0000 (SD 0.0000, n=6), details.sanity.bloom_vs_declared_agreement=0.7986 (SD 0.0590, n=6), objective_activity_similarity=0.4517 (SD 0.0378, n=6), objective_assessment_similarity=0.4651 (SD 0.0382, n=6), objective_cognitive_congruence=0.4711 (SD 0.0320, n=6), porter_mean=0.4781 (SD 0.0147, n=6), webb_bloom_consistency=0.4578 (SD 0.0469, n=6)
### qwen3.5-4b
- alignmentgraph-isd: activity_assessment_similarity=0.5945 (SD 0.0309, n=6), counts.activities=2.0000 (SD 0.0000, n=6), counts.assessment_items=2.0000 (SD 0.0000, n=6), counts.objectives=2.0000 (SD 0.0000, n=6), details.sanity.bloom_vs_declared_agreement=0.8563 (SD 0.0387, n=6), objective_activity_similarity=0.5808 (SD 0.0519, n=6), objective_assessment_similarity=0.5912 (SD 0.0303, n=6), objective_cognitive_congruence=0.6036 (SD 0.0498, n=6), porter_mean=0.5923 (SD 0.0197, n=6), webb_bloom_consistency=0.5910 (SD 0.0593, n=6)
- baseline: activity_assessment_similarity=0.4833 (SD 0.0640, n=5), counts.activities=2.0000 (SD 0.0000, n=5), counts.assessment_items=2.0000 (SD 0.0000, n=5), counts.objectives=2.0000 (SD 0.0000, n=5), details.sanity.bloom_vs_declared_agreement=0.8161 (SD 0.0617, n=5), objective_activity_similarity=0.4675 (SD 0.0396, n=5), objective_assessment_similarity=0.4808 (SD 0.0423, n=5), objective_cognitive_congruence=0.4588 (SD 0.0342, n=5), porter_mean=0.4604 (SD 0.0315, n=5), webb_bloom_consistency=0.4947 (SD 0.0258, n=5)
- react-isd: activity_assessment_similarity=0.4947 (SD 0.0418, n=6), counts.activities=2.0000 (SD 0.0000, n=6), counts.assessment_items=2.0000 (SD 0.0000, n=6), counts.objectives=2.0000 (SD 0.0000, n=6), details.sanity.bloom_vs_declared_agreement=0.7929 (SD 0.0632, n=6), objective_activity_similarity=0.5225 (SD 0.0338, n=6), objective_assessment_similarity=0.5166 (SD 0.0451, n=6), objective_cognitive_congruence=0.4788 (SD 0.0359, n=6), porter_mean=0.4986 (SD 0.0208, n=6), webb_bloom_consistency=0.5177 (SD 0.0405, n=6)

## Alignment panel (every score, descriptive + paired, proposed vs baselines)

No score is primary: each is reported for every comparison, win or lose. `p_holm` corrects within one signal (6 comparisons); `p_panel` corrects over the whole panel x baseline family for that size.

### qwen3.5-0.8b
**Missing outputs (complete-case layer is conditioned on these):** `baseline` 1 scenario(s), 1 agent-run cell(s)

#### objective_assessment_similarity [correspondence]
mean [bootstrap CI95] per agent: alignmentgraph-isd=0.543 [0.517, 0.573] (n=6), baseline=0.435 [0.402, 0.478] (n=5), react-isd=0.465 [0.440, 0.495] (n=6)
conditional (>=1 objective): alignmentgraph-isd=0.543 (n=6), baseline=0.435 (n=5), react-isd=0.465 (n=6)

complete-case (over AVAILABLE outputs, not unconditional):

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| react-isd | 6 | +0.0782 | [+0.0450, +0.1181] | 6.250e-02 | 3.750e-01 |
| baseline | 5 | +0.1075 | [+0.0327, +0.1765] | 1.250e-01 | 5.000e-01 |

failure=0 mean per agent: alignmentgraph-isd=0.543 (n=6), baseline=0.363 (n=6), react-isd=0.465 (n=6)

failure=0 (missing output scored 0):

| baseline | n | mean diff | 95% CI | p_holm |
|---|---|---|---|---|
| react-isd | 6 | +0.0782 | [+0.0450, +0.1181] | 6.250e-02 |
| baseline | 6 | +0.1808 | [+0.0633, +0.3331] | 6.250e-02 |

#### objective_activity_similarity [correspondence]
mean [bootstrap CI95] per agent: alignmentgraph-isd=0.544 [0.528, 0.564] (n=6), baseline=0.437 [0.399, 0.469] (n=5), react-isd=0.452 [0.424, 0.479] (n=6)
conditional (>=1 objective): alignmentgraph-isd=0.544 (n=6), baseline=0.437 (n=5), react-isd=0.452 (n=6)

complete-case (over AVAILABLE outputs, not unconditional):

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| react-isd | 6 | +0.0925 | [+0.0523, +0.1327] | 6.250e-02 | 3.750e-01 |
| baseline | 5 | +0.0988 | [+0.0687, +0.1288] | 6.250e-02 | 5.000e-01 |

failure=0 mean per agent: alignmentgraph-isd=0.544 (n=6), baseline=0.364 (n=6), react-isd=0.452 (n=6)

failure=0 (missing output scored 0):

| baseline | n | mean diff | 95% CI | p_holm |
|---|---|---|---|---|
| react-isd | 6 | +0.0925 | [+0.0523, +0.1327] | 6.250e-02 |
| baseline | 6 | +0.1800 | [+0.0783, +0.3462] | 6.250e-02 |

#### activity_assessment_similarity [correspondence]
mean [bootstrap CI95] per agent: alignmentgraph-isd=0.547 [0.531, 0.564] (n=6), baseline=0.441 [0.414, 0.471] (n=5), react-isd=0.497 [0.448, 0.545] (n=6)
conditional (>=1 objective): alignmentgraph-isd=0.547 (n=6), baseline=0.441 (n=5), react-isd=0.497 (n=6)

complete-case (over AVAILABLE outputs, not unconditional):

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| react-isd | 6 | +0.0505 | [+0.0019, +0.0948] | 1.562e-01 | 5.000e-01 |
| baseline | 5 | +0.1074 | [+0.0784, +0.1353] | 1.250e-01 | 5.000e-01 |

failure=0 mean per agent: alignmentgraph-isd=0.547 (n=6), baseline=0.368 (n=6), react-isd=0.497 (n=6)

failure=0 (missing output scored 0):

| baseline | n | mean diff | 95% CI | p_holm |
|---|---|---|---|---|
| react-isd | 6 | +0.0505 | [+0.0019, +0.0948] | 1.562e-01 |
| baseline | 6 | +0.1796 | [+0.0879, +0.3271] | 6.250e-02 |

#### objective_cognitive_congruence [cognitive]
mean [bootstrap CI95] per agent: alignmentgraph-isd=0.523 [0.504, 0.538] (n=6), baseline=0.418 [0.387, 0.449] (n=5), react-isd=0.471 [0.449, 0.495] (n=6)
conditional (>=1 objective): alignmentgraph-isd=0.523 (n=6), baseline=0.418 (n=5), react-isd=0.471 (n=6)

complete-case (over AVAILABLE outputs, not unconditional):

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| react-isd | 6 | +0.0521 | [+0.0300, +0.0771] | 6.250e-02 | 3.750e-01 |
| baseline | 5 | +0.1045 | [+0.0644, +0.1423] | 6.250e-02 | 5.000e-01 |

failure=0 mean per agent: alignmentgraph-isd=0.523 (n=6), baseline=0.348 (n=6), react-isd=0.471 (n=6)

failure=0 (missing output scored 0):

| baseline | n | mean diff | 95% CI | p_holm |
|---|---|---|---|---|
| react-isd | 6 | +0.0521 | [+0.0300, +0.0771] | 6.250e-02 |
| baseline | 6 | +0.1750 | [+0.0778, +0.3250] | 6.250e-02 |

#### porter_mean [cognitive]
mean [bootstrap CI95] per agent: alignmentgraph-isd=0.554 [0.517, 0.594] (n=6), baseline=0.422 [0.395, 0.455] (n=5), react-isd=0.478 [0.469, 0.490] (n=6)
conditional (>=1 objective): alignmentgraph-isd=0.554 (n=6), baseline=0.422 (n=5), react-isd=0.478 (n=6)

complete-case (over AVAILABLE outputs, not unconditional):

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| react-isd | 6 | +0.0762 | [+0.0428, +0.1117] | 6.250e-02 | 3.750e-01 |
| baseline | 5 | +0.1429 | [+0.0956, +0.2021] | 6.250e-02 | 5.000e-01 |

failure=0 mean per agent: alignmentgraph-isd=0.554 (n=6), baseline=0.351 (n=6), react-isd=0.478 (n=6)

failure=0 (missing output scored 0):

| baseline | n | mean diff | 95% CI | p_holm |
|---|---|---|---|---|
| react-isd | 6 | +0.0762 | [+0.0428, +0.1117] | 6.250e-02 |
| baseline | 6 | +0.2028 | [+0.1086, +0.3296] | 6.250e-02 |

#### webb_bloom_consistency [cognitive]
mean [bootstrap CI95] per agent: alignmentgraph-isd=0.561 [0.538, 0.585] (n=6), baseline=0.432 [0.405, 0.459] (n=5), react-isd=0.458 [0.425, 0.494] (n=6)
conditional (>=1 objective): alignmentgraph-isd=0.561 (n=6), baseline=0.432 (n=5), react-isd=0.458 (n=6)

complete-case (over AVAILABLE outputs, not unconditional):

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| react-isd | 6 | +0.1036 | [+0.0488, +0.1470] | 1.250e-01 | 5.000e-01 |
| baseline | 5 | +0.1212 | [+0.0859, +0.1495] | 1.250e-01 | 5.000e-01 |

failure=0 mean per agent: alignmentgraph-isd=0.561 (n=6), baseline=0.360 (n=6), react-isd=0.458 (n=6)

failure=0 (missing output scored 0):

| baseline | n | mean diff | 95% CI | p_holm |
|---|---|---|---|---|
| react-isd | 6 | +0.1036 | [+0.0488, +0.1470] | 6.250e-02 |
| baseline | 6 | +0.2016 | [+0.0971, +0.3704] | 6.250e-02 |

### qwen3.5-4b
**Missing outputs (complete-case layer is conditioned on these):** `baseline` 1 scenario(s), 1 agent-run cell(s)

#### objective_assessment_similarity [correspondence]
mean [bootstrap CI95] per agent: alignmentgraph-isd=0.591 [0.571, 0.614] (n=6), baseline=0.481 [0.453, 0.519] (n=5), react-isd=0.517 [0.485, 0.551] (n=6)
conditional (>=1 objective): alignmentgraph-isd=0.591 (n=6), baseline=0.481 (n=5), react-isd=0.517 (n=6)

complete-case (over AVAILABLE outputs, not unconditional):

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| react-isd | 6 | +0.0746 | [+0.0268, +0.1215] | 1.250e-01 | 5.625e-01 |
| baseline | 5 | +0.1110 | [+0.0580, +0.1620] | 1.250e-01 | 5.625e-01 |

failure=0 mean per agent: alignmentgraph-isd=0.591 (n=6), baseline=0.401 (n=6), react-isd=0.517 (n=6)

failure=0 (missing output scored 0):

| baseline | n | mean diff | 95% CI | p_holm |
|---|---|---|---|---|
| react-isd | 6 | +0.0746 | [+0.0268, +0.1215] | 6.250e-02 |
| baseline | 6 | +0.1905 | [+0.0746, +0.3607] | 6.250e-02 |

#### objective_activity_similarity [correspondence]
mean [bootstrap CI95] per agent: alignmentgraph-isd=0.581 [0.545, 0.620] (n=6), baseline=0.467 [0.442, 0.503] (n=5), react-isd=0.523 [0.499, 0.548] (n=6)
conditional (>=1 objective): alignmentgraph-isd=0.581 (n=6), baseline=0.467 (n=5), react-isd=0.523 (n=6)

complete-case (over AVAILABLE outputs, not unconditional):

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| react-isd | 6 | +0.0583 | [+0.0108, +0.1031] | 1.250e-01 | 5.625e-01 |
| baseline | 5 | +0.1276 | [+0.0678, +0.1813] | 1.250e-01 | 5.625e-01 |

failure=0 mean per agent: alignmentgraph-isd=0.581 (n=6), baseline=0.390 (n=6), react-isd=0.523 (n=6)

failure=0 (missing output scored 0):

| baseline | n | mean diff | 95% CI | p_holm |
|---|---|---|---|---|
| react-isd | 6 | +0.0583 | [+0.0108, +0.1031] | 9.375e-02 |
| baseline | 6 | +0.1913 | [+0.0876, +0.3305] | 6.250e-02 |

#### activity_assessment_similarity [correspondence]
mean [bootstrap CI95] per agent: alignmentgraph-isd=0.594 [0.572, 0.616] (n=6), baseline=0.483 [0.434, 0.533] (n=5), react-isd=0.495 [0.466, 0.523] (n=6)
conditional (>=1 objective): alignmentgraph-isd=0.594 (n=6), baseline=0.483 (n=5), react-isd=0.495 (n=6)

complete-case (over AVAILABLE outputs, not unconditional):

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| react-isd | 6 | +0.0998 | [+0.0678, +0.1357] | 6.250e-02 | 3.750e-01 |
| baseline | 5 | +0.1046 | [+0.0649, +0.1429] | 6.250e-02 | 5.625e-01 |

failure=0 mean per agent: alignmentgraph-isd=0.594 (n=6), baseline=0.403 (n=6), react-isd=0.495 (n=6)

failure=0 (missing output scored 0):

| baseline | n | mean diff | 95% CI | p_holm |
|---|---|---|---|---|
| react-isd | 6 | +0.0998 | [+0.0678, +0.1357] | 6.250e-02 |
| baseline | 6 | +0.1917 | [+0.0782, +0.3759] | 6.250e-02 |

#### objective_cognitive_congruence [cognitive]
mean [bootstrap CI95] per agent: alignmentgraph-isd=0.604 [0.568, 0.638] (n=6), baseline=0.459 [0.432, 0.486] (n=5), react-isd=0.479 [0.453, 0.504] (n=6)
conditional (>=1 objective): alignmentgraph-isd=0.604 (n=6), baseline=0.459 (n=5), react-isd=0.479 (n=6)

complete-case (over AVAILABLE outputs, not unconditional):

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| react-isd | 6 | +0.1248 | [+0.0781, +0.1750] | 6.250e-02 | 3.750e-01 |
| baseline | 5 | +0.1361 | [+0.0932, +0.1712] | 6.250e-02 | 5.625e-01 |

failure=0 mean per agent: alignmentgraph-isd=0.604 (n=6), baseline=0.382 (n=6), react-isd=0.479 (n=6)

failure=0 (missing output scored 0):

| baseline | n | mean diff | 95% CI | p_holm |
|---|---|---|---|---|
| react-isd | 6 | +0.1248 | [+0.0781, +0.1750] | 6.250e-02 |
| baseline | 6 | +0.2212 | [+0.1087, +0.3996] | 6.250e-02 |

#### porter_mean [cognitive]
mean [bootstrap CI95] per agent: alignmentgraph-isd=0.592 [0.579, 0.607] (n=6), baseline=0.460 [0.436, 0.485] (n=5), react-isd=0.499 [0.485, 0.514] (n=6)
conditional (>=1 objective): alignmentgraph-isd=0.592 (n=6), baseline=0.460 (n=5), react-isd=0.499 (n=6)

complete-case (over AVAILABLE outputs, not unconditional):

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| react-isd | 6 | +0.0937 | [+0.0766, +0.1085] | 6.250e-02 | 3.750e-01 |
| baseline | 5 | +0.1380 | [+0.1103, +0.1642] | 6.250e-02 | 5.625e-01 |

failure=0 mean per agent: alignmentgraph-isd=0.592 (n=6), baseline=0.384 (n=6), react-isd=0.499 (n=6)

failure=0 (missing output scored 0):

| baseline | n | mean diff | 95% CI | p_holm |
|---|---|---|---|---|
| react-isd | 6 | +0.0937 | [+0.0766, +0.1085] | 6.250e-02 |
| baseline | 6 | +0.2087 | [+0.1193, +0.3551] | 6.250e-02 |

#### webb_bloom_consistency [cognitive]
mean [bootstrap CI95] per agent: alignmentgraph-isd=0.591 [0.548, 0.633] (n=6), baseline=0.495 [0.476, 0.515] (n=5), react-isd=0.518 [0.489, 0.546] (n=6)
conditional (>=1 objective): alignmentgraph-isd=0.591 (n=6), baseline=0.495 (n=5), react-isd=0.518 (n=6)

complete-case (over AVAILABLE outputs, not unconditional):

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| react-isd | 6 | +0.0733 | [+0.0344, +0.1021] | 1.250e-01 | 5.625e-01 |
| baseline | 5 | +0.1073 | [+0.0696, +0.1482] | 1.250e-01 | 5.625e-01 |

failure=0 mean per agent: alignmentgraph-isd=0.591 (n=6), baseline=0.412 (n=6), react-isd=0.518 (n=6)

failure=0 (missing output scored 0):

| baseline | n | mean diff | 95% CI | p_holm |
|---|---|---|---|---|
| react-isd | 6 | +0.0733 | [+0.0344, +0.1021] | 6.250e-02 |
| baseline | 6 | +0.1787 | [+0.0823, +0.3259] | 6.250e-02 |

### Interaction (objective->assessment similarity DiD, qwen3.5-4b - qwen3.5-0.8b)
DiD on the paired objective_assessment_similarity delta (proposed - baseline): value at the largest size (qwen3.5-4b) minus the smallest (qwen3.5-0.8b), per scenario; negative = the gap narrows as the model grows (i.e. widens toward small models). Bootstrap CI (10000, seed 42) + Wilcoxon p on the per-scenario DiD values.
- vs react-isd: n=6, DiD=-0.0037 CI[-0.0616, +0.0519] p=8.438e-01
- vs baseline: n=5, DiD=+0.0035 CI[-0.0666, +0.0742] p=1.000e+00

