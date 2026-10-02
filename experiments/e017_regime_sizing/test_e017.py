"""E017 tests: cost decomposition, sizing-rule semantics, cluster-stop machine, risk budget."""

import unittest

import numpy as np
import pandas as pd

from experiments.e017_regime_sizing.sizing import (
    FROZEN,
    FLAT_ENTRY_EXIT,
    FLAT_PER_HEDGE,
    apply_rule,
    breakeven_fraction,
    cluster_stop_series,
    elevated_flags,
    gates,
    load_base,
    scaled_series,
    summarize,
    validate_decomposition,
)


def _sess(net_v, flat, hedge_trades=0):
    """Minimal session frame for the arithmetic functions."""
    n = len(net_v)
    return pd.DataFrame({
        "date": pd.date_range("2021-03-01", periods=n, freq="B").date,
        "hedge_trades": [hedge_trades] * n,
        "net_v": np.asarray(net_v, dtype=float),
        "flat": np.asarray(flat, dtype=float),
    })


class TestDecomposition(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = load_base()

    def test_frozen_total_reproduced(self):
        validate_decomposition(self.df)  # raises on any inconsistency
        self.assertAlmostEqual(float(self.df["net_pnl"].sum()), 743572.25, places=2)

    def test_flat_formula_matches_engine_cost_model(self):
        expect = FLAT_ENTRY_EXIT + FLAT_PER_HEDGE * self.df["hedge_trades"]
        self.assertTrue(np.allclose(self.df["flat"], expect))

    def test_row1_decomposition_pinned_by_hand(self):
        # 2021-03-01, hand-derived from the engine cost model:
        # friction 726.41 = flat 165.20 (94.4 + 23.6*3) + option-var 517.87 + futures 43.34.
        r = self.df.iloc[0]
        self.assertAlmostEqual(float(r["flat"]), 94.4 + 23.6 * r["hedge_trades"], places=6)
        opt_var = r["lot_size"] * (
            r["initial_credit"] * (0.001 + 0.000505 * 1.18 + 0.00003 * 1.18)
            + r["final_debit"] * 0.000505 * 1.18
            + 6.0
        )
        self.assertAlmostEqual(r["friction"] - r["flat"] - opt_var, 43.34, places=2)

    def test_f1_scaling_reproduces_frozen_net(self):
        s = scaled_series(self.df, np.ones(len(self.df)))
        self.assertTrue(np.allclose(s["net_pnl"], self.df["net_pnl"], atol=1e-6))

    def test_base_metrics_match_published_e011(self):
        m = summarize(scaled_series(self.df, np.ones(len(self.df))), "base")
        self.assertAlmostEqual(m["net_ev_per_trade"], 2537.79, places=2)
        self.assertAlmostEqual(m["max_drawdown_inr"], -51274.41, places=2)
        self.assertAlmostEqual(m["sharpe_ratio"], 2.85, places=2)
        self.assertAlmostEqual(m["profit_factor"], 3.99, places=2)


class TestScaling(unittest.TestCase):
    def test_linear_in_size_with_flat_drag(self):
        # CSV row 1: net(1) = 340.79, flat = 165.20 -> net_v = 505.99;
        # net(0.5) = 0.5*net_v - flat = 0.5*net(1) - 0.5*flat = 87.795.
        df = _sess([505.99], [165.20])
        s = scaled_series(df, np.array([0.5]))
        self.assertAlmostEqual(s["net_pnl"].iloc[0], 0.5 * 505.99 - 165.20, places=6)
        self.assertAlmostEqual(s["net_pnl"].iloc[0], 0.5 * 340.79 - 0.5 * 165.20, places=6)

    def test_losses_stay_losses_but_marginal_wins_flip(self):
        # net_v=150, flat=100: win at f=1 (+50) but loss at f=0.5 (-25).
        # (flat fees do not shrink; only the gross+variable part does.)
        df = _sess([150.0, -150.0], [100.0, 100.0])
        s = scaled_series(df, np.array([1.0, 0.5]))
        self.assertGreater(s["net_pnl"].iloc[0], 0)
        self.assertLess(s["net_pnl"].iloc[1], 0)


class TestSizingRule(unittest.TestCase):
    def _rule(self, net_v, flat, elevated, mode="combined"):
        df = _sess(net_v, flat)
        flags = apply_rule(df, pd.Series(elevated), mode=mode)
        return flags, df

    def test_cluster_half_size_after_two_losses_until_win(self):
        # W, L, L, L, W with flat=0 (signs size-invariant).
        flags, _ = self._rule([100, -100, -100, -100, 100], [0] * 5, [False] * 5)
        self.assertEqual(flags["size_fraction"].tolist(), [1.0, 1.0, 1.0, 0.5, 0.5])
        self.assertEqual(flags["cluster_active"].tolist(), [False, False, False, True, True])

    def test_win_resets_cluster(self):
        flags, _ = self._rule([-100, -100, 100, -100], [0] * 4, [False] * 4)
        self.assertEqual(flags["size_fraction"].tolist(), [1.0, 1.0, 0.5, 1.0])

    def test_elevated_regime_flag_halves_independently(self):
        flags, _ = self._rule([100, 100, -100], [0] * 3, [True, False, False])
        self.assertEqual(flags["size_fraction"].tolist(), [0.5, 1.0, 1.0])
        self.assertEqual(flags["regime_elevated"].tolist(), [True, False, False])

    def test_regime_mode_ignores_cluster_and_vice_versa(self):
        flags_r, _ = self._rule([-100, -100], [0] * 2, [False] * 2, mode="regime")
        self.assertEqual(flags_r["size_fraction"].tolist(), [1.0, 1.0])
        flags_c, _ = self._rule([100, 100], [0] * 2, [True, True], mode="cluster")
        self.assertEqual(flags_c["size_fraction"].tolist(), [1.0, 1.0])

    def test_outcome_measured_at_taken_size(self):
        # Marginal win flips to a loss at half size (flat drag), feeding the streak:
        # elevated marginal win (net_v=150, flat=100 -> -25 at f=0.5), then a full loss,
        # so session 3 sits in an active cluster.
        flags, _ = self._rule([150, -100, 100], [100, 0, 0], [True, False, False])
        self.assertEqual(flags["size_fraction"].tolist(), [0.5, 1.0, 0.5])


class TestElevatedFlags(unittest.TestCase):
    def test_trailing_percentile_no_lookahead(self):
        n_flat, n_spike = 40, 10
        sigma = [0.10] * n_flat + [0.50] * n_spike
        dates = pd.date_range("2021-01-04", periods=n_flat + n_spike, freq="B").date
        vdf = pd.DataFrame({"date": dates, "sigma_gk_10d_t1": sigma})
        sessions = pd.DataFrame({"date": dates})
        flags = elevated_flags(sessions, vdf)
        self.assertFalse(bool(flags.iloc[0]))  # warm-up: NaN hurdle -> not elevated
        self.assertFalse(bool(flags.iloc[n_flat - 1]))  # last quiet session
        self.assertTrue(bool(flags.iloc[n_flat]))  # spike vs trailing hurdle
        self.assertTrue(bool(flags.iloc[-1]))

    def test_missing_session_date_raises(self):
        vdf = pd.DataFrame({
            "date": pd.date_range("2021-01-04", periods=40, freq="B").date,
            "sigma_gk_10d_t1": [0.1] * 40,
        })
        sessions = pd.DataFrame({"date": [pd.Timestamp("2030-01-01").date()]})
        with self.assertRaises(AssertionError):
            elevated_flags(sessions, vdf)


class TestClusterStop(unittest.TestCase):
    def test_skip_cooldown_after_k_losses_then_resume(self):
        # L at i1-i2 triggers the stop: i3-i4 skipped (zero PnL), i5 taken.
        df = _sess([100, -100, -100, -100, -100, 100], [0] * 6)
        df["net_pnl"] = df["net_v"] - df["flat"]
        series, taken = cluster_stop_series(df, k=2)
        self.assertEqual(taken.tolist(), [True, True, True, False, False, True])
        self.assertEqual(series.loc[~taken, "net_pnl"].tolist(), [0.0, 0.0])  # flat: no fees

    def test_win_during_cooldown_gap_resets(self):
        df = _sess([-100, -100, 100, 100], [0] * 4)
        df["net_pnl"] = df["net_v"]
        series, taken = cluster_stop_series(df, k=2)
        # losses i0-i1 -> skip i2-i3; both would have been wins but are skipped.
        self.assertEqual(taken.tolist(), [True, True, False, False])


class TestRiskBudget(unittest.TestCase):
    def test_breakeven_fraction_analytic(self):
        # pnl(f): [110f-10, -190f-10]; |maxDD| = 190f+10 -> cap 100 allows f <= 0.4736.
        df = pd.DataFrame({"net_pnl": [100.0, -200.0], "flat": [10.0, 10.0]})
        be = breakeven_fraction(df, cap=100.0)
        self.assertEqual(be["f_star"], 0.473)
        self.assertAlmostEqual(be["max_dd_at_f_star"], -(190 * 0.473 + 10), places=6)
        self.assertAlmostEqual(be["annual_net_at_f_star"], be["total_net_at_f_star"] / FROZEN["years"], places=2)

    def test_breakeven_unreachable_reports_none(self):
        df = pd.DataFrame({"net_pnl": [-5000.0] * 30, "flat": [100.0] * 30})
        be = breakeven_fraction(df, cap=100.0)  # pure-loss book: DD grows as f shrinks
        self.assertIsNone(be["f_star"])

    def test_gates(self):
        ok = gates({"max_drawdown_inr": -15000.0, "net_ev_per_trade": 1500.0, "total_net_pnl": 400000.0})
        self.assertEqual(ok["verdict"], "PASS")
        bad = gates({"max_drawdown_inr": -20000.0, "net_ev_per_trade": 1500.0, "total_net_pnl": 400000.0})
        self.assertFalse(bad["gate1_max_dd_le_16k"])
        self.assertEqual(bad["verdict"], "FAIL")
        ev = gates({"max_drawdown_inr": -15000.0, "net_ev_per_trade": 1000.0, "total_net_pnl": 400000.0})
        self.assertFalse(ev["gate2_ev_ge_1200"])


if __name__ == "__main__":
    unittest.main()
