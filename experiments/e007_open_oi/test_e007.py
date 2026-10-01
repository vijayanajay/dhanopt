"""Self-checks: gate-0 building blocks — opening-OI walls come from the 09:15 bar's
per-strike OI, and the opening-wall gate stands down on days the frozen book (day-t
EOD walls) would have traded. Synthetic chains, no API."""
from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import pandas as pd

from experiments.e007_open_oi.build_book import _opening_walls, trade_day
from experiments.e005_theta_condor.test_paper_trade import _candles, _row

D = date(2026, 10, 6)


def _opening_entry(pe_walls: dict, ce_walls: dict) -> dict:
    """opening chain in fetch_open_oi's schema; strikes without opening bars get oi_open=None."""
    opening = []
    for st, oi in pe_walls.items():
        opening.append({"strike": float(st), "side": "PE", "oi_open": oi,
                        "open_price": 50.0, "first_hm": "09:15", "oi_first": None})
    for st, oi in ce_walls.items():
        opening.append({"strike": float(st), "side": "CE", "oi_open": oi,
                        "open_price": 50.0, "first_hm": "09:15", "oi_first": None})
    return {"date": str(D), "status": "OK", "spot_open_api": 24100.0, "opening": opening}


def _day_chain() -> pd.DataFrame:
    # Day-t chain: breached call wall 24200 (open 100, close 60), wing 24350 (40, 5),
    # plus put side for completeness.
    return pd.DataFrame([
        _row(24000, "PE", 400, 60, 20), _row(23850, "PE", 400, 10, 1),
        _row(24200, "CE", 800, 100, 60), _row(24350, "CE", 800, 40, 5),
    ])


class TestOpeningWalls(unittest.TestCase):
    def test_walls_are_argmax_opening_oi(self):
        e = _opening_entry({23850: 900, 24000: 500, 23700: None}, {24200: 500, 24350: 10})
        put_w, call_w, n_oi, n_all = _opening_walls(e)
        self.assertEqual(put_w, 23850.0)   # max OI, not closest to spot
        self.assertEqual(call_w, 24200.0)
        self.assertEqual(n_oi, 4)          # the None strike is excluded from the argmax
        self.assertEqual(n_all, 5)

    def test_no_oi_on_a_side_is_no_chain(self):
        e = _opening_entry({23850: None}, {24200: 500})
        put_w, call_w, _, _ = _opening_walls(e)
        self.assertIsNone(put_w)
        self.assertIsNone(call_w)


class TestOpeningWallGate(unittest.TestCase):
    def test_opening_breach_trades_and_agrees_with_frozen(self):
        # Opening walls put 24000 / call 24200; day opens 24250 ABOVE the call wall.
        e = _opening_entry({24000: 500, 23850: 10}, {24200: 500, 24350: 10})
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "day.parquet"
            _day_chain().to_parquet(p)
            with mock.patch("experiments.e007_open_oi.build_book.load_intraday_candles",
                            return_value=_candles(24250, 24230, 24180)):
                r = trade_day(D, e, pd.read_parquet(p), _candles(24250, 24230, 24180), "call")
        self.assertEqual(r["signal"], "TRADE")
        self.assertEqual(r["side"], "call")
        self.assertEqual(r["wall"], 24200.0)
        self.assertEqual(r["wing"], 24350.0)
        self.assertEqual(r["credit_pts"], 60.0)
        self.assertTrue(r["agree_frozen"])

    def test_valid_opening_structure_stands_down_on_a_frozen_breach_day(self):
        # Same opening walls, but the day opens BETWEEN them: the live gate stands down
        # even though the frozen (day-t EOD wall) book traded this date.
        e = _opening_entry({24000: 500, 23850: 10}, {24200: 500, 24350: 10})
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "day.parquet"
            _day_chain().to_parquet(p)
            with mock.patch("experiments.e007_open_oi.build_book.load_intraday_candles",
                            return_value=_candles(24100, 24105, 24120)):
                r = trade_day(D, e, pd.read_parquet(p), _candles(24100, 24105, 24120), "put")
        self.assertEqual(r["signal"], "STANDDOWN")
        self.assertFalse(r["agree_frozen"])
        self.assertEqual(r["net_pnl"], 0.0)


if __name__ == "__main__":
    unittest.main()
