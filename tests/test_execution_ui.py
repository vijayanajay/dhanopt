"""Unit tests for Phase 5: One-Click Execution & UI / Telegram Delivery.

Verifies:
- Zerodha Basket Builder: Strict sequencing (Buy legs 1st, Sell legs 2nd), JSON format, Publisher URL.
- Terminal Rich UI: Clean rendering of all 3 panels for both trade and standby modes.
- Telegram Push: Trade card formatting and stdlib urllib HTTP dispatch handling.
"""

import json
import unittest
from datetime import datetime, time
from unittest.mock import MagicMock, patch

import config
from core.auditors.rule_gatekeeper import TradeProposal
from core.execution.basket_builder import (
    KiteBasket,
    build_kite_basket,
    format_tradingsymbol,
)
from core.friction.zerodha import FrictionBreakdown, OptionLeg
from core.signals import MarketSignals
from core.signals.ker import KERSignal
from core.signals.oi_micro import OIMicroSignal
from core.signals.orb import ORBSignal
from core.signals.vix_iv import VIXIVSignal
from core.signals.vwap import VWAPSignal
from core.strategies.audit_engine import AuditEntry, AuditReport
from core.ui.telegram_push import (
    format_telegram_trade_card,
    push_trade_alert,
    send_telegram_message,
)
from core.ui.terminal_rich import (
    render_dashboard_to_string,
    render_terminal_dashboard,
)


def _build_test_signals() -> MarketSignals:
    """Helper to create dummy signals for UI tests."""
    return MarketSignals(
        timestamp=datetime(2026, 9, 30, 10, 15, 0),
        spot_price=25240.50,
        vwap=VWAPSignal(
            vwap=25215.00,
            upper_band=25260.00,
            lower_band=25170.00,
            std_dev=30.0,
            slope_15m=0.032,
            regime="BULLISH",
            price=25240.50,
            price_vs_vwap_pct=0.10,
        ),
        orb=ORBSignal(
            orh=25255.0,
            orl=25195.0,
            width=60.0,
            width_pct=0.24,
            is_compressed=False,
            status="BULLISH_BREAKOUT",
            volume_ratio=1.60,
        ),
        vix_iv=VIXIVSignal(
            vix=13.20,
            prev_vix=13.40,
            delta_vix=-1.49,
            regime="NORMAL_VOL",
            shift="STABLE",
            atm_iv=12.80,
            parkinson_vol=11.40,
            iv_spread=1.40,
            is_rich=False,
        ),
        oi=OIMicroSignal(
            call_wall=25400.0,
            put_wall=25100.0,
            pcr_oi=1.18,
            pcr_volume=1.05,
            delta_pcr=0.18,
            total_call_oi=1000000,
            total_put_oi=1180000,
            net_bias="BULLISH_FLOOR",
            spot_price=25240.50,
            atm_strike=25250.0,
        ),
        ker=KERSignal(
            ker=0.64,
            is_trending=True,
            is_noisy=False,
            net_change=45.0,
            total_path=70.0,
        ),
    )


def _build_test_proposal() -> TradeProposal:
    """Helper to create dummy TradeProposal with mixed leg order to verify sequencing."""
    legs = [
        OptionLeg(
            strike=25400.0,
            option_type="CE",
            action="SELL",
            entry_price=34.0,
            target_price=10.0,
            stop_price=52.0,
            lots=1,
            symbol="NIFTY26OCT25400CE",
        ),
        OptionLeg(
            strike=25250.0,
            option_type="CE",
            action="BUY",
            entry_price=110.0,
            target_price=145.0,
            stop_price=75.0,
            lots=1,
            symbol="NIFTY26OCT25250CE",
        ),
    ]
    friction = FrictionBreakdown(
        brokerage=80.0,
        stt=12.0,
        exchange_turnover=15.0,
        sebi_turnover=0.15,
        stamp_duty=2.5,
        gst=17.1,
        slippage=75.0,
        total_rupees=186.75,
        points_equivalent=2.49,
    )
    return TradeProposal(
        strategy_name="Nifty Bull Call Debit Spread",
        underlying="NIFTY",
        expiry="2026-10-01",
        legs=legs,
        max_loss=2100.0,
        target_profit=3600.0,
        win_rate=0.59,
        net_debit_or_credit=76.0,
        is_credit=False,
        friction=friction,
        gross_ev=969.0,
        net_ev=782.25,
        payoff_ratio=1.71,
    )


class TestExecutionUI(unittest.TestCase):
    """Test suite for Phase 5 components."""

    def test_basket_builder_strict_sequencing(self):
        """Action Plan Task 5.1: Assert Buy legs come first, Sell legs second."""
        prop = _build_test_proposal()
        # Input has SELL leg at index 0, BUY leg at index 1
        self.assertEqual(prop.legs[0].action, "SELL")
        self.assertEqual(prop.legs[1].action, "BUY")

        basket = build_kite_basket(prop)
        orders = basket.orders

        self.assertEqual(len(orders), 2)
        # In output basket, BUY leg must be first (index 0)
        self.assertEqual(orders[0].transaction_type, "BUY")
        self.assertEqual(orders[0].tradingsymbol, "NIFTY26OCT25250CE")
        self.assertEqual(orders[0].quantity, config.NIFTY_LOT_SIZE)  # era-correct (65 since 2025-12-30)
        self.assertEqual(orders[0].product, "MIS")
        self.assertEqual(orders[0].order_type, "LIMIT")
        self.assertEqual(orders[0].price, 110.0)

        # SELL leg must be second (index 1)
        self.assertEqual(orders[1].transaction_type, "SELL")
        self.assertEqual(orders[1].tradingsymbol, "NIFTY26OCT25400CE")
        self.assertEqual(orders[1].quantity, config.NIFTY_LOT_SIZE)
        self.assertEqual(orders[1].price, 34.0)

    def test_basket_builder_json_and_publisher_url(self):
        """Action Plan Task 5.1: Verify JSON basket formatting and Kite Publisher link."""
        prop = _build_test_proposal()
        basket = build_kite_basket(prop, api_key="my_kite_key")

        # Parse JSON payload
        parsed = json.loads(basket.json_payload)
        self.assertIsInstance(parsed, list)
        self.assertEqual(len(parsed), 2)
        self.assertIn("variety", parsed[0])
        self.assertIn("exchange", parsed[0])
        self.assertEqual(parsed[0]["exchange"], "NFO")

        # Check publisher URL
        self.assertIn("https://kite.zerodha.com/connect/basket", basket.publisher_url)
        self.assertIn("api_key=my_kite_key", basket.publisher_url)
        self.assertIn("data=", basket.publisher_url)

    def test_terminal_rich_rendering_approved_trade(self):
        """Action Plan Task 5.2: Verify multi-panel terminal UI renders approved trade cleanly."""
        signals = _build_test_signals()
        prop = _build_test_proposal()
        report = AuditReport(
            verdict="FINAL VERDICT: NIFTY BULL CALL SPREAD SELECTED",
            selected_strategy_name="Debit Spread",
            selected_proposal=prop,
            entries=[
                AuditEntry(
                    strategy_name="Debit Spread",
                    status="SELECTED",
                    ev_score=782.25,
                    reason="PASSED: ORB-30 Breakout confirmed, KER 0.64 > 0.55",
                    proposal=prop,
                ),
                AuditEntry(
                    strategy_name="Credit Spread",
                    status="REJECTED",
                    ev_score=180.0,
                    reason="REJECTED: IV Spread low; net credit fails 2.0x fee hurdle",
                    proposal=None,
                ),
                AuditEntry(
                    strategy_name="Iron Condor",
                    status="REJECTED",
                    ev_score=-410.0,
                    reason="REJECTED: Trend breakout active; KER breaches max chop cap",
                    proposal=None,
                ),
            ],
        )
        basket = build_kite_basket(prop)

        output = render_dashboard_to_string(
            signals=signals,
            report=report,
            basket=basket,
            weekday_window_status="Wednesday Window (10:00-11:00)",
            is_optimal_window=True,
        )

        self.assertIn("QUANTITATIVE NIFTY OPTIONS ON-DEMAND ENGINE", output)
        self.assertIn("PANEL 1: MARKET MICROSTRUCTURE DIAGNOSTICS", output)
        self.assertIn("PANEL 2: MANDATORY 3-STRATEGY COMPARATIVE AUDIT", output)
        self.assertIn("NIFTY26OCT25250CE", output)
        self.assertIn("NIFTY26OCT25400CE", output)
        self.assertIn("SELECTED", output)
        self.assertIn("REJECTED", output)

    def test_terminal_rich_rendering_no_trade(self):
        """Action Plan Task 5.2: Verify terminal UI renders STAND BY / NO TRADE cleanly."""
        signals = _build_test_signals()
        report = AuditReport(
            verdict="TIER 0: NO TRADE (Capital Preservation Active)",
            selected_strategy_name=None,
            selected_proposal=None,
            entries=[
                AuditEntry("Debit Spread", "REJECTED", 0.0, "REJECTED: KER too low"),
                AuditEntry("Credit Spread", "REJECTED", 0.0, "REJECTED: Low IV"),
                AuditEntry("Iron Condor", "REJECTED", 0.0, "REJECTED: Wide spread"),
            ],
        )

        output = render_dashboard_to_string(
            signals=signals,
            report=report,
            basket=None,
            weekday_window_status="Outside optimal windows",
            is_optimal_window=False,
        )

        self.assertIn("CAPITAL PRESERVATION", output)
        self.assertIn("STAND BY", output)
        self.assertIn("Bankroll: ₹2,00,000.00 intact", output)

    def test_telegram_trade_card_formatting(self):
        """Action Plan Task 5.3: Verify Telegram markdown trade card formatting."""
        signals = _build_test_signals()
        prop = _build_test_proposal()
        report = AuditReport(
            verdict="FINAL VERDICT: NIFTY BULL CALL SPREAD SELECTED",
            selected_strategy_name="Debit Spread",
            selected_proposal=prop,
            entries=[
                AuditEntry("Debit Spread", "SELECTED", 782.25, "PASSED: Trend confirmed", prop),
                AuditEntry("Credit Spread", "REJECTED", 180.0, "REJECTED: Low IV"),
                AuditEntry("Iron Condor", "REJECTED", -410.0, "REJECTED: Trend active"),
            ],
        )
        basket = build_kite_basket(prop)

        card = format_telegram_trade_card(signals=signals, report=report, basket=basket)

        self.assertIn("NIFTY OPTIONS TRADE RECOMMENDATION", card)
        self.assertIn("NIFTY BULL CALL DEBIT SPREAD", card)
        self.assertIn("Basket Execution Sequence", card)
        self.assertIn("Tap Here to Execute Zerodha Basket", card)

    def test_telegram_dispatcher_mock(self):
        """Action Plan Task 5.3: Verify stdlib urllib Telegram dispatcher."""
        # Unconfigured tokens should return False safely without error
        res = send_telegram_message("Test message", bot_token="", chat_id="")
        self.assertFalse(res)

        # Mocking successful HTTP 200 response
        mock_resp = MagicMock()
        mock_resp.getcode.return_value = 200
        mock_resp.__enter__.return_value = mock_resp

        with patch("core.ui.telegram_push.urlopen", return_value=mock_resp) as mock_url:
            ok = send_telegram_message(
                "Hello Quant",
                bot_token="fake_bot_token",
                chat_id="fake_chat_id",
            )
            self.assertTrue(ok)
            mock_url.assert_called_once()


if __name__ == "__main__":
    unittest.main()
