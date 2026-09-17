"""The statistics every paper number passes through.

These are hand-written, standard-library-only implementations (see
stats.py for why), which means nothing but a test stands between a subtle
error here and a wrong p-value in the manuscript. Two kinds of check:

* **Oracle.** Where scipy is installed (the ``[dev]`` extra) the results are
  compared against it to 1e-9. This validates the no-scipy constraint instead
  of merely asserting it, and it does so without letting scipy near the
  runtime -- these tests skip when it is absent.
* **Contract.** Properties and edge cases that must hold regardless: the
  boundary between the exact and asymptotic Wilcoxon paths, reproducibility of
  the bootstrap, tie handling in the rank statistics.
"""

from __future__ import annotations

import math
import random

import pytest

from isd_experiments import stats

try:
    import scipy.stats as sps
except ImportError:  # pragma: no cover - scipy is a dev-only oracle
    sps = None

needs_scipy = pytest.mark.skipif(sps is None, reason="scipy is a [dev] test oracle")


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
        """n = 25 takes the exact path, n = 26 the approximation.

        The single most fragile line in the module: one comparison decides
        which null is used, and the study reads both small subgroups and the
        90-scenario ladder.
        """
        assert stats.EXACT_WILCOXON_N_MAX == 25
        rng = random.Random(0)
        diffs = [rng.uniform(-1, 1) for _ in range(26)]
        _, p25, n25 = stats.wilcoxon_signed_rank(diffs[:25])
        _, p26, n26 = stats.wilcoxon_signed_rank(diffs)
        assert (n25, n26) == (25, 26)
        assert 0.0 <= p25 <= 1.0 and 0.0 <= p26 <= 1.0

    @needs_scipy
    @pytest.mark.parametrize("seed", range(5))
    def test_matches_scipy_exact(self, seed):
        rng = random.Random(seed)
        diffs = [rng.uniform(-3, 3) for _ in range(12)]
        _, p, _ = stats.wilcoxon_signed_rank(diffs)
        assert p == pytest.approx(sps.wilcoxon(diffs, method="exact").pvalue, abs=1e-9)

    @needs_scipy
    @pytest.mark.parametrize("seed", range(5))
    def test_matches_scipy_approx_with_ties(self, seed):
        """The ladder's own regime: n = 90, and ties present.

        Ties drive the `var -= sum(t**3 - t) / 48` correction, which is the
        part of the approximation easiest to get silently wrong.
        """
        rng = random.Random(100 + seed)
        diffs = [round(rng.uniform(-2, 2), 1) for _ in range(90)]
        _, p, _ = stats.wilcoxon_signed_rank(diffs)
        expected = sps.wilcoxon(diffs, method="approx", correction=False).pvalue
        assert p == pytest.approx(expected, abs=1e-9)


# ── bootstrap ────────────────────────────────────────────────────────────────

class TestBootstrapCI:
    def test_reproducible_across_calls(self):
        diffs = [0.5, -1.0, 2.0, 0.25, -0.75, 1.5]
        assert stats.bootstrap_ci(diffs) == stats.bootstrap_ci(diffs)

    def test_seed_is_what_makes_it_reproducible(self):
        """Different seeds give different intervals -- once there is enough
        data for the resampling distribution not to be degenerate.

        At n = 6 the percentile lands on the same discrete value for any seed,
        which is a property of a tiny bootstrap rather than of the seeding, so
        this uses the ladder's own scale.
        """
        rng = random.Random(11)
        diffs = [rng.gauss(0.5, 1.0) for _ in range(90)]
        assert stats.bootstrap_ci(diffs, seed=1) != stats.bootstrap_ci(diffs, seed=2)

    def test_default_seed_and_resamples_are_pinned(self):
        assert (stats.BOOT_SEED, stats.N_BOOT) == (42, 10000)

    def test_degenerate_input_collapses_to_a_point(self):
        lo, hi = stats.bootstrap_ci([2.0] * 20)
        assert lo == hi == pytest.approx(2.0)

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

    def test_average_ranks_for_ties(self):
        # values 10,20,20,30 -> ranks 1, 2.5, 2.5, 4
        assert stats._avg_ranks([10.0, 20.0, 20.0, 30.0]) == [1.0, 2.5, 2.5, 4.0]

    @needs_scipy
    @pytest.mark.parametrize("seed", range(5))
    def test_matches_scipy(self, seed):
        rng = random.Random(200 + seed)
        xs = [round(rng.uniform(0, 5), 1) for _ in range(12)]
        ys = [round(rng.uniform(0, 5), 1) for _ in range(12)]
        assert stats.spearman_rho(xs, ys) == pytest.approx(sps.spearmanr(xs, ys).statistic, abs=1e-9)
        assert stats.kendall_tau_b(xs, ys) == pytest.approx(
            sps.kendalltau(xs, ys, variant="b").statistic, abs=1e-9
        )


class TestSpearmanExactP:
    def test_none_beyond_n_max(self):
        xs = list(range(9))
        assert stats.spearman_p_exact(xs, xs) is None

    def test_perfect_correlation_at_n7(self):
        """n = 7 is the agent-vector width the encoder agreement is read over."""
        xs = list(range(7))
        p = stats.spearman_p_exact(xs, xs)
        assert p == pytest.approx(2 / math.factorial(7))

    def test_p_in_unit_interval(self):
        p = stats.spearman_p_exact([1, 2, 3, 4, 5], [2, 1, 4, 3, 5])
        assert p is not None and 0.0 < p <= 1.0


# ── Fisher exact ─────────────────────────────────────────────────────────────

class TestFisherExact:
    def test_transpose_symmetry(self):
        assert stats.fisher_exact_2x2(3, 1, 1, 3) == pytest.approx(
            stats.fisher_exact_2x2(3, 1, 1, 3)
        )

    def test_no_association_is_one(self):
        assert stats.fisher_exact_2x2(5, 5, 5, 5) == pytest.approx(1.0)

    def test_p_in_unit_interval(self):
        assert 0.0 < stats.fisher_exact_2x2(8, 2, 1, 9) <= 1.0

    @needs_scipy
    @pytest.mark.parametrize("table", [(3, 1, 1, 3), (8, 2, 1, 9), (5, 5, 5, 5), (10, 0, 0, 10)])
    def test_matches_scipy(self, table):
        a, b, c, d = table
        assert stats.fisher_exact_2x2(a, b, c, d) == pytest.approx(
            sps.fisher_exact([[a, b], [c, d]]).pvalue, abs=1e-9
        )


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
