"""Abstract Base Strategy interface and common trade evaluation contracts.

Defines the structure for all quantitative options strategies:
- evaluate_gates(signals): Evaluates microstructure and regime filters.
- build_proposal(signals, chain, lots): Selects strikes, builds legs, and computes friction/EV.
- calculate_ev(win_rate, target_profit, max_loss, friction_rupees): Computes gross and net EV.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

import config
from core.auditors.rule_gatekeeper import TradeProposal
from core.feeds.base import OptionChainSnapshot, OptionContract
from core.friction.zerodha import FrictionBreakdown, OptionLeg, calculate_friction
from core.signals import MarketSignals

_CALIBRATED_EDGE_CACHE: Optional[Dict[str, Any]] = None


def get_calibrated_data() -> Dict[str, Any]:
    """Loads calibrated parameters and empirical edge tables with memory caching."""
    global _CALIBRATED_EDGE_CACHE
    if _CALIBRATED_EDGE_CACHE is None:
        if config.CALIBRATED_PARAMS_PATH.exists():
            try:
                with open(config.CALIBRATED_PARAMS_PATH, "r", encoding="utf-8") as f:
                    _CALIBRATED_EDGE_CACHE = json.load(f)
            except Exception:
                _CALIBRATED_EDGE_CACHE = {}
        else:
            _CALIBRATED_EDGE_CACHE = {}
    return _CALIBRATED_EDGE_CACHE


def get_calibrated_strategy_edge(strategy_name: str) -> Optional[Dict[str, Any]]:
    """Retrieves empirical 5-year edge statistics for a given strategy from Bhavcopy backtest.

    Fail-closed: Returns None if data is missing or strategy not found,
    signaling the caller to zero-rate the edge and trigger TIER 0 NO TRADE.
    """
    data = get_calibrated_data()
    strats = data.get("strategy_empirical_edge", {})
    for k, v in strats.items():
        if strategy_name.lower() in k.lower():
            return v
    return None


def get_calibrated_weekday_edge(weekday: str) -> Optional[Dict[str, Any]]:
    """Retrieves empirical 5-year edge statistics for a given weekday from Bhavcopy backtest.

    Fail-closed: Returns None if data is missing or weekday not found.
    """
    data = get_calibrated_data()
    days = data.get("weekday_empirical_edge", {})
    if weekday in days:
        return days[weekday]
    return None


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
