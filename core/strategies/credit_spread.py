"""Directional Credit Vertical Spread Strategy (Bull Put / Bear Call).

Used when market exhibits moderate trend supported by major Dealer OI Walls,
sufficient volatility premium (VIX >= 13, IV Spread >= +1.5), and controlled slope velocity.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import config
from core.auditors.rule_gatekeeper import TradeProposal
from core.feeds.base import OptionChainSnapshot, OptionContract
from core.friction.zerodha import OptionLeg, calculate_friction
from core.signals import MarketSignals
from core.strategies.base import BaseStrategy


class CreditSpreadStrategy(BaseStrategy):
    """Directional Credit Vertical Spread (Bull Put or Bear Call)."""

    def __init__(self) -> None:
        super().__init__(name="Credit Spread")

    def evaluate_gates(self, signals: MarketSignals) -> Tuple[bool, str]:
        """Evaluates whether market signals support a directional credit spread."""
        price = signals.spot_price
        vwap = signals.vwap.vwap
        slope = signals.vwap.slope_15m
        vix = signals.vix_iv.vix
        iv_spread = signals.vix_iv.iv_spread
        put_wall = signals.oi.put_wall
        call_wall = signals.oi.call_wall

        # Gate 1: Volatility richness check (collecting sufficient premium)
        if vix < 13.0 or iv_spread < 1.5:
            return False, f"IV Spread (+{iv_spread:.1f}) or VIX ({vix:.1f}) too low; insufficient credit collected"

        # Gate 2: Severe momentum veto (credit selling vetoed in explosive breakouts)
        if abs(slope) > 0.06:
            return False, f"VWAP slope ({slope:+.3f}%) is too aggressive for credit writing; risk of delta steamroll"

        # Gate 3: Wall alignment
        # Bull Put setup: Spot supported by Put Wall
        if price >= vwap and price >= (put_wall - 50.0):
            if abs(slope) < 0.005:
                return False, f"Slope ({slope:+.3f}%) is flat; market lacks directional drift for directional credit"
            return True, f"PASSED: Supported by Put Wall ({put_wall:,.0f}), moderate slope {slope:+.3f}%, rich IV spread +{iv_spread:.1f}"

        # Bear Call setup: Spot capped by Call Wall
        elif price <= vwap and price <= (call_wall + 50.0):
            if abs(slope) < 0.005:
                return False, f"Slope ({slope:+.3f}%) is flat; market lacks directional drift for directional credit"
            return True, f"PASSED: Capped by Call Wall ({call_wall:,.0f}), moderate slope {slope:+.3f}%, rich IV spread +{iv_spread:.1f}"

        return False, f"Spot (₹{price:,.1f}) not well positioned relative to Put Wall ({put_wall:,.0f}) or Call Wall ({call_wall:,.0f})"

    def build_proposal(
        self,
        signals: MarketSignals,
        chain: OptionChainSnapshot,
        lots: int = 1,
    ) -> Optional[TradeProposal]:
        """Constructs Bull Put or Bear Call trade proposal with hedge-leg first sequencing."""
        is_bullish = signals.spot_price >= signals.vwap.vwap
        atm = chain.atm_strike()
        qty = lots * config.NIFTY_LOT_SIZE
        opt_type = "PE" if is_bullish else "CE"

        if is_bullish:
            # Bull Put Spread: Sell Short Put at/below Put Wall (e.g. ATM - 100), Buy Deep OTM Hedge (ATM - 250)
            short_strike = min(atm - 100.0, signals.oi.put_wall)
            hedge_strike = short_strike - 150.0
        else:
            # Bear Call Spread: Sell Short Call at/above Call Wall (e.g. ATM + 100), Buy Deep OTM Hedge (ATM + 250)
            short_strike = max(atm + 100.0, signals.oi.call_wall)
            hedge_strike = short_strike + 150.0

        short_contract = chain.get_contract(short_strike, opt_type)
        hedge_contract = chain.get_contract(hedge_strike, opt_type)

        if not short_contract or not hedge_contract:
            return None

        short_price = short_contract.bid if short_contract.bid > 0 else short_contract.ltp
        hedge_price = hedge_contract.ask if hedge_contract.ask > 0 else hedge_contract.ltp
        net_credit = short_price - hedge_price

        if net_credit <= 0.5:
            return None

        # Risk & Profit Rules (BRD 4.1):
        # Stop-loss: 1.4x of credit received
        # Profit target: 65% credit decay
        max_risk_rupees = round(1.40 * net_credit * qty, 2)
        target_profit_rupees = round(0.65 * net_credit * qty, 2)

        # Execution Sequencing (BRD 5.1): HEDGE LEG FIRST (BUY), SHORT LEG SECOND (SELL)
        legs = [
            OptionLeg(
                strike=hedge_strike,
                option_type=opt_type,
                action="BUY",
                entry_price=hedge_price,
                target_price=max(0.2, hedge_price * 0.35),
                stop_price=hedge_price + 10.0,
                lots=lots,
                delta=hedge_contract.delta,
                symbol=hedge_contract.symbol,
            ),
            OptionLeg(
                strike=short_strike,
                option_type=opt_type,
                action="SELL",
                entry_price=short_price,
                target_price=max(0.5, short_price * 0.35),
                stop_price=short_price + (net_credit * 1.40),
                lots=lots,
                delta=short_contract.delta,
                symbol=short_contract.symbol,
            ),
        ]

        friction = calculate_friction(legs)
        win_rate = 0.64
        gross_ev, net_ev, payoff = self.calculate_ev(
            win_rate=win_rate,
            target_profit=target_profit_rupees,
            max_loss=max_risk_rupees,
            friction_rupees=friction.total_rupees,
        )

        direction_name = "Bull Put" if is_bullish else "Bear Call"
        return TradeProposal(
            strategy_name=f"Nifty {direction_name} Credit Spread",
            underlying="NIFTY",
            expiry=chain.expiry,
            legs=legs,
            max_loss=max_risk_rupees,
            target_profit=target_profit_rupees,
            win_rate=win_rate,
            net_debit_or_credit=round(net_credit, 2),
            is_credit=True,
            friction=friction,
            gross_ev=gross_ev,
            net_ev=net_ev,
            payoff_ratio=payoff,
            contracts=[hedge_contract, short_contract],
        )
