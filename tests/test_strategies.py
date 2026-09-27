"""Unit tests for The 3 Core Strategies and Comparative Audit Engine.

Verifies:
- Directional Debit Spread (Bull Call & Bear Put) gates and strike construction
- Directional Credit Spread (Bull Put & Bear Call) hedge-first sequencing
- Range-bound Iron Condor 4-leg structure and chop filters
- Comparative Audit Engine:
  * Trend breakout rejects Iron Condor with "KER breaches max chop threshold"
  * Chop session selects Iron Condor and rejects directional spreads
  * Noise regime outputs TIER 0: NO TRADE
"""

import unittest
from datetime import datetime

from core.auditors.rule_gatekeeper import RuleGatekeeper
from core.feeds.base import OptionChainSnapshot, OptionContract
from core.signals import MarketSignals
from core.signals.ker import KERSignal
from core.signals.oi_micro import OIMicroSignal
from core.signals.orb import ORBSignal
from core.signals.vix_iv import VIXIVSignal
from core.signals.vwap import VWAPSignal
from core.strategies.audit_engine import ComparativeAuditEngine
from core.strategies.credit_spread import CreditSpreadStrategy
from core.strategies.debit_spread import DebitSpreadStrategy
from core.strategies.iron_condor import IronCondorStrategy


def _build_mock_chain(spot: float = 25050.0) -> OptionChainSnapshot:
    """Builds an option chain around spot price with realistic spreads."""
    import math
    contracts = {}
    strikes = [24600.0, 24750.0, 24900.0, 25000.0, 25050.0, 25100.0, 25200.0, 25350.0, 25500.0]

    for k in strikes:
        dist = k - spot
        # Realistic monotonic option pricing: ATM ~160, 150 OTM ~85, 300 OTM ~35, 450 OTM ~15
        if dist >= 0:
            ce_price = max(5.0, 160.0 * math.exp(-dist / 225.0))
        else:
            ce_price = max(5.0, 160.0 - dist)

        if dist <= 0:
            pe_price = max(5.0, 160.0 * math.exp(dist / 225.0))
        else:
            pe_price = max(5.0, 160.0 + dist)

        contracts[(k, "CE")] = OptionContract(
            symbol=f"N{int(k)}CE",
            strike=k,
            option_type="CE",
            expiry="2026-10-01",
            ltp=round(ce_price, 2),
            bid=round(ce_price - 0.2, 2),
            ask=round(ce_price + 0.2, 2),
            oi=280000 if k == 25200.0 else 180000,
            volume=45000,
            iv=13.0,
            delta=round(0.50 - dist / 600.0, 2),
        )
        contracts[(k, "PE")] = OptionContract(
            symbol=f"N{int(k)}PE",
            strike=k,
            option_type="PE",
            expiry="2026-10-01",
            ltp=round(pe_price, 2),
            bid=round(pe_price - 0.2, 2),
            ask=round(pe_price + 0.2, 2),
            oi=290000 if k == 24900.0 else 170000,
            volume=50000,
            iv=13.5,
            delta=round(-0.50 - dist / 600.0, 2),
        )

    return OptionChainSnapshot(
        timestamp=datetime.now(),
        spot_price=spot,
        contracts=contracts,
        expiry="2026-10-01",
    )


def _build_trending_signals(is_bullish: bool = True) -> MarketSignals:
    """Builds MarketSignals representing a clean directional trend breakout."""
    spot = 25120.0 if is_bullish else 24880.0
    vwap_px = 25050.0
    slope = +0.035 if is_bullish else -0.035
    status = "BULLISH_BREAKOUT" if is_bullish else "BEARISH_BREAKDOWN"

    return MarketSignals(
        timestamp=datetime.now(),
        spot_price=spot,
        vwap=VWAPSignal(
            vwap=vwap_px,
            upper_band=vwap_px + 50.0,
            lower_band=vwap_px - 50.0,
            std_dev=33.3,
            slope_15m=slope,
            regime="BULLISH" if is_bullish else "BEARISH",
            price=spot,
            price_vs_vwap_pct=0.28 if is_bullish else -0.28,
        ),
        orb=ORBSignal(
            orh=25080.0,
            orl=25000.0,
            width=80.0,
            width_pct=0.32,
            is_compressed=True,
            status=status,
            volume_ratio=1.8,
        ),
        vix_iv=VIXIVSignal(
            vix=14.0,
            prev_vix=13.8,
            delta_vix=1.45,
            regime="NORMAL_VOL",
            shift="STABLE",
            atm_iv=13.2,
            parkinson_vol=12.0,
            iv_spread=1.2,
            is_rich=False,
        ),
        oi=OIMicroSignal(
            call_wall=25350.0,
            put_wall=24750.0,
            pcr_oi=1.15,
            pcr_volume=1.2,
            delta_pcr=+0.20,
            total_call_oi=450000,
            total_put_oi=520000,
            net_bias="BULLISH_FLOOR" if is_bullish else "BEARISH_CAP",
            spot_price=spot,
            atm_strike=25100.0 if is_bullish else 24900.0,
        ),
        ker=KERSignal(
            ker=0.62,
            is_trending=True,
            is_noisy=False,
            net_change=70.0,
            total_path=112.9,
        ),
    )


def _build_chop_signals() -> MarketSignals:
    """Builds MarketSignals representing an equilibrium range-bound session."""
    spot = 25050.0
    vwap_px = 25050.0

    return MarketSignals(
        timestamp=datetime.now(),
        spot_price=spot,
        vwap=VWAPSignal(
            vwap=vwap_px,
            upper_band=vwap_px + 45.0,
            lower_band=vwap_px - 45.0,
            std_dev=30.0,
            slope_15m=0.002,
            regime="CHOP",
            price=spot,
            price_vs_vwap_pct=0.0,
        ),
        orb=ORBSignal(
            orh=25080.0,
            orl=25020.0,
            width=60.0,
            width_pct=0.24,
            is_compressed=True,
            status="INSIDE_RANGE",
            volume_ratio=0.8,
        ),
        vix_iv=VIXIVSignal(
            vix=15.5,
            prev_vix=15.5,
            delta_vix=0.0,
            regime="NORMAL_VOL",
            shift="STABLE",
            atm_iv=16.5,
            parkinson_vol=12.5,
            iv_spread=4.0,
            is_rich=True,
        ),
        oi=OIMicroSignal(
            call_wall=25200.0,
            put_wall=24900.0,
            pcr_oi=1.02,
            pcr_volume=1.01,
            delta_pcr=0.02,
            total_call_oi=500000,
            total_put_oi=510000,
            net_bias="NEUTRAL",
            spot_price=spot,
            atm_strike=25050.0,
        ),
        ker=KERSignal(
            ker=0.24,
            is_trending=False,
            is_noisy=True,
            net_change=12.0,
            total_path=50.0,
        ),
    )


class TestStrategies(unittest.TestCase):
    def setUp(self):
        self.chain = _build_mock_chain(spot=25050.0)

    def test_debit_spread_bull_call(self):
        strat = DebitSpreadStrategy()
        signals = _build_trending_signals(is_bullish=True)
        
        passed, reason = strat.evaluate_gates(signals)
        self.assertTrue(passed)
        self.assertIn("Bullish breakout", reason)

        proposal = strat.build_proposal(signals, self.chain, lots=1)
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal.strategy_name, "Nifty Bull Call Debit Spread")
        self.assertEqual(len(proposal.legs), 2)
        self.assertEqual(proposal.legs[0].action, "BUY")
        self.assertEqual(proposal.legs[1].action, "SELL")
        self.assertFalse(proposal.is_credit)
        self.assertGreater(proposal.net_ev, 0.0)

    def test_debit_spread_bear_put(self):
        strat = DebitSpreadStrategy()
        signals = _build_trending_signals(is_bullish=False)

        passed, reason = strat.evaluate_gates(signals)
        self.assertTrue(passed)
        self.assertIn("Bearish breakdown", reason)

        proposal = strat.build_proposal(signals, self.chain, lots=1)
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal.strategy_name, "Nifty Bear Put Debit Spread")
        self.assertEqual(len(proposal.legs), 2)
        self.assertEqual(proposal.legs[0].option_type, "PE")
        self.assertFalse(proposal.is_credit)

    def test_credit_spread_bull_put(self):
        strat = CreditSpreadStrategy()
        # Build signals with spot above Put Wall, rich IV, moderate slope
        signals = _build_chop_signals()
        signals.spot_price = 25050.0
        signals.vwap.slope_15m = 0.025  # Moderate bullish slope
        signals.oi.put_wall = 24900.0   # Spot supported by Put Wall
        signals.vix_iv.vix = 14.5
        signals.vix_iv.iv_spread = 2.5

        passed, reason = strat.evaluate_gates(signals)
        self.assertTrue(passed)
        self.assertIn("Supported by Put Wall", reason)

        proposal = strat.build_proposal(signals, self.chain, lots=1)
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal.strategy_name, "Nifty Bull Put Credit Spread")
        self.assertEqual(len(proposal.legs), 2)
        # Hedge Leg First (BUY), Short Leg Second (SELL)
        self.assertEqual(proposal.legs[0].action, "BUY")
        self.assertEqual(proposal.legs[1].action, "SELL")
        self.assertTrue(proposal.is_credit)

    def test_credit_spread_rejections(self):
        strat = CreditSpreadStrategy()
        # Case 1: Low IV Spread
        signals = _build_chop_signals()
        signals.vix_iv.iv_spread = 0.8
        passed, reason = strat.evaluate_gates(signals)
        self.assertFalse(passed)
        self.assertIn("insufficient credit collected", reason)

        # Case 2: Excessive Slope (Breakout)
        signals2 = _build_chop_signals()
        signals2.vwap.slope_15m = 0.08  # > 0.06%
        passed2, reason2 = strat.evaluate_gates(signals2)
        self.assertFalse(passed2)
        self.assertIn("risk of delta steamroll", reason2)

    def test_iron_condor_rejection_on_trend_breakout(self):
        """Action Plan Verification Requirement:
        Assert that a trend breakout rejects Iron Condor with reason 'KER breaches max chop threshold'.
        """
        strat = IronCondorStrategy()
        trend_signals = _build_trending_signals(is_bullish=True)  # KER = 0.62

        passed, reason = strat.evaluate_gates(trend_signals)
        self.assertFalse(passed)
        self.assertIn("KER breaches max chop threshold", reason)

    def test_iron_condor_selection_on_chop(self):
        strat = IronCondorStrategy()
        chop_signals = _build_chop_signals()  # KER = 0.24, flat slope, inside ORB

        passed, reason = strat.evaluate_gates(chop_signals)
        self.assertTrue(passed)

        proposal = strat.build_proposal(chop_signals, self.chain, lots=1)
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal.strategy_name, "Nifty Neutral Iron Condor")
        self.assertEqual(len(proposal.legs), 4)

        # Strict execution sequencing: Hedges (BUY) 1st & 2nd, Short Wings (SELL) 3rd & 4th
        self.assertEqual(proposal.legs[0].action, "BUY")
        self.assertEqual(proposal.legs[1].action, "BUY")
        self.assertEqual(proposal.legs[2].action, "SELL")
        self.assertEqual(proposal.legs[3].action, "SELL")
        self.assertTrue(proposal.is_credit)

    def test_comparative_audit_engine_trend_flow(self):
        engine = ComparativeAuditEngine()
        trend_signals = _build_trending_signals(is_bullish=True)

        report = engine.run_audit(trend_signals, self.chain, lots=1)
        self.assertTrue(report.is_trade_approved)
        self.assertEqual(report.selected_strategy_name, "Debit Spread")
        self.assertIn("BULL CALL DEBIT SPREAD", report.verdict)

        # Verify audit table entries for the other two rejected strategies
        ic_entry = report.get_entry("Iron Condor")
        self.assertIsNotNone(ic_entry)
        self.assertEqual(ic_entry.status, "REJECTED")
        self.assertIn("KER breaches max chop threshold", ic_entry.reason)

    def test_comparative_audit_engine_chop_flow(self):
        engine = ComparativeAuditEngine()
        chop_signals = _build_chop_signals()

        report = engine.run_audit(chop_signals, self.chain, lots=1)
        self.assertTrue(report.is_trade_approved)
        self.assertEqual(report.selected_strategy_name, "Iron Condor")
        self.assertIn("IRON CONDOR", report.verdict)

        # Debit spread must be rejected due to low KER
        debit_entry = report.get_entry("Debit Spread")
        self.assertIsNotNone(debit_entry)
        self.assertEqual(debit_entry.status, "REJECTED")
        self.assertIn("below directional hurdle", debit_entry.reason)

    def test_comparative_audit_engine_noise_tier_0_no_trade(self):
        engine = ComparativeAuditEngine()
        # Build noisy signals with KER in the dead zone (0.45), neither trending nor choppy
        noise_signals = _build_chop_signals()
        noise_signals.ker = KERSignal(ker=0.45, is_trending=False, is_noisy=False, net_change=25.0, total_path=55.5)

        report = engine.run_audit(noise_signals, self.chain, lots=1)
        self.assertFalse(report.is_trade_approved)
        self.assertIsNone(report.selected_strategy_name)
        self.assertIsNone(report.selected_proposal)
        self.assertIn("TIER 0: NO TRADE", report.verdict)

        # All entries must be REJECTED
        for entry in report.entries:
            self.assertEqual(entry.status, "REJECTED")


if __name__ == "__main__":
    unittest.main()
