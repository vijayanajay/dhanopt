"""E002 self-checks: shift discipline, fold construction, matched-count gating.

Run: python -m unittest experiments.e002_regime_models.test_features -v
"""

from __future__ import annotations

import unittest
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from experiments.e002_regime_models.features import (
    FEATURE_COLUMNS,
    attach_labels,
    build_feature_rows,
)
from experiments.e002_regime_models.walkforward import (
    ARCH_KEYS,
    PNL_COLUMNS,
    RULE_TO_ARCH,
    TARGETS,
    _pick_ml_trades,
    gating_simulation,
    make_folds,
)


def _synthetic_day(td: date, open_: float, close: float, pcr: float = 1.0, straddle: float = 160.0) -> pd.DataFrame:
    rows = [{
        "symbol": "NIFTY", "instrument": "FUTIDX", "expiry": "28-Jan-2021", "strike": 0.0, "option_type": "",
        "open": open_, "high": max(open_, close) + 30, "low": min(open_, close) - 30, "close": close,
        "settle_price": close, "contracts": 1000, "open_interest": 0, "change_in_oi": 0,
        "trade_date": td.strftime("%d-%b-%Y"),
    }]
    atm = int(round(close / 50.0) * 50.0)
    for strike in range(atm - 300, atm + 350, 50):
        call_oi = 100.0 if strike != atm + 300 else 500_000.0
        put_oi = 100.0 if strike != atm - 300 else 500_000.0 * pcr
        rows.append({
            "symbol": "NIFTY", "instrument": "OPTIDX", "expiry": "28-Jan-2021", "strike": float(strike),
            "option_type": "CE", "open": straddle / 2, "high": straddle / 2, "low": straddle / 2,
            "close": straddle / 2, "settle_price": straddle / 2, "contracts": 100,
            "open_interest": call_oi, "change_in_oi": 0, "trade_date": td.strftime("%d-%b-%Y"),
        })
        rows.append({
            "symbol": "NIFTY", "instrument": "OPTIDX", "expiry": "28-Jan-2021", "strike": float(strike),
            "option_type": "PE", "open": straddle / 2, "high": straddle / 2, "low": straddle / 2,
            "close": straddle / 2, "settle_price": straddle / 2, "contracts": 100,
            "open_interest": put_oi, "change_in_oi": 0, "trade_date": td.strftime("%d-%b-%Y"),
        })
    return pd.DataFrame(rows)


class TestShiftDiscipline(unittest.TestCase):
    def test_day_t_feature_row_never_sees_day_t(self):
        """The day-t feature row must be built from day t-1 data only (no look-ahead)."""
        with TemporaryDirectory() as tmp:
            hist = Path(tmp)
            d0 = date(2021, 1, 4)
            # Day 3 (index 2) has an extreme +5% close that must NOT appear in its own row.
            specs = [(d0 + timedelta(days=i), 25000.0, 25010.0) for i in range(2)]
            specs.append((d0 + timedelta(days=2), 25000.0, 26250.0))  # extreme day
            specs += [(d0 + timedelta(days=3), 26000.0, 26010.0)]
            for i, (td, o, c) in enumerate(specs):
                _synthetic_day(td, o, c).to_parquet(hist / f"day_{i}.parquet", index=False)
            feats = build_feature_rows(hist)
            extreme_row = feats[feats["date"] == pd.Timestamp(d0 + timedelta(days=2))].iloc[0]
            # fut_prev_ret for the extreme day must reflect the PRIOR day (+0.04%), not +5%.
            self.assertAlmostEqual(extreme_row["fut_prev_ret"], (25010.0 - 25000.0) / 25000.0 * 100.0, places=6)
            # day 4's row DOES see the extreme day (that's the legit t-1 use).
            day4 = feats[feats["date"] == pd.Timestamp(d0 + timedelta(days=3))].iloc[0]
            self.assertAlmostEqual(day4["fut_prev_ret"], (26250.0 - 25000.0) / 25000.0 * 100.0, places=6)
            self.assertEqual(len(FEATURE_COLUMNS), 16)


class TestLabelsJoin(unittest.TestCase):
    def test_attach_labels_pivots_archetypes(self):
        feats = pd.DataFrame({"date": pd.to_datetime(["2021-03-01", "2021-03-02"]), "x": [1, 2]})
        labels = pd.DataFrame({
            "date": pd.to_datetime(["2021-03-01"] * 3),
            "archetype": ["Bull Call Spread", "Bear Put Spread", "Iron Condor"],
            "win": [True, False, True],
            "net_pnl": [100.0, -50.0, 20.0],
            "simulated": [True, True, True],
        })
        ds = attach_labels(feats, labels)
        self.assertIn("Bull_Call_Spread_won", ds.columns)
        self.assertIn("Iron_Condor_net", ds.columns)
        self.assertEqual(ds.loc[0, "Bull_Call_Spread_won"], True)
        self.assertTrue(pd.isna(ds.loc[1, "Bull_Call_Spread_won"]))


class TestFoldsAndGating(unittest.TestCase):
    def test_make_folds_count_and_order(self):
        dates = pd.Series(pd.date_range("2021-01-01", "2023-06-30", freq="D"))
        folds = make_folds(dates, train_months=24)
        # months: 30 total (2021-01 .. 2023-06); first test month = 2023-01
        self.assertEqual(len(folds), 30 - 24)
        self.assertEqual(folds[0][1], pd.Timestamp("2023-01-01"))
        self.assertEqual(folds[-1][1], pd.Timestamp("2023-06-01"))

    def test_pick_ml_trades_matches_count_and_one_per_day(self):
        n = 8
        month = pd.DataFrame({
            "date": pd.date_range("2023-01-02", periods=n),
            "rule_signal": ["UP"] * n,
            "dow": [0] * n,
        })
        for arch in ARCH_KEYS:
            month[arch.replace(" ", "_") + "_sim"] = True
            month[TARGETS[arch]] = True
            month[PNL_COLUMNS[arch]] = np.linspace(-100, 100, n)
            # Give the condor model a distinct probability profile to be selected first.
            month[f"lgbm__{arch}"] = 0.3 if arch != "Iron Condor" else 0.9
        picked = _pick_ml_trades(month, "lgbm", k=3)
        self.assertEqual(len(picked), 3)
        self.assertEqual(picked["date"].nunique(), 3)          # one trade per day
        self.assertTrue((picked["archetype"] == "Iron Condor").all())  # highest P chosen

    def test_gating_matched_trade_count(self):
        n = 20
        signals = ["UP", "FLAT", "NONE", "DOWN", "FLAT"] * (n // 5)  # 4 NONE days excluded
        preds = pd.DataFrame({
            "date": pd.date_range("2023-01-02", periods=n),
            "rule_signal": signals,
            "dow": [0] * n,
        })
        rng = np.random.default_rng(7)
        for arch in ARCH_KEYS:
            preds[arch.replace(" ", "_") + "_sim"] = True
            preds[TARGETS[arch]] = rng.random(n) > 0.5
            preds[PNL_COLUMNS[arch]] = rng.normal(0, 500, n)
            preds[f"lgbm__{arch}"] = rng.random(n)
            preds[f"logistic__{arch}"] = rng.random(n)
        res = gating_simulation(preds)
        self.assertEqual(res["baseline"]["n"], res["ml_lgbm"]["n"])   # matched count
        self.assertEqual(res["baseline"]["n"], res["ml_logistic"]["n"])
        self.assertEqual(res["baseline"]["n"], 16)                    # NONE days not traded


if __name__ == "__main__":
    unittest.main()
