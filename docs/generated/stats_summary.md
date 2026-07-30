# Ladder statistics summary

Generated: 2026-07-30T17:41:41

- Proposed agent: `alignmentgraph-isd`
- Size order: Qwen3.5-0.8B, Qwen3.5-2B, Qwen3.5-4B, Qwen3.5-9B
- Pooling: mean of 3 runs per scenario; primary policy complete-case
- Bootstrap: 10000 resamples, seed 42
- Holm family: 6 comparisons (proposed vs each baseline) per model size

## Qwen3.5-0.8B (macro suffix: ZeroEightB)

- alignmentgraph-isd: Total=81.4766, runSD=0.2575, nCC=90, missing=0

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| baseline | 5 | +34.9227 | [+26.9093, +44.0800] | 15.0 | +1.000 | 6.250e-02 | 1.250e-01 |
| react-isd | 90 | +2.9800 | [+2.2153, +3.7271] | 3576.0 | +0.747 | 7.738e-10 | 3.095e-09 |
| dick-carey-agent | 90 | +0.7162 | [-0.1084, +1.5417] | 2429.5 | +0.187 | 1.243e-01 | 1.250e-01 |
| addie-agent | 90 | +6.9118 | [+5.8028, +8.0670] | 4023.0 | +0.965 | 1.776e-15 | 1.066e-14 |
| rpisd-agent | 88 | +2.6411 | [+2.0195, +3.2511] | 3510.5 | +0.793 | 1.049e-10 | 5.244e-10 |
| eduplanner | 7 | +33.3310 | [+25.2914, +40.2590] | 28.0 | +1.000 | 1.562e-02 | 4.688e-02 |

Sensitivity (mean diff under imputation policies):
- zero: baseline=+61.35, react-isd=+2.98, dick-carey-agent=+0.72, addie-agent=+6.91, rpisd-agent=+3.23, eduplanner=+61.28
- min_score: baseline=+49.64, react-isd=+2.98, dick-carey-agent=+0.72, addie-agent=+6.91, rpisd-agent=+3.09, eduplanner=+50.27

## Qwen3.5-2B (macro suffix: TwoB)

- alignmentgraph-isd: Total=85.9268, runSD=0.0209, nCC=90, missing=0

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| baseline | 47 | +26.8296 | [+24.3645, +29.1793] | 1128.0 | +1.000 | 2.397e-09 | 2.397e-09 |
| react-isd | 90 | +2.5088 | [+2.0207, +2.9856] | 3828.5 | +0.870 | 7.712e-13 | 2.313e-12 |
| dick-carey-agent | 90 | +5.0708 | [+4.5230, +5.6285] | 4091.0 | +0.998 | 2.220e-16 | 1.332e-15 |
| addie-agent | 90 | +7.7153 | [+7.1923, +8.2517] | 4095.0 | +1.000 | 2.220e-16 | 1.332e-15 |
| rpisd-agent | 90 | +5.0041 | [+4.6206, +5.3874] | 4092.0 | +0.999 | 2.220e-16 | 1.332e-15 |
| eduplanner | 57 | +29.4271 | [+27.8119, +31.1363] | 1653.0 | +1.000 | 5.143e-11 | 1.029e-10 |

Sensitivity (mean diff under imputation policies):
- zero: baseline=+39.32, react-isd=+2.51, dick-carey-agent=+5.07, addie-agent=+7.72, rpisd-agent=+5.00, eduplanner=+36.53
- min_score: baseline=+33.51, react-isd=+2.51, dick-carey-agent=+5.07, addie-agent=+7.72, rpisd-agent=+5.00, eduplanner=+33.24

## Qwen3.5-4B (macro suffix: FourB)

- alignmentgraph-isd: Total=87.1126, runSD=0.1574, nCC=90, missing=0

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| baseline | 82 | +7.1454 | [+5.5387, +8.8672] | 3322.5 | +0.953 | 6.684e-14 | 1.337e-13 |
| react-isd | 90 | +0.7996 | [+0.5139, +1.0889] | 3175.5 | +0.551 | 5.659e-06 | 5.659e-06 |
| dick-carey-agent | 89 | +4.0250 | [+3.5938, +4.4598] | 4005.0 | +1.000 | 2.220e-16 | 1.332e-15 |
| addie-agent | 90 | +6.0600 | [+5.7594, +6.3597] | 4095.0 | +1.000 | 2.220e-16 | 1.332e-15 |
| rpisd-agent | 90 | +4.8499 | [+4.5466, +5.1558] | 4095.0 | +1.000 | 2.220e-16 | 1.332e-15 |
| eduplanner | 77 | +8.2485 | [+7.4905, +9.0531] | 3003.0 | +1.000 | 2.465e-14 | 7.394e-14 |

Sensitivity (mean diff under imputation policies):
- zero: baseline=+9.17, react-isd=+0.80, dick-carey-agent=+4.37, addie-agent=+6.06, rpisd-agent=+4.85, eduplanner=+12.52
- min_score: baseline=+8.02, react-isd=+0.80, dick-carey-agent=+4.22, addie-agent=+6.06, rpisd-agent=+4.85, eduplanner=+10.35

## Qwen3.5-9B (macro suffix: NineB)

- alignmentgraph-isd: Total=87.4076, runSD=0.1471, nCC=90, missing=0

| baseline | n | mean diff | 95% CI | W+ | r_rb | p | p_holm |
|---|---|---|---|---|---|---|---|
| baseline | 86 | +2.7224 | [+1.9907, +3.5403] | 3602.0 | +0.926 | 8.926e-14 | 1.785e-13 |
| react-isd | 90 | -0.0781 | [-0.3700, +0.2138] | 1875.0 | -0.084 | 4.876e-01 | 4.876e-01 |
| dick-carey-agent | 90 | +7.3427 | [+6.9470, +7.7500] | 4095.0 | +1.000 | 2.220e-16 | 1.332e-15 |
| addie-agent | 90 | +5.8025 | [+5.5177, +6.0866] | 4095.0 | +1.000 | 2.220e-16 | 1.332e-15 |
| rpisd-agent | 90 | +4.7490 | [+4.4141, +5.0665] | 4095.0 | +1.000 | 2.220e-16 | 1.332e-15 |
| eduplanner | 85 | +5.9755 | [+5.2161, +6.7629] | 3653.0 | +0.999 | 1.332e-15 | 3.997e-15 |

Sensitivity (mean diff under imputation policies):
- zero: baseline=+3.94, react-isd=-0.08, dick-carey-agent=+7.34, addie-agent=+5.80, rpisd-agent=+4.75, eduplanner=+7.43
- min_score: baseline=+3.36, react-isd=-0.08, dick-carey-agent=+7.34, addie-agent=+5.80, rpisd-agent=+4.75, eduplanner=+6.70

## Interaction (method x model size, DiD largest - smallest)

DiD on addie_median = mean over scenarios of [delta(largest size) - delta(smallest size)], delta = proposed - baseline per scenario (mean of runs, complete-case); bootstrap CI (10k, seed 42) resamples scenarios; positive DiD means the proposed method's advantage GROWS with model size, negative means it shrinks (i.e. the method helps small models more).

- vs baseline: n=5, DiD=-32.5567 CI[-42.1553, -23.8193] p=6.250e-02; trend Qwen3.5-0.8B:+36.46 Qwen3.5-2B:+21.34 Qwen3.5-4B:+3.73 Qwen3.5-9B:+1.23; slope/step=-12.3300 CI[-12.3300, -12.3300]
- vs react-isd: n=90, DiD=-3.0581 CI[-3.8178, -2.2625] p=5.557e-10; trend Qwen3.5-0.8B:+2.98 Qwen3.5-2B:+2.51 Qwen3.5-4B:+0.80 Qwen3.5-9B:-0.08; slope/step=-1.0884 CI[-1.3299, -0.8464]
- vs dick-carey-agent: n=90, DiD=+6.6265 CI[+5.7419, +7.5157] p=8.882e-16; trend Qwen3.5-0.8B:+0.72 Qwen3.5-2B:+5.07 Qwen3.5-4B:+4.02 Qwen3.5-9B:+7.36; slope/step=+1.8896 CI[+1.6305, +2.1543]
- vs addie-agent: n=90, DiD=-1.1093 CI[-2.2595, -0.0118] p=2.086e-01; trend Qwen3.5-0.8B:+6.91 Qwen3.5-2B:+7.72 Qwen3.5-4B:+6.06 Qwen3.5-9B:+5.80; slope/step=-0.4983 CI[-0.8671, -0.1530]
- vs rpisd-agent: n=88, DiD=+2.1346 CI[+1.4484, +2.8047] p=2.266e-07; trend Qwen3.5-0.8B:+2.64 Qwen3.5-2B:+5.05 Qwen3.5-4B:+4.85 Qwen3.5-9B:+4.78; slope/step=+0.6208 CI[+0.4084, +0.8279]
- vs eduplanner: n=7, DiD=-28.8471 CI[-35.3824, -21.9905] p=1.562e-02; trend Qwen3.5-0.8B:+42.36 Qwen3.5-2B:+27.75 Qwen3.5-4B:+6.65 Qwen3.5-9B:+5.05; slope/step=-13.3013 CI[-15.2343, -11.3683]

## Alignment metrics (RQ2)
### Qwen3.5-0.8B
- addie-agent: assessment_objective_similarity=0.5238 (SD 0.0473, n=90), counts.activities=14.2037 (SD 0.8206, n=90), counts.assessment=9.4296 (SD 0.9576, n=90), counts.evaluation=13.4296 (SD 0.9576, n=90), counts.objectives=5.0037 (SD 0.1967, n=90), counts.topics=3.1222 (SD 0.3294, n=90), details.sanity.bloom_vs_declared_agreement=0.8326 (SD 0.1087, n=90), details.sanity.n_bloom_classified=5.0037 (SD 0.1967, n=90), details.sanity.n_comparable=4.9815 (SD 0.2082, n=90), details.sanity.n_declared=4.9815 (SD 0.2082, n=90), details.sanity.n_objectives=5.0037 (SD 0.1967, n=90), details.validation.declared_link_agreement=0.6330 (SD 0.1267, n=90), details.validation.declared_links=19.7704 (SD 1.1225, n=90), details.validation.declared_links_checked=19.6444 (SD 1.2042, n=90), objective_activity_similarity=0.4449 (SD 0.0286, n=90), objective_assessment_similarity=0.5951 (SD 0.0590, n=90), objective_cognitive_congruence=0.5649 (SD 0.1475, n=90), objective_evaluation_similarity=0.5959 (SD 0.0580, n=90), porter.activities=0.3530 (SD 0.1138, n=90), porter.assessment=0.3606 (SD 0.1220, n=90), porter.evaluation=0.3511 (SD 0.1009, n=90), porter_mean=0.3549 (SD 0.0833, n=90), webb_bloom_consistency=0.4770 (SD 0.1330, n=90)
- alignmentgraph-isd: assessment_objective_similarity=0.6823 (SD 0.0607, n=90), counts.activities=23.7148 (SD 5.5518, n=90), counts.assessment=21.9815 (SD 6.1200, n=90), counts.evaluation=10.3852 (SD 2.2783, n=90), counts.objectives=5.0889 (SD 0.5844, n=90), counts.topics=3.1222 (SD 0.3294, n=90), details.sanity.bloom_vs_declared_agreement=0.7093 (SD 0.1647, n=90), details.sanity.n_bloom_classified=5.0889 (SD 0.5844, n=90), details.sanity.n_comparable=3.7074 (SD 0.6719, n=90), details.sanity.n_declared=3.7074 (SD 0.6719, n=90), details.sanity.n_objectives=5.0889 (SD 0.5844, n=90), details.validation.declared_link_agreement=0.7822 (SD 0.0997, n=90), details.validation.declared_links=33.7148 (SD 13.3299, n=90), details.validation.declared_links_checked=33.7148 (SD 13.3299, n=90), objective_activity_similarity=0.6973 (SD 0.0452, n=90), objective_assessment_similarity=0.8513 (SD 0.0521, n=90), objective_cognitive_congruence=0.8128 (SD 0.1114, n=90), objective_evaluation_similarity=0.8059 (SD 0.0657, n=90), porter.activities=0.3858 (SD 0.0717, n=90), porter.assessment=0.4553 (SD 0.0859, n=90), porter.evaluation=0.4567 (SD 0.1082, n=90), porter_mean=0.4326 (SD 0.0656, n=90), webb_bloom_consistency=0.6824 (SD 0.0932, n=90)
- baseline: assessment_objective_similarity=0.5284 (SD 0.0768, n=17), counts.activities=2.3095 (SD 4.3404, n=70), counts.assessment=1.3810 (SD 2.5898, n=70), counts.evaluation=22.5952 (SD 1.9460, n=70), counts.objectives=1.7690 (SD 2.2932, n=70), counts.topics=3.1571 (SD 0.3666, n=70), details.sanity.bloom_vs_declared_agreement=0.5619 (SD 0.2703, n=30), details.sanity.n_bloom_classified=5.0111 (SD 0.8598, n=30), details.sanity.n_comparable=4.9444 (SD 0.8973, n=30), details.sanity.n_declared=4.9444 (SD 0.8973, n=30), details.sanity.n_objectives=5.0111 (SD 0.8598, n=30), details.validation.declared_link_agreement=0.6149 (SD 0.2936, n=8), details.validation.declared_links=1.9167 (SD 3.1625, n=30), details.validation.declared_links_checked=1.6333 (SD 3.0876, n=30), objective_activity_similarity=0.1168 (SD 0.2249, n=70), objective_assessment_similarity=0.1042 (SD 0.2014, n=70), objective_cognitive_congruence=0.6284 (SD 0.2861, n=17), objective_evaluation_similarity=0.1498 (SD 0.1975, n=70), porter.activities=0.1736 (SD 0.1767, n=30), porter.assessment=0.1249 (SD 0.1527, n=30), porter.evaluation=0.2439 (SD 0.1204, n=30), porter_mean=0.1808 (SD 0.1100, n=30), webb_bloom_consistency=0.2762 (SD 0.3261, n=30)
- dick-carey-agent: assessment_objective_similarity=0.4676 (SD 0.0511, n=90), counts.activities=6.9556 (SD 0.3006, n=90), counts.assessment=5.0593 (SD 0.4315, n=90), counts.evaluation=8.0593 (SD 0.4315, n=90), counts.objectives=6.3296 (SD 0.6350, n=90), counts.topics=3.1222 (SD 0.3294, n=90), details.sanity.n_bloom_classified=6.3519 (SD 0.5856, n=90), details.sanity.n_comparable=0.0000 (SD 0.0000, n=90), details.sanity.n_declared=0.0000 (SD 0.0000, n=90), details.sanity.n_objectives=6.3519 (SD 0.5856, n=90), details.validation.declared_links=5.1148 (SD 0.5545, n=90), details.validation.declared_links_checked=0.0000 (SD 0.0000, n=90), objective_activity_similarity=0.3931 (SD 0.0334, n=90), objective_assessment_similarity=0.4409 (SD 0.0466, n=90), objective_cognitive_congruence=0.7657 (SD 0.0945, n=90), objective_evaluation_similarity=0.4514 (SD 0.0444, n=90), porter.activities=0.2769 (SD 0.1101, n=90), porter.assessment=0.3201 (SD 0.1147, n=90), porter.evaluation=0.3514 (SD 0.1106, n=90), porter_mean=0.3161 (SD 0.0921, n=90), webb_bloom_consistency=0.8462 (SD 0.1240, n=90)
- eduplanner: assessment_objective_similarity=0.4771 (SD 0.0960, n=59), counts.activities=9.6416 (SD 6.0824, n=73), counts.assessment=8.0137 (SD 3.8937, n=73), counts.evaluation=9.1256 (SD 4.3365, n=73), counts.objectives=3.5890 (SD 2.6316, n=73), counts.topics=3.1233 (SD 0.3310, n=73), details.sanity.bloom_vs_declared_agreement=0.6413 (SD 0.1955, n=59), details.sanity.n_bloom_classified=5.1780 (SD 1.7290, n=59), details.sanity.n_comparable=4.9831 (SD 1.6942, n=59), details.sanity.n_declared=4.9831 (SD 1.6942, n=59), details.sanity.n_objectives=5.1780 (SD 1.7290, n=59), details.validation.declared_links=0.0000 (SD 0.0000, n=59), details.validation.declared_links_checked=0.0000 (SD 0.0000, n=59), objective_activity_similarity=0.3943 (SD 0.2408, n=73), objective_assessment_similarity=0.3602 (SD 0.2298, n=73), objective_cognitive_congruence=0.6302 (SD 0.2499, n=59), objective_evaluation_similarity=0.3157 (SD 0.2329, n=73), porter.activities=0.2890 (SD 0.1384, n=59), porter.assessment=0.3097 (SD 0.1618, n=59), porter.evaluation=0.2525 (SD 0.1779, n=59), porter_mean=0.2837 (SD 0.1211, n=59), webb_bloom_consistency=0.5955 (SD 0.2366, n=59)
- react-isd: assessment_objective_similarity=0.3619 (SD 0.0619, n=90), counts.activities=12.9741 (SD 1.6240, n=90), counts.assessment=14.3889 (SD 1.9062, n=90), counts.evaluation=7.1185 (SD 1.1019, n=90), counts.objectives=3.4556 (SD 0.4933, n=90), counts.topics=3.1222 (SD 0.3294, n=90), details.sanity.bloom_vs_declared_agreement=0.2875 (SD 0.1986, n=90), details.sanity.n_bloom_classified=3.4556 (SD 0.4933, n=90), details.sanity.n_comparable=3.4519 (SD 0.4929, n=90), details.sanity.n_declared=3.4519 (SD 0.4929, n=90), details.sanity.n_objectives=3.4556 (SD 0.4933, n=90), details.validation.declared_link_agreement=0.3466 (SD 0.1141, n=90), details.validation.declared_links=11.2926 (SD 2.8843, n=90), details.validation.declared_links_checked=6.9741 (SD 2.8719, n=90), objective_activity_similarity=0.4034 (SD 0.0641, n=90), objective_assessment_similarity=0.5038 (SD 0.1091, n=90), objective_cognitive_congruence=0.5697 (SD 0.2269, n=90), objective_evaluation_similarity=0.4651 (SD 0.1126, n=90), porter.activities=0.3366 (SD 0.1887, n=90), porter.assessment=0.1453 (SD 0.1165, n=90), porter.evaluation=0.1865 (SD 0.1251, n=90), porter_mean=0.2228 (SD 0.0861, n=90), webb_bloom_consistency=0.3860 (SD 0.2146, n=90)
- rpisd-agent: assessment_objective_similarity=0.4982 (SD 0.0596, n=90), counts.activities=13.9852 (SD 0.0691, n=90), counts.assessment=6.2444 (SD 1.7081, n=90), counts.evaluation=11.2444 (SD 1.7081, n=90), counts.objectives=4.8389 (SD 0.5936, n=90), counts.topics=3.1222 (SD 0.3294, n=90), details.sanity.bloom_vs_declared_agreement=0.5944 (SD 0.1870, n=90), details.sanity.n_bloom_classified=4.8389 (SD 0.5936, n=90), details.sanity.n_comparable=4.7648 (SD 0.6042, n=90), details.sanity.n_declared=4.7648 (SD 0.6042, n=90), details.sanity.n_objectives=4.8389 (SD 0.5936, n=90), details.validation.declared_links=1.4815 (SD 3.2809, n=90), details.validation.declared_links_checked=0.0000 (SD 0.0000, n=90), objective_activity_similarity=0.4356 (SD 0.0465, n=90), objective_assessment_similarity=0.5103 (SD 0.0653, n=90), objective_cognitive_congruence=0.5520 (SD 0.1883, n=90), objective_evaluation_similarity=0.5265 (SD 0.0561, n=90), porter.activities=0.2814 (SD 0.0986, n=90), porter.assessment=0.2731 (SD 0.1264, n=90), porter.evaluation=0.2541 (SD 0.1029, n=90), porter_mean=0.2696 (SD 0.0785, n=90), webb_bloom_consistency=0.5757 (SD 0.1862, n=90)
### Qwen3.5-2B
- addie-agent: assessment_objective_similarity=0.5309 (SD 0.0638, n=90), counts.activities=14.0259 (SD 0.1598, n=90), counts.assessment=9.0481 (SD 1.6705, n=90), counts.evaluation=13.0481 (SD 1.6705, n=90), counts.objectives=4.9926 (SD 0.3568, n=90), counts.topics=3.1222 (SD 0.3294, n=90), details.sanity.bloom_vs_declared_agreement=0.8453 (SD 0.1123, n=90), details.sanity.n_bloom_classified=4.9926 (SD 0.3568, n=90), details.sanity.n_comparable=4.9852 (SD 0.3600, n=90), details.sanity.n_declared=4.9852 (SD 0.3600, n=90), details.sanity.n_objectives=4.9926 (SD 0.3568, n=90), details.validation.declared_link_agreement=0.6190 (SD 0.1503, n=90), details.validation.declared_links=19.6444 (SD 1.6759, n=90), details.validation.declared_links_checked=19.6370 (SD 1.6757, n=90), objective_activity_similarity=0.4539 (SD 0.0485, n=90), objective_assessment_similarity=0.6057 (SD 0.0835, n=90), objective_cognitive_congruence=0.6237 (SD 0.1697, n=90), objective_evaluation_similarity=0.6078 (SD 0.0794, n=90), porter.activities=0.2914 (SD 0.0852, n=90), porter.assessment=0.4116 (SD 0.1254, n=90), porter.evaluation=0.3732 (SD 0.1068, n=90), porter_mean=0.3587 (SD 0.0808, n=90), webb_bloom_consistency=0.5727 (SD 0.1611, n=90)
- alignmentgraph-isd: assessment_objective_similarity=0.6520 (SD 0.0589, n=90), counts.activities=16.5852 (SD 2.6831, n=90), counts.assessment=19.5037 (SD 3.2450, n=90), counts.evaluation=9.4259 (SD 1.9172, n=90), counts.objectives=5.0556 (SD 0.2967, n=90), counts.topics=3.1222 (SD 0.3294, n=90), details.sanity.bloom_vs_declared_agreement=0.8805 (SD 0.1043, n=90), details.sanity.n_bloom_classified=5.0556 (SD 0.2967, n=90), details.sanity.n_comparable=4.3111 (SD 0.5188, n=90), details.sanity.n_declared=4.3111 (SD 0.5188, n=90), details.sanity.n_objectives=5.0556 (SD 0.2967, n=90), details.validation.declared_link_agreement=0.7521 (SD 0.0981, n=90), details.validation.declared_links=20.6407 (SD 5.6417, n=90), details.validation.declared_links_checked=20.6407 (SD 5.6417, n=90), objective_activity_similarity=0.6796 (SD 0.0403, n=90), objective_assessment_similarity=0.8504 (SD 0.0607, n=90), objective_cognitive_congruence=0.8654 (SD 0.0970, n=90), objective_evaluation_similarity=0.8058 (SD 0.0935, n=90), porter.activities=0.3789 (SD 0.0717, n=90), porter.assessment=0.4851 (SD 0.0900, n=90), porter.evaluation=0.4786 (SD 0.1073, n=90), porter_mean=0.4475 (SD 0.0689, n=90), webb_bloom_consistency=0.7243 (SD 0.0972, n=90)
- baseline: assessment_objective_similarity=0.4676 (SD 0.0563, n=82), counts.activities=9.8485 (SD 4.7919, n=88), counts.assessment=5.8258 (SD 3.2321, n=88), counts.evaluation=23.3788 (SD 2.1282, n=88), counts.objectives=4.3409 (SD 2.4970, n=88), counts.topics=3.1250 (SD 0.3326, n=88), details.sanity.bloom_vs_declared_agreement=0.7610 (SD 0.1748, n=85), details.sanity.n_bloom_classified=5.3510 (SD 2.1392, n=85), details.sanity.n_comparable=4.8431 (SD 0.9520, n=85), details.sanity.n_declared=4.8431 (SD 0.9520, n=85), details.sanity.n_objectives=5.3510 (SD 2.1392, n=85), details.validation.declared_link_agreement=0.5627 (SD 0.1820, n=38), details.validation.declared_links=2.3667 (SD 3.2819, n=85), details.validation.declared_links_checked=2.2529 (SD 3.1752, n=85), objective_activity_similarity=0.4203 (SD 0.1870, n=88), objective_assessment_similarity=0.3834 (SD 0.1720, n=88), objective_cognitive_congruence=0.7217 (SD 0.2034, n=82), objective_evaluation_similarity=0.3281 (SD 0.1346, n=88), porter.activities=0.3042 (SD 0.1086, n=85), porter.assessment=0.2682 (SD 0.1316, n=85), porter.evaluation=0.2523 (SD 0.1142, n=85), porter_mean=0.2749 (SD 0.0719, n=85), webb_bloom_consistency=0.6012 (SD 0.2201, n=85)
- dick-carey-agent: assessment_objective_similarity=0.5411 (SD 0.0604, n=90), counts.activities=6.9815 (SD 0.1157, n=90), counts.assessment=4.9148 (SD 0.3553, n=90), counts.evaluation=7.9148 (SD 0.3553, n=90), counts.objectives=6.0667 (SD 0.4719, n=90), counts.topics=3.1222 (SD 0.3294, n=90), details.sanity.n_bloom_classified=6.0889 (SD 0.4175, n=90), details.sanity.n_comparable=0.0000 (SD 0.0000, n=90), details.sanity.n_declared=0.0000 (SD 0.0000, n=90), details.sanity.n_objectives=6.0889 (SD 0.4175, n=90), details.validation.declared_links=4.9185 (SD 0.3509, n=90), details.validation.declared_links_checked=0.0000 (SD 0.0000, n=90), objective_activity_similarity=0.4734 (SD 0.0401, n=90), objective_assessment_similarity=0.4988 (SD 0.0545, n=90), objective_cognitive_congruence=0.7558 (SD 0.1250, n=90), objective_evaluation_similarity=0.5053 (SD 0.0520, n=90), porter.activities=0.3435 (SD 0.1070, n=90), porter.assessment=0.3659 (SD 0.1149, n=90), porter.evaluation=0.3511 (SD 0.0811, n=90), porter_mean=0.3535 (SD 0.0730, n=90), webb_bloom_consistency=0.7608 (SD 0.1187, n=90)
- eduplanner: assessment_objective_similarity=0.5223 (SD 0.0727, n=89), counts.activities=11.8370 (SD 3.2121, n=90), counts.assessment=9.5593 (SD 1.6511, n=90), counts.evaluation=11.7074 (SD 2.1438, n=90), counts.objectives=4.1889 (SD 1.1450, n=90), counts.topics=3.1222 (SD 0.3294, n=90), details.sanity.bloom_vs_declared_agreement=0.8532 (SD 0.1173, n=89), details.sanity.n_bloom_classified=4.9888 (SD 0.1173, n=89), details.sanity.n_comparable=4.9551 (SD 0.2272, n=89), details.sanity.n_declared=4.9551 (SD 0.2272, n=89), details.sanity.n_objectives=4.9888 (SD 0.1173, n=89), details.validation.declared_links=0.0000 (SD 0.0000, n=89), details.validation.declared_links_checked=0.0000 (SD 0.0000, n=89), objective_activity_similarity=0.4317 (SD 0.1235, n=90), objective_assessment_similarity=0.4997 (SD 0.1561, n=90), objective_cognitive_congruence=0.6848 (SD 0.1650, n=89), objective_evaluation_similarity=0.4776 (SD 0.1668, n=90), porter.activities=0.2720 (SD 0.0878, n=89), porter.assessment=0.4029 (SD 0.1523, n=89), porter.evaluation=0.3576 (SD 0.1407, n=89), porter_mean=0.3442 (SD 0.1019, n=89), webb_bloom_consistency=0.6590 (SD 0.1303, n=89)
- react-isd: assessment_objective_similarity=0.4278 (SD 0.0593, n=90), counts.activities=12.7778 (SD 1.9812, n=90), counts.assessment=14.7074 (SD 0.8623, n=90), counts.evaluation=7.8000 (SD 0.5515, n=90), counts.objectives=4.3111 (SD 0.5354, n=90), counts.topics=3.1222 (SD 0.3294, n=90), details.sanity.bloom_vs_declared_agreement=0.5726 (SD 0.2105, n=90), details.sanity.n_bloom_classified=4.3111 (SD 0.5354, n=90), details.sanity.n_comparable=4.3111 (SD 0.5354, n=90), details.sanity.n_declared=4.3111 (SD 0.5354, n=90), details.sanity.n_objectives=4.3111 (SD 0.5354, n=90), details.validation.declared_link_agreement=0.3045 (SD 0.1280, n=90), details.validation.declared_links=9.8296 (SD 0.7228, n=90), details.validation.declared_links_checked=7.9111 (SD 1.8160, n=90), objective_activity_similarity=0.4904 (SD 0.0727, n=90), objective_assessment_similarity=0.5831 (SD 0.0953, n=90), objective_cognitive_congruence=0.6617 (SD 0.1652, n=90), objective_evaluation_similarity=0.5546 (SD 0.0997, n=90), porter.activities=0.3097 (SD 0.1124, n=90), porter.assessment=0.2418 (SD 0.0953, n=90), porter.evaluation=0.2539 (SD 0.1003, n=90), porter_mean=0.2685 (SD 0.0584, n=90), webb_bloom_consistency=0.4957 (SD 0.1763, n=90)
- rpisd-agent: assessment_objective_similarity=0.4499 (SD 0.0411, n=90), counts.activities=14.0000 (SD 0.0000, n=90), counts.assessment=10.8370 (SD 0.5896, n=90), counts.evaluation=15.8370 (SD 0.5896, n=90), counts.objectives=4.8815 (SD 0.3750, n=90), counts.topics=3.1222 (SD 0.3294, n=90), details.sanity.bloom_vs_declared_agreement=0.7528 (SD 0.1542, n=90), details.sanity.n_bloom_classified=4.8815 (SD 0.3750, n=90), details.sanity.n_comparable=4.6333 (SD 0.4820, n=90), details.sanity.n_declared=4.6333 (SD 0.4820, n=90), details.sanity.n_objectives=4.8815 (SD 0.3750, n=90), details.validation.declared_links=0.0000 (SD 0.0000, n=90), details.validation.declared_links_checked=0.0000 (SD 0.0000, n=90), objective_activity_similarity=0.5416 (SD 0.0590, n=90), objective_assessment_similarity=0.5191 (SD 0.0506, n=90), objective_cognitive_congruence=0.5591 (SD 0.1721, n=90), objective_evaluation_similarity=0.5234 (SD 0.0494, n=90), porter.activities=0.2959 (SD 0.0912, n=90), porter.assessment=0.3292 (SD 0.1155, n=90), porter.evaluation=0.3395 (SD 0.1163, n=90), porter_mean=0.3215 (SD 0.0857, n=90), webb_bloom_consistency=0.5388 (SD 0.1452, n=90)
### Qwen3.5-4B
- addie-agent: assessment_objective_similarity=0.5576 (SD 0.0557, n=90), counts.activities=14.0074 (SD 0.0494, n=90), counts.assessment=9.6926 (SD 0.8107, n=90), counts.evaluation=13.6926 (SD 0.8107, n=90), counts.objectives=5.1889 (SD 0.3082, n=90), counts.topics=3.1222 (SD 0.3294, n=90), details.sanity.bloom_vs_declared_agreement=0.7460 (SD 0.1088, n=90), details.sanity.n_bloom_classified=5.1889 (SD 0.3082, n=90), details.sanity.n_comparable=5.1889 (SD 0.3082, n=90), details.sanity.n_declared=5.1889 (SD 0.3082, n=90), details.sanity.n_objectives=5.1889 (SD 0.3082, n=90), details.validation.declared_link_agreement=0.8028 (SD 0.1266, n=90), details.validation.declared_links=19.9852 (SD 0.2443, n=90), details.validation.declared_links_checked=19.9852 (SD 0.2443, n=90), objective_activity_similarity=0.5365 (SD 0.0386, n=90), objective_assessment_similarity=0.6081 (SD 0.0586, n=90), objective_cognitive_congruence=0.6737 (SD 0.1693, n=90), objective_evaluation_similarity=0.6081 (SD 0.0586, n=90), porter.activities=0.3057 (SD 0.0812, n=90), porter.assessment=0.4653 (SD 0.1222, n=90), porter.evaluation=0.4076 (SD 0.1030, n=90), porter_mean=0.3929 (SD 0.0831, n=90), webb_bloom_consistency=0.6684 (SD 0.1302, n=90)
- alignmentgraph-isd: assessment_objective_similarity=0.6628 (SD 0.0662, n=90), counts.activities=15.9222 (SD 7.2116, n=90), counts.assessment=15.1444 (SD 0.4092, n=90), counts.evaluation=8.4889 (SD 0.3505, n=90), counts.objectives=5.0037 (SD 0.0351, n=90), counts.topics=3.1222 (SD 0.3294, n=90), details.sanity.bloom_vs_declared_agreement=0.9030 (SD 0.0938, n=90), details.sanity.n_bloom_classified=5.0037 (SD 0.0351, n=90), details.sanity.n_comparable=4.9704 (SD 0.1552, n=90), details.sanity.n_declared=4.9704 (SD 0.1552, n=90), details.sanity.n_objectives=5.0037 (SD 0.0351, n=90), details.validation.declared_link_agreement=0.8561 (SD 0.0573, n=90), details.validation.declared_links=15.1481 (SD 0.4063, n=90), details.validation.declared_links_checked=15.1481 (SD 0.4063, n=90), objective_activity_similarity=0.6865 (SD 0.0312, n=90), objective_assessment_similarity=0.8058 (SD 0.0702, n=90), objective_cognitive_congruence=0.9180 (SD 0.0829, n=90), objective_evaluation_similarity=0.7889 (SD 0.0766, n=90), porter.activities=0.3516 (SD 0.0585, n=90), porter.assessment=0.5261 (SD 0.0725, n=90), porter.evaluation=0.4607 (SD 0.0852, n=90), porter_mean=0.4462 (SD 0.0543, n=90), webb_bloom_consistency=0.8707 (SD 0.0604, n=90)
- baseline: assessment_objective_similarity=0.4830 (SD 0.0422, n=90), counts.activities=8.9352 (SD 1.3519, n=90), counts.assessment=12.5685 (SD 2.3117, n=90), counts.evaluation=27.9111 (SD 1.6624, n=90), counts.objectives=4.8074 (SD 0.6119, n=90), counts.topics=3.1222 (SD 0.3294, n=90), details.sanity.bloom_vs_declared_agreement=0.7497 (SD 0.1283, n=90), details.sanity.n_bloom_classified=5.0111 (SD 0.0782, n=90), details.sanity.n_comparable=5.0111 (SD 0.0782, n=90), details.sanity.n_declared=5.0111 (SD 0.0782, n=90), details.sanity.n_objectives=5.0111 (SD 0.0782, n=90), details.validation.declared_link_agreement=0.5778 (SD 0.1475, n=90), details.validation.declared_links=8.8444 (SD 1.9354, n=90), details.validation.declared_links_checked=8.8333 (SD 1.9316, n=90), objective_activity_similarity=0.4859 (SD 0.0757, n=90), objective_assessment_similarity=0.5472 (SD 0.0898, n=90), objective_cognitive_congruence=0.7293 (SD 0.1456, n=90), objective_evaluation_similarity=0.4967 (SD 0.0876, n=90), porter.activities=0.3072 (SD 0.0947, n=90), porter.assessment=0.3414 (SD 0.0844, n=90), porter.evaluation=0.2777 (SD 0.0864, n=90), porter_mean=0.3088 (SD 0.0525, n=90), webb_bloom_consistency=0.5905 (SD 0.1085, n=90)
- dick-carey-agent: assessment_objective_similarity=0.5645 (SD 0.0531, n=90), counts.activities=6.7111 (SD 0.3246, n=90), counts.assessment=4.9889 (SD 0.1453, n=90), counts.evaluation=7.9889 (SD 0.1453, n=90), counts.objectives=6.0370 (SD 0.1363, n=90), counts.topics=3.1222 (SD 0.3294, n=90), details.sanity.n_bloom_classified=6.0370 (SD 0.1363, n=90), details.sanity.n_comparable=0.0000 (SD 0.0000, n=90), details.sanity.n_declared=0.0000 (SD 0.0000, n=90), details.sanity.n_objectives=6.0370 (SD 0.1363, n=90), details.validation.declared_links=4.9889 (SD 0.1453, n=90), details.validation.declared_links_checked=0.0000 (SD 0.0000, n=90), objective_activity_similarity=0.5447 (SD 0.0411, n=90), objective_assessment_similarity=0.5363 (SD 0.0493, n=90), objective_cognitive_congruence=0.7913 (SD 0.1004, n=90), objective_evaluation_similarity=0.5366 (SD 0.0493, n=90), porter.activities=0.4272 (SD 0.1054, n=90), porter.assessment=0.3556 (SD 0.1047, n=90), porter.evaluation=0.3074 (SD 0.0826, n=90), porter_mean=0.3634 (SD 0.0714, n=90), webb_bloom_consistency=0.7611 (SD 0.1298, n=90)
- eduplanner: assessment_objective_similarity=0.4946 (SD 0.0510, n=89), counts.activities=13.5318 (SD 1.6149, n=89), counts.assessment=13.4494 (SD 1.8618, n=89), counts.evaluation=12.9176 (SD 0.7559, n=89), counts.objectives=4.8221 (SD 0.5955, n=89), counts.topics=3.1236 (SD 0.3310, n=89), details.sanity.bloom_vs_declared_agreement=0.8629 (SD 0.0856, n=89), details.sanity.n_bloom_classified=5.0000 (SD 0.0000, n=89), details.sanity.n_comparable=5.0000 (SD 0.0000, n=89), details.sanity.n_declared=5.0000 (SD 0.0000, n=89), details.sanity.n_objectives=5.0000 (SD 0.0000, n=89), details.validation.declared_links=0.0000 (SD 0.0000, n=89), details.validation.declared_links_checked=0.0000 (SD 0.0000, n=89), objective_activity_similarity=0.4738 (SD 0.0750, n=89), objective_assessment_similarity=0.5976 (SD 0.0901, n=89), objective_cognitive_congruence=0.7251 (SD 0.1306, n=89), objective_evaluation_similarity=0.5946 (SD 0.0940, n=89), porter.activities=0.2544 (SD 0.0876, n=89), porter.assessment=0.4282 (SD 0.0963, n=89), porter.evaluation=0.4227 (SD 0.0906, n=89), porter_mean=0.3684 (SD 0.0672, n=89), webb_bloom_consistency=0.7024 (SD 0.1004, n=89)
- react-isd: assessment_objective_similarity=0.4613 (SD 0.0568, n=90), counts.activities=13.0185 (SD 6.0407, n=90), counts.assessment=15.0000 (SD 0.0500, n=90), counts.evaluation=8.0000 (SD 0.0000, n=90), counts.objectives=4.7333 (SD 0.3972, n=90), counts.topics=3.1222 (SD 0.3294, n=90), details.sanity.bloom_vs_declared_agreement=0.6797 (SD 0.1693, n=90), details.sanity.n_bloom_classified=4.7333 (SD 0.3972, n=90), details.sanity.n_comparable=4.7333 (SD 0.3972, n=90), details.sanity.n_declared=4.7333 (SD 0.3972, n=90), details.sanity.n_objectives=4.7333 (SD 0.3972, n=90), details.validation.declared_link_agreement=0.3286 (SD 0.1650, n=90), details.validation.declared_links=9.9630 (SD 0.3549, n=90), details.validation.declared_links_checked=9.6630 (SD 1.0816, n=90), objective_activity_similarity=0.5341 (SD 0.0602, n=90), objective_assessment_similarity=0.5792 (SD 0.0562, n=90), objective_cognitive_congruence=0.7673 (SD 0.1424, n=90), objective_evaluation_similarity=0.5622 (SD 0.0582, n=90), porter.activities=0.3145 (SD 0.1005, n=90), porter.assessment=0.3216 (SD 0.0952, n=90), porter.evaluation=0.2600 (SD 0.0854, n=90), porter_mean=0.2987 (SD 0.0662, n=90), webb_bloom_consistency=0.6237 (SD 0.1167, n=90)
- rpisd-agent: assessment_objective_similarity=0.4106 (SD 0.0404, n=90), counts.activities=14.0000 (SD 0.0000, n=90), counts.assessment=9.9519 (SD 0.2526, n=90), counts.evaluation=14.9519 (SD 0.2526, n=90), counts.objectives=5.0519 (SD 0.1215, n=90), counts.topics=3.1222 (SD 0.3294, n=90), details.sanity.bloom_vs_declared_agreement=0.6842 (SD 0.1347, n=90), details.sanity.n_bloom_classified=5.0519 (SD 0.1215, n=90), details.sanity.n_comparable=4.9222 (SD 0.2829, n=90), details.sanity.n_declared=4.9222 (SD 0.2829, n=90), details.sanity.n_objectives=5.0519 (SD 0.1215, n=90), details.validation.declared_links=0.0000 (SD 0.0000, n=90), details.validation.declared_links_checked=0.0000 (SD 0.0000, n=90), objective_activity_similarity=0.5382 (SD 0.0342, n=90), objective_assessment_similarity=0.4656 (SD 0.0424, n=90), objective_cognitive_congruence=0.5284 (SD 0.1662, n=90), objective_evaluation_similarity=0.4722 (SD 0.0403, n=90), porter.activities=0.2902 (SD 0.1001, n=90), porter.assessment=0.2842 (SD 0.0963, n=90), porter.evaluation=0.2982 (SD 0.0878, n=90), porter_mean=0.2909 (SD 0.0703, n=90), webb_bloom_consistency=0.5013 (SD 0.1570, n=90)
### Qwen3.5-9B
- addie-agent: assessment_objective_similarity=0.5441 (SD 0.0527, n=90), counts.activities=13.8963 (SD 0.6917, n=90), counts.assessment=8.8333 (SD 1.5500, n=90), counts.evaluation=12.8333 (SD 1.5500, n=90), counts.objectives=5.2185 (SD 0.3395, n=90), counts.topics=3.1222 (SD 0.3294, n=90), details.sanity.bloom_vs_declared_agreement=0.6937 (SD 0.1397, n=90), details.sanity.n_bloom_classified=5.2185 (SD 0.3395, n=90), details.sanity.n_comparable=5.2185 (SD 0.3395, n=90), details.sanity.n_declared=5.2185 (SD 0.3395, n=90), details.sanity.n_objectives=5.2185 (SD 0.3395, n=90), details.validation.declared_link_agreement=0.7346 (SD 0.1722, n=90), details.validation.declared_links=20.1037 (SD 0.3301, n=90), details.validation.declared_links_checked=20.1037 (SD 0.3301, n=90), objective_activity_similarity=0.5047 (SD 0.0443, n=90), objective_assessment_similarity=0.5856 (SD 0.0618, n=90), objective_cognitive_congruence=0.5978 (SD 0.1768, n=90), objective_evaluation_similarity=0.5856 (SD 0.0617, n=90), porter.activities=0.2972 (SD 0.0814, n=90), porter.assessment=0.4242 (SD 0.1175, n=90), porter.evaluation=0.3806 (SD 0.0966, n=90), porter_mean=0.3673 (SD 0.0747, n=90), webb_bloom_consistency=0.5910 (SD 0.1536, n=90)
- alignmentgraph-isd: assessment_objective_similarity=0.6934 (SD 0.0554, n=90), counts.activities=14.2630 (SD 0.9501, n=90), counts.assessment=15.0481 (SD 0.2094, n=90), counts.evaluation=8.8037 (SD 0.5214, n=90), counts.objectives=4.9852 (SD 0.0853, n=90), counts.topics=3.1222 (SD 0.3294, n=90), details.sanity.bloom_vs_declared_agreement=0.9706 (SD 0.0513, n=90), details.sanity.n_bloom_classified=4.9852 (SD 0.0853, n=90), details.sanity.n_comparable=4.7630 (SD 0.3286, n=90), details.sanity.n_declared=4.7630 (SD 0.3286, n=90), details.sanity.n_objectives=4.9852 (SD 0.0853, n=90), details.validation.declared_link_agreement=0.9023 (SD 0.0498, n=90), details.validation.declared_links=15.0519 (SD 0.2055, n=90), details.validation.declared_links_checked=15.0000 (SD 0.2548, n=90), objective_activity_similarity=0.6776 (SD 0.0330, n=90), objective_assessment_similarity=0.8315 (SD 0.0525, n=90), objective_cognitive_congruence=0.9178 (SD 0.0728, n=90), objective_evaluation_similarity=0.8108 (SD 0.0548, n=90), porter.activities=0.3731 (SD 0.0702, n=90), porter.assessment=0.5312 (SD 0.0846, n=90), porter.evaluation=0.4710 (SD 0.0791, n=90), porter_mean=0.4584 (SD 0.0582, n=90), webb_bloom_consistency=0.8655 (SD 0.0623, n=90)
- baseline: assessment_objective_similarity=0.4747 (SD 0.0356, n=90), counts.activities=11.9148 (SD 0.9773, n=90), counts.assessment=13.3778 (SD 1.5150, n=90), counts.evaluation=28.5259 (SD 1.3173, n=90), counts.objectives=4.9630 (SD 0.2471, n=90), counts.topics=3.1222 (SD 0.3294, n=90), details.sanity.bloom_vs_declared_agreement=0.6581 (SD 0.1463, n=90), details.sanity.n_bloom_classified=5.0000 (SD 0.0000, n=90), details.sanity.n_comparable=5.0000 (SD 0.0000, n=90), details.sanity.n_declared=5.0000 (SD 0.0000, n=90), details.sanity.n_objectives=5.0000 (SD 0.0000, n=90), details.validation.declared_link_agreement=0.6241 (SD 0.1239, n=90), details.validation.declared_links=9.5685 (SD 1.3791, n=90), details.validation.declared_links_checked=9.5130 (SD 1.4085, n=90), objective_activity_similarity=0.5720 (SD 0.0554, n=90), objective_assessment_similarity=0.5622 (SD 0.0516, n=90), objective_cognitive_congruence=0.6619 (SD 0.1372, n=90), objective_evaluation_similarity=0.5160 (SD 0.0620, n=90), porter.activities=0.3379 (SD 0.0805, n=90), porter.assessment=0.3138 (SD 0.0828, n=90), porter.evaluation=0.2644 (SD 0.0840, n=90), porter_mean=0.3054 (SD 0.0510, n=90), webb_bloom_consistency=0.5146 (SD 0.1016, n=90)
- dick-carey-agent: assessment_objective_similarity=0.5702 (SD 0.0571, n=90), counts.activities=6.2519 (SD 0.3093, n=90), counts.assessment=5.0000 (SD 0.0000, n=90), counts.evaluation=8.0000 (SD 0.0000, n=90), counts.objectives=6.0222 (SD 0.1095, n=90), counts.topics=3.1222 (SD 0.3294, n=90), details.sanity.n_bloom_classified=6.0222 (SD 0.1095, n=90), details.sanity.n_comparable=0.0000 (SD 0.0000, n=90), details.sanity.n_declared=0.0000 (SD 0.0000, n=90), details.sanity.n_objectives=6.0222 (SD 0.1095, n=90), details.validation.declared_links=5.0000 (SD 0.0000, n=90), details.validation.declared_links_checked=0.0000 (SD 0.0000, n=90), objective_activity_similarity=0.5471 (SD 0.0379, n=90), objective_assessment_similarity=0.5565 (SD 0.0548, n=90), objective_cognitive_congruence=0.7949 (SD 0.1153, n=90), objective_evaluation_similarity=0.5567 (SD 0.0543, n=90), porter.activities=0.4140 (SD 0.1079, n=90), porter.assessment=0.4089 (SD 0.1145, n=90), porter.evaluation=0.3574 (SD 0.0853, n=90), porter_mean=0.3934 (SD 0.0784, n=90), webb_bloom_consistency=0.7652 (SD 0.1225, n=90)
- eduplanner: assessment_objective_similarity=0.4750 (SD 0.0372, n=90), counts.activities=13.8444 (SD 0.8424, n=90), counts.assessment=14.1907 (SD 1.4952, n=90), counts.evaluation=12.6593 (SD 1.0810, n=90), counts.objectives=4.9741 (SD 0.3208, n=90), counts.topics=3.1222 (SD 0.3294, n=90), details.sanity.bloom_vs_declared_agreement=0.7201 (SD 0.1094, n=90), details.sanity.n_bloom_classified=5.0296 (SD 0.0954, n=90), details.sanity.n_comparable=5.0296 (SD 0.0954, n=90), details.sanity.n_declared=5.0296 (SD 0.0954, n=90), details.sanity.n_objectives=5.0296 (SD 0.0954, n=90), details.validation.declared_links=0.0000 (SD 0.0000, n=90), details.validation.declared_links_checked=0.0000 (SD 0.0000, n=90), objective_activity_similarity=0.5133 (SD 0.0523, n=90), objective_assessment_similarity=0.5916 (SD 0.0660, n=90), objective_cognitive_congruence=0.6899 (SD 0.1367, n=90), objective_evaluation_similarity=0.5838 (SD 0.0746, n=90), porter.activities=0.2871 (SD 0.0793, n=90), porter.assessment=0.3881 (SD 0.0873, n=90), porter.evaluation=0.3699 (SD 0.0908, n=90), porter_mean=0.3484 (SD 0.0671, n=90), webb_bloom_consistency=0.6692 (SD 0.1002, n=90)
- react-isd: assessment_objective_similarity=0.4537 (SD 0.0558, n=90), counts.activities=12.0000 (SD 0.0000, n=90), counts.assessment=15.9111 (SD 0.5823, n=90), counts.evaluation=7.9815 (SD 0.1757, n=90), counts.objectives=4.9630 (SD 0.1763, n=90), counts.topics=3.1222 (SD 0.3294, n=90), details.sanity.bloom_vs_declared_agreement=0.7185 (SD 0.1195, n=90), details.sanity.n_bloom_classified=4.9630 (SD 0.1763, n=90), details.sanity.n_comparable=4.9630 (SD 0.1763, n=90), details.sanity.n_declared=4.9630 (SD 0.1763, n=90), details.sanity.n_objectives=4.9630 (SD 0.1763, n=90), details.validation.declared_link_agreement=0.2643 (SD 0.1468, n=89), details.validation.declared_links=10.9296 (SD 0.5686, n=90), details.validation.declared_links_checked=8.3704 (SD 2.7389, n=90), objective_activity_similarity=0.5644 (SD 0.0475, n=90), objective_assessment_similarity=0.5702 (SD 0.0591, n=90), objective_cognitive_congruence=0.7465 (SD 0.1507, n=90), objective_evaluation_similarity=0.5501 (SD 0.0679, n=90), porter.activities=0.2789 (SD 0.0737, n=90), porter.assessment=0.3171 (SD 0.0832, n=90), porter.evaluation=0.2610 (SD 0.0847, n=90), porter_mean=0.2856 (SD 0.0564, n=90), webb_bloom_consistency=0.6205 (SD 0.1081, n=90)
- rpisd-agent: assessment_objective_similarity=0.3950 (SD 0.0337, n=90), counts.activities=14.0000 (SD 0.0000, n=90), counts.assessment=9.8852 (SD 0.2789, n=90), counts.evaluation=14.8852 (SD 0.2789, n=90), counts.objectives=5.0000 (SD 0.0000, n=90), counts.topics=3.1222 (SD 0.3294, n=90), details.sanity.bloom_vs_declared_agreement=0.6412 (SD 0.1538, n=90), details.sanity.n_bloom_classified=5.0000 (SD 0.0000, n=90), details.sanity.n_comparable=4.8889 (SD 0.2396, n=90), details.sanity.n_declared=4.8889 (SD 0.2396, n=90), details.sanity.n_objectives=5.0000 (SD 0.0000, n=90), details.validation.declared_links=0.0000 (SD 0.0000, n=90), details.validation.declared_links_checked=0.0000 (SD 0.0000, n=90), objective_activity_similarity=0.5427 (SD 0.0340, n=90), objective_assessment_similarity=0.4514 (SD 0.0416, n=90), objective_cognitive_congruence=0.4733 (SD 0.1469, n=90), objective_evaluation_similarity=0.4578 (SD 0.0395, n=90), porter.activities=0.3333 (SD 0.0968, n=90), porter.assessment=0.2528 (SD 0.0921, n=90), porter.evaluation=0.2729 (SD 0.0819, n=90), porter_mean=0.2863 (SD 0.0664, n=90), webb_bloom_consistency=0.4460 (SD 0.1341, n=90)

## RQ2 alignment panel (every signal, descriptive + paired, proposed vs baselines)

No signal is primary: each is reported for every comparison, win or lose. `p_holm` corrects within one signal (6 comparisons); `p_panel` corrects over the whole panel x baseline family for that size.

### Qwen3.5-0.8B
#### objective_assessment_similarity [correspondence]
mean [bootstrap CI95] per agent: addie-agent=0.595 [0.583, 0.607] (n=90), alignmentgraph-isd=0.851 [0.841, 0.862] (n=90), baseline=0.104 [0.059, 0.153] (n=70), dick-carey-agent=0.441 [0.431, 0.450] (n=90), eduplanner=0.360 [0.307, 0.413] (n=73), react-isd=0.504 [0.482, 0.526] (n=90), rpisd-agent=0.510 [0.497, 0.524] (n=90)
conditional (>=1 objective): addie-agent=0.595 (n=90), alignmentgraph-isd=0.851 (n=90), baseline=0.315 (n=19), dick-carey-agent=0.443 (n=89), eduplanner=0.523 (n=42), react-isd=0.504 (n=90), rpisd-agent=0.510 (n=90)

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| baseline | 70 | +0.7484 | [+0.6976, +0.7961] | 3.559e-13 | 6.051e-12 |
| react-isd | 90 | +0.3474 | [+0.3240, +0.3703] | 1.332e-15 | 9.326e-15 |
| dick-carey-agent | 90 | +0.4104 | [+0.3950, +0.4258] | 1.332e-15 | 9.326e-15 |
| addie-agent | 90 | +0.2562 | [+0.2403, +0.2725] | 1.332e-15 | 9.326e-15 |
| rpisd-agent | 90 | +0.3410 | [+0.3248, +0.3565] | 1.332e-15 | 9.326e-15 |
| eduplanner | 73 | +0.4883 | [+0.4342, +0.5414] | 2.265e-13 | 2.491e-12 |

#### objective_activity_similarity [correspondence]
mean [bootstrap CI95] per agent: addie-agent=0.445 [0.439, 0.451] (n=90), alignmentgraph-isd=0.697 [0.688, 0.707] (n=90), baseline=0.117 [0.067, 0.172] (n=70), dick-carey-agent=0.393 [0.386, 0.400] (n=90), eduplanner=0.394 [0.340, 0.448] (n=73), react-isd=0.403 [0.390, 0.416] (n=90), rpisd-agent=0.436 [0.426, 0.445] (n=90)
conditional (>=1 objective): addie-agent=0.445 (n=90), alignmentgraph-isd=0.697 (n=90), baseline=0.351 (n=19), dick-carey-agent=0.395 (n=89), eduplanner=0.568 (n=42), react-isd=0.403 (n=90), rpisd-agent=0.436 (n=90)

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| baseline | 70 | +0.5836 | [+0.5246, +0.6380] | 5.722e-13 | 8.011e-12 |
| react-isd | 90 | +0.2939 | [+0.2793, +0.3091] | 1.332e-15 | 9.326e-15 |
| dick-carey-agent | 90 | +0.3043 | [+0.2933, +0.3158] | 1.332e-15 | 9.326e-15 |
| addie-agent | 90 | +0.2524 | [+0.2418, +0.2632] | 1.332e-15 | 9.326e-15 |
| rpisd-agent | 90 | +0.2618 | [+0.2477, +0.2754] | 1.332e-15 | 9.326e-15 |
| eduplanner | 73 | +0.3034 | [+0.2490, +0.3590] | 3.428e-13 | 3.257e-12 |

#### objective_evaluation_similarity [correspondence]
mean [bootstrap CI95] per agent: addie-agent=0.596 [0.584, 0.608] (n=90), alignmentgraph-isd=0.806 [0.793, 0.819] (n=90), baseline=0.150 [0.105, 0.197] (n=70), dick-carey-agent=0.451 [0.442, 0.460] (n=90), eduplanner=0.316 [0.263, 0.369] (n=73), react-isd=0.465 [0.442, 0.488] (n=90), rpisd-agent=0.527 [0.515, 0.538] (n=90)
conditional (>=1 objective): addie-agent=0.596 (n=90), alignmentgraph-isd=0.806 (n=90), baseline=0.438 (n=19), dick-carey-agent=0.454 (n=89), eduplanner=0.464 (n=42), react-isd=0.465 (n=90), rpisd-agent=0.527 (n=90)

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| baseline | 70 | +0.6583 | [+0.6086, +0.7053] | 3.559e-13 | 6.051e-12 |
| react-isd | 90 | +0.3408 | [+0.3142, +0.3669] | 1.332e-15 | 9.326e-15 |
| dick-carey-agent | 90 | +0.3545 | [+0.3373, +0.3718] | 1.332e-15 | 9.326e-15 |
| addie-agent | 90 | +0.2101 | [+0.1919, +0.2286] | 1.332e-15 | 9.326e-15 |
| rpisd-agent | 90 | +0.2794 | [+0.2626, +0.2962] | 1.332e-15 | 9.326e-15 |
| eduplanner | 73 | +0.4874 | [+0.4310, +0.5418] | 2.265e-13 | 2.491e-12 |

#### assessment_objective_similarity [correspondence] — diagnostic, direction not one-way-good
mean [bootstrap CI95] per agent: addie-agent=0.524 [0.514, 0.533] (n=90), alignmentgraph-isd=0.682 [0.670, 0.695] (n=90), baseline=0.528 [0.493, 0.563] (n=17), dick-carey-agent=0.468 [0.457, 0.478] (n=90), eduplanner=0.477 [0.453, 0.502] (n=59), react-isd=0.362 [0.349, 0.375] (n=90), rpisd-agent=0.498 [0.486, 0.510] (n=90)
conditional (>=1 objective): addie-agent=0.524 (n=90), alignmentgraph-isd=0.682 (n=90), baseline=0.544 (n=12), dick-carey-agent=0.469 (n=89), eduplanner=0.481 (n=42), react-isd=0.362 (n=90), rpisd-agent=0.498 (n=90)

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| baseline | 17 | +0.1343 | [+0.0775, +0.1858] | 5.035e-04 | 2.014e-03 |
| react-isd | 90 | +0.3204 | [+0.3052, +0.3358] | 1.332e-15 | 9.326e-15 |
| dick-carey-agent | 90 | +0.2146 | [+0.1979, +0.2310] | 1.332e-15 | 9.326e-15 |
| addie-agent | 90 | +0.1585 | [+0.1434, +0.1735] | 1.332e-15 | 9.326e-15 |
| rpisd-agent | 90 | +0.1841 | [+0.1677, +0.2006] | 1.332e-15 | 9.326e-15 |
| eduplanner | 59 | +0.2041 | [+0.1754, +0.2334] | 5.871e-11 | 3.229e-10 |

#### objective_cognitive_congruence [cognitive]
mean [bootstrap CI95] per agent: addie-agent=0.565 [0.535, 0.595] (n=90), alignmentgraph-isd=0.813 [0.790, 0.835] (n=90), baseline=0.628 [0.495, 0.759] (n=17), dick-carey-agent=0.766 [0.746, 0.784] (n=90), eduplanner=0.630 [0.566, 0.693] (n=59), react-isd=0.570 [0.524, 0.616] (n=90), rpisd-agent=0.552 [0.514, 0.590] (n=90)
conditional (>=1 objective): addie-agent=0.565 (n=90), alignmentgraph-isd=0.813 (n=90), baseline=0.607 (n=12), dick-carey-agent=0.767 (n=89), eduplanner=0.622 (n=42), react-isd=0.570 (n=90), rpisd-agent=0.552 (n=90)

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| baseline | 17 | +0.1873 | [+0.0386, +0.3382] | 6.213e-02 | 7.309e-02 |
| react-isd | 90 | +0.2431 | [+0.1942, +0.2935] | 8.432e-12 | 2.741e-11 |
| dick-carey-agent | 90 | +0.0471 | [+0.0150, +0.0788] | 2.328e-02 | 3.491e-02 |
| addie-agent | 90 | +0.2479 | [+0.2090, +0.2874] | 1.412e-13 | 5.436e-13 |
| rpisd-agent | 90 | +0.2609 | [+0.2166, +0.3049] | 7.216e-13 | 2.887e-12 |
| eduplanner | 59 | +0.1794 | [+0.1077, +0.2507] | 6.842e-05 | 1.597e-04 |

#### porter_mean [cognitive]
mean [bootstrap CI95] per agent: addie-agent=0.355 [0.338, 0.372] (n=90), alignmentgraph-isd=0.433 [0.419, 0.446] (n=90), baseline=0.181 [0.142, 0.219] (n=30), dick-carey-agent=0.316 [0.297, 0.335] (n=90), eduplanner=0.284 [0.253, 0.314] (n=59), react-isd=0.223 [0.204, 0.240] (n=90), rpisd-agent=0.270 [0.253, 0.286] (n=90)
conditional (>=1 objective): addie-agent=0.355 (n=90), alignmentgraph-isd=0.433 (n=90), baseline=0.178 (n=19), dick-carey-agent=0.317 (n=89), eduplanner=0.284 (n=42), react-isd=0.223 (n=90), rpisd-agent=0.270 (n=90)

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| baseline | 30 | +0.2586 | [+0.2082, +0.3089] | 1.734e-06 | 1.388e-05 |
| react-isd | 90 | +0.2098 | [+0.1886, +0.2312] | 1.332e-15 | 9.326e-15 |
| dick-carey-agent | 90 | +0.1164 | [+0.0960, +0.1377] | 1.734e-12 | 6.501e-12 |
| addie-agent | 90 | +0.0777 | [+0.0550, +0.1007] | 1.053e-07 | 4.741e-07 |
| rpisd-agent | 90 | +0.1630 | [+0.1425, +0.1837] | 5.551e-15 | 2.776e-14 |
| eduplanner | 59 | +0.1471 | [+0.1135, +0.1808] | 9.360e-09 | 3.120e-08 |

#### webb_bloom_consistency [cognitive]
mean [bootstrap CI95] per agent: addie-agent=0.477 [0.450, 0.505] (n=90), alignmentgraph-isd=0.682 [0.663, 0.702] (n=90), baseline=0.276 [0.165, 0.393] (n=30), dick-carey-agent=0.846 [0.820, 0.870] (n=90), eduplanner=0.595 [0.535, 0.654] (n=59), react-isd=0.386 [0.342, 0.431] (n=90), rpisd-agent=0.576 [0.537, 0.613] (n=90)
conditional (>=1 objective): addie-agent=0.477 (n=90), alignmentgraph-isd=0.682 (n=90), baseline=0.272 (n=19), dick-carey-agent=0.846 (n=89), eduplanner=0.585 (n=42), react-isd=0.386 (n=90), rpisd-agent=0.576 (n=90)

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| baseline | 30 | +0.4116 | [+0.2825, +0.5295] | 1.022e-04 | 2.043e-04 |
| react-isd | 90 | +0.2964 | [+0.2495, +0.3430] | 1.359e-13 | 5.436e-13 |
| dick-carey-agent | 90 | -0.1639 | [-0.1962, -0.1302] | 1.122e-11 | 3.367e-11 |
| addie-agent | 90 | +0.2053 | [+0.1721, +0.2378] | 1.472e-12 | 5.300e-12 |
| rpisd-agent | 90 | +0.1067 | [+0.0624, +0.1518] | 1.022e-04 | 2.434e-04 |
| eduplanner | 59 | +0.0798 | [+0.0154, +0.1453] | 3.655e-02 | 7.309e-02 |

### Qwen3.5-2B
#### objective_assessment_similarity [correspondence]
mean [bootstrap CI95] per agent: addie-agent=0.606 [0.588, 0.623] (n=90), alignmentgraph-isd=0.850 [0.838, 0.863] (n=90), baseline=0.383 [0.347, 0.418] (n=88), dick-carey-agent=0.499 [0.488, 0.510] (n=90), eduplanner=0.500 [0.468, 0.532] (n=90), react-isd=0.583 [0.563, 0.602] (n=90), rpisd-agent=0.519 [0.509, 0.530] (n=90)
conditional (>=1 objective): addie-agent=0.606 (n=90), alignmentgraph-isd=0.850 (n=90), baseline=0.485 (n=55), dick-carey-agent=0.500 (n=89), eduplanner=0.600 (n=56), react-isd=0.583 (n=90), rpisd-agent=0.519 (n=90)

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| baseline | 88 | +0.4658 | [+0.4276, +0.5059] | 1.332e-15 | 1.110e-14 |
| react-isd | 90 | +0.2674 | [+0.2464, +0.2890] | 1.332e-15 | 9.326e-15 |
| dick-carey-agent | 90 | +0.3516 | [+0.3367, +0.3667] | 1.332e-15 | 9.326e-15 |
| addie-agent | 90 | +0.2448 | [+0.2234, +0.2659] | 1.332e-15 | 9.326e-15 |
| rpisd-agent | 90 | +0.3313 | [+0.3168, +0.3457] | 1.332e-15 | 9.326e-15 |
| eduplanner | 90 | +0.3508 | [+0.3167, +0.3866] | 1.332e-15 | 9.326e-15 |

#### objective_activity_similarity [correspondence]
mean [bootstrap CI95] per agent: addie-agent=0.454 [0.444, 0.464] (n=90), alignmentgraph-isd=0.680 [0.671, 0.688] (n=90), baseline=0.420 [0.381, 0.458] (n=88), dick-carey-agent=0.473 [0.465, 0.482] (n=90), eduplanner=0.432 [0.406, 0.456] (n=90), react-isd=0.490 [0.476, 0.505] (n=90), rpisd-agent=0.542 [0.530, 0.554] (n=90)
conditional (>=1 objective): addie-agent=0.454 (n=90), alignmentgraph-isd=0.680 (n=90), baseline=0.528 (n=55), dick-carey-agent=0.475 (n=89), eduplanner=0.515 (n=56), react-isd=0.490 (n=90), rpisd-agent=0.542 (n=90)

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| baseline | 88 | +0.2602 | [+0.2204, +0.3010] | 1.332e-15 | 1.110e-14 |
| react-isd | 90 | +0.1892 | [+0.1737, +0.2053] | 1.332e-15 | 9.326e-15 |
| dick-carey-agent | 90 | +0.2062 | [+0.1934, +0.2185] | 1.332e-15 | 9.326e-15 |
| addie-agent | 90 | +0.2257 | [+0.2131, +0.2386] | 1.332e-15 | 9.326e-15 |
| rpisd-agent | 90 | +0.1380 | [+0.1250, +0.1511] | 1.332e-15 | 9.326e-15 |
| eduplanner | 90 | +0.2479 | [+0.2217, +0.2753] | 1.332e-15 | 9.326e-15 |

#### objective_evaluation_similarity [correspondence]
mean [bootstrap CI95] per agent: addie-agent=0.608 [0.592, 0.624] (n=90), alignmentgraph-isd=0.806 [0.786, 0.825] (n=90), baseline=0.328 [0.300, 0.356] (n=88), dick-carey-agent=0.505 [0.495, 0.516] (n=90), eduplanner=0.478 [0.444, 0.511] (n=90), react-isd=0.555 [0.534, 0.575] (n=90), rpisd-agent=0.523 [0.513, 0.534] (n=90)
conditional (>=1 objective): addie-agent=0.608 (n=90), alignmentgraph-isd=0.806 (n=90), baseline=0.408 (n=55), dick-carey-agent=0.507 (n=89), eduplanner=0.574 (n=56), react-isd=0.555 (n=90), rpisd-agent=0.523 (n=90)

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| baseline | 88 | +0.4761 | [+0.4427, +0.5103] | 1.332e-15 | 1.110e-14 |
| react-isd | 90 | +0.2512 | [+0.2254, +0.2775] | 1.332e-15 | 9.326e-15 |
| dick-carey-agent | 90 | +0.3005 | [+0.2801, +0.3206] | 1.332e-15 | 9.326e-15 |
| addie-agent | 90 | +0.1979 | [+0.1729, +0.2224] | 1.332e-15 | 1.865e-14 |
| rpisd-agent | 90 | +0.2824 | [+0.2622, +0.3021] | 1.332e-15 | 9.326e-15 |
| eduplanner | 90 | +0.3282 | [+0.2880, +0.3696] | 1.332e-15 | 9.326e-15 |

#### assessment_objective_similarity [correspondence] — diagnostic, direction not one-way-good
mean [bootstrap CI95] per agent: addie-agent=0.531 [0.518, 0.544] (n=90), alignmentgraph-isd=0.652 [0.640, 0.664] (n=90), baseline=0.468 [0.455, 0.480] (n=82), dick-carey-agent=0.541 [0.529, 0.554] (n=90), eduplanner=0.522 [0.507, 0.537] (n=89), react-isd=0.428 [0.416, 0.440] (n=90), rpisd-agent=0.450 [0.441, 0.458] (n=90)
conditional (>=1 objective): addie-agent=0.531 (n=90), alignmentgraph-isd=0.652 (n=90), baseline=0.469 (n=55), dick-carey-agent=0.540 (n=89), eduplanner=0.528 (n=56), react-isd=0.428 (n=90), rpisd-agent=0.450 (n=90)

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| baseline | 82 | +0.1857 | [+0.1716, +0.2000] | 7.327e-15 | 6.040e-14 |
| react-isd | 90 | +0.2242 | [+0.2104, +0.2388] | 1.332e-15 | 9.326e-15 |
| dick-carey-agent | 90 | +0.1109 | [+0.0958, +0.1259] | 7.327e-15 | 4.396e-14 |
| addie-agent | 90 | +0.1211 | [+0.1056, +0.1365] | 2.665e-15 | 1.465e-14 |
| rpisd-agent | 90 | +0.2021 | [+0.1903, +0.2145] | 1.332e-15 | 9.326e-15 |
| eduplanner | 89 | +0.1291 | [+0.1115, +0.1466] | 8.882e-15 | 1.421e-13 |

#### objective_cognitive_congruence [cognitive]
mean [bootstrap CI95] per agent: addie-agent=0.624 [0.587, 0.658] (n=90), alignmentgraph-isd=0.865 [0.845, 0.885] (n=90), baseline=0.722 [0.678, 0.765] (n=82), dick-carey-agent=0.756 [0.730, 0.781] (n=90), eduplanner=0.685 [0.650, 0.718] (n=89), react-isd=0.662 [0.627, 0.695] (n=90), rpisd-agent=0.559 [0.524, 0.594] (n=90)
conditional (>=1 objective): addie-agent=0.624 (n=90), alignmentgraph-isd=0.865 (n=90), baseline=0.713 (n=55), dick-carey-agent=0.757 (n=89), eduplanner=0.697 (n=56), react-isd=0.662 (n=90), rpisd-agent=0.559 (n=90)

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| baseline | 82 | +0.1485 | [+0.1018, +0.1955] | 3.177e-07 | 1.271e-06 |
| react-isd | 90 | +0.2036 | [+0.1690, +0.2399] | 1.643e-13 | 5.751e-13 |
| dick-carey-agent | 90 | +0.1096 | [+0.0760, +0.1429] | 3.561e-08 | 8.902e-08 |
| addie-agent | 90 | +0.2417 | [+0.2012, +0.2846] | 5.329e-14 | 1.599e-13 |
| rpisd-agent | 90 | +0.3062 | [+0.2664, +0.3473] | 5.329e-15 | 1.865e-14 |
| eduplanner | 89 | +0.1790 | [+0.1401, +0.2194] | 2.783e-11 | 9.276e-11 |

#### porter_mean [cognitive]
mean [bootstrap CI95] per agent: addie-agent=0.359 [0.342, 0.375] (n=90), alignmentgraph-isd=0.448 [0.434, 0.462] (n=90), baseline=0.275 [0.259, 0.290] (n=85), dick-carey-agent=0.354 [0.339, 0.368] (n=90), eduplanner=0.344 [0.323, 0.365] (n=89), react-isd=0.268 [0.256, 0.280] (n=90), rpisd-agent=0.322 [0.304, 0.339] (n=90)
conditional (>=1 objective): addie-agent=0.359 (n=90), alignmentgraph-isd=0.448 (n=90), baseline=0.268 (n=55), dick-carey-agent=0.354 (n=89), eduplanner=0.354 (n=56), react-isd=0.268 (n=90), rpisd-agent=0.322 (n=90)

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| baseline | 85 | +0.1723 | [+0.1537, +0.1906] | 8.882e-15 | 3.375e-14 |
| react-isd | 90 | +0.1791 | [+0.1616, +0.1970] | 1.332e-15 | 9.326e-15 |
| dick-carey-agent | 90 | +0.0940 | [+0.0727, +0.1157] | 2.328e-10 | 9.313e-10 |
| addie-agent | 90 | +0.0888 | [+0.0675, +0.1107] | 1.889e-10 | 5.668e-10 |
| rpisd-agent | 90 | +0.1260 | [+0.1046, +0.1476] | 5.063e-13 | 1.645e-12 |
| eduplanner | 89 | +0.1024 | [+0.0768, +0.1281] | 5.347e-10 | 3.208e-09 |

#### webb_bloom_consistency [cognitive]
mean [bootstrap CI95] per agent: addie-agent=0.573 [0.538, 0.605] (n=90), alignmentgraph-isd=0.724 [0.704, 0.744] (n=90), baseline=0.601 [0.553, 0.647] (n=85), dick-carey-agent=0.761 [0.736, 0.785] (n=90), eduplanner=0.659 [0.631, 0.686] (n=89), react-isd=0.496 [0.460, 0.532] (n=90), rpisd-agent=0.539 [0.509, 0.568] (n=90)
conditional (>=1 objective): addie-agent=0.573 (n=90), alignmentgraph-isd=0.724 (n=90), baseline=0.608 (n=55), dick-carey-agent=0.763 (n=89), eduplanner=0.677 (n=56), react-isd=0.496 (n=90), rpisd-agent=0.539 (n=90)

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| baseline | 85 | +0.1253 | [+0.0738, +0.1765] | 3.098e-05 | 3.098e-05 |
| react-isd | 90 | +0.2285 | [+0.1882, +0.2685] | 1.713e-12 | 3.427e-12 |
| dick-carey-agent | 90 | -0.0365 | [-0.0682, -0.0049] | 5.419e-02 | 5.419e-02 |
| addie-agent | 90 | +0.1516 | [+0.1141, +0.1908] | 7.065e-10 | 1.236e-09 |
| rpisd-agent | 90 | +0.1855 | [+0.1515, +0.2190] | 3.912e-12 | 8.607e-12 |
| eduplanner | 89 | +0.0639 | [+0.0307, +0.0963] | 1.535e-04 | 1.535e-04 |

### Qwen3.5-4B
#### objective_assessment_similarity [correspondence]
mean [bootstrap CI95] per agent: addie-agent=0.608 [0.596, 0.620] (n=90), alignmentgraph-isd=0.806 [0.791, 0.820] (n=90), baseline=0.547 [0.528, 0.565] (n=90), dick-carey-agent=0.536 [0.526, 0.546] (n=90), eduplanner=0.598 [0.578, 0.615] (n=89), react-isd=0.579 [0.568, 0.591] (n=90), rpisd-agent=0.466 [0.457, 0.474] (n=90)
conditional (>=1 objective): addie-agent=0.608 (n=90), alignmentgraph-isd=0.806 (n=90), baseline=0.572 (n=80), dick-carey-agent=0.536 (n=90), eduplanner=0.620 (n=81), react-isd=0.579 (n=90), rpisd-agent=0.466 (n=90)

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| baseline | 90 | +0.2586 | [+0.2378, +0.2802] | 1.332e-15 | 9.326e-15 |
| react-isd | 90 | +0.2266 | [+0.2139, +0.2389] | 1.332e-15 | 9.326e-15 |
| dick-carey-agent | 90 | +0.2695 | [+0.2561, +0.2820] | 1.332e-15 | 9.326e-15 |
| addie-agent | 90 | +0.1977 | [+0.1829, +0.2128] | 1.332e-15 | 9.326e-15 |
| rpisd-agent | 90 | +0.3402 | [+0.3246, +0.3556] | 1.332e-15 | 9.326e-15 |
| eduplanner | 89 | +0.2078 | [+0.1864, +0.2306] | 1.332e-15 | 9.326e-15 |

#### objective_activity_similarity [correspondence]
mean [bootstrap CI95] per agent: addie-agent=0.536 [0.528, 0.544] (n=90), alignmentgraph-isd=0.686 [0.680, 0.693] (n=90), baseline=0.486 [0.470, 0.501] (n=90), dick-carey-agent=0.545 [0.536, 0.553] (n=90), eduplanner=0.474 [0.458, 0.489] (n=89), react-isd=0.534 [0.522, 0.547] (n=90), rpisd-agent=0.538 [0.531, 0.545] (n=90)
conditional (>=1 objective): addie-agent=0.536 (n=90), alignmentgraph-isd=0.686 (n=90), baseline=0.508 (n=80), dick-carey-agent=0.545 (n=90), eduplanner=0.492 (n=81), react-isd=0.534 (n=90), rpisd-agent=0.538 (n=90)

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| baseline | 90 | +0.2006 | [+0.1847, +0.2185] | 1.332e-15 | 9.326e-15 |
| react-isd | 90 | +0.1524 | [+0.1396, +0.1656] | 1.332e-15 | 9.326e-15 |
| dick-carey-agent | 90 | +0.1418 | [+0.1311, +0.1524] | 1.332e-15 | 9.326e-15 |
| addie-agent | 90 | +0.1500 | [+0.1402, +0.1598] | 1.332e-15 | 9.326e-15 |
| rpisd-agent | 90 | +0.1483 | [+0.1396, +0.1574] | 1.332e-15 | 9.326e-15 |
| eduplanner | 89 | +0.2129 | [+0.1976, +0.2295] | 1.332e-15 | 9.326e-15 |

#### objective_evaluation_similarity [correspondence]
mean [bootstrap CI95] per agent: addie-agent=0.608 [0.596, 0.620] (n=90), alignmentgraph-isd=0.789 [0.773, 0.804] (n=90), baseline=0.497 [0.478, 0.514] (n=90), dick-carey-agent=0.537 [0.526, 0.547] (n=90), eduplanner=0.595 [0.574, 0.613] (n=89), react-isd=0.562 [0.551, 0.574] (n=90), rpisd-agent=0.472 [0.464, 0.480] (n=90)
conditional (>=1 objective): addie-agent=0.608 (n=90), alignmentgraph-isd=0.789 (n=90), baseline=0.519 (n=80), dick-carey-agent=0.537 (n=90), eduplanner=0.617 (n=81), react-isd=0.562 (n=90), rpisd-agent=0.472 (n=90)

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| baseline | 90 | +0.2923 | [+0.2705, +0.3149] | 1.332e-15 | 9.326e-15 |
| react-isd | 90 | +0.2268 | [+0.2124, +0.2409] | 1.332e-15 | 9.326e-15 |
| dick-carey-agent | 90 | +0.2524 | [+0.2373, +0.2665] | 1.332e-15 | 9.326e-15 |
| addie-agent | 90 | +0.1809 | [+0.1648, +0.1971] | 1.332e-15 | 9.326e-15 |
| rpisd-agent | 90 | +0.3167 | [+0.3001, +0.3332] | 1.332e-15 | 9.326e-15 |
| eduplanner | 89 | +0.1939 | [+0.1709, +0.2181] | 1.332e-15 | 9.326e-15 |

#### assessment_objective_similarity [correspondence] — diagnostic, direction not one-way-good
mean [bootstrap CI95] per agent: addie-agent=0.558 [0.546, 0.569] (n=90), alignmentgraph-isd=0.663 [0.649, 0.676] (n=90), baseline=0.483 [0.474, 0.492] (n=90), dick-carey-agent=0.564 [0.553, 0.575] (n=90), eduplanner=0.495 [0.484, 0.505] (n=89), react-isd=0.461 [0.450, 0.473] (n=90), rpisd-agent=0.411 [0.402, 0.419] (n=90)
conditional (>=1 objective): addie-agent=0.558 (n=90), alignmentgraph-isd=0.663 (n=90), baseline=0.484 (n=80), dick-carey-agent=0.564 (n=90), eduplanner=0.496 (n=81), react-isd=0.461 (n=90), rpisd-agent=0.411 (n=90)

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| baseline | 90 | +0.1798 | [+0.1684, +0.1914] | 1.332e-15 | 9.326e-15 |
| react-isd | 90 | +0.2015 | [+0.1919, +0.2109] | 1.332e-15 | 9.326e-15 |
| dick-carey-agent | 90 | +0.0983 | [+0.0857, +0.1102] | 1.776e-15 | 1.954e-14 |
| addie-agent | 90 | +0.1052 | [+0.0938, +0.1166] | 1.332e-15 | 9.326e-15 |
| rpisd-agent | 90 | +0.2522 | [+0.2394, +0.2650] | 1.332e-15 | 9.326e-15 |
| eduplanner | 89 | +0.1688 | [+0.1559, +0.1818] | 1.332e-15 | 9.326e-15 |

#### objective_cognitive_congruence [cognitive]
mean [bootstrap CI95] per agent: addie-agent=0.674 [0.638, 0.707] (n=90), alignmentgraph-isd=0.918 [0.900, 0.934] (n=90), baseline=0.729 [0.699, 0.759] (n=90), dick-carey-agent=0.791 [0.770, 0.812] (n=90), eduplanner=0.725 [0.698, 0.752] (n=89), react-isd=0.767 [0.737, 0.796] (n=90), rpisd-agent=0.528 [0.494, 0.563] (n=90)
conditional (>=1 objective): addie-agent=0.674 (n=90), alignmentgraph-isd=0.918 (n=90), baseline=0.725 (n=80), dick-carey-agent=0.791 (n=90), eduplanner=0.723 (n=81), react-isd=0.767 (n=90), rpisd-agent=0.528 (n=90)

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| baseline | 90 | +0.1887 | [+0.1564, +0.2221] | 3.271e-13 | 7.632e-13 |
| react-isd | 90 | +0.1507 | [+0.1216, +0.1814] | 3.093e-12 | 9.279e-12 |
| dick-carey-agent | 90 | +0.1268 | [+0.0975, +0.1561] | 3.718e-11 | 1.116e-10 |
| addie-agent | 90 | +0.2443 | [+0.2109, +0.2801] | 9.992e-15 | 1.998e-14 |
| rpisd-agent | 90 | +0.3896 | [+0.3488, +0.4298] | 7.994e-15 | 1.599e-14 |
| eduplanner | 89 | +0.1928 | [+0.1613, +0.2252] | 2.043e-13 | 4.086e-13 |

#### porter_mean [cognitive]
mean [bootstrap CI95] per agent: addie-agent=0.393 [0.375, 0.410] (n=90), alignmentgraph-isd=0.446 [0.435, 0.457] (n=90), baseline=0.309 [0.298, 0.319] (n=90), dick-carey-agent=0.363 [0.349, 0.378] (n=90), eduplanner=0.368 [0.354, 0.382] (n=89), react-isd=0.299 [0.285, 0.312] (n=90), rpisd-agent=0.291 [0.276, 0.305] (n=90)
conditional (>=1 objective): addie-agent=0.393 (n=90), alignmentgraph-isd=0.446 (n=90), baseline=0.311 (n=80), dick-carey-agent=0.363 (n=90), eduplanner=0.365 (n=81), react-isd=0.299 (n=90), rpisd-agent=0.291 (n=90)

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| baseline | 90 | +0.1374 | [+0.1225, +0.1528] | 1.332e-15 | 9.326e-15 |
| react-isd | 90 | +0.1474 | [+0.1301, +0.1647] | 2.220e-15 | 9.326e-15 |
| dick-carey-agent | 90 | +0.0828 | [+0.0641, +0.1008] | 2.006e-11 | 4.012e-11 |
| addie-agent | 90 | +0.0533 | [+0.0335, +0.0733] | 8.186e-06 | 8.186e-06 |
| rpisd-agent | 90 | +0.1553 | [+0.1377, +0.1735] | 2.220e-15 | 9.326e-15 |
| eduplanner | 89 | +0.0784 | [+0.0623, +0.0947] | 1.169e-11 | 1.948e-11 |

#### webb_bloom_consistency [cognitive]
mean [bootstrap CI95] per agent: addie-agent=0.668 [0.641, 0.695] (n=90), alignmentgraph-isd=0.871 [0.858, 0.883] (n=90), baseline=0.591 [0.568, 0.613] (n=90), dick-carey-agent=0.761 [0.734, 0.787] (n=90), eduplanner=0.702 [0.681, 0.723] (n=89), react-isd=0.624 [0.599, 0.647] (n=90), rpisd-agent=0.501 [0.469, 0.534] (n=90)
conditional (>=1 objective): addie-agent=0.668 (n=90), alignmentgraph-isd=0.871 (n=90), baseline=0.590 (n=80), dick-carey-agent=0.761 (n=90), eduplanner=0.701 (n=81), react-isd=0.624 (n=90), rpisd-agent=0.501 (n=90)

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| baseline | 90 | +0.2802 | [+0.2540, +0.3068] | 1.332e-15 | 9.326e-15 |
| react-isd | 90 | +0.2471 | [+0.2222, +0.2733] | 1.332e-15 | 9.326e-15 |
| dick-carey-agent | 90 | +0.1096 | [+0.0795, +0.1399] | 1.971e-09 | 3.942e-09 |
| addie-agent | 90 | +0.2023 | [+0.1756, +0.2306] | 1.332e-15 | 9.326e-15 |
| rpisd-agent | 90 | +0.3694 | [+0.3343, +0.4041] | 1.332e-15 | 9.326e-15 |
| eduplanner | 89 | +0.1673 | [+0.1421, +0.1918] | 1.155e-14 | 5.196e-14 |

### Qwen3.5-9B
#### objective_assessment_similarity [correspondence]
mean [bootstrap CI95] per agent: addie-agent=0.586 [0.573, 0.598] (n=90), alignmentgraph-isd=0.832 [0.821, 0.842] (n=90), baseline=0.562 [0.551, 0.573] (n=90), dick-carey-agent=0.557 [0.545, 0.568] (n=90), eduplanner=0.592 [0.578, 0.605] (n=90), react-isd=0.570 [0.558, 0.582] (n=90), rpisd-agent=0.451 [0.443, 0.460] (n=90)
conditional (>=1 objective): addie-agent=0.586 (n=90), alignmentgraph-isd=0.832 (n=90), baseline=0.566 (n=88), dick-carey-agent=0.557 (n=90), eduplanner=0.598 (n=87), react-isd=0.570 (n=90), rpisd-agent=0.451 (n=90)

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| baseline | 90 | +0.2693 | [+0.2565, +0.2824] | 1.332e-15 | 9.326e-15 |
| react-isd | 90 | +0.2614 | [+0.2487, +0.2736] | 1.332e-15 | 9.326e-15 |
| dick-carey-agent | 90 | +0.2750 | [+0.2632, +0.2865] | 1.332e-15 | 9.326e-15 |
| addie-agent | 90 | +0.2460 | [+0.2335, +0.2584] | 1.332e-15 | 9.326e-15 |
| rpisd-agent | 90 | +0.3802 | [+0.3695, +0.3905] | 1.332e-15 | 9.326e-15 |
| eduplanner | 90 | +0.2399 | [+0.2248, +0.2551] | 1.332e-15 | 9.326e-15 |

#### objective_activity_similarity [correspondence]
mean [bootstrap CI95] per agent: addie-agent=0.505 [0.495, 0.514] (n=90), alignmentgraph-isd=0.678 [0.671, 0.684] (n=90), baseline=0.572 [0.560, 0.583] (n=90), dick-carey-agent=0.547 [0.539, 0.555] (n=90), eduplanner=0.513 [0.502, 0.524] (n=90), react-isd=0.564 [0.554, 0.574] (n=90), rpisd-agent=0.543 [0.536, 0.550] (n=90)
conditional (>=1 objective): addie-agent=0.505 (n=90), alignmentgraph-isd=0.678 (n=90), baseline=0.576 (n=88), dick-carey-agent=0.547 (n=90), eduplanner=0.519 (n=87), react-isd=0.564 (n=90), rpisd-agent=0.543 (n=90)

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| baseline | 90 | +0.1055 | [+0.0932, +0.1187] | 1.332e-15 | 9.326e-15 |
| react-isd | 90 | +0.1132 | [+0.1039, +0.1228] | 1.332e-15 | 9.326e-15 |
| dick-carey-agent | 90 | +0.1305 | [+0.1220, +0.1392] | 1.332e-15 | 9.326e-15 |
| addie-agent | 90 | +0.1729 | [+0.1634, +0.1831] | 1.332e-15 | 9.326e-15 |
| rpisd-agent | 90 | +0.1348 | [+0.1271, +0.1427] | 1.332e-15 | 9.326e-15 |
| eduplanner | 90 | +0.1642 | [+0.1536, +0.1751] | 1.332e-15 | 9.326e-15 |

#### objective_evaluation_similarity [correspondence]
mean [bootstrap CI95] per agent: addie-agent=0.586 [0.573, 0.599] (n=90), alignmentgraph-isd=0.811 [0.800, 0.822] (n=90), baseline=0.516 [0.503, 0.529] (n=90), dick-carey-agent=0.557 [0.546, 0.568] (n=90), eduplanner=0.584 [0.568, 0.599] (n=90), react-isd=0.550 [0.536, 0.564] (n=90), rpisd-agent=0.458 [0.450, 0.466] (n=90)
conditional (>=1 objective): addie-agent=0.586 (n=90), alignmentgraph-isd=0.811 (n=90), baseline=0.520 (n=88), dick-carey-agent=0.557 (n=90), eduplanner=0.590 (n=87), react-isd=0.550 (n=90), rpisd-agent=0.458 (n=90)

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| baseline | 90 | +0.2948 | [+0.2800, +0.3096] | 1.332e-15 | 9.326e-15 |
| react-isd | 90 | +0.2607 | [+0.2459, +0.2754] | 1.332e-15 | 9.326e-15 |
| dick-carey-agent | 90 | +0.2540 | [+0.2418, +0.2659] | 1.332e-15 | 9.326e-15 |
| addie-agent | 90 | +0.2251 | [+0.2122, +0.2379] | 1.332e-15 | 9.326e-15 |
| rpisd-agent | 90 | +0.3529 | [+0.3423, +0.3634] | 1.332e-15 | 9.326e-15 |
| eduplanner | 90 | +0.2269 | [+0.2103, +0.2437] | 1.332e-15 | 9.326e-15 |

#### assessment_objective_similarity [correspondence] — diagnostic, direction not one-way-good
mean [bootstrap CI95] per agent: addie-agent=0.544 [0.533, 0.555] (n=90), alignmentgraph-isd=0.693 [0.682, 0.704] (n=90), baseline=0.475 [0.467, 0.482] (n=90), dick-carey-agent=0.570 [0.558, 0.582] (n=90), eduplanner=0.475 [0.467, 0.483] (n=90), react-isd=0.454 [0.442, 0.465] (n=90), rpisd-agent=0.395 [0.388, 0.402] (n=90)
conditional (>=1 objective): addie-agent=0.544 (n=90), alignmentgraph-isd=0.693 (n=90), baseline=0.474 (n=88), dick-carey-agent=0.570 (n=90), eduplanner=0.475 (n=87), react-isd=0.454 (n=90), rpisd-agent=0.395 (n=90)

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| baseline | 90 | +0.2187 | [+0.2086, +0.2288] | 1.332e-15 | 9.326e-15 |
| react-isd | 90 | +0.2397 | [+0.2289, +0.2507] | 1.332e-15 | 9.326e-15 |
| dick-carey-agent | 90 | +0.1232 | [+0.1116, +0.1343] | 1.332e-15 | 9.326e-15 |
| addie-agent | 90 | +0.1493 | [+0.1396, +0.1587] | 1.332e-15 | 9.326e-15 |
| rpisd-agent | 90 | +0.2984 | [+0.2876, +0.3087] | 1.332e-15 | 9.326e-15 |
| eduplanner | 90 | +0.2184 | [+0.2076, +0.2288] | 1.332e-15 | 9.326e-15 |

#### objective_cognitive_congruence [cognitive]
mean [bootstrap CI95] per agent: addie-agent=0.598 [0.561, 0.634] (n=90), alignmentgraph-isd=0.918 [0.903, 0.933] (n=90), baseline=0.662 [0.634, 0.690] (n=90), dick-carey-agent=0.795 [0.771, 0.818] (n=90), eduplanner=0.690 [0.661, 0.717] (n=90), react-isd=0.747 [0.714, 0.777] (n=90), rpisd-agent=0.473 [0.444, 0.504] (n=90)
conditional (>=1 objective): addie-agent=0.598 (n=90), alignmentgraph-isd=0.918 (n=90), baseline=0.662 (n=88), dick-carey-agent=0.795 (n=90), eduplanner=0.691 (n=87), react-isd=0.747 (n=90), rpisd-agent=0.473 (n=90)

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| baseline | 90 | +0.2559 | [+0.2211, +0.2907] | 1.599e-14 | 3.197e-14 |
| react-isd | 90 | +0.1712 | [+0.1371, +0.2076] | 3.743e-12 | 7.486e-12 |
| dick-carey-agent | 90 | +0.1229 | [+0.0942, +0.1525] | 1.655e-10 | 4.964e-10 |
| addie-agent | 90 | +0.3199 | [+0.2815, +0.3590] | 2.220e-15 | 9.326e-15 |
| rpisd-agent | 90 | +0.4444 | [+0.4111, +0.4785] | 1.332e-15 | 9.326e-15 |
| eduplanner | 90 | +0.2279 | [+0.1957, +0.2605] | 1.599e-14 | 3.264e-14 |

#### porter_mean [cognitive]
mean [bootstrap CI95] per agent: addie-agent=0.367 [0.352, 0.383] (n=90), alignmentgraph-isd=0.458 [0.446, 0.470] (n=90), baseline=0.305 [0.295, 0.316] (n=90), dick-carey-agent=0.393 [0.377, 0.410] (n=90), eduplanner=0.348 [0.335, 0.362] (n=90), react-isd=0.286 [0.274, 0.297] (n=90), rpisd-agent=0.286 [0.273, 0.300] (n=90)
conditional (>=1 objective): addie-agent=0.367 (n=90), alignmentgraph-isd=0.458 (n=90), baseline=0.306 (n=88), dick-carey-agent=0.393 (n=90), eduplanner=0.348 (n=87), react-isd=0.286 (n=90), rpisd-agent=0.286 (n=90)

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| baseline | 90 | +0.1531 | [+0.1363, +0.1703] | 1.332e-15 | 9.326e-15 |
| react-isd | 90 | +0.1728 | [+0.1573, +0.1883] | 1.332e-15 | 9.326e-15 |
| dick-carey-agent | 90 | +0.0650 | [+0.0462, +0.0836] | 9.257e-09 | 1.851e-08 |
| addie-agent | 90 | +0.0911 | [+0.0744, +0.1074] | 1.132e-12 | 2.830e-12 |
| rpisd-agent | 90 | +0.1721 | [+0.1553, +0.1896] | 1.332e-15 | 9.326e-15 |
| eduplanner | 90 | +0.1101 | [+0.0911, +0.1287] | 2.478e-13 | 4.956e-13 |

#### webb_bloom_consistency [cognitive]
mean [bootstrap CI95] per agent: addie-agent=0.591 [0.559, 0.623] (n=90), alignmentgraph-isd=0.866 [0.853, 0.878] (n=90), baseline=0.515 [0.493, 0.535] (n=90), dick-carey-agent=0.765 [0.740, 0.790] (n=90), eduplanner=0.669 [0.648, 0.689] (n=90), react-isd=0.621 [0.598, 0.643] (n=90), rpisd-agent=0.446 [0.418, 0.474] (n=90)
conditional (>=1 objective): addie-agent=0.591 (n=90), alignmentgraph-isd=0.866 (n=90), baseline=0.512 (n=88), dick-carey-agent=0.765 (n=90), eduplanner=0.667 (n=87), react-isd=0.621 (n=90), rpisd-agent=0.446 (n=90)

| baseline | n | mean diff | 95% CI | p_holm | p_panel |
|---|---|---|---|---|---|
| baseline | 90 | +0.3510 | [+0.3280, +0.3744] | 1.332e-15 | 9.326e-15 |
| react-isd | 90 | +0.2450 | [+0.2208, +0.2692] | 1.332e-15 | 9.326e-15 |
| dick-carey-agent | 90 | +0.1004 | [+0.0710, +0.1300] | 2.434e-08 | 2.434e-08 |
| addie-agent | 90 | +0.2745 | [+0.2421, +0.3089] | 1.332e-15 | 9.326e-15 |
| rpisd-agent | 90 | +0.4195 | [+0.3901, +0.4492] | 1.332e-15 | 9.326e-15 |
| eduplanner | 90 | +0.1964 | [+0.1758, +0.2173] | 1.332e-15 | 9.326e-15 |

### Interaction (assessment-alignment DiD, Qwen3.5-9B - Qwen3.5-0.8B)
DiD on the paired objective_assessment_similarity delta (proposed - baseline): value at the largest size (Qwen3.5-9B) minus the smallest (Qwen3.5-0.8B), per scenario; negative = the gap narrows as the model grows (i.e. widens toward small models). Bootstrap CI (10000, seed 42) + Wilcoxon p on the per-scenario DiD values.
- vs baseline: n=70, DiD=-0.4839 CI[-0.5297, -0.4352] p=6.508e-13
- vs react-isd: n=90, DiD=-0.0861 CI[-0.1116, -0.0614] p=4.812e-08
- vs dick-carey-agent: n=90, DiD=-0.1354 CI[-0.1538, -0.1173] p=1.776e-15
- vs addie-agent: n=90, DiD=-0.0102 CI[-0.0301, +0.0097] p=2.818e-01
- vs rpisd-agent: n=90, DiD=+0.0392 CI[+0.0215, +0.0572] p=1.332e-04
- vs eduplanner: n=73, DiD=-0.2515 CI[-0.3040, -0.1977] p=8.591e-11

