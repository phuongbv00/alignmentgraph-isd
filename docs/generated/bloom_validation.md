# Bloom axis validation — lexicon (sensitivity arm), rule-based

- Provenance: corpus = EDM2022CLO, the 21,380 expert-labelled learning objectives released by Li et al. (EDM 2022); split = the full labelled set as supplied, with no split held back. Measured file: `EDM2022CLO/data/sample_full.csv` (21380 labelled rows: 18773 single-label, 2607 multi-label).

## Lexicon arm (Anderson & Krathwohl verb rules) vs gold labels

- Coverage (classifiable): 84.1% (15790 classified, 2983 unclassified)
- Accuracy (on classifiable): 72.7%
- Adjacent accuracy (|pred-gold| <= 1): 86.0%
- Cohen's kappa (on classifiable): 0.657

- Majority-class floor: 27.1%
- First-token oracle: 77.6% — the best attainable by mapping each leading token to one fixed level, i.e. a ceiling for token-keyed rules such as this lexicon. It is NOT a bound on classifiers that read the whole text.
- Lexicon accuracy within the floor-to-oracle range: 90% (this share is meaningful for the lexicon only, because the oracle bounds token-keyed rules only)
- Multi-label rows (2541 scored): hit rate 79.9% (prediction names one of the assigned levels)

## Lexicon arm stratified by gold-label consistency

Public Bloom datasets label the same construction at different levels (e.g. "Compare X and Y" appearing as both Understand and Analyze). *Purity* = the share of rows sharing a leading token that carry that token's most common label; low purity is gold-label noise, which no classifier can fit. The mid-purity strata (60-90%) are the honest read of the instrument; the >= 100% stratum is a small, skewed slice and is read separately — see the note under the table. `rows` is the size of the stratum, `scored` the subset the lexicon does not abstain on; accuracy and kappa are computed over `scored` only.

| min purity | rows | scored | accuracy | kappa |
|---|---|---|---|---|
| >= 0% | 18773 | 15790 | 72.7% | 0.657 |
| >= 60% | 14981 | 12730 | 74.6% | 0.666 |
| >= 70% | 11333 | 9377 | 81.0% | 0.756 |
| >= 80% | 10555 | 8845 | 81.9% | 0.768 |
| >= 90% | 7485 | 6054 | 86.5% | 0.820 |
| >= 100% | 994 | 615 | 66.2% | 0.499 |

Note: the >= 100% stratum does not continue the trend, and is not expected to. Most of its leading-token groups occur only once or twice, so their purity is 1.0 by construction rather than by annotator consistency, while its remaining mass sits on a handful of idiosyncratic verbs. It is therefore not a cleaner subsample of the corpus but a differently composed one, with a shifted gold-level mix, and its accuracy and kappa are not comparable with the rows above. Read the 60-90% rows.

Lexicon confusion matrix (gold rows x lexicon prediction columns, classifiable rows only):

| gold \ pred | Remember | Understand | Apply | Analyze | Evaluate | Create |
|---|---|---|---|---|---|---|
| Remember | 609 | 15 | 39 | 19 | 5 | 23 |
| Understand | 300 | 2091 | 956 | 74 | 48 | 314 |
| Apply | 118 | 228 | 3947 | 150 | 24 | 276 |
| Analyze | 102 | 156 | 225 | 1358 | 20 | 93 |
| Evaluate | 42 | 388 | 78 | 71 | 1630 | 60 |
| Create | 42 | 53 | 168 | 141 | 75 | 1852 |

Levels (revised taxonomy): Remember, Understand, Apply, Analyze, Evaluate, Create = 1..6.
