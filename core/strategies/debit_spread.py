"""Directional Debit Vertical Spread Strategy (Bull Call / Bear Put).

Used when market exhibits high directional efficiency (KER > 0.55), confirmed ORB-30
breakout with volume, institutional benchmark slope dominance, and normal/cheap volatility.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import config
from core.auditors.rule_gatekeeper import TradeProposal
from core.feeds.base import OptionChainSnapshot, OptionContract
from core.friction.zerodha import OptionLeg, calculate_friction
from core.signals import MarketSignals
from core.strategies.base import BaseStrategy


class DebitSpreadStrategy(BaseStrategy):
    """Directional Debit Vertical Spread (Bull Call or Bear Put)."""

    def __init__(self) -> None:
        super().__init__(name="Debit Spread")

    def evaluate_gates(self, signals: MarketSignals) -> Tuple[bool, str]:
        """Evaluates whether market signals support a directional debit spread."""
        price = signals.spot_price
        vwap = signals.vwap.vwap
        slope = signals.vwap.slope_15m
        ker = signals.ker.ker
        orb = signals.orb
        vix = signals.vix_iv.vix
        iv_spread = signals.vix_iv.iv_spread

        # Gate 1: KER directional efficiency check
        if ker <= 0.55:
            return False, f"KER ({ker:.2f}) below directional hurdle (0.55); path is too noisy"

        # Gate 2: Volatility pricing check (debit spreads favored when premiums are not rich)
        if vix > 16.0 and iv_spread > 2.0:
            return False, f"Volatility is elevated (VIX {vix:.1f}, IV Spread +{iv_spread:.1f}); favors credit selling"

        # Gate 3: Directional alignment (Bullish vs Bearish)
        if orb.status == "BULLISH_BREAKOUT" or (price > vwap and slope > 0.02):
            if price <= vwap:
                return False, f"Price (₹{price:,.1f}) below VWAP (₹{vwap:,.1f}); breaks bullish alignment"
            if slope <= 0.02:
                return False, f"VWAP slope ({slope:+.3f}%) lacks bullish institutional velocity (> +0.02%)"
            return True, f"PASSED: Bullish breakout confirmed, KER {ker:.2f} > 0.55, VWAP slope {slope:+.3f}%/15m"

        elif orb.status == "BEARISH_BREAKDOWN" or (price < vwap and slope < -0.02):
            if price >= vwap:
                return False, f"Price (₹{price:,.1f}) above VWAP (₹{vwap:,.1f}); breaks bearish alignment"
            if slope >= -0.02:
                return False, f"VWAP slope ({slope:+.3f}%) lacks bearish institutional velocity (< -0.02%)"
            return True, f"PASSED: Bearish breakdown confirmed, KER {ker:.2f} > 0.55, VWAP slope {slope:+.3f}%/15m"

        return False, f"No confirmed ORB breakout and VWAP slope ({slope:+.3f}%) is in equilibrium"

    def build_proposal(
        self,
        signals: MarketSignals,
        chain: OptionChainSnapshot,
        lots: int = 1,
    ) -> Optional[TradeProposal]:
        """Constructs Bull Call or Bear Put trade proposal based on prevailing trend."""
        is_bullish = signals.spot_price > signals.vwap.vwap
        atm = chain.atm_strike()
        qty = lots * config.NIFTY_LOT_SIZE
        opt_type = "CE" if is_bullish else "PE"

        # Long Leg: ATM Strike
        long_strike = atm
        # Short Leg: OTM Strike 150 pts away
        short_strike = atm + 150.0 if is_bullish else atm - 150.0

        long_contract = chain.get_contract(long_strike, opt_type)
        short_contract = chain.get_contract(short_strike, opt_type)

        if not long_contract or not short_contract:
            return None

        long_price = long_contract.ask if long_contract.ask > 0 else long_contract.ltp
        short_price = short_contract.bid if short_contract.bid > 0 else short_contract.ltp
        net_debit = long_price - short_price

        if net_debit <= 0:
            return None

        spread_width = abs(short_strike - long_strike)
        
        # Risk & Profit Rules (BRD 4.1):
        # Stop-loss: 35% of net debit paid
        # Profit target: 70% of max spread profit (spread width - net debit)
        max_risk_rupees = round(0.35 * net_debit * qty, 2)
        target_profit_rupees = round(0.70 * (spread_width - net_debit) * qty, 2)

        legs = [
            OptionLeg(
                strike=long_strike,
                option_type=opt_type,
                action="BUY",
                entry_price=long_price,
                target_price=long_price + (spread_width - net_debit) * 0.70,
                stop_price=max(0.5, long_price - net_debit * 0.35),
                lots=lots,
                delta=long_contract.delta,
                symbol=long_contract.symbol,
            ),
            OptionLeg(
                strike=short_strike,
                option_type=opt_type,
                action="SELL",
                entry_price=short_price,
                target_price=max(0.5, short_price * 0.30),
                stop_price=short_price + net_debit * 0.35,
                lots=lots,
                delta=short_contract.delta,
                symbol=short_contract.symbol,
            ),
        ]

        friction = calculate_friction(legs)
        win_rate = 0.58 if signals.orb.is_breakout else 0.56
        gross_ev, net_ev, payoff = self.calculate_ev(
            win_rate=win_rate,
            target_profit=target_profit_rupees,
            max_loss=max_risk_rupees,
            friction_rupees=friction.total_rupees,
        )

        direction_name = "Bull Call" if is_bullish else "Bear Put"
        return TradeProposal(
            strategy_name=f"Nifty {direction_name} Debit Spread",
            underlying="NIFTY",
            expiry=chain.expiry,
            legs=legs,
            max_loss=max_risk_rupees,
            target_profit=target_profit_rupees,
            win_rate=win_rate,
            net_debit_or_credit=round(net_debit, 2),
            is_credit=False,
            friction=friction,
            gross_ev=gross_ev,
            net_ev=net_ev,
            payoff_ratio=payoff,
            contracts=[long_contract, short_contract],
        )
