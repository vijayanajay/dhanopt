"""Range-Bound Neutral Iron Condor Strategy (4-Leg Credit Spread).

Used on low-efficiency, choppy sessions:
- Price inside ORB-30 (no breakout)
- KER < 0.35 (noise regime)
- Flat VWAP benchmark (|Slope| <= 0.01%/15m)
- Balanced Put and Call walls flanking spot
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import config
from core.auditors.rule_gatekeeper import TradeProposal
from core.feeds.base import OptionChainSnapshot, OptionContract
from core.friction.zerodha import OptionLeg, calculate_friction
from core.signals import MarketSignals
from core.strategies.base import BaseStrategy, get_calibrated_strategy_edge


class IronCondorStrategy(BaseStrategy):
    """4-Leg Neutral Iron Condor (OTM Short Wings + Deep OTM Long Hedges)."""

    def __init__(self) -> None:
        super().__init__(name="Iron Condor")

    def evaluate_gates(self, signals: MarketSignals) -> Tuple[bool, str]:
        """Evaluates whether market signals support a range-bound neutral Iron Condor."""
        ker = signals.ker.ker
        orb = signals.orb
        slope = signals.vwap.slope_15m

        # Gate 1: KER chop threshold check (Directional trend breaches Iron Condor)
        if ker >= 0.35:
            return False, f"Directional breakout detected; KER breaches max chop threshold ({ker:.2f} >= 0.35)"

        # Gate 2: ORB-30 boundary check
        if orb.is_breakout:
            return False, f"Price broke outside ORB-30 range ({orb.status}); breaches range-bound condition"

        # Gate 3: Flat VWAP institutional benchmark check
        if abs(slope) > 0.01:
            return False, f"VWAP slope ({slope:+.3f}%) exceeds flat equilibrium threshold (+/-0.01%/15m)"

        return True, f"PASSED: Price inside ORB-30, flat VWAP slope ({slope:+.3f}%), KER {ker:.2f} < 0.35"

    def build_proposal(
        self,
        signals: MarketSignals,
        chain: OptionChainSnapshot,
        lots: int = 1,
    ) -> Optional[TradeProposal]:
        """Constructs 4-leg Iron Condor with strict Hedge-First execution ordering."""
        atm = chain.atm_strike()
        qty = lots * config.NIFTY_LOT_SIZE

        available = sorted(chain.strikes())
        if not available:
            return None

        # Strike Placement:
        # Short Put at or below Put Wall (or ATM - 150)
        target_short_put = min(atm - 150.0, signals.oi.put_wall)
        pe_shorts = [s for s in available if s <= target_short_put]
        short_put_strike = pe_shorts[-1] if pe_shorts else (available[1] if len(available) > 1 else atm - 150.0)

        pe_hedges = [s for s in available if s < short_put_strike]
        hedge_put_strike = pe_hedges[-1] if pe_hedges else short_put_strike - 150.0

        # Short Call at or above Call Wall (or ATM + 150)
        target_short_call = max(atm + 150.0, signals.oi.call_wall)
        ce_shorts = [s for s in available if s >= target_short_call]
        short_call_strike = ce_shorts[0] if ce_shorts else (available[-2] if len(available) > 1 else atm + 150.0)

        ce_hedges = [s for s in available if s > short_call_strike]
        hedge_call_strike = ce_hedges[0] if ce_hedges else short_call_strike + 150.0

        # Retrieve contracts
        short_pe = chain.get_contract(short_put_strike, "PE")
        hedge_pe = chain.get_contract(hedge_put_strike, "PE")
        short_ce = chain.get_contract(short_call_strike, "CE")
        hedge_ce = chain.get_contract(hedge_call_strike, "CE")

        if not (short_pe and hedge_pe and short_ce and hedge_ce):
            return None

        short_pe_price = short_pe.bid if short_pe.bid > 0 else short_pe.ltp
        hedge_pe_price = hedge_pe.ask if hedge_pe.ask > 0 else hedge_pe.ltp
        short_ce_price = short_ce.bid if short_ce.bid > 0 else short_ce.ltp
        hedge_ce_price = hedge_ce.ask if hedge_ce.ask > 0 else hedge_ce.ltp

        put_credit = max(0.0, short_pe_price - hedge_pe_price)
        call_credit = max(0.0, short_ce_price - hedge_ce_price)
        total_credit = put_credit + call_credit

        if total_credit <= 1.0:
            return None

        # Risk & Profit Rules (BRD 4.1):
        # Stop-loss: 1.4x of total net credit collected, hard capped at capital daily loss limit
        # Profit target: 50% of total credit collected
        max_risk_rupees = min(round(1.40 * total_credit * qty, 2), config.MAX_DAILY_LOSS)
        target_profit_rupees = round(0.50 * total_credit * qty, 2)

        # STRICT EXECUTION SEQUENCING (BRD 5.1):
        # 1. Buy Long Put Hedge (Leg 1)
        # 2. Buy Long Call Hedge (Leg 2)
        # 3. Sell Short Put Wing (Leg 3)
        # 4. Sell Short Call Wing (Leg 4)
        legs = [
            OptionLeg(
                strike=hedge_put_strike,
                option_type="PE",
                action="BUY",
                entry_price=hedge_pe_price,
                target_price=max(0.2, hedge_pe_price * 0.20),
                stop_price=hedge_pe_price + 15.0,
                lots=lots,
                delta=hedge_pe.delta,
                symbol=hedge_pe.symbol,
            ),
            OptionLeg(
                strike=hedge_call_strike,
                option_type="CE",
                action="BUY",
                entry_price=hedge_ce_price,
                target_price=max(0.2, hedge_ce_price * 0.20),
                stop_price=hedge_ce_price + 15.0,
                lots=lots,
                delta=hedge_ce.delta,
                symbol=hedge_ce.symbol,
            ),
            OptionLeg(
                strike=short_put_strike,
                option_type="PE",
                action="SELL",
                entry_price=short_pe_price,
                target_price=max(0.5, short_pe_price * 0.50),
                stop_price=short_pe_price + (total_credit * 0.70),
                lots=lots,
                delta=short_pe.delta,
                symbol=short_pe.symbol,
            ),
            OptionLeg(
                strike=short_call_strike,
                option_type="CE",
                action="SELL",
                entry_price=short_ce_price,
                target_price=max(0.5, short_ce_price * 0.50),
                stop_price=short_ce_price + (total_credit * 0.70),
                lots=lots,
                delta=short_ce.delta,
                symbol=short_ce.symbol,
            ),
        ]

        friction = calculate_friction(legs)
        # Probability of achieving 50% credit decay target before stop-loss:
        # For a delta-neutral 4-leg condor with early 50% profit target, empirical
        # probability of profit scales as: P_target ~ 1.0 - 0.70 * (|delta_put| + |delta_call|)
        wing_delta_sum = abs(short_pe.delta) + abs(short_ce.delta)
        target_p_win = max(0.40, min(0.85, 1.0 - (0.70 * wing_delta_sum)))
        win_rate = round(target_p_win, 3)
        gross_ev, net_ev, payoff = self.calculate_ev(
            win_rate=win_rate,
            target_profit=target_profit_rupees,
            max_loss=max_risk_rupees,
            friction_rupees=friction.total_rupees,
        )

        return TradeProposal(
            strategy_name="Nifty Neutral Iron Condor",
            underlying="NIFTY",
            expiry=chain.expiry,
            legs=legs,
            max_loss=max_risk_rupees,
            target_profit=target_profit_rupees,
            win_rate=win_rate,
            net_debit_or_credit=round(total_credit, 2),
            is_credit=True,
            friction=friction,
            gross_ev=gross_ev,
            net_ev=net_ev,
            payoff_ratio=payoff,
            contracts=[hedge_pe, hedge_ce, short_pe, short_ce],
        )
