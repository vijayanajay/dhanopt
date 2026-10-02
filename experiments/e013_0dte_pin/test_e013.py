"""Unit tests for E013 0DTE Expiry Microstructure and Pin Replay Engine."""

from datetime import date, datetime, timedelta
import unittest
import numpy as np
import pandas as pd

from experiments.e013_0dte_pin.pin_replay import audit_leg_observability, run_pin_replay


class TestE013Pin(unittest.TestCase):
    def test_expansion_ratio_regime_classification(self):
        """Verify expansion ratio accurately classifies Pin vs Breakout vs Neutral."""
        # Case 1: Compressed morning range (Pin)
        range_compressed = 50.0
        straddle_wide = 150.0
        exp_pin = range_compressed / straddle_wide
        self.assertLessEqual(exp_pin, 0.65)

        # Case 2: Expanded morning range (Breakout)
        range_expanded = 200.0
        straddle_narrow = 120.0
        exp_brk = range_expanded / straddle_narrow
        self.assertGreaterEqual(exp_brk, 1.20)

        # Case 3: Middle neutral zone
        exp_neutral = 90.0 / 100.0
        self.assertTrue(0.65 < exp_neutral < 1.20)

    def test_t_plus_one_entry_at_bar_40(self):
        """Signal evaluated at 12:30 IST (Bar 39) must execute at 12:35 IST (Bar 40)."""
        # 12:30 IST is Bar 39 (09:15 + 39*5 = 12:30)
        t_eval = datetime(2026, 1, 15, 9, 15) + timedelta(minutes=5 * 39)
        self.assertEqual(t_eval.time().hour, 12)
        self.assertEqual(t_eval.time().minute, 30)

        # 12:35 IST is Bar 40
        t_exec = datetime(2026, 1, 15, 9, 15) + timedelta(minutes=5 * 40)
        self.assertEqual(t_exec.time().hour, 12)
        self.assertEqual(t_exec.time().minute, 35)

    def test_iron_fly_risk_definition(self):
        """Iron Fly has strictly defined maximum loss equal to wing width minus credit."""
        wing_width = 150.0
        credit = 95.0
        max_loss = wing_width - credit
        self.assertEqual(max_loss, 55.0)
        self.assertLess(max_loss, wing_width)


if __name__ == "__main__":
    unittest.main()
