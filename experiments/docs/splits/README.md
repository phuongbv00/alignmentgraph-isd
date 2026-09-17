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

Regenerate the splits themselves with:

```bash
./isd-exp data split test-90        # test    -> test_90
./isd-exp data split tune-30        # train   -> train_30
./isd-exp data split ablation-30    # test_90 -> test_30, disjoint from train_30
```

That writes a `<name>_metadata.json` beside each subset carrying the same
matrix in machine-readable form; these Markdown reports are the human-readable
rendering kept from when the splits were first cut.
