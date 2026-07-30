# Bloom lexicon validation

- Dataset: `sample_full.csv` (21380 labeled rows; 18773 single-label, 2607 multi-label)
- Coverage (classifiable): 84.1% (15790 classified, 2983 unclassified)
- Accuracy (on classifiable): 72.7%
- Adjacent accuracy (|pred-gold| <= 1): 86.0%
- Cohen's kappa (on classifiable): 0.657

- Majority-class floor: 27.1%
- Leading-verb ORACLE ceiling: 77.6% (upper bound for any verb-driven classifier on this gold standard)
- Share of the achievable range attained: 90%
- Multi-label rows (2541 scored): hit rate 79.9% (prediction names one of the assigned levels)

## Stratified by gold-label consistency

Public Bloom datasets label the same construction at different levels (e.g. "Compare X and Y" appearing as both Understand and Analyze). *Purity* = the share of rows sharing a leading verb that carry that verb's most common label; low purity is gold-label noise, which no classifier can fit. Agreement on the consistent subset is the honest read of the instrument.

| min purity | rows | accuracy | kappa |
|---|---|---|---|
| >= 0% | 18773 | 72.7% | 0.657 |
| >= 60% | 14981 | 74.6% | 0.666 |
| >= 70% | 11333 | 81.0% | 0.756 |
| >= 80% | 10555 | 81.9% | 0.768 |
| >= 90% | 7485 | 86.5% | 0.820 |
| >= 100% | 994 | 66.2% | 0.499 |

| gold \ pred | Remember | Understand | Apply | Analyze | Evaluate | Create |
|---|---|---|---|---|---|---|
| Remember | 609 | 15 | 39 | 19 | 5 | 23 |
| Understand | 300 | 2091 | 956 | 74 | 48 | 314 |
| Apply | 118 | 228 | 3947 | 150 | 24 | 276 |
| Analyze | 102 | 156 | 225 | 1358 | 20 | 93 |
| Evaluate | 42 | 388 | 78 | 71 | 1630 | 60 |
| Create | 42 | 53 | 168 | 141 | 75 | 1852 |

Levels (revised taxonomy): Remember, Understand, Apply, Analyze, Evaluate, Create = 1..6.
