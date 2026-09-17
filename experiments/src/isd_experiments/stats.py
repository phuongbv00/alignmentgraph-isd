"""Hand-rolled inferential statistics. Standard library only, on purpose.

Every number the paper reports passes through this module, so two properties
matter more than convenience:

* **Determinism.** No numpy, no scipy. A result cannot drift because a
  dependency changed its tie-breaking or its RNG. ``bootstrap_ci`` seeds an
  explicit ``random.Random`` so the same input gives the same interval on any
  machine and any Python version.
* **Exactness at small n.** Both ``wilcoxon_signed_rank`` and
  ``spearman_p_exact`` enumerate the permutation null rather than approximate
  it, because the asymptotic form is anti-conservative exactly where this study
  reads small subgroups.

That the implementations are hand-written is not a gap to be closed by adding
scipy later; scipy is a *test oracle* here (an optional ``[dev]`` dependency)
and ``tests/test_stats.py`` checks these against it to 1e-9 without letting it
into the runtime.
"""

from __future__ import annotations

import itertools
import math
import random
from collections import Counter
from typing import Optional

#: Bootstrap resamples, and the seed that makes an interval reproducible.
N_BOOT = 10000
BOOT_SEED = 42


EXACT_WILCOXON_N_MAX = 25  # exact permutation null up to this n_effective


def wilcoxon_signed_rank(diffs: list[float]) -> tuple[float, float, int]:
    """Two-sided Wilcoxon signed-rank (zeros discarded). Returns
    (W_plus, p_value, n_effective).

    For n_effective <= EXACT_WILCOXON_N_MAX the p-value is EXACT: the full
    sign-flip permutation null of W+ is enumerated by dynamic programming
    over (tie-averaged, doubled-to-integer) ranks. The normal approximation
    is only used beyond that — it is anti-conservative at tiny n (e.g. it
    can print p=0.11 at n=3 where the exact two-sided minimum is 0.25),
    which misled the first ladder report."""
    d = [x for x in diffs if x != 0]
    n = len(d)
    if n == 0:
        return 0.0, 1.0, 0
    absd = sorted((abs(x), i) for i, x in enumerate(d))
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

    if n <= EXACT_WILCOXON_N_MAX:
        # DP over doubled ranks (tie-averaged ranks are multiples of 0.5,
        # so doubling makes them integers). dp[s] = #sign assignments whose
        # positive-rank doubled-sum equals s.
        dranks = [round(2 * r) for r in ranks]
        total = sum(dranks)
        dp = [0] * (total + 1)
        dp[0] = 1
        for r in dranks:
            for s in range(total, r - 1, -1):
                dp[s] += dp[s - r]
        w2 = round(2 * w_plus)
        lo, hi = min(w2, total - w2), max(w2, total - w2)
        count = sum(dp[: lo + 1]) + sum(dp[hi:])
        if lo == hi:
            count -= dp[lo]  # the single central point was counted in both tails
        p = min(1.0, count / (1 << n))
        return w_plus, p, n

    mu = n * (n + 1) / 4
    var = n * (n + 1) * (2 * n + 1) / 24
    cnt = Counter(abs(x) for x in d)
    var -= sum(t**3 - t for t in cnt.values()) / 48
    if var <= 0:
        return w_plus, 1.0, n
    z = (w_plus - mu) / math.sqrt(var)
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    return w_plus, p, n


def bootstrap_ci(diffs: list[float], n_boot: int = N_BOOT, seed: int = BOOT_SEED) -> tuple[float, float]:
    if not diffs:
        return float("nan"), float("nan")
    rng = random.Random(seed)
    n = len(diffs)
    means = sorted(sum(rng.choices(diffs, k=n)) / n for _ in range(n_boot))
    return means[int(0.025 * n_boot)], means[int(0.975 * n_boot) - 1]


def fisher_exact_2x2(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact test p for the 2x2 table [[a, b], [c, d]]
    (sum of hypergeometric probabilities <= that of the observed table)."""
    row1, row2, col1 = a + b, c + d, a + c
    n = row1 + row2

    def p_table(x: int) -> float:
        return (math.comb(row1, x) * math.comb(row2, col1 - x)) / math.comb(n, col1)

    p_obs = p_table(a)
    lo_x = max(0, col1 - row2)
    hi_x = min(col1, row1)
    return min(1.0, sum(p for x in range(lo_x, hi_x + 1)
                        if (p := p_table(x)) <= p_obs * (1 + 1e-12)))


def holm_correct(pvalues: list[float]) -> list[float]:
    order = sorted(range(len(pvalues)), key=lambda i: pvalues[i])
    m = len(pvalues)
    adjusted: list[float] = [1.0] * m
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvalues[idx]))
        adjusted[idx] = running
    return adjusted


def _avg_ranks(vals: list[float]) -> list[float]:
    """Ranks 1..n with ties averaged."""
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    r = [0.0] * len(vals)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def spearman_rho(xs: list[float], ys: list[float]) -> float:
    """Spearman rank correlation with average ranks for ties (stdlib only)."""
    n = len(xs)
    if n < 3:
        return float("nan")
    rx, ry = _avg_ranks(xs), _avg_ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else float("nan")


def kendall_tau_b(xs: list[float], ys: list[float]) -> float:
    """Kendall's tau-b (ties corrected in both margins).

    Reported next to Spearman because the cross-encoder agreement is computed
    over the agent vector (n = 7), where Spearman is noisy; tau-b is the
    defensible small-n rank statistic and is the one prose should quote.
    """
    n = len(xs)
    if n < 3:
        return float("nan")
    concordant = discordant = tx = ty = 0
    for i in range(n):
        for j in range(i + 1, n):
            dx, dy = xs[i] - xs[j], ys[i] - ys[j]
            if dx == 0 and dy == 0:
                tx += 1
                ty += 1
            elif dx == 0:
                tx += 1
            elif dy == 0:
                ty += 1
            elif (dx > 0) == (dy > 0):
                concordant += 1
            else:
                discordant += 1
    n0 = n * (n - 1) / 2
    den = math.sqrt((n0 - tx) * (n0 - ty))
    return (concordant - discordant) / den if den else float("nan")


def spearman_p_exact(xs: list[float], ys: list[float],
                     n_max: int = 8) -> Optional[float]:
    """Two-sided permutation p for Spearman's rho; None when n > n_max.

    Full enumeration of the n! orderings of one vector against the other —
    5040 for the 7-agent ladder, i.e. instant and exact. Same
    exact-null-at-small-n convention as wilcoxon_signed_rank(), and for the
    same reason: an asymptotic approximation is anti-conservative at these n.
    """
    n = len(xs)
    if n < 3 or n > n_max:
        return None
    observed = spearman_rho(xs, ys)
    if observed != observed:  # NaN
        return None
    hits = total = 0
    for perm in itertools.permutations(ys):
        rho = spearman_rho(xs, list(perm))
        total += 1
        if rho == rho and abs(rho) >= abs(observed) - 1e-12:
            hits += 1
    return hits / total if total else None



def rank_biserial(diffs: list[float]) -> float:
    """Matched-pairs rank-biserial correlation r = (W+ - W-) / (W+ + W-)."""
    d = [x for x in diffs if x != 0]
    n = len(d)
    if n == 0:
        return 0.0
    w_plus, _, _ = wilcoxon_signed_rank(d)
    total = n * (n + 1) / 2
    return (2 * w_plus - total) / total


