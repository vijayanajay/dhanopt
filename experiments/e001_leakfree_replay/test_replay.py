"""E001 self-check: pins the leak-free replay semantics on synthetic bhavcopy days.

Run: python -m unittest experiments.e001_leakfree_replay.test_replay -v
"""

from __future__ import annotations

import math
import unittest
from datetime import date

import pandas as pd

from experiments.common.lots import lot_for_date
from experiments.e001_leakfree_replay.replay import (
    BEAR,
    BULL,
    CONDOR,
    replay_day,
)

EXP = "28-Jan-2028"
OFFSET = 150.0


def tv(m: float) -> float:
    """Time value by OTM distance m (m>0 means strike is m pts OTM). No look-ahead: depends only on distance."""
    if m <= 0:
        return 60.0
    if m <= 150:
        return 20.0
    if m <= 300:
        return 10.0
    return 5.0


def make_day(prev_close: float, open_: float, close: float, put_oi: float = 500_000.0, call_oi: float = 500_000.0) -> pd.DataFrame:
    """Builds a synthetic normalized bhavcopy day with a simple deterministic option chain.

    Option prices: intrinsic + tv(otm_distance) — same schedule for entry (open) and exit (close).
    """
    rows = []
    rows.append({
        "symbol": "NIFTY", "instrument": "FUTIDX", "expiry": EXP, "strike": 0.0, "option_type": "",
        "open": open_, "high": max(open_, close) + 20, "low": min(open_, close) - 20, "close": close,
        "settle_price": close, "contracts": 1000, "open_interest": 0, "change_in_oi": 0, "trade_date": "05-Jan-2028",
    })
    for strike in range(24000, 26100, 50):
        call_o = max(open_ - strike, 0.0) + tv(strike - open_)
        call_c = max(close - strike, 0.0) + tv(strike - close)
        put_o = max(strike - open_, 0.0) + tv(open_ - strike)
        put_c = max(strike - close, 0.0) + tv(close - strike)
        put_w = put_oi if strike == 24800 else 1000.0
        call_w = call_oi if strike == 25300 else 1000.0
        rows.append({
            "symbol": "NIFTY", "instrument": "OPTIDX", "expiry": EXP, "strike": float(strike),
            "option_type": "CE", "open": call_o, "high": call_o, "low": call_c, "close": call_c,
            "settle_price": call_c, "contracts": 100, "open_interest": call_w, "change_in_oi": 0,
            "trade_date": "05-Jan-2028",
        })
        rows.append({
            "symbol": "NIFTY", "instrument": "OPTIDX", "expiry": EXP, "strike": float(strike),
            "option_type": "PE", "open": put_o, "high": put_o, "low": put_c, "close": put_c,
            "settle_price": put_c, "contracts": 100, "open_interest": put_w, "change_in_oi": 0,
            "trade_date": "05-Jan-2028",
        })
    return pd.DataFrame(rows)


class TestLots(unittest.TestCase):
    def test_era_table(self):
        self.assertEqual(lot_for_date(date(2021, 6, 1)), 75)   # pre-Jul-2021: 75
        self.assertEqual(lot_for_date(date(2021, 7, 1)), 50)   # FAOP47854 era: 50
        self.assertEqual(lot_for_date(date(2024, 4, 25)), 50)
        self.assertEqual(lot_for_date(date(2024, 4, 26)), 25)  # Apr-2024 review: 25
        self.assertEqual(lot_for_date(date(2024, 11, 19)), 25)
        self.assertEqual(lot_for_date(date(2024, 11, 20)), 75)
        self.assertEqual(lot_for_date(date(2025, 12, 29)), 75)
        self.assertEqual(lot_for_date(date(2025, 12, 30)), 65)
        self.assertEqual(lot_for_date(date(2026, 9, 1)), 65)


class TestReplaySemantics(unittest.TestCase):
    def test_decision_uses_prior_day_not_today(self):
        """A UP signal from t-1 must not flip if day-t itself closes down (no look-ahead)."""
        # t-1 was a big up day (prev_pct = +0.5%), day-t opens 25000, closes 24800 (down).
        day_df = make_day(prev_close=24875.0, open_=25000.0, close=24800.0)
        rows = {r["archetype"]: r for r in replay_day(day_df, prev_pct=0.5)}
        self.assertEqual(rows[BULL]["signal"], "UP")
        self.assertTrue(rows[BULL]["selected_by_rule"])
        self.assertFalse(rows[BEAR]["selected_by_rule"])

    def test_bull_spread_pnl_math(self):
        """Bull spread bought at open, exited at close, net of friction (fixture math pinned)."""
        day_df = make_day(prev_close=24875.0, open_=25000.0, close=25100.0)
        rows = {r["archetype"]: r for r in replay_day(day_df, prev_pct=0.5)}
        bull = rows[BULL]
        qty = lot_for_date(date(2028, 1, 5))  # 65
        # long ATM call (25000): open = 0 + tv(0) = 60; close = 100 + tv(-100) = 160
        # short 150-OTM call (25150): open = 0 + tv(150) = 20; close = 0 + tv(50) = 20
        expected_gross = ((160.0 - 20.0) - (60.0 - 20.0)) * qty  # 100 * 65 = 6500
        self.assertEqual(bull["gross_pnl"], round(expected_gross, 2))
        self.assertLess(bull["net_pnl"], bull["gross_pnl"])         # friction subtracted
        self.assertTrue(bull["win"])

    def test_all_three_archetypes_produced(self):
        day_df = make_day(prev_close=24875.0, open_=25000.0, close=25010.0)
        rows = replay_day(day_df, prev_pct=0.5)
        self.assertEqual({r["archetype"] for r in rows}, {BULL, BEAR, CONDOR})
        self.assertTrue(all(r["simulated"] for r in rows))

    def test_flat_signal_selects_condor(self):
        day_df = make_day(prev_close=24875.0, open_=25000.0, close=25005.0)
        rows = {r["archetype"]: r for r in replay_day(day_df, prev_pct=0.1)}
        self.assertEqual(rows[CONDOR]["signal"], "FLAT")
        self.assertTrue(rows[CONDOR]["selected_by_rule"])

    def test_first_day_has_no_signal(self):
        day_df = make_day(prev_close=24875.0, open_=25000.0, close=25010.0)
        rows = replay_day(day_df, prev_pct=None)
        self.assertTrue(all(r["signal"] == "NONE" for r in rows))
        self.assertFalse(any(r["selected_by_rule"] for r in rows))


if __name__ == "__main__":
    unittest.main()
