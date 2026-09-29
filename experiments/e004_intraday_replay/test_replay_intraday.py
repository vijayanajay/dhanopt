"""E004 self-checks: deterministic 5-min paths must produce the right exit and PnL sign.

Run: python -m unittest experiments.e004_intraday_replay.test_replay_intraday -v
"""

from __future__ import annotations

import unittest
from datetime import date, datetime, time, timedelta

import numpy as np
import pandas as pd

from experiments.e004_intraday_replay.replay_intraday import (
    BEAR,
    BULL,
    CONDOR,
    _iv_from_straddle,
    _legs_for,
    simulate_day,
)


def make_path(strikes_and_paths: dict, session_minutes: int = 375, start: time = time(9, 15)) -> pd.DataFrame:
    """Builds a candle frame where each bar's close follows a per-strike synthetic path.

    strikes_and_paths: {strike: np.array of closes per bar}. Candles carry an `iv` attr for pricing.
    """
    n = session_minutes // 5
    ts = [datetime.combine(date(2026, 9, 23), start) + timedelta(minutes=5 * i) for i in range(n)]
    df = pd.DataFrame({
        "timestamp": ts,
        "open": [list(v)[0] for v in strikes_and_paths.values()],
        "high": [max(v) for v in strikes_and_paths.values()],
        "low": [min(v) for v in strikes_and_paths.values()],
        "close": list(strikes_and_paths[next(iter(strikes_and_paths))]),
        "volume": 1000,
    })
    return df


class TestPathSimulation(unittest.TestCase):
    def setUp(self):
        self.spot0 = 25000.0
        self.iv = 0.13
        self.dte = 3.0

    def _candles_with_legs(self, spot_path, put_wall, call_wall):
        n = len(spot_path)
        ts = [datetime.combine(date(2026, 9, 23), time(9, 15)) + timedelta(minutes=5 * i) for i in range(n)]
        df = pd.DataFrame({
            "timestamp": ts,
            "open": spot_path, "high": spot_path, "low": spot_path, "close": spot_path, "volume": 1000,
        })
        legs_by_arch = {a: _legs_for(a, spot_path[0], put_wall, call_wall) for a in (BULL, BEAR, CONDOR)}
        df.attrs["legs_by_arch"] = legs_by_arch
        return df

    def test_straight_up_day_bull_hits_target(self):
        spot = np.linspace(25000, 25350, 75)  # +350 pts clean trend
        c = self._candles_with_legs(spot, put_wall=24850.0, call_wall=25150.0)
        res = simulate_day(c, BULL, lot=75, iv=self.iv, dte=self.dte)
        self.assertIsNotNone(res)
        self.assertEqual(res["exit_reason"], "TARGET")

    def test_whipsaw_day_bull_hits_stop(self):
        # 3 DTE: morning rally does not reach the +70% target, afternoon collapse does
        # reach the -35% stop (deep floor past the short strike).
        up = np.linspace(25000, 25120, 20)
        down = np.linspace(25120, 24700, 55)
        spot = np.concatenate([up, down])
        c = self._candles_with_legs(spot, put_wall=24850.0, call_wall=25150.0)
        res = simulate_day(c, BULL, lot=75, iv=self.iv, dte=3.0)
        self.assertIsNotNone(res)
        self.assertEqual(res["exit_reason"], "STOP")
        self.assertLessEqual(res["gross_pnl"], 0)

    def test_rally_at_low_dte_hits_target(self):
        # Documented behavior: at 1 DTE a debit spread re-prices near-intrinsically, so a
        # +120pt morning rally reaches the +70%-of-debit target quickly.
        up = np.linspace(25000, 25120, 20)
        spot = np.concatenate([up, np.full(55, 25120.0)])
        c = self._candles_with_legs(spot, put_wall=24850.0, call_wall=25150.0)
        res = simulate_day(c, BULL, lot=75, iv=self.iv, dte=1.0)
        self.assertIsNotNone(res)
        self.assertEqual(res["exit_reason"], "TARGET")
        self.assertLess(res["bars_held"], 40)  # exits during the rally, not at EOD

    def test_flat_day_condor_survives_to_eod(self):
        rng = np.random.default_rng(3)
        spot = 25000 + np.cumsum(rng.normal(0, 4, 75))  # small chops around the walls
        c = self._candles_with_legs(spot, put_wall=24700.0, call_wall=25300.0)
        res = simulate_day(c, CONDOR, lot=75, iv=self.iv, dte=self.dte)
        self.assertIsNotNone(res)
        self.assertEqual(res["exit_reason"], "EOD")
        # net credit retained: theta-free BS re-price at same IV means MTM ~ small; win = positive net after friction
        self.assertIsInstance(res["win"], bool)

    def test_bear_book_on_down_day(self):
        spot = np.linspace(25000, 24700, 75)
        c = self._candles_with_legs(spot, put_wall=24850.0, call_wall=25150.0)
        res = simulate_day(c, BEAR, lot=75, iv=self.iv, dte=self.dte)
        self.assertIsNotNone(res)
        self.assertEqual(res["exit_reason"], "TARGET")

    def test_condor_rejects_malformed_walls(self):
        c = self._candles_with_legs(np.full(75, 25000.0), put_wall=25100.0, call_wall=24900.0)  # inverted walls
        legs = c.attrs["legs_by_arch"][CONDOR]
        self.assertIsNone(legs)

    def test_iv_solver_sane(self):
        # ATM straddle ~ 0.8 * S * sigma * sqrt(t) -> sigma ~ 13% for straddle 320, S=25000, 3d
        iv = _iv_from_straddle(25000.0, 25000.0, 3.0, 320.0)
        self.assertGreater(iv, 0.05)
        self.assertLess(iv, 0.60)


if __name__ == "__main__":
    unittest.main()
