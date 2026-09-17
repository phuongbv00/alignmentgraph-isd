# Train 10 Distribution Report

Created at: 2026-09-17T17:47:47

## Summary
- Source split: `scenarios/train` (24593 scenarios)
- Target subset: `scenarios/train_10` (10 scenarios)
- Sampling seed: `42`
- Allocation: 1 per (domain × difficulty) cell, then down-sampled to 10
- Coverage: **10 of 30 cells**
- Sampling method: deterministic stratified random sampling within each domain-difficulty cell, then round-robin down-sampling over a seed-shuffled cell order

**This split is NOT a stratified sample of the corpus.** Ten scenarios cannot
cover thirty cells, so ten cells carry one scenario each and twenty carry none.
It exists for cost and budget calibration; its results never enter the paper,
and at n=10 no panel comparison could reach significance under the Holm family
in any case. The two splits the study reports on — `test_90` and `test_30` —
are stratified over the full grid and have their own reports beside this one.

## Allocation Matrix

| Domain | Easy | Moderate | Hard | Total |
|---|---:|---:|---:|---:|
| AI | 1 | 0 | 0 | 1 |
| Business/HR/Admin Support | 0 | 0 | 1 | 1 |
| Education (Teaching & Learning) | 0 | 0 | 0 | 0 |
| Language | 1 | 0 | 0 | 1 |
| Mathematics | 0 | 0 | 1 | 1 |
| Medical/Nursing | 0 | 0 | 0 | 0 |
| Science | 0 | 1 | 1 | 2 |
| Service/Customer Support | 1 | 0 | 1 | 2 |
| Social Studies | 0 | 1 | 0 | 1 |
| Software Development/IT | 0 | 1 | 0 | 1 |
| **Total** | **3** | **3** | **4** | **10** |

## Source Availability Per Cell

| Domain | Easy | Moderate | Hard | Total |
|---|---:|---:|---:|---:|
| AI | 292 | 337 | 351 | 980 |
| Business/HR/Admin Support | 285 | 327 | 365 | 977 |
| Education (Teaching & Learning) | 307 | 370 | 378 | 1055 |
| Language | 1585 | 1649 | 1485 | 4719 |
| Mathematics | 1694 | 1568 | 1379 | 4641 |
| Medical/Nursing | 294 | 349 | 336 | 979 |
| Science | 1586 | 1532 | 1541 | 4659 |
| Service/Customer Support | 299 | 333 | 347 | 979 |
| Social Studies | 1497 | 1538 | 1590 | 4625 |
| Software Development/IT | 275 | 362 | 342 | 979 |
| **Total** | **8114** | **8365** | **8114** | **24593** |

## Variant Type Counts

| Variant type | Count |
|---|---:|
| balance_large_scale | 1 |
| balance_large_scale_v2 | 2 |
| balance_medium_scale | 1 |
| balance_teen_filtered | 1 |
| balance_teen_k12 | 2 |
| context_variant | 2 |
| idld_aligned | 1 |

## Selected Files By Cell

### AI
- Easy: `scenario_bal_medium_0560.json`

### Business/HR/Admin Support
- Hard: `scenario_idld_1144_v.json`

### Language
- Easy: `scenario_bal_large_0015.json`

### Mathematics
- Hard: `scenario_bal_teen_0404.json`

### Science
- Moderate: `scenario_bal_large2_0903.json`
- Hard: `scenario_idld_6367.json`

### Service/Customer Support
- Easy: `scenario_bal_teen_new_0522.json`
- Hard: `scenario_idld_7200_v.json`

### Social Studies
- Moderate: `scenario_bal_teen_0756.json`

### Software Development/IT
- Moderate: `scenario_bal_large2_0110.json`

## Cells With No Scenario

Listed so the gap is on the record rather than inferred from the matrix:

- AI / Moderate
- AI / Hard
- Business/HR/Admin Support / Easy
- Business/HR/Admin Support / Moderate
- Education (Teaching & Learning) / Easy
- Education (Teaching & Learning) / Moderate
- Education (Teaching & Learning) / Hard
- Language / Moderate
- Language / Hard
- Mathematics / Easy
- Mathematics / Moderate
- Medical/Nursing / Easy
- Medical/Nursing / Moderate
- Medical/Nursing / Hard
- Science / Easy
- Service/Customer Support / Moderate
- Social Studies / Easy
- Social Studies / Hard
- Software Development/IT / Easy
- Software Development/IT / Hard
