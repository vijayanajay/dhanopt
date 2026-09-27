"""Abstract Base Strategy interface and common trade evaluation contracts.

Defines the structure for all quantitative options strategies:
- evaluate_gates(signals): Evaluates microstructure and regime filters.
- build_proposal(signals, chain, lots): Selects strikes, builds legs, and computes friction/EV.
- calculate_ev(win_rate, target_profit, max_loss, friction_rupees): Computes gross and net EV.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

import config
from core.auditors.rule_gatekeeper import TradeProposal
from core.feeds.base import OptionChainSnapshot, OptionContract
from core.friction.zerodha import FrictionBreakdown, OptionLeg, calculate_friction
from core.signals import MarketSignals


class BaseStrategy(ABC):
    """Abstract base class for all quantitative options strategies."""

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def evaluate_gates(self, signals: MarketSignals) -> Tuple[bool, str]:
        """Evaluates whether current market regime satisfies strategy criteria.
        
        Returns:
            Tuple of (passed: bool, reason: str).
            If passed is False, reason must state the exact quantitative metric that failed.
        """
        pass

    @abstractmethod
    def build_proposal(
        self,
        signals: MarketSignals,
        chain: OptionChainSnapshot,
        lots: int = 1,
    ) -> Optional[TradeProposal]:
        """Selects strikes from OptionChainSnapshot, constructs legs, and calculates EV."""
        pass

    @staticmethod
    def calculate_ev(
        win_rate: float,
        target_profit: float,
        max_loss: float,
        friction_rupees: float,
    ) -> Tuple[float, float, float]:
        """Calculates Gross EV, Net EV, and Payoff Ratio b.
        
        Formula:
            Gross EV = (P_win * Target Profit) - ((1 - P_win) * Max Loss)
            Net EV = Gross EV - Friction
            b = Target Profit / Max Loss
        """
        gross_ev = (win_rate * target_profit) - ((1.0 - win_rate) * max_loss)
        net_ev = gross_ev - friction_rupees
        payoff_ratio = target_profit / max_loss if max_loss > 0 else 0.0
        return round(gross_ev, 2), round(net_ev, 2), round(payoff_ratio, 2)
