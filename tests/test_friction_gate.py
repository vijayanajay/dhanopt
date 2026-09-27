"""Unit tests for Friction Accounting and Deterministic Rule Gatekeeper.

Verifies:
- Zerodha post-Oct 2024 SEBI fee schedule and slippage calculations
- RuleGatekeeper vetos (capital cap, liquidity OI, spread, economic hurdle, win-rate edge)
"""

import unittest

import config
from core.auditors.rule_gatekeeper import GateResult, RuleGatekeeper, TradeProposal
from core.feeds.base import OptionContract
from core.friction.zerodha import (
    FrictionBreakdown,
    OptionLeg,
    calculate_friction,
    estimate_spread_friction,
)


class TestFrictionEngine(unittest.TestCase):
    def test_two_leg_spread_friction_breakdown(self):
        # Bull Call Spread: Long 25000 CE @ 100.0, Short 25150 CE @ 45.0, 1 lot (75 qty)
        legs = [
            OptionLeg(strike=25000.0, option_type="CE", action="BUY", entry_price=100.0, target_price=130.0, lots=1),
            OptionLeg(strike=25150.0, option_type="CE", action="SELL", entry_price=45.0, target_price=15.0, lots=1),
        ]
        fb = calculate_friction(legs, slippage_pts_per_leg=1.5)

        # 1. Brokerage: 2 legs * 2 sides * ₹20 = ₹80.00
        self.assertEqual(fb.brokerage, 80.00)

        # 2. Slippage: 1.5 pts * 75 qty * 2 legs = ₹225.00
        self.assertEqual(fb.slippage, 225.00)

        # 3. STT: 0.1% on sell-side turnover
        # Long leg exit sell: 130 * 75 = 9750
        # Short leg entry sell: 45 * 75 = 3375
        # Total sell turnover = 13125 -> STT = 13.125 ~= 13.12 or 13.13
        self.assertAlmostEqual(fb.stt, 13.13, delta=0.05)

        # 4. Total rupees must include all charges
        self.assertGreater(fb.total_rupees, 320.00)
        self.assertAlmostEqual(fb.points_equivalent, fb.total_rupees / 75.0, places=2)

    def test_four_leg_iron_condor_friction(self):
        fb = estimate_spread_friction(num_legs=4, avg_premium=50.0, lots=1)
        # 4 legs * 2 sides * ₹20 = ₹160 brokerage
        self.assertEqual(fb.brokerage, 160.00)
        # 4 legs * 1.5 pts * 75 = ₹450 slippage
        self.assertEqual(fb.slippage, 450.00)
        self.assertGreater(fb.total_rupees, 610.00)


class TestRuleGatekeeper(unittest.TestCase):
    def setUp(self):
        self.gatekeeper = RuleGatekeeper(
            max_daily_loss=2500.0,
            min_win_rate=0.55,
            min_strike_oi=100_000,
            max_bid_ask_spread=1.5,
            economic_hurdle_ratio=2.0,
            off_window_hurdle_ratio=3.0,
            monthly_drawdown_cap=10_000.0,
        )
        self.dummy_friction = FrictionBreakdown(
            brokerage=80.0,
            stt=10.0,
            exchange_turnover=5.0,
            sebi_turnover=0.02,
            stamp_duty=0.2,
            gst=15.3,
            slippage=225.0,
            total_rupees=335.52,
            points_equivalent=4.47,
        )
        self.valid_contracts = [
            OptionContract(symbol="N25000CE", strike=25000.0, option_type="CE", expiry="2026-10-01", bid=99.8, ask=100.2, oi=250000),
            OptionContract(symbol="N25150CE", strike=25150.0, option_type="CE", expiry="2026-10-01", bid=44.8, ask=45.2, oi=180000),
        ]

    def test_valid_trade_passes(self):
        proposal = TradeProposal(
            strategy_name="Bull Call Debit Spread",
            underlying="NIFTY",
            expiry="2026-10-01",
            legs=[],
            max_loss=2200.0,        # Under ₹2,500
            target_profit=3200.0,   # Expected win = 0.56 * 3200 = 1792 > 2.0 * 335.52 (671.04)
            win_rate=0.56,          # > 55%
            net_debit_or_credit=55.0,
            is_credit=False,
            friction=self.dummy_friction,
            gross_ev=824.0,
            net_ev=488.48,
            payoff_ratio=1.45,
            contracts=self.valid_contracts,
        )
        res = self.gatekeeper.validate(proposal)
        self.assertTrue(res.passed)
        self.assertIsNone(res.veto_reason)

    def test_veto_capital_cap(self):
        proposal = TradeProposal(
            strategy_name="Bull Call Spread",
            underlying="NIFTY",
            expiry="2026-10-01",
            legs=[],
            max_loss=2800.0,        # Breaches ₹2,500 cap
            target_profit=4000.0,
            win_rate=0.56,
            net_debit_or_credit=70.0,
            is_credit=False,
            friction=self.dummy_friction,
            gross_ev=1008.0,
            net_ev=672.48,
            payoff_ratio=1.43,
            contracts=self.valid_contracts,
        )
        res = self.gatekeeper.validate(proposal)
        self.assertFalse(res.passed)
        self.assertEqual(res.veto_code, "CAPITAL_CAP")
        self.assertIn("Trade max loss", res.veto_reason)

    def test_veto_liquidity_low_oi(self):
        illiquid_contracts = [
            OptionContract(symbol="N25000CE", strike=25000.0, option_type="CE", expiry="2026-10-01", bid=99.8, ask=100.2, oi=50000),  # < 100k
            OptionContract(symbol="N25150CE", strike=25150.0, option_type="CE", expiry="2026-10-01", bid=44.8, ask=45.2, oi=150000),
        ]
        proposal = TradeProposal(
            strategy_name="Bull Call Spread",
            underlying="NIFTY",
            expiry="2026-10-01",
            legs=[],
            max_loss=2000.0,
            target_profit=3000.0,
            win_rate=0.56,
            net_debit_or_credit=50.0,
            is_credit=False,
            friction=self.dummy_friction,
            gross_ev=800.0,
            net_ev=464.48,
            payoff_ratio=1.5,
            contracts=illiquid_contracts,
        )
        res = self.gatekeeper.validate(proposal)
        self.assertFalse(res.passed)
        self.assertEqual(res.veto_code, "LIQUIDITY_OI")

    def test_veto_liquidity_wide_spread(self):
        wide_spread_contracts = [
            OptionContract(symbol="N25000CE", strike=25000.0, option_type="CE", expiry="2026-10-01", bid=98.0, ask=100.5, oi=200000),  # spread 2.5 > 1.5
            OptionContract(symbol="N25150CE", strike=25150.0, option_type="CE", expiry="2026-10-01", bid=44.8, ask=45.2, oi=150000),
        ]
        proposal = TradeProposal(
            strategy_name="Bull Call Spread",
            underlying="NIFTY",
            expiry="2026-10-01",
            legs=[],
            max_loss=2000.0,
            target_profit=3000.0,
            win_rate=0.56,
            net_debit_or_credit=50.0,
            is_credit=False,
            friction=self.dummy_friction,
            gross_ev=800.0,
            net_ev=464.48,
            payoff_ratio=1.5,
            contracts=wide_spread_contracts,
        )
        res = self.gatekeeper.validate(proposal)
        self.assertFalse(res.passed)
        self.assertEqual(res.veto_code, "LIQUIDITY_SPREAD")

    def test_veto_uneconomic_trade(self):
        # Target profit ₹500 -> expected profit = 0.56 * 500 = ₹280 < 2.0 * ₹335.52 (₹671.04)
        proposal = TradeProposal(
            strategy_name="Low Edge Spread",
            underlying="NIFTY",
            expiry="2026-10-01",
            legs=[],
            max_loss=1500.0,
            target_profit=500.0,
            win_rate=0.56,
            net_debit_or_credit=20.0,
            is_credit=False,
            friction=self.dummy_friction,
            gross_ev=20.0,
            net_ev=-315.52,
            payoff_ratio=0.33,
            contracts=self.valid_contracts,
        )
        res = self.gatekeeper.validate(proposal)
        self.assertFalse(res.passed)
        self.assertEqual(res.veto_code, "ECONOMIC_HURDLE")

    def test_veto_low_win_rate(self):
        proposal = TradeProposal(
            strategy_name="Coin Toss Trade",
            underlying="NIFTY",
            expiry="2026-10-01",
            legs=[],
            max_loss=2000.0,
            target_profit=3500.0,
            win_rate=0.48,          # < 55%
            net_debit_or_credit=50.0,
            is_credit=False,
            friction=self.dummy_friction,
            gross_ev=640.0,
            net_ev=304.48,
            payoff_ratio=1.75,
            contracts=self.valid_contracts,
        )
        res = self.gatekeeper.validate(proposal)
        self.assertFalse(res.passed)
        self.assertEqual(res.veto_code, "EDGE_HURDLE")

    def test_veto_daily_loss_circuit_breaker(self):
        proposal = TradeProposal(
            strategy_name="Bull Call Spread",
            underlying="NIFTY",
            expiry="2026-10-01",
            legs=[],
            max_loss=1000.0,
            target_profit=2000.0,
            win_rate=0.56,
            net_debit_or_credit=40.0,
            is_credit=False,
            friction=self.dummy_friction,
            gross_ev=680.0,
            net_ev=344.48,
            payoff_ratio=2.0,
            contracts=self.valid_contracts,
        )
        # Already lost ₹2,500 today
        res = self.gatekeeper.validate(proposal, current_daily_loss=2500.0)
        self.assertFalse(res.passed)
        self.assertEqual(res.veto_code, "DAILY_LOSS_LIMIT")


if __name__ == "__main__":
    unittest.main()
