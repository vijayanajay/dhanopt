"""E015 tests: combined-book arithmetic consistency over the frozen artifacts."""

import unittest

from experiments.e015_book_combo.combo import run_combo


class TestBookCombo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.combined, cls.metrics = run_combo()

    def test_combined_total_equals_sum_of_books(self):
        combined = self.metrics["combined_book"]["total_net_pnl"]
        e011 = self.metrics["books"]["e011_vrp_straddle"]["total_net_pnl"]
        e013 = self.metrics["books"]["e013_pin_iron_fly"]["total_net_pnl"]
        self.assertAlmostEqual(combined, e011 + e013, places=1)

    def test_daily_rows_internally_consistent(self):
        df = self.combined
        self.assertTrue((df["net_pnl"] - (df["e011_pnl"] + df["e013_pnl"])).abs().max() < 1e-6)
        self.assertTrue(df["n_books"].isin([1, 2]).all())
        self.assertEqual(int((df["n_books"] == 2).sum()), self.metrics["overlap"]["overlap_sessions"])

    def test_margin_breaches_only_on_stacked_days(self):
        breaches = self.combined[self.combined["margin_breach_ub"]]
        self.assertTrue((breaches["n_books"] == 2).all())
        self.assertEqual(len(breaches), self.metrics["capital"]["overlap_days_breached_ub"])

    def test_overlap_vs_independent_expectation_reported(self):
        ov = self.metrics["overlap"]
        self.assertEqual(ov["overlap_sessions"], len(set(self.combined[self.combined["n_books"] == 2]["date"])))
        # Sanity: observed overlap is within 3x of the independent expectation (frozen data).
        self.assertLess(ov["overlap_sessions"], 3 * ov["expected_overlap_if_independent"])


if __name__ == "__main__":
    unittest.main()
