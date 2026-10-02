"""Unit tests for E012 Volatility Skew and 1x2 Ratio Spread Engine."""

from datetime import date, datetime, timedelta
import unittest
import numpy as np
import pandas as pd

from core.pricing import bs_put, delta_pe
from experiments.e012_skew_ratio.skew import invert_option_iv, load_or_compute_skew
from experiments.e012_skew_ratio.replay_skew import simulate_skew_session


class TestE012Skew(unittest.TestCase):
    def test_single_option_iv_inversion(self):
        """Inverting Black-Scholes put price returns the input volatility."""
        spot = 24000.0
        strike = 23500.0
        iv_true = 0.18
        dte = 5.0

        t = dte / 365.0
        p = bs_put(spot, strike, iv_true, t)
        iv_inv = invert_option_iv(spot, strike, p, dte, is_call=False)
        self.assertAlmostEqual(iv_true, iv_inv, places=2)

    def test_skew_strict_shift1_discipline(self):
        """Verify Day t Skew signal uses strictly t-1 metrics."""
        df_skew = load_or_compute_skew()
        sub = df_skew.dropna(subset=["skew_25d", "skew_25d_t1"]).head(10)
        for i in range(1, len(sub)):
            prev_skew = sub.iloc[i - 1]["skew_25d"]
            curr_shifted_skew = sub.iloc[i]["skew_25d_t1"]
            self.assertAlmostEqual(prev_skew, curr_shifted_skew, places=5)

    def test_invalid_strike_ordering_rejected(self):
        """Put ratio spread requires strike_long > strike_short > strike_wing."""
        candles = pd.DataFrame([{
            "timestamp": datetime(2026, 1, 15, 9, 15) + timedelta(minutes=5 * i),
            "open": 24000.0, "high": 24050.0, "low": 23950.0, "close": 24000.0, "volume": 1000
        } for i in range(72)])

        # Bad order: strike_short > strike_long
        res = simulate_skew_session(
            trade_date=date(2026, 1, 15),
            candles=candles,
            strike_long=23500.0,
            strike_short=23800.0,
            strike_wing=23000.0,
            atm_iv=0.15,
            dte_days=4.0,
        )
        self.assertIsNone(res)

    def test_ratio_spread_path_execution(self):
        """Simulate session returns valid PnL, exit reason, and friction."""
        candles = pd.DataFrame([{
            "timestamp": datetime(2026, 1, 15, 9, 15) + timedelta(minutes=5 * i),
            "open": 24000.0, "high": 24020.0, "low": 23980.0, "close": 24000.0, "volume": 1000
        } for i in range(72)])

        res = simulate_skew_session(
            trade_date=date(2026, 1, 15),
            candles=candles,
            strike_long=23800.0,
            strike_short=23500.0,
            strike_wing=23000.0,
            atm_iv=0.15,
            dte_days=4.0,
        )
        self.assertIsNotNone(res)
        self.assertIn(res["exit_reason"], ["TARGET", "STOP", "EOD"])
        self.assertIn("net_pnl", res)
        self.assertGreater(res["friction"], 0.0)


if __name__ == "__main__":
    unittest.main()
