# Split distribution reports

Stratification evidence for the subsets this study reports on. They live here
rather than in the benchmark because they describe splits the benchmark does
not keep — `scenarios/.gitignore` excludes `test_*` and `train_*`, so the
derived subsets are reproduced from the committed corpus with seed 42 rather
than stored.

Each report shows the domain × difficulty matrix actually achieved, which is
what makes "stratified" checkable rather than asserted, and for `test_30` the
disjointness from the tuning split — a scenario seen while tuning is no longer
held out.

`train_10` gets a report for the opposite reason: it is the one split that is
NOT stratified over the full grid. Ten scenarios cannot cover thirty cells, so
it covers ten of them, and its report is what states which ten. It is a
cost-calibration set whose results never enter the paper; the report exists so
the gap between its name and the word "stratified" is on the record rather than
assumed away.

Regenerate the splits themselves with:

```bash
./isd-exp data split test-90        # test    -> test_90
./isd-exp data split tune-10        # train   -> train_10
./isd-exp data split ablation-30    # test_90 -> test_30, disjoint from train_10
```

That writes a `<name>_metadata.json` beside each subset carrying the same
matrix in machine-readable form; these Markdown reports are the human-readable
rendering kept from when the splits were first cut.
