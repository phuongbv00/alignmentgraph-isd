"""Paired Wilcoxon signed-rank (normal approx, tie-corrected) + Holm correction
+ bootstrap 95% CI of mean paired difference, for alignmentgraph-isd vs each
baseline, per benchmark run, on per-scenario total_score (2-judge avg)."""
import json
import math
import random
from pathlib import Path

RESULTS = Path("/Users/phuongbv/Projects/master-thesis/isd-agent-benchmark/results")
RUNS = {
    "deepseek": RESULTS / "test_90_benchmark_deepseek-v4-flash-nitro_20260630_205456" / "test_90",
    "qwen": RESULTS / "test_90_benchmark_qwen3.5-9b-nitro_20260708_151413" / "test_90",
}
PROPOSED = "alignmentgraph-isd"
BASELINES = ["baseline", "react-isd", "dick-carey-agent", "addie-agent", "rpisd-agent", "eduplanner"]


def load_scores(run_dir: Path) -> dict[str, dict[str, float]]:
    """scenario_id -> agent_id -> total_score"""
    out = {}
    for d in sorted(run_dir.iterdir()):
        rep = d / "comparison_report.json"
        if not rep.exists():
            continue
        data = json.loads(rep.read_text())
        out[d.name] = {
            r["agent_id"]: r["total_score"] for r in data["comparison"]["rankings"]
        }
    return out


def wilcoxon_signed_rank(diffs: list[float]) -> tuple[float, float, int]:
    """Two-sided Wilcoxon signed-rank test, zeros discarded, tie-corrected
    normal approximation. Returns (W_plus, p_value, n_effective)."""
    d = [x for x in diffs if x != 0]
    n = len(d)
    absd = sorted((abs(x), i) for i, x in enumerate(d))
    # average ranks with ties
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and absd[j + 1][0] == absd[i][0]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[absd[k][1]] = avg
        i = j + 1
    w_plus = sum(r for r, x in zip(ranks, d) if x > 0)
    mu = n * (n + 1) / 4
    var = n * (n + 1) * (2 * n + 1) / 24
    # tie correction
    from collections import Counter
    cnt = Counter(abs(x) for x in d)
    var -= sum(t**3 - t for t in cnt.values()) / 48
    z = (w_plus - mu) / math.sqrt(var)
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    return w_plus, p, n


def bootstrap_ci(diffs: list[float], n_boot=10000, seed=42) -> tuple[float, float]:
    rng = random.Random(seed)
    n = len(diffs)
    means = sorted(sum(rng.choices(diffs, k=n)) / n for _ in range(n_boot))
    return means[int(0.025 * n_boot)], means[int(0.975 * n_boot) - 1]


for run_name, run_dir in RUNS.items():
    scores = load_scores(run_dir)
    print(f"\n=== {run_name} ({len(scores)} scenarios) ===")
    results = []
    for b in BASELINES:
        pairs = [
            (s[PROPOSED], s[b]) for s in scores.values() if PROPOSED in s and b in s
        ]
        diffs = [a - x for a, x in pairs]
        mean_d = sum(diffs) / len(diffs)
        w, p, n_eff = wilcoxon_signed_rank(diffs)
        lo, hi = bootstrap_ci(diffs)
        results.append((b, len(pairs), mean_d, lo, hi, p))
    # Holm correction
    order = sorted(range(len(results)), key=lambda i: results[i][5])
    m = len(results)
    holm = [None] * m
    running = 0.0
    for rank, idx in enumerate(order):
        adj = min(1.0, (m - rank) * results[idx][5])
        running = max(running, adj)
        holm[idx] = running
    for (b, npairs, mean_d, lo, hi, p), ph in zip(results, holm):
        print(
            f"{b:18s} n={npairs:2d}  mean diff={mean_d:+6.2f}  "
            f"95% CI [{lo:+6.2f}, {hi:+6.2f}]  p={p:.2e}  p_holm={ph:.2e}"
        )
