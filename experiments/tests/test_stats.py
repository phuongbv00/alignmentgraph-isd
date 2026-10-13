"""The statistics every paper number passes through.

Most of them are SciPy (see stats.py); what is tested here is the CONTRACT
the pool relies on -- seeding, degenerate input, tie handling, the shape of
what is returned -- and, for the one routine of our own, correctness:

* **Wilcoxon exact null.** Checked against SciPy's full enumeration of the
  sign flips (``PermutationMethod(n_resamples=inf)``) with tied ranks and
  zeros, which is the case SciPy's own exact path does not cover, and against
  ``method="exact"`` where there are no ties.
* **Holm and rank-biserial.** Worked examples and invariants.
* **paired / describe.** The two row shapes every comparison reports.
"""

from __future__ import annotations

import math
import random

import numpy as np
import pytest
import scipy.stats as sps

from isd_experiments import stats


def _judge_like(rng: random.Random, n: int, shift: float = 0.4) -> list[float]:
    """Paired differences on a half-point grid: many ties, some zeros."""
    return [round(rng.gauss(shift, 1.2) * 2) / 2 for _ in range(n)]


# ── Wilcoxon signed-rank ─────────────────────────────────────────────────────

class TestWilcoxon:
    def test_zeros_are_discarded_and_reported(self):
        w, p, n = stats.wilcoxon_signed_rank([0.0, 1.0, 2.0, 0.0, 3.0])
        assert n == 3, "n_effective counts the non-zero differences only"
        assert w == 6.0

    def test_all_zero_is_the_null(self):
        assert stats.wilcoxon_signed_rank([0.0, 0.0, 0.0]) == (0.0, 1.0, 0)

    def test_empty(self):
        assert stats.wilcoxon_signed_rank([]) == (0.0, 1.0, 0)

    def test_exact_minimum_at_n3(self):
        """The docstring's own claim: the exact two-sided p bottoms out at 0.25.

        This is the case that motivated the exact path -- the normal
        approximation returns ~0.11 here, and that number reached a report.
        """
        _, p, _ = stats.wilcoxon_signed_rank([1.0, 2.0, 3.0])
        assert p == pytest.approx(0.25)

    def test_exact_asymptotic_boundary(self):
        """The exact null covers every scenario count the experiments use;
        only beyond EXACT_WILCOXON_N_MAX does the approximation take over."""
        assert stats.EXACT_WILCOXON_N_MAX >= 90
        rng = random.Random(0)
        n = stats.EXACT_WILCOXON_N_MAX + 1
        diffs = [round(rng.uniform(-2, 2), 1) or 0.1 for _ in range(n)]
        _, p, n_eff = stats.wilcoxon_signed_rank(diffs)
        expected = sps.wilcoxon(diffs, method="asymptotic", correction=False).pvalue
        assert n_eff == n
        assert p == pytest.approx(expected, abs=1e-9)

    @pytest.mark.parametrize("seed", range(5))
    def test_matches_scipy_exact_without_ties(self, seed):
        rng = random.Random(seed)
        diffs = [rng.uniform(-3, 3) for _ in range(30)]
        _, p, _ = stats.wilcoxon_signed_rank(diffs)
        assert p == pytest.approx(sps.wilcoxon(diffs, method="exact").pvalue, abs=1e-9)

    @pytest.mark.parametrize("seed", range(8))
    def test_matches_full_enumeration_with_ties_and_zeros(self, seed):
        """The regime of judge scores, and the reason this routine is ours:
        SciPy's exact path ignores ties, so the reference is its permutation
        test over all 2**n sign flips -- feasible here at n <= 16."""
        diffs = _judge_like(random.Random(seed), 18)
        nonzero = [x for x in diffs if x != 0][:16]
        assert len({abs(x) for x in nonzero}) < len(nonzero), "the case must carry ties"
        _, p, _ = stats.wilcoxon_signed_rank(nonzero)
        method = sps.PermutationMethod(n_resamples=np.inf)
        assert p == pytest.approx(sps.wilcoxon(nonzero, method=method).pvalue, abs=1e-9)

    def test_float_noise_is_a_tie_and_not_a_difference(self):
        """A mean of runs minus another lands 1e-16 away from an equal value;
        that must rank as one tie, and a near-zero must drop out."""
        a = (0.1 + 0.2) - 0.3          # 5.55e-17, mathematically 0
        noisy = [0.3, 0.1 + 0.2, -0.3, 1.0, a]
        clean = [0.3, 0.3, -0.3, 1.0, 0.0]
        assert stats.wilcoxon_signed_rank(noisy) == stats.wilcoxon_signed_rank(clean)
        assert stats.rank_biserial(noisy) == stats.rank_biserial(clean)


# ── bootstrap ────────────────────────────────────────────────────────────────

class TestBootstrapCI:
    def test_reproducible_across_calls(self):
        diffs = [0.5, -1.0, 2.0, 0.25, -0.75, 1.5]
        assert stats.bootstrap_ci(diffs) == stats.bootstrap_ci(diffs)

    def test_seed_is_what_makes_it_reproducible(self):
        rng = random.Random(11)
        diffs = [rng.gauss(0.5, 1.0) for _ in range(90)]
        assert stats.bootstrap_ci(diffs, seed=1) != stats.bootstrap_ci(diffs, seed=2)

    def test_is_scipys_bca_interval(self):
        rng = random.Random(5)
        diffs = [rng.gauss(0.5, 1.0) for _ in range(30)]
        res = sps.bootstrap((np.asarray(diffs),), np.mean, n_resamples=stats.N_BOOT,
                            method="BCa", rng=np.random.default_rng(stats.BOOT_SEED))
        assert stats.BOOT_METHOD == "BCa"
        assert stats.bootstrap_ci(diffs) == pytest.approx(
            (res.confidence_interval.low, res.confidence_interval.high), abs=1e-12)

    def test_custom_statistic_resamples_the_items(self):
        """The trend slope resamples scenario ids and recomputes a statistic
        over them; the interval must bracket the point estimate."""
        rng = random.Random(9)
        values = {f"S{i}": rng.gauss(2.0, 1.0) for i in range(40)}
        ids = sorted(values)

        def mean_of(subset):
            return sum(values[s] for s in subset) / len(subset)
        lo, hi = stats.bootstrap_ci(ids, mean_of, n_boot=2000)
        assert lo < mean_of(ids) < hi

    def test_default_seed_and_resamples_are_pinned(self):
        assert (stats.BOOT_SEED, stats.N_BOOT) == (42, 10000)

    def test_degenerate_input_collapses_to_a_point(self):
        lo, hi = stats.bootstrap_ci([2.0] * 20)
        assert lo == hi == pytest.approx(2.0)
        assert stats.bootstrap_ci([3.5]) == (3.5, 3.5)

    def test_empty_is_nan_not_a_crash(self):
        lo, hi = stats.bootstrap_ci([])
        assert math.isnan(lo) and math.isnan(hi)

    def test_interval_brackets_the_mean(self):
        rng = random.Random(7)
        diffs = [rng.gauss(1.0, 0.5) for _ in range(60)]
        lo, hi = stats.bootstrap_ci(diffs)
        assert lo < sum(diffs) / len(diffs) < hi


# ── Holm ─────────────────────────────────────────────────────────────────────

class TestHolm:
    def test_family_of_one_is_the_identity(self):
        assert stats.holm_correct([0.03]) == [pytest.approx(0.03)]

    def test_worked_example(self):
        # m=3: 0.01*3=0.03, 0.02*2=0.04, 0.03*1=0.03 -> monotone max -> 0.04.
        assert stats.holm_correct([0.01, 0.02, 0.03]) == pytest.approx([0.03, 0.04, 0.04])

    def test_monotone_and_never_below_raw(self):
        raw = [0.001, 0.2, 0.04, 0.9, 0.03]
        adj = stats.holm_correct(raw)
        assert all(a >= r - 1e-12 for a, r in zip(adj, raw))
        ordered = [adj[i] for i in sorted(range(len(raw)), key=lambda i: raw[i])]
        assert ordered == sorted(ordered), "adjusted p must not decrease with rank"

    def test_capped_at_one(self):
        assert max(stats.holm_correct([0.5, 0.6, 0.7])) <= 1.0

    def test_preserves_input_order(self):
        adj = stats.holm_correct([0.9, 0.001])
        assert adj[1] < adj[0], "the adjusted value must stay with its own hypothesis"


# ── rank correlations ────────────────────────────────────────────────────────

class TestRankCorrelations:
    def test_perfect_and_reversed(self):
        xs = [1, 2, 3, 4, 5]
        assert stats.spearman_rho(xs, xs) == pytest.approx(1.0)
        assert stats.spearman_rho(xs, xs[::-1]) == pytest.approx(-1.0)
        assert stats.kendall_tau_b(xs, xs) == pytest.approx(1.0)
        assert stats.kendall_tau_b(xs, xs[::-1]) == pytest.approx(-1.0)

    def test_too_few_points_is_nan(self):
        assert math.isnan(stats.spearman_rho([1, 2], [2, 1]))
        assert math.isnan(stats.kendall_tau_b([1, 2], [2, 1]))

    def test_all_tied_is_nan_not_zero(self):
        """No dispersion means no correlation is defined -- not that it is 0."""
        assert math.isnan(stats.spearman_rho([1, 1, 1, 1], [1, 2, 3, 4]))
        assert math.isnan(stats.kendall_tau_b([1, 1, 1, 1], [1, 1, 1, 1]))

    def test_tau_b_corrects_for_ties(self):
        # 10,20,20,30 against 1,2,3,4: tau-b = 5 / sqrt(5 * 6)
        assert stats.kendall_tau_b([10, 20, 20, 30], [1, 2, 3, 4]) == pytest.approx(
            5 / math.sqrt(30))


# ── the two shapes every comparison reports ──────────────────────────────────

class TestPairedAndDescribe:
    def test_paired_carries_the_test_the_interval_and_the_effect_size(self):
        diffs = [0.5, 1.0, -0.25, 2.0, 1.5, 0.75, -0.5, 1.25]
        row = stats.paired(diffs)
        assert set(row) == {"n", "n_effective_nonzero", "mean_diff", "ci95",
                            "wilcoxon_w_plus", "p_raw", "rank_biserial_r"}
        assert row["mean_diff"] == pytest.approx(sum(diffs) / len(diffs))
        assert row["p_raw"] == stats.wilcoxon_signed_rank(diffs)[1]
        assert row["ci95"] == list(stats.bootstrap_ci(diffs))

    def test_describe_estimates_and_does_not_test(self):
        row = stats.describe([1.0, 2.0, 4.0])
        assert set(row) == {"n", "mean_diff", "ci95"}

    def test_empty_is_n_zero(self):
        assert stats.paired([]) == {"n": 0}
        assert stats.describe([]) == {"n": 0}


# ── effect size ──────────────────────────────────────────────────────────────

class TestRankBiserial:
    def test_bounds(self):
        assert stats.rank_biserial([1.0, 2.0, 3.0]) == pytest.approx(1.0)
        assert stats.rank_biserial([-1.0, -2.0, -3.0]) == pytest.approx(-1.0)

    def test_all_zero_is_zero(self):
        assert stats.rank_biserial([0.0, 0.0]) == 0.0

    def test_sign_agrees_with_the_mean_difference(self):
        """A table printing a positive mean beside a negative effect size is
        the kind of contradiction a reader catches and an author does not."""
        rng = random.Random(3)
        for _ in range(20):
            diffs = [rng.uniform(-1, 3) for _ in range(15)]
            m = sum(diffs) / len(diffs)
            r = stats.rank_biserial(diffs)
            if abs(m) > 0.3:
                assert (m > 0) == (r > 0)
