"""Inferential statistics: SciPy where SciPy is exact, one exact routine where it is not.

Every number the paper reports passes through this module, so it is written to
be checkable rather than clever:

* **SciPy for everything it computes exactly.** The bootstrap interval
  (``scipy.stats.bootstrap``, BCa) and the descriptive rank correlations
  (``spearmanr``, ``kendalltau`` tau-b). The bootstrap is seeded, so the same
  input gives the same interval on any machine with the same SciPy, and
  :func:`software` records which SciPy that was.
* **One routine of our own: the Wilcoxon signed-rank p.** Judge scores are
  discrete, so paired differences carry tied ranks and zeros, and SciPy has no
  exact path for that case: ``method="exact"`` assumes untied ranks and
  silently returns a wrong p, ``"auto"`` falls back to the normal
  approximation, and the exact permutation route enumerates all 2**n sign
  flips, which is out of reach at n = 30. :func:`wilcoxon_signed_rank`
  computes the same conditional permutation null by the shift algorithm of
  Streitberg & Roehmel (1986) in O(n^3) time, and ``tests/test_stats.py``
  checks it against SciPy's full enumeration, ties included, to 1e-9.
* **Holm and the rank-biserial r** are a step-down product and a ratio of rank
  sums; SciPy carries neither, and both are checked on worked examples.

Paired differences are settled to ``TIE_DECIMALS`` decimals before ranking, so
two differences that are equal up to floating-point noise (a mean of three
runs minus another) are one tie, and a difference of 1e-15 is a zero.
"""

from __future__ import annotations

import math
import warnings
from typing import Callable, Optional, Sequence

import numpy as np
import scipy
from scipy import stats as sps

#: Bootstrap resamples, and the seed that makes an interval reproducible.
N_BOOT = 10000
BOOT_SEED = 42
#: The interval every bootstrap in the pool reports.
BOOT_METHOD = "BCa"

#: Exact Wilcoxon null up to this many non-zero differences; the normal
#: approximation beyond. Covers every scenario count the experiments use
#: (test_30, test_90) with room to spare; the DP holds n(n+1) probabilities.
EXACT_WILCOXON_N_MAX = 500

#: Decimals a paired difference is rounded to before ties and zeros are read.
#: Far below any score's resolution (LLM judge scores have two decimals, panel
#: signals are means of cosines) and far above float noise.
TIE_DECIMALS = 9


def software() -> dict[str, str]:
    """The library versions the statistics were computed with."""
    return {"scipy": scipy.__version__, "numpy": np.__version__}


def _settle(values: Sequence[float]) -> list[float]:
    # ``+ 0.0`` turns a rounded -0.0 into 0.0.
    return [round(float(x), TIE_DECIMALS) + 0.0 for x in values]


def _nonzero(diffs: Sequence[float]) -> list[float]:
    return [x for x in _settle(diffs) if x != 0]


def wilcoxon_signed_rank(diffs: list[float]) -> tuple[float, float, int]:
    """Two-sided Wilcoxon signed-rank (zeros discarded). Returns
    (W_plus, p_value, n_effective).

    For n_effective <= EXACT_WILCOXON_N_MAX the p-value is EXACT under the
    conditional null: every assignment of signs to the observed (tie-averaged)
    ranks is equally likely. Tie-averaged ranks are multiples of 0.5, so the
    null of the doubled positive-rank sum is built by the shift algorithm
    (Streitberg & Roehmel 1986): one convolution with {0, rank} per difference,
    each sign with probability 1/2. Beyond that n the normal approximation
    with tie-corrected variance is used (SciPy's ``method="asymptotic"``)."""
    d = _nonzero(diffs)
    n = len(d)
    if n == 0:
        return 0.0, 1.0, 0
    ranks = sps.rankdata([abs(x) for x in d])
    w_plus = float(sum(r for r, x in zip(ranks, d) if x > 0))

    if n > EXACT_WILCOXON_N_MAX:
        p = sps.wilcoxon(d, zero_method="wilcox", correction=False,
                         method="asymptotic").pvalue
        return w_plus, float(p), n

    doubled = [int(round(2 * r)) for r in ranks]
    total = sum(doubled)
    prob = np.zeros(total + 1)
    prob[0] = 1.0
    reach = 0
    for r in doubled:
        nxt = 0.5 * prob
        nxt[r:reach + r + 1] += 0.5 * prob[:reach + 1]
        prob, reach = nxt, reach + r
    w2 = int(round(2 * w_plus))
    lo, hi = min(w2, total - w2), max(w2, total - w2)
    p = prob[:lo + 1].sum() + prob[hi:].sum()
    if lo == hi:
        p -= prob[lo]  # the central point was counted in both tails
    return w_plus, float(min(1.0, p)), n


def rank_biserial(diffs: list[float]) -> float:
    """Matched-pairs rank-biserial correlation r = (W+ - W-) / (W+ + W-),
    over the same non-zero differences the Wilcoxon test ranks."""
    d = _nonzero(diffs)
    n = len(d)
    if n == 0:
        return 0.0
    w_plus, _, _ = wilcoxon_signed_rank(d)
    total = n * (n + 1) / 2
    return (2 * w_plus - total) / total


def bootstrap_ci(values: Sequence, statistic: Optional[Callable] = None, *,
                 n_boot: int = N_BOOT, seed: int = BOOT_SEED) -> tuple[float, float]:
    """95% BCa bootstrap interval of ``statistic`` (the mean by default).

    ``values`` are resampled with replacement. A ``statistic`` other than the
    mean receives the resampled list. Degenerate input -- one value, or every
    value equal -- has no sampling spread and collapses to the point estimate.
    """
    vals = list(values)
    if not vals:
        return float("nan"), float("nan")
    if statistic is None:
        data = np.asarray(vals, dtype=float)
        estimate = float(data.mean())
        degenerate = len(vals) < 2 or bool(np.all(data == data[0]))

        def fn(sample, axis=-1):
            return np.mean(sample, axis=axis)
        vectorized = True
    else:
        estimate = float(statistic(vals))
        index = np.arange(len(vals))
        data = index
        degenerate = len(vals) < 2

        def fn(sample):
            return statistic([vals[int(i)] for i in sample])
        vectorized = False
    if degenerate:
        return estimate, estimate
    with warnings.catch_warnings():
        # A sample with no spread in the jackknife leaves BCa undefined; SciPy
        # warns (numpy divides by zero) and returns NaN, handled below.
        warnings.simplefilter("ignore", sps.DegenerateDataWarning)
        warnings.simplefilter("ignore", RuntimeWarning)
        res = sps.bootstrap((data,), fn, n_resamples=n_boot, vectorized=vectorized,
                            confidence_level=0.95, method=BOOT_METHOD,
                            rng=np.random.default_rng(seed))
    lo, hi = float(res.confidence_interval.low), float(res.confidence_interval.high)
    if math.isnan(lo) or math.isnan(hi):
        return estimate, estimate
    return lo, hi


def holm_correct(pvalues: list[float]) -> list[float]:
    """Holm step-down adjusted p-values, in the input order."""
    order = sorted(range(len(pvalues)), key=lambda i: pvalues[i])
    m = len(pvalues)
    adjusted: list[float] = [1.0] * m
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvalues[idx]))
        adjusted[idx] = running
    return adjusted


def _constant(values: Sequence[float]) -> bool:
    return len(set(values)) < 2


def spearman_rho(xs: list[float], ys: list[float]) -> float:
    """Spearman rank correlation (average ranks for ties). NaN below n = 3 or
    when either vector is constant."""
    if len(xs) < 3 or _constant(xs) or _constant(ys):
        return float("nan")
    return float(sps.spearmanr(xs, ys).statistic)


def kendall_tau_b(xs: list[float], ys: list[float]) -> float:
    """Kendall's tau-b (ties corrected in both margins).

    Reported next to Spearman because the cross-encoder agreement is computed
    over the agent vector (n = 7), where Spearman is noisy; tau-b is the
    defensible small-n rank statistic and is the one prose should quote.
    """
    if len(xs) < 3 or _constant(xs) or _constant(ys):
        return float("nan")
    return float(sps.kendalltau(xs, ys, variant="b").statistic)


def paired(diffs: list[float]) -> dict:
    """What every paired comparison reports: the two-sided Wilcoxon test, the
    BCa interval of the mean difference and the rank-biserial r."""
    if not diffs:
        return {"n": 0}
    w, p, n_eff = wilcoxon_signed_rank(diffs)
    lo, hi = bootstrap_ci(diffs)
    return {"n": len(diffs), "n_effective_nonzero": n_eff,
            "mean_diff": sum(diffs) / len(diffs), "ci95": [lo, hi],
            "wilcoxon_w_plus": w, "p_raw": p, "rank_biserial_r": rank_biserial(diffs)}


def describe(diffs: list[float]) -> dict:
    """A difference estimated and not tested: its mean and BCa interval."""
    if not diffs:
        return {"n": 0}
    lo, hi = bootstrap_ci(diffs)
    return {"n": len(diffs), "mean_diff": sum(diffs) / len(diffs), "ci95": [lo, hi]}
