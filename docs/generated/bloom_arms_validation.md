# Bloom axis validation — transformer (primary arm) vs lexicon (sensitivity arm)

- Provenance: corpus = EDM2022CLO, the 21,380 expert-labelled learning objectives released by Li et al. (EDM 2022); split = held-out eval split written next to the transformer checkpoint by `evaluator/scripts/train_bloom_6way_classifier.py`; it is a strict subset of the corpus's single-label rows, so the lexicon figures here are nested inside the full-corpus report, not independent of it. Measured file: `isd-agent-benchmark/models/bloom-bert-edm2022/eval_split.csv` (3755 labelled rows: 3755 single-label, 0 multi-label).

## Lexicon arm (Anderson & Krathwohl verb rules) vs gold labels

- Coverage (classifiable): 83.4% (3133 classified, 622 unclassified)
- Accuracy (on classifiable): 72.3%
- Adjacent accuracy (|pred-gold| <= 1): 86.0%
- Cohen's kappa (on classifiable): 0.650

- Majority-class floor: 27.1%
- First-token oracle: 78.6% — the best attainable by mapping each leading token to one fixed level, i.e. a ceiling for token-keyed rules such as this lexicon. It is NOT a bound on classifiers that read the whole text.
- Lexicon accuracy within the floor-to-oracle range: 88% (this share is meaningful for the lexicon only, because the oracle bounds token-keyed rules only)

## Lexicon arm stratified by gold-label consistency

Public Bloom datasets label the same construction at different levels (e.g. "Compare X and Y" appearing as both Understand and Analyze). *Purity* = the share of rows sharing a leading token that carry that token's most common label; low purity is gold-label noise, which no classifier can fit. The mid-purity strata (60-90%) are the honest read of the instrument; the >= 100% stratum is a small, skewed slice and is read separately — see the note under the table. `rows` is the size of the stratum, `scored` the subset the lexicon does not abstain on; accuracy and kappa are computed over `scored` only.

| min purity | rows | scored | accuracy | kappa |
|---|---|---|---|---|
| >= 0% | 3755 | 3133 | 72.3% | 0.650 |
| >= 60% | 3077 | 2606 | 73.5% | 0.651 |
| >= 70% | 2341 | 1914 | 78.9% | 0.729 |
| >= 80% | 2182 | 1768 | 80.7% | 0.749 |
| >= 90% | 1502 | 1180 | 82.3% | 0.761 |
| >= 100% | 737 | 602 | 79.4% | 0.644 |

Note: the >= 100% stratum does not continue the trend, and is not expected to. Most of its leading-token groups occur only once or twice, so their purity is 1.0 by construction rather than by annotator consistency, while its remaining mass sits on a handful of idiosyncratic verbs. It is therefore not a cleaner subsample of the corpus but a differently composed one, with a shifted gold-level mix, and its accuracy and kappa are not comparable with the rows above. Read the 60-90% rows.

Lexicon confusion matrix (gold rows x lexicon prediction columns, classifiable rows only):

| gold \ pred | Remember | Understand | Apply | Analyze | Evaluate | Create |
|---|---|---|---|---|---|---|
| Remember | 119 | 2 | 11 | 3 | 3 | 6 |
| Understand | 66 | 394 | 205 | 16 | 13 | 58 |
| Apply | 17 | 38 | 803 | 25 | 6 | 56 |
| Analyze | 18 | 29 | 50 | 270 | 4 | 15 |
| Evaluate | 8 | 81 | 17 | 12 | 315 | 12 |
| Create | 7 | 7 | 39 | 30 | 15 | 363 |

Levels (revised taxonomy): Remember, Understand, Apply, Analyze, Evaluate, Create = 1..6.

## Bloom axis — transformer (primary arm) vs lexicon (sensitivity arm)

Checkpoint under test: `isd-agent-benchmark/models/bloom-bert-edm2022`. Both arms scored on the same 3755 single-label rows.

| arm | coverage | accuracy | kappa vs gold |
|---|---|---|---|
| lexicon (Anderson & Krathwohl verb rules, sensitivity arm) | 83.4% | 72.3% | 0.650 |
| transformer (BERT-base head fine-tuned on the EDM2022CLO corpus, PRIMARY) | 100.0% | 94.1% | 0.926 |

- Arm-vs-arm agreement (rows both classify, n=3133): 73.5% raw, kappa 0.665. The arms are far from interchangeable, which is what makes the sensitivity axis informative.
- The transformer never abstains, so its coverage is 100% by construction; the two arms are NOT equalised.
- The transformer reuses Li et al.'s *corpus*, not their classifier design: their notebooks yield six independent binary heads or one multi-label sigmoid head, whereas this arm is a single 6-way softmax head, so every text gets exactly one level as the panel requires.
- The first-token oracle reported above (78.6%) bounds rules keyed on the leading token, such as the lexicon; it does not bound this arm, which reads the whole text and scores above it (94.1%).
- Held-out status: this CSV **is** the checkpoint's own `eval_split.csv` (3755 rows), never seen during fine-tuning, so the transformer numbers above are OUT-OF-SAMPLE. Cross-check against the training run's own record (`held_out_metrics.json`): n=3755, accuracy 94.1%, kappa 0.926.
