"""Comparative 3-Strategy Elimination & Selection Audit Engine.

Evaluates all 3 core strategies (Debit Spread, Credit Spread, Iron Condor) simultaneously.
Enforces that every execution produces an unambiguous audit explaining why one strategy won
and why the other two were eliminated. If no strategy satisfies edge hurdles, enforces
TIER 0: NO TRADE for capital preservation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from core.auditors.rule_gatekeeper import GateResult, RuleGatekeeper, TradeProposal
from core.feeds.base import OptionChainSnapshot
from core.signals import MarketSignals
from core.strategies.base import BaseStrategy
from core.strategies.credit_spread import CreditSpreadStrategy
from core.strategies.debit_spread import DebitSpreadStrategy
from core.strategies.iron_condor import IronCondorStrategy


@dataclass(slots=True)
class AuditEntry:
    """Individual strategy evaluation audit record."""
    strategy_name: str
    status: str       # "SELECTED", "REJECTED", "QUALIFIED"
    ev_score: float
    reason: str
    proposal: Optional[TradeProposal] = None


@dataclass(slots=True)
class AuditReport:
    """Consolidated comparative audit report across all 3 strategies."""
    verdict: str
    selected_strategy_name: Optional[str]
    selected_proposal: Optional[TradeProposal]
    entries: List[AuditEntry]

    @property
    def is_trade_approved(self) -> bool:
        return self.selected_proposal is not None

    def get_entry(self, strategy_name: str) -> Optional[AuditEntry]:
        for e in self.entries:
            if strategy_name.lower() in e.strategy_name.lower():
                return e
        return None


class ComparativeAuditEngine:
    """Orchestrates simultaneous 3-strategy evaluation and competitive elimination."""

    def __init__(
        self,
        gatekeeper: Optional[RuleGatekeeper] = None,
        strategies: Optional[List[BaseStrategy]] = None,
    ) -> None:
        self.gatekeeper = gatekeeper or RuleGatekeeper()
        self.strategies = strategies or [
            DebitSpreadStrategy(),
            CreditSpreadStrategy(),
            IronCondorStrategy(),
        ]

    def run_audit(
        self,
        signals: MarketSignals,
        chain: OptionChainSnapshot,
        lots: int = 1,
        current_daily_loss: float = 0.0,
        current_monthly_drawdown: float = 0.0,
        is_optimal_window: bool = True,
    ) -> AuditReport:
        """Evaluates all strategies, applies gatekeeper vetos, and ranks by net EV."""
        preliminary_entries: List[AuditEntry] = []

        for strat in self.strategies:
            # Step 1: Microstructure Gate Evaluation
            gates_passed, gate_reason = strat.evaluate_gates(signals)
            if not gates_passed:
                preliminary_entries.append(
                    AuditEntry(
                        strategy_name=strat.name,
                        status="REJECTED",
                        ev_score=0.0,
                        reason=f"REJECTED: {gate_reason}",
                        proposal=None,
                    )
                )
                continue

            # Step 2: Strike Selection & Proposal Construction
            proposal = strat.build_proposal(signals, chain, lots=lots)
            if not proposal:
                preliminary_entries.append(
                    AuditEntry(
                        strategy_name=strat.name,
                        status="REJECTED",
                        ev_score=0.0,
                        reason="REJECTED: Strike selection failed (insufficient contracts or inverted spread)",
                        proposal=None,
                    )
                )
                continue

            # Step 3: Deterministic Rule Gatekeeper Validation
            gate_res = self.gatekeeper.validate(
                proposal=proposal,
                current_daily_loss=current_daily_loss,
                current_monthly_drawdown=current_monthly_drawdown,
                is_optimal_window=is_optimal_window,
            )

            if gate_res.is_vetoed:
                preliminary_entries.append(
                    AuditEntry(
                        strategy_name=strat.name,
                        status="REJECTED",
                        ev_score=proposal.net_ev,
                        reason=f"REJECTED: {gate_res.veto_reason}",
                        proposal=proposal,
                    )
                )
            else:
                preliminary_entries.append(
                    AuditEntry(
                        strategy_name=strat.name,
                        status="QUALIFIED",
                        ev_score=proposal.net_ev,
                        reason=f"PASSED: {gate_reason}",
                        proposal=proposal,
                    )
                )

        # Step 4: Competitive Elimination & Winner Selection
        qualified = [e for e in preliminary_entries if e.status == "QUALIFIED" and e.ev_score > 0.0]

        if not qualified:
            # All strategies rejected -> TIER 0: NO TRADE
            return AuditReport(
                verdict="TIER 0: NO TRADE (Capital Preservation Active - No strategy passed hurdle)",
                selected_strategy_name=None,
                selected_proposal=None,
                entries=preliminary_entries,
            )

        # Winner is the qualified strategy with the highest friction-adjusted Net EV
        winner = max(qualified, key=lambda e: e.ev_score)

        final_entries: List[AuditEntry] = []
        for e in preliminary_entries:
            if e.strategy_name == winner.strategy_name:
                final_entries.append(
                    AuditEntry(
                        strategy_name=e.strategy_name,
                        status="SELECTED",
                        ev_score=e.ev_score,
                        reason=e.reason,
                        proposal=e.proposal,
                    )
                )
            else:
                reason = e.reason
                if e.status == "QUALIFIED":
                    reason = f"REJECTED: Lower Net EV (+₹{e.ev_score:.2f}) than winner {winner.strategy_name} (+₹{winner.ev_score:.2f})"
                final_entries.append(
                    AuditEntry(
                        strategy_name=e.strategy_name,
                        status="REJECTED",
                        ev_score=e.ev_score,
                        reason=reason,
                        proposal=e.proposal,
                    )
                )

        return AuditReport(
            verdict=f"FINAL VERDICT: {winner.proposal.strategy_name.upper()} SELECTED (Net EV: +₹{winner.ev_score:,.2f})",
            selected_strategy_name=winner.strategy_name,
            selected_proposal=winner.proposal,
            entries=final_entries,
        )
