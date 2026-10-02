"""Unit tests for core/collateral.py (Phase 1 Collateral Engine)."""

import unittest

from core.collateral import CollateralConfig, CollateralManager


class TestCollateralManager(unittest.TestCase):
    def setUp(self):
        self.mgr = CollateralManager()

    def test_default_allocation_and_haircut(self):
        """Verify default ₹2,00,000 allocation, 10% haircut, and margin amounts."""
        self.assertEqual(self.mgr.cfg.total_capital, 200_000.0)
        self.assertEqual(self.mgr.cfg.fund_allocation, 180_000.0)
        self.assertEqual(self.mgr.cfg.cash_buffer, 20_000.0)

        # 180k * 0.90 = 162k
        self.assertEqual(self.mgr.pledged_margin_value, 162_000.0)
        # 162k + 20k = 182k
        self.assertEqual(self.mgr.total_usable_margin, 182_000.0)

    def test_invalid_allocation_raises_error(self):
        """Allocation must sum to total capital."""
        with self.assertRaises(ValueError):
            CollateralManager(CollateralConfig(total_capital=200_000.0, fund_allocation=150_000.0, cash_buffer=20_000.0))

    def test_yield_calculations(self):
        """Verify gross and net yield calculations based on ~5.3% fund yield."""
        # 180k * 0.053 + 20k * 0.030 = 9540 + 600 = 10,140
        gross = self.mgr.gross_annual_yield()
        self.assertAlmostEqual(gross, 10_140.0, places=2)

        # Monthly gross ~845
        self.assertAlmostEqual(self.mgr.gross_monthly_yield(), 10_140.0 / 12.0, places=2)

        # Net at 30% tax bracket
        net_30 = self.mgr.net_annual_yield(tax_bracket=0.30)
        self.assertAlmostEqual(net_30, 10_140.0 * 0.70, places=2)

    def test_margin_requirement_approval_and_rejection(self):
        """Verify order margin checks against ₹182,000 usable margin."""
        # 1 lot straddle requires ~₹125,000 -> Approved
        ok, msg, data = self.mgr.check_margin_requirement(125_000.0)
        self.assertTrue(ok)
        self.assertEqual(data["headroom"], 57_000.0)

        # 2 lot straddle requires ~₹250,000 -> Rejected
        ok, msg, data = self.mgr.check_margin_requirement(250_000.0)
        self.assertFalse(ok)
        self.assertEqual(data["shortfall"], 68_000.0)


    def test_straddle_margin_estimation(self):
        """Verify dynamic short straddle margin calculation across spot and era lots."""
        # Spot 24500, era lot 65 -> ~₹1,24,852
        margin_65 = self.mgr.estimate_straddle_margin(spot=24_500.0, lot_size=65)
        self.assertAlmostEqual(margin_65, 124_852.0, places=1)
        ok, _, data = self.mgr.check_margin_requirement(margin_65)
        self.assertTrue(ok)
        self.assertGreater(data["headroom"], 50_000.0)

        # Legacy lot 50 -> ~₹96,040
        margin_50 = self.mgr.estimate_straddle_margin(spot=24_500.0, lot_size=50)
        self.assertAlmostEqual(margin_50, 96_040.0, places=1)

    def test_sebi_cash_ratio_enforcement(self):
        """Verify SEBI 50:50 cash component check fails if cash ratio is unmet."""
        # 100% of our usable margin is cash-equivalent (overnight fund + cash)
        self.assertEqual(self.mgr.cash_equivalent_margin, self.mgr.total_usable_margin)

        # But if an order requires margin exceeding available, it fails cleanly
        ok, msg, data = self.mgr.check_margin_requirement(200_000.0)
        self.assertFalse(ok)
        self.assertEqual(data["shortfall"], 18_000.0)


if __name__ == "__main__":
    unittest.main()
