"""E014 integration tests: harness fidelity + maker-arm structural invariants.

1. The TAKER arm must reproduce the published E013 (per-session) and E011 (aggregate)
   accounting exactly — otherwise the maker comparison is not apples-to-apples.
2. Maker arm invariants: AON property, NO-TRADE accounting, penalty application,
   entry bars inside the frozen window.
"""

import json
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.e014_maker_tca.tca import (
    ARMS_E011,
    ARMS_E013,
    E011_ARTIFACTS,
    E013_ARTIFACTS,
    FROZEN,
    run_tca,
)

HERE = Path(__file__).resolve().parent


class TestE014Harness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trades, cls.fills, cls.metrics = run_tca()
        cls.pin_pub = pd.read_csv(E013_ARTIFACTS / "pin_daily.csv")
        cls.pin_pub = cls.pin_pub[cls.pin_pub["trade_type"] == "PIN_IRON_FLY"].copy()
        cls.pin_pub["date"] = pd.to_datetime(cls.pin_pub["date"]).dt.date
        with open(E011_ARTIFACTS / "metrics.json") as f:
            cls.e011_pub = json.load(f)

    def test_e013_taker_arm_reproduces_published_sessions(self):
        taker = self.trades[(self.trades["strategy"] == "E013_PIN_FLY") & (self.trades["arm"] == "TAKER")]
        merged = taker.merge(self.pin_pub[["date", "gross_pnl", "friction", "net_pnl"]], on="date", suffixes=("", "_pub"))
        self.assertEqual(len(merged), len(self.pin_pub))
        self.assertTrue(np.allclose(merged["gross_pnl"], merged["gross_pnl_pub"], atol=0.01))
        self.assertTrue(np.allclose(merged["friction"], merged["friction_pub"], atol=0.01))
        self.assertTrue(np.allclose(merged["net_pnl"], merged["net_pnl_pub"], atol=0.01))

    def test_e011_taker_arm_reproduces_published_total(self):
        taker = self.trades[(self.trades["strategy"] == "E011_VRP_STRADDLE") & (self.trades["arm"] == "TAKER")]
        self.assertEqual(len(taker), self.metrics["sessions"]["e011_vrp_signaled"])
        self.assertAlmostEqual(float(taker["net_pnl"].sum()), self.e011_pub["total_net_pnl"], places=1)

    def test_maker_aon_property(self):
        for strategy, legs in (("E013_PIN_FLY", 4), ("E011_VRP_STRADDLE", 2)):
            maker = self.trades[(self.trades["strategy"] == strategy) & (self.trades["arm"] == "MAKER")]
            filled = maker[maker["filled"]]
            # AON: a filled session has every leg; a NO-TRADE session has zero PnL.
            self.assertTrue((filled["legs_filled"] == legs).all())
            unfilled = maker[~maker["filled"]]
            self.assertTrue((unfilled["net_pnl"] == 0.0).all())
            self.assertTrue((unfilled["friction"] == 0.0).all())

    def test_maker_entry_bars_inside_frozen_window(self):
        win = FROZEN["entry_window_bars"]
        e013 = self.trades[(self.trades["strategy"] == "E013_PIN_FLY") & (self.trades["arm"] == "MAKER") & self.trades["filled"]]
        self.assertTrue(e013["entry_bar"].between(FROZEN["e013_entry_bar"], FROZEN["e013_entry_bar"] + win - 1).all())
        e011 = self.trades[(self.trades["strategy"] == "E011_VRP_STRADDLE") & (self.trades["arm"] == "MAKER") & self.trades["filled"]]
        self.assertTrue(e011["entry_bar"].between(FROZEN["e011_entry_bar"], FROZEN["e011_entry_bar"] + win - 1).all())

    def test_hybrid_always_trades_and_fills_all_legs(self):
        hybrid = self.trades[(self.trades["strategy"] == "E013_PIN_FLY") & (self.trades["arm"] == "HYBRID")]
        self.assertTrue(hybrid["filled"].all())
        self.assertTrue((hybrid["legs_filled"] == 4).all())

    def test_adverse_penalty_applied_to_flagged_fills(self):
        maker_fills = self.fills[self.fills["arm"] != "TAKER"]
        flagged = maker_fills[maker_fills["adverse"]]
        if len(flagged):
            self.assertTrue(np.allclose(flagged["fill_price"], flagged["taker_price"], atol=1e-6))
            self.assertTrue((flagged["penalty"] > 0).all())
        clean = maker_fills[~maker_fills["adverse"]]
        self.assertTrue(np.allclose(clean["fill_price"], clean["raw_fill_price"], atol=1e-6))

    def test_gates_present_for_both_strategies(self):
        for key in ("e013_pin_iron_fly", "e011_vrp_straddle"):
            gates = self.metrics[key].get("gates")
            self.assertIsNotNone(gates, f"missing gates for {key}")
            for g in ("gate1_fill_rate", "gate2_per_trade_quality", "gate3_aggregate_survival"):
                self.assertIn(g, gates)
                self.assertIn("pass", gates[g])


if __name__ == "__main__":
    unittest.main()
