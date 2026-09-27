"""Deterministic Rule Gatekeeper (Zero-AI Risk & Edge Auditor).

Enforces institutional sanity boundaries in sub-microsecond pure Python arithmetic:
1. Capital Cap: Max loss <= ₹2,500 (1.25% of bankroll).
2. Liquidity Veto: Strike OI >= 100,000 and Bid-Ask Spread <= 1.5 pts.
3. Economic Hurdle: Expected Gross Profit >= 2.0x Friction Cost (3.0x off-window).
4. Edge Hurdle: Out-of-sample win rate P_win >= 55%.
5. Circuit Breakers: Daily loss cap (₹2,500) and monthly drawdown cap (₹10,000).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import config
from core.feeds.base import OptionContract
from core.friction.zerodha import FrictionBreakdown, OptionLeg


@dataclass(slots=True)
class TradeProposal:
    """Standardized representation of a candidate trade structure."""
    strategy_name: str
    underlying: str
    expiry: str
    legs: List[OptionLeg]
    max_loss: float
    target_profit: float
    win_rate: float
    net_debit_or_credit: float
    is_credit: bool
    friction: FrictionBreakdown
    gross_ev: float
    net_ev: float
    payoff_ratio: float
    contracts: List[OptionContract] = field(default_factory=list)


@dataclass(slots=True)
class GateResult:
    """Outcome of RuleGatekeeper deterministic validation."""
    passed: bool
    veto_reason: Optional[str] = None
    veto_code: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_vetoed(self) -> bool:
        return not self.passed


class RuleGatekeeper:
    """Deterministic, sub-microsecond risk and economic edge gatekeeper."""

    def __init__(
        self,
        max_daily_loss: float = config.MAX_DAILY_LOSS,
        min_win_rate: float = config.MIN_WIN_RATE,
        min_strike_oi: int = 100_000,
        max_bid_ask_spread: float = 1.5,
        economic_hurdle_ratio: float = config.ECONOMIC_HURDLE_RATIO,
        off_window_hurdle_ratio: float = config.OFF_WINDOW_HURDLE_RATIO,
        monthly_drawdown_cap: float = config.MONTHLY_DRAWDOWN_CAP,
    ) -> None:
        self.max_daily_loss = max_daily_loss
        self.min_win_rate = min_win_rate
        self.min_strike_oi = min_strike_oi
        self.max_bid_ask_spread = max_bid_ask_spread
        self.economic_hurdle_ratio = economic_hurdle_ratio
        self.off_window_hurdle_ratio = off_window_hurdle_ratio
        self.monthly_drawdown_cap = monthly_drawdown_cap

    def validate(
        self,
        proposal: TradeProposal,
        current_daily_loss: float = 0.0,
        current_monthly_drawdown: float = 0.0,
        is_optimal_window: bool = True,
    ) -> GateResult:
        """Validates a candidate trade against all deterministic non-negotiables."""
        
        # Circuit Breaker 1: Monthly drawdown cap hit
        if current_monthly_drawdown >= self.monthly_drawdown_cap:
            return GateResult(
                passed=False,
                veto_code="DRAWDOWN_CAP",
                veto_reason=f"Monthly drawdown (₹{current_monthly_drawdown:,.2f}) breaches cap of ₹{self.monthly_drawdown_cap:,.2f}",
                details={"current_monthly_drawdown": current_monthly_drawdown, "cap": self.monthly_drawdown_cap},
            )

        # Circuit Breaker 2: Daily loss limit already reached
        if current_daily_loss >= self.max_daily_loss:
            return GateResult(
                passed=False,
                veto_code="DAILY_LOSS_LIMIT",
                veto_reason=f"Daily loss (₹{current_daily_loss:,.2f}) reaches hard stop of ₹{self.max_daily_loss:,.2f}",
                details={"current_daily_loss": current_daily_loss, "max_daily_loss": self.max_daily_loss},
            )

        # VETO 1: Max loss exceeds single-trade capital cap (₹2,500)
        effective_max_loss = proposal.max_loss
        remaining_daily_budget = self.max_daily_loss - current_daily_loss
        if effective_max_loss > remaining_daily_budget:
            return GateResult(
                passed=False,
                veto_code="CAPITAL_CAP",
                veto_reason=f"Trade max loss (₹{effective_max_loss:,.2f}) breaches daily budget of ₹{remaining_daily_budget:,.2f}",
                details={"max_loss": effective_max_loss, "remaining_budget": remaining_daily_budget},
            )

        # VETO 2: Liquidity Verification on all option contracts
        if proposal.contracts:
            for c in proposal.contracts:
                if c.oi < self.min_strike_oi:
                    return GateResult(
                        passed=False,
                        veto_code="LIQUIDITY_OI",
                        veto_reason=f"Strike {c.strike} {c.option_type} OI ({c.oi:,}) below minimum threshold of {self.min_strike_oi:,}",
                        details={"strike": c.strike, "oi": c.oi, "min_oi": self.min_strike_oi},
                    )
                if c.bid_ask_spread > self.max_bid_ask_spread:
                    return GateResult(
                        passed=False,
                        veto_code="LIQUIDITY_SPREAD",
                        veto_reason=f"Strike {c.strike} {c.option_type} bid-ask spread ({c.bid_ask_spread:.2f} pts) exceeds max allowable {self.max_bid_ask_spread:.2f} pts",
                        details={"strike": c.strike, "spread": c.bid_ask_spread, "max_spread": self.max_bid_ask_spread},
                    )

        # VETO 3: Economic Hurdle Rate (Expected Gross Profit >= N * Friction Cost)
        hurdle_ratio = self.economic_hurdle_ratio if is_optimal_window else self.off_window_hurdle_ratio
        min_required_profit = proposal.friction.total_rupees * hurdle_ratio
        expected_gross_profit = proposal.win_rate * proposal.target_profit

        if expected_gross_profit < min_required_profit:
            return GateResult(
                passed=False,
                veto_code="ECONOMIC_HURDLE",
                veto_reason=f"Expected profit (₹{expected_gross_profit:,.2f}) fails {hurdle_ratio:.1f}x fee hurdle (₹{min_required_profit:,.2f})",
                details={
                    "expected_gross_profit": round(expected_gross_profit, 2),
                    "friction": proposal.friction.total_rupees,
                    "required_hurdle": round(min_required_profit, 2),
                    "hurdle_ratio": hurdle_ratio,
                },
            )

        # VETO 4: Edge Hurdle Rate (P_win >= 55%)
        if proposal.win_rate < self.min_win_rate:
            return GateResult(
                passed=False,
                veto_code="EDGE_HURDLE",
                veto_reason=f"Win probability ({proposal.win_rate * 100:.1f}%) is below minimum edge hurdle of {self.min_win_rate * 100:.1f}%",
                details={"win_rate": proposal.win_rate, "min_win_rate": self.min_win_rate},
            )

        # All deterministic gates passed
        return GateResult(
            passed=True,
            veto_reason=None,
            veto_code=None,
            details={
                "max_loss": proposal.max_loss,
                "target_profit": proposal.target_profit,
                "win_rate": proposal.win_rate,
                "net_ev": proposal.net_ev,
                "friction": proposal.friction.total_rupees,
            },
        )
