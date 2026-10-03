"""E029 tests.

The experiment's whole value is that it refuses the flattering answer, so the
tests are mostly about the refusal:

  - `test_the_two_eras_never_overlap` -- the reason this is not in-sample.
  - `test_f5_is_an_era_detector` -- the trap the selection rule walked past.
  - `test_no_filter_reads_the_outcome` -- gate 6, as an invariant not a report.
  - `test_the_early_era_loses_at_every_fill` -- the finding, pinned.

`run()` reads a CSV artifact, so the whole file runs in about a second.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.e029_era_slices.eras import (
    CONSERVATIVE_PTS_PER_LEG, FILTERS, MODELLED_PTS_PER_LEG, OUTCOME_FIELDS,
    PRE_ENTRY_FIELDS, SELECTION_MIN_N, SELECTION_YEARS, VERDICT_MIN_N, VERDICT_YEARS,
    apply_filter, assert_no_hindsight, bootstrap_p_positive, choose_filter, load_universe,
    null_distribution, run, score, selection_credit_median,
)

_CACHE: dict = {}


def once():
    if "r" not in _CACHE:
        _CACHE["r"] = run()
    return _CACHE["r"]


class TestControl(unittest.TestCase):
    """Gate 0. Nothing below is meaningful if the unfiltered book moved."""

    def test_unfiltered_book_reproduces_e028(self):
        _, m = once()
        c = m["control"]
        self.assertTrue(m["gates"]["0_control_reproduces_e028"]["pass"], m["gates"]["0_control_reproduces_e028"])
        self.assertAlmostEqual(c["unfiltered_at_0.75pts"]["net_pnl"], 45567.74, delta=1.0)
        self.assertAlmostEqual(c["unfiltered_at_2.0pts"]["net_pnl"], -29082.26, delta=1.0)
        self.assertEqual(c["unfiltered_at_0.75pts"]["trades"], 129)

    def test_the_sample_is_the_corrected_one(self):
        """n=129, not e026's 64. This is the whole difference between e026,
        e028 and e029; a silent drop back to 64 would make the early era vanish
        and the experiment meaningless."""
        uni = load_universe()
        self.assertEqual(len(uni.df), 129)
        self.assertEqual(int((uni.df.era == "selection").sum()), 58)
        self.assertEqual(int((uni.df.era == "verdict").sum()), 71)


class TestTheSplit(unittest.TestCase):
    def test_the_two_eras_never_overlap(self):
        uni = load_universe()
        s = set(uni.selection.date)
        v = set(uni.verdict.date)
        self.assertEqual(s & v, set())
        self.assertEqual(max(s) < min(v), True, "selection must be strictly earlier")

    def test_eras_are_the_years_the_prereg_named(self):
        self.assertEqual(SELECTION_YEARS, (2021, 2022, 2023))
        self.assertEqual(VERDICT_YEARS, (2024, 2025, 2026))

    def test_selection_never_scores_itself(self):
        """The structural property that makes arm 2 a verdict. Only checkable
        when a filter was actually carried out of sample."""
        _, m = once()
        if "arms" in m:
            self.assertEqual(m["chosen_filter"]["gate6_selection_era_only"], True)
            self.assertEqual(m["arms"]["B_verdict_era_HELD_OUT"]["trades"] <= 71, True)


class TestFilters(unittest.TestCase):
    def test_no_filter_reads_the_outcome(self):
        """Gate 6 as an invariant. A filter touching `debit_real` or `net_real`
        is the result grading itself."""
        for key, spec in FILTERS.items():
            self.assertEqual(set(spec["uses"]) & OUTCOME_FIELDS, set(), key)
            self.assertEqual(set(spec["uses"]) - PRE_ENTRY_FIELDS, set(), key)

    def test_assert_no_hindsight_actually_raises(self):
        FILTERS["_canary"] = dict(fn=lambda df: df, uses={"net_real"}, why="canary")
        try:
            with self.assertRaises(AssertionError):
                assert_no_hindsight("_canary", load_universe().df)
        finally:
            del FILTERS["_canary"]

    def test_every_filter_is_a_real_subset(self):
        """A filter that returns everything is not a slice; one that returns
        nothing is a bug that looks like a negative result."""
        uni = load_universe()
        cm = selection_credit_median(uni)
        for key in FILTERS:
            sub = apply_filter(uni.df, key, cm)
            self.assertGreater(len(sub), 0, f"{key} returned an empty frame")
            self.assertLess(len(sub), len(uni.df), f"{key} returned the whole book")

    def test_f5_refuses_to_guess_its_threshold(self):
        """F5's median must come from the selection era, passed in. Computing it
        from whatever frame the filter is applied to silently yields n=0 on the
        verdict era -- a bug indistinguishable from a negative result."""
        with self.assertRaises(ValueError):
            apply_filter(load_universe().verdict,
                         "F5_credit_ge_selection_median", None)

    def test_f5_is_an_era_detector(self):
        """The trap PREREG 8 named, pinned so nobody offers it later.

        The selection-era median credit is 102.43 and EVERY 2024-2026 session
        clears it, so F5 does not find a better fly -- it finds the year. A
        filter that is really a date filter will always look brilliant in
        sample and has no holdout to be tested in.
        """
        uni = load_universe()
        cm = selection_credit_median(uni)
        self.assertEqual(len(apply_filter(uni.verdict, "F5_credit_ge_selection_median", cm)),
                         len(uni.verdict))


class TestSelectionRule(unittest.TestCase):
    def test_it_returns_exactly_one_filter_or_none(self):
        uni = load_universe()
        pick = choose_filter(uni.selection, CONSERVATIVE_PTS_PER_LEG, selection_credit_median(uni))
        self.assertEqual(len(pick["survivors"]), len(FILTERS))
        self.assertIn(pick["chosen"], list(FILTERS) + [None])
        if pick["chosen"] is not None:
            chosen = next(s for s in pick["survivors"] if s["key"] == pick["chosen"])
            self.assertTrue(chosen["ok"])
            self.assertGreaterEqual(chosen["n"], SELECTION_MIN_N)
            self.assertGreater(chosen["ev"], 0.0)

    def test_no_filter_qualifies_on_this_data(self):
        """The recorded finding. If this starts failing, the early era has
        changed -- which would be a finding in its own right, so re-read the
        PREREG before celebrating it."""
        _, m = once()
        self.assertIsNone(m["selection_era"]["chosen"])
        self.assertFalse(m["gates"]["1_selection_is_real"]["pass"])
        for s in m["selection_era"]["survivors"]:
            self.assertLess(s["ev"], 0.0, s["key"])

    def test_the_run_is_deterministic(self):
        """Seeded null and bootstrap. A verdict that moves between runs is not
        a verdict."""
        _, a = once()
        _, b = run()
        self.assertEqual(a["verdict"], b["verdict"])
        self.assertEqual(a["selection_era"]["chosen"], b["selection_era"]["chosen"])


class TestTheFinding(unittest.TestCase):
    def test_the_early_era_loses_at_every_fill(self):
        """Not a slippage problem. The early era is dead at the engine's own
        optimistic 0.75 pts/leg as well as at 2.0, so no fill assumption
        rescues it and there is nothing to re-price."""
        uni = load_universe()
        for p in (MODELLED_PTS_PER_LEG, 1.5, CONSERVATIVE_PTS_PER_LEG):
            s = score(uni.selection, p)
            self.assertLess(s["ev_per_trade"], 0.0, f"selection era positive at {p} pts")

    def test_the_late_era_is_positive_at_every_fill(self):
        """The uncomfortable half. Reported because it is true; NOT a slice,
        because the era boundary was chosen by looking at the eras."""
        uni = load_universe()
        for p in (MODELLED_PTS_PER_LEG, 1.5, CONSERVATIVE_PTS_PER_LEG):
            s = score(uni.verdict, p)
            self.assertGreater(s["ev_per_trade"], 0.0, f"verdict era negative at {p} pts")

    def test_the_verdict_is_no_slice(self):
        _, m = once()
        self.assertTrue(m["verdict"].startswith("NO SLICE"), m["verdict"])

    def test_the_era_warning_travels_with_the_artifact(self):
        """The trap must be in the JSON, not only in the README. Anyone who
        opens verdict.json must see why 'trade only 2024+' is not a book."""
        _, m = once()
        self.assertIn("no holdout", m["era_diagnostic"]["warning"])


class TestHonestNull(unittest.TestCase):
    def test_the_null_is_centred_on_the_eras_own_ev(self):
        """A random subset of the held-out era should land near that era's own
        mean. If it does not, the null is measuring something else."""
        uni = load_universe()
        n = 30
        null = null_distribution(uni.verdict, n, CONSERVATIVE_PTS_PER_LEG)
        self.assertEqual(len(null), 500)
        own = score(uni.verdict, CONSERVATIVE_PTS_PER_LEG)["ev_per_trade"]
        self.assertAlmostEqual(float(null.mean()), own, delta=own * 0.5 + 50.0)

    def test_bootstrap_is_bounded(self):
        from experiments.e027_spread_realism.spread_realism import price_book
        uni = load_universe()
        p = bootstrap_p_positive(price_book(uni.verdict, 0.75))
        self.assertGreaterEqual(p, 0.0)
        self.assertLessEqual(p, 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)