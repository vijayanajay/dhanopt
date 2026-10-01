"""Self-checks: the paper-trade gate — t-1 walls, signal classification, adverse-fill
stress, and the drift-vs-boundary report. Pure-function + synthetic-parquet level; no
API, no real store."""
from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import pandas as pd

from experiments.e005_theta_condor import paper_trade as pt

D1 = date(2026, 10, 5)   # t-1 session (Monday)
D2 = date(2026, 10, 6)   # decision day (Tuesday, expiry -> dte0 = 0.5)
EXP_T = "06-Oct-2026"    # t-1 chain's expiry, stored in real partitions as %d-%b-%Y
EXP_THU = "08-Oct-2026"


def _candles(spot_open: float, spot_0920: float, spot_close: float, n: int = 75) -> pd.DataFrame:
    path = [spot_0920 + (spot_close - spot_0920) * i / (n - 1) for i in range(n)]
    return pd.DataFrame({"timestamp": pd.date_range("2026-10-06 09:20", periods=n, freq="5min"),
                         "open": [spot_open] + path[1:],
                         "high": [max(x, spot_open) for x in path],
                         "low": [min(x, spot_open) for x in path],
                         "close": path})


def _row(strike, ot, oi, o, c, expiry=EXP_T):
    return dict(symbol="NIFTY", instrument="OPTIDX", option_type=ot, expiry=expiry,
                strike=float(strike), open_interest=float(oi), open=float(o), close=float(c))


def _evaluate(prev_rows, day_rows, candles):
    """Run evaluate_day against synthetic t-1/day partitions and a stub candle store."""
    with tempfile.TemporaryDirectory() as tmp:
        p1 = Path(tmp) / "prev.parquet"
        p2 = Path(tmp) / "day.parquet"
        pd.DataFrame(prev_rows).to_parquet(p1)
        pd.DataFrame(day_rows).to_parquet(p2)
        cal = {D1: p1, D2: p2}
        with mock.patch.object(pt, "load_intraday_candles", return_value=candles):
            return pt.evaluate_day(D2, cal, {D2: D1})


class TestGateSignals(unittest.TestCase):
    def test_valid_structure_stands_down(self):
        # t-1 walls: put 24000 / call 24200; day opens between them -> no trade.
        prev = [_row(24000, "PE", 500, 55, 30), _row(24200, "CE", 500, 55, 30),
                _row(23850, "PE", 10, 8, 1), _row(24350, "CE", 10, 8, 1)]
        day = [_row(24000, "PE", 400, 60, 20), _row(24200, "CE", 400, 60, 20)]
        r = _evaluate(prev, day, _candles(24100, 24105, 24120))
        self.assertEqual(r["signal"], "STANDDOWN")
        self.assertEqual(r["side"], "none")
        self.assertEqual(r["dte0"], 0.5)
        self.assertIsNone(r["credit_pts"])

    def test_call_breach_trades_with_wall_wing_and_stress(self):
        # t-1 call wall 24200; day opens 24250 above it -> SELL 24200 CE / BUY 24350 CE.
        prev = [_row(24000, "PE", 500, 55, 30), _row(24200, "CE", 900, 70, 40),
                _row(23850, "PE", 10, 8, 1), _row(24350, "CE", 10, 8, 1)]
        day = [_row(24000, "PE", 400, 60, 2), _row(23850, "PE", 400, 10, 1),
               _row(24200, "CE", 800, 100, 60), _row(24350, "CE", 800, 40, 5)]
        r = _evaluate(prev, day, _candles(24250, 24230, 24180))
        self.assertEqual(r["signal"], "TRADE")
        self.assertEqual(r["side"], "call")
        self.assertEqual(r["wall"], 24200.0)
        self.assertEqual(r["wing"], 24350.0)
        self.assertEqual(r["put_wall_t1"], 24000.0)
        self.assertEqual(r["credit_pts"], 60.0)
        self.assertEqual(r["lot"], 65)  # current era
        self.assertIn(r["exit_reason"], {"TARGET", "STOP", "EOD"})
        self.assertGreater(r["max_leg_drift"], 0)
        # Adverse-fill stress (sell lower / buy higher) must not help.
        self.assertLess(r["net_pnl_stressed"], r["net_pnl"])

    def test_breach_beyond_dte1_is_held(self):
        prev = [_row(24000, "PE", 500, 55, 30), _row(24200, "CE", 900, 70, 40),
                _row(23850, "PE", 10, 8, 1), _row(24350, "CE", 10, 8, 1)]
        # Day chain has only the Thursday contract -> dte0 = 3.
        day = [_row(24200, "CE", 800, 100, 60, expiry=EXP_THU),
               _row(24350, "CE", 800, 40, 5, expiry=EXP_THU)]
        r = _evaluate(prev, day, _candles(24250, 24230, 24180))
        self.assertEqual(r["signal"], "DTE_HOLD")
        self.assertEqual(r["dte0"], 2.0)  # Tue -> Thu
        self.assertEqual(r["wall"], 24200.0)
        self.assertIsNone(r["credit_pts"])

    def test_missing_wing_open_is_nofill(self):
        prev = [_row(24000, "PE", 500, 55, 30), _row(24200, "CE", 900, 70, 40),
                _row(23850, "PE", 10, 8, 1), _row(24350, "CE", 10, 8, 1)]
        day = [_row(24200, "CE", 800, 100, 60)]  # wing absent -> no observable fill
        r = _evaluate(prev, day, _candles(24250, 24230, 24180))
        self.assertEqual(r["signal"], "NOFILL")


class TestGateReport(unittest.TestCase):
    def test_report_flags_and_stress_aggregate(self):
        rows = pd.DataFrame([
            {"date": "2026-09-01T00:00:00", "signal": "TRADE", "side": "call", "wall": 24000.0,
             "credit_pts": 50.0, "max_leg_drift": 3.0, "exit_reason": "TARGET",
             "net_pnl": 100.0, "net_pnl_stressed": 50.0},
            {"date": "2026-09-02T00:00:00", "signal": "TRADE", "side": "put", "wall": 24300.0,
             "credit_pts": 40.0, "max_leg_drift": 25.0, "exit_reason": "STOP",
             "net_pnl": -4000.0, "net_pnl_stressed": -4500.0},
            {"date": "2026-09-03T00:00:00", "signal": "STANDDOWN", "side": "none", "wall": None,
             "credit_pts": None, "max_leg_drift": None, "exit_reason": None,
             "net_pnl": None, "net_pnl_stressed": None},
        ])
        rep = pt.gate_report(rows, gate_weeks=4)
        self.assertEqual(rep["n_trades"], 2)
        self.assertEqual(rep["net"], -3900.0)
        self.assertEqual(rep["net_stressed"], -4450.0)
        self.assertEqual(rep["max_leg_drift_pts"]["max"], 25.0)
        self.assertFalse(rep["within_12x_boundary"])   # 25 >= 18
        self.assertFalse(rep["within_stage2_trigger"])
        self.assertEqual(rep["gate_window"]["n_trades"], 2)


if __name__ == "__main__":
    unittest.main()
