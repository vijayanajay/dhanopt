"""E016 tests: adaptive width rule, wing-seam behavior, and frozen-run gates."""

import unittest
from datetime import date

from core.feeds.intraday import load_intraday_candles
from experiments.e011_vrp_delta_hedge.replay_vrp import simulate_session
from experiments.e016_vrp_iron_fly.run_e016 import FROZEN, adaptive_width, run_e016


class TestAdaptiveWidth(unittest.TestCase):
    def test_floor_applies(self):
        # Low vol, short horizon -> floor 150 binds.
        self.assertEqual(adaptive_width(0.08, 1.0, 20000.0), 150.0)

    def test_scales_with_sigma_dte_and_spot(self):
        w1 = adaptive_width(0.20, 5.0, 20000.0)
        w2 = adaptive_width(0.40, 5.0, 20000.0)
        self.assertGreater(w2, w1)
        self.assertGreater(adaptive_width(0.20, 20.0, 20000.0), w1)
        self.assertGreater(adaptive_width(0.20, 5.0, 40000.0), w1)

    def test_fifty_point_grid(self):
        w = adaptive_width(0.234, 7.0, 21347.0)
        self.assertEqual(w % 50.0, 0.0)
        self.assertGreaterEqual(w, FROZEN["width_floor_pts"])


class TestWingSeam(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = date(2021, 3, 1)
        cls.candles = load_intraday_candles(cls.d)
        cls.naked = simulate_session(cls.d, cls.candles, 0.2756277, 6.0)
        cls.fly = simulate_session(cls.d, cls.candles, 0.2756277, 6.0, wing_offset=150.0)

    def test_naked_defaults_unchanged(self):
        self.assertIsNone(self.naked["wing_offset_ce"])
        # Published net for 2021-03-01.
        self.assertAlmostEqual(self.naked["net_pnl"], 340.79, places=1)

    def test_fly_has_four_legs_and_smaller_credit(self):
        self.assertEqual(self.fly["wing_offset_ce"], 150.0)
        self.assertEqual(self.fly["wing_offset_pe"], 150.0)
        self.assertLess(self.fly["initial_credit"], self.naked["initial_credit"])
        # Wings neutralize entry gamma -> fewer or equal hedges on this session.
        self.assertLessEqual(self.fly["hedge_trades"], self.naked["hedge_trades"])

    def test_fly_loss_capped_by_wing_geometry(self):
        # Max theoretical fly loss per session: (W - credit) * lot; realized loss must respect it.
        lot = self.fly["lot_size"]
        max_loss = (150.0 - self.fly["initial_credit"]) * lot
        self.assertLessEqual(self.fly["opt_gross_pnl"], max_loss + 1e-6)


class TestFrozenRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fly_df, cls.naked_df, cls.metrics = run_e016()

    def test_all_sessions_traded(self):
        self.assertEqual(len(self.fly_df), 293)
        self.assertEqual(int(self.fly_df["wing_ce_pts"].isna().sum()), 0)

    def test_gates_structure_and_expected_failures(self):
        gates = self.metrics["gates"]
        for g in ("gate1_max_dd_le_16k", "gate2_ev_ge_500", "gate3_total_ge_40pct_e011"):
            self.assertIn(g, gates)
            self.assertIn("pass", gates[g])
        self.assertFalse(self.metrics["all_gates_pass"])

    def test_naked_baseline_matches_published(self):
        self.assertAlmostEqual(
            self.metrics["e011_naked_published"]["total_net_pnl"], 743572.25, places=1
        )

    def test_width_diagnostics_monotonic_toward_naked(self):
        diag = self.metrics["width_diagnostics"]
        totals = [diag[f"w{w}_pts"]["total_net_pnl"] for w in (100, 150, 200, 250, 300)]
        self.assertTrue(all(b > a for a, b in zip(totals, totals[1:])), f"not monotonic: {totals}")


if __name__ == "__main__":
    unittest.main()
