# Bloom lexicon validation

- Dataset: `eval_split.csv` (3755 labeled rows; 3755 single-label, 0 multi-label)
- Coverage (classifiable): 83.4% (3133 classified, 622 unclassified)
- Accuracy (on classifiable): 72.3%
- Adjacent accuracy (|pred-gold| <= 1): 86.0%
- Cohen's kappa (on classifiable): 0.650

- Majority-class floor: 27.1%
- Leading-verb ORACLE ceiling: 78.6% (upper bound for any verb-driven classifier on this gold standard)
- Share of the achievable range attained: 88%


## Stratified by gold-label consistency

Public Bloom datasets label the same construction at different levels (e.g. "Compare X and Y" appearing as both Understand and Analyze). *Purity* = the share of rows sharing a leading verb that carry that verb's most common label; low purity is gold-label noise, which no classifier can fit. Agreement on the consistent subset is the honest read of the instrument.

| min purity | rows | accuracy | kappa |
|---|---|---|---|
| >= 0% | 3755 | 72.3% | 0.650 |
| >= 60% | 3077 | 73.5% | 0.651 |
| >= 70% | 2341 | 78.9% | 0.729 |
| >= 80% | 2182 | 80.7% | 0.749 |
| >= 90% | 1502 | 82.3% | 0.761 |
| >= 100% | 737 | 79.4% | 0.644 |

| gold \ pred | Remember | Understand | Apply | Analyze | Evaluate | Create |
|---|---|---|---|---|---|---|
| Remember | 119 | 2 | 11 | 3 | 3 | 6 |
| Understand | 66 | 394 | 205 | 16 | 13 | 58 |
| Apply | 17 | 38 | 803 | 25 | 6 | 56 |
| Analyze | 18 | 29 | 50 | 270 | 4 | 15 |
| Evaluate | 8 | 81 | 17 | 12 | 315 | 12 |
| Create | 7 | 7 | 39 | 30 | 15 | 363 |

Levels (revised taxonomy): Remember, Understand, Apply, Analyze, Evaluate, Create = 1..6.

## Bloom axis — transformer (primary) vs lexicon (sensitivity arm)

Checkpoint: `models/bloom-bert-edm2022`. Both arms scored on the same 3755 single-label rows.

| arm | coverage | accuracy | kappa vs gold |
|---|---|---|---|
| lexicon (A&K rules, sweep arm) | 83.4% | 72.3% | 0.650 |
| transformer (EDM2022CLO, PRIMARY) | 100.0% | 94.1% | 0.926 |

- Arm-vs-arm agreement (rows both classify, n=3133): 73.5% raw, kappa 0.665
- The transformer never abstains, so its coverage is 100% by construction; the two arms are NOT equalised.
- If this CSV is the corpus the transformer was fine-tuned on, its numbers are IN-SAMPLE and not comparable. Use the `eval_split.csv` written next to the checkpoint.
