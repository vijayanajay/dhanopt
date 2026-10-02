"""Tests for experiments/common/spread_sensitivity.py — exact friction reconstruction."""

import json
import unittest
from pathlib import Path

import pandas as pd

from experiments.common.spread_sensitivity import (
    BASELINE_PTS,
    SPREADS_PTS,
    reconstruct_net,
    run_sweep,
)

ROOT = Path(__file__).resolve().parents[1]


class TestSpreadSensitivity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = run_sweep()

    def test_reconstruction_formula(self):
        df = pd.DataFrame({"gross": [1000.0], "friction": [500.0], "lot": [65]})
        # +1.0 pt/leg over baseline on 4 leg-orders x 65 lot = +260 friction.
        net = reconstruct_net(df, BASELINE_PTS + 1.0, 4)
        self.assertAlmostEqual(float(net.iloc[0]), 1000.0 - (500.0 + 4 * 65.0), places=6)
        # At baseline, reconstruction returns the published net exactly.
        self.assertAlmostEqual(float(reconstruct_net(df, BASELINE_PTS, 4).iloc[0]), 500.0, places=6)

    def test_baseline_point_matches_published_totals(self):
        published = {"e011_vrp_straddle": 743572.25, "e013_pin_iron_fly": 414721.03}
        for key, total in published.items():
            point = next(c for c in self.res[key]["sweep"] if c["half_spread_pts"] == BASELINE_PTS)
            self.assertAlmostEqual(point["total_net_pnl"], total, places=1)

    def test_curves_are_monotonic_and_breakeven_far_above_range(self):
        for key in ("e011_vrp_straddle", "e013_pin_iron_fly"):
            evs = [c["net_ev_per_trade"] for c in self.res[key]["sweep"]]
            self.assertEqual(len(evs), len(SPREADS_PTS))
            self.assertTrue(all(b < a for a, b in zip(evs, evs[1:])), f"{key} EV not strictly decreasing")
            # Frozen books stay positive far beyond the swept 3.0 pts.
            self.assertGreater(self.res[key]["breakeven_half_spread_pts"], 3.0)

    def test_artifacts_written_to_strategy_folders(self):
        for rel in ("experiments/e011_vrp_delta_hedge/artifacts/spread_sensitivity.json",
                    "experiments/e013_0dte_pin/artifacts/spread_sensitivity.json"):
            path = ROOT / rel
            self.assertTrue(path.exists(), f"missing {rel}")
            with open(path) as f:
                data = json.load(f)
            self.assertIn("sweep", data)
            self.assertIn("breakeven_half_spread_pts", data)


if __name__ == "__main__":
    unittest.main()
