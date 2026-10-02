"""Collateral & Capital Optimization Module (Phase 1).

Implements capital allocation, SEBI cash-equivalent margin calculations,
haircut mechanics, and risk-free yield accrual for idle capital according
to SEBI F&O margin rules and COLLATERAL_PLAYBOOK.md.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config


@dataclass(frozen=True)
class CollateralConfig:
    """Configuration for collateral allocation and yield parameters."""

    total_capital: float = config.TOTAL_CAPITAL  # Default ₹2,00,000
    fund_allocation: float = 180_000.0          # Overnight/Liquid fund purchase
    cash_buffer: float = 20_000.0               # Unpledged cash reserve
    haircut_pct: float = 0.10                   # 10% standard broker haircut on fund units
    annual_yield_pct: float = 0.053             # ~5.3% gross category yield (Oct 2026 era)


class CollateralManager:
    """Manages margin pledge calculations, SEBI 50:50 cash checks, and yield tracking."""

    def __init__(self, cfg: CollateralConfig | None = None) -> None:
        self.cfg = cfg or CollateralConfig()
        if abs(self.cfg.fund_allocation + self.cfg.cash_buffer - self.cfg.total_capital) > 1e-4:
            raise ValueError(
                f"Fund allocation (₹{self.cfg.fund_allocation:,.2f}) + "
                f"cash buffer (₹{self.cfg.cash_buffer:,.2f}) must equal total capital "
                f"(₹{self.cfg.total_capital:,.2f})"
            )

    @property
    def pledged_margin_value(self) -> float:
        """Margin credit received after broker haircut on pledged units."""
        return self.cfg.fund_allocation * (1.0 - self.cfg.haircut_pct)

    @property
    def total_usable_margin(self) -> float:
        """Total trading margin = Pledged fund value (post-haircut) + Cash buffer."""
        return self.pledged_margin_value + self.cfg.cash_buffer

    @property
    def cash_equivalent_margin(self) -> float:
        """SEBI cash-equivalent margin.

        Under SEBI F&O collateral circulars, Liquid and Overnight mutual funds
        pledged via approved depositories count toward the 50% CASH COMPONENT.
        Thus, 100% of usable margin qualifies as cash-equivalent.
        """
        return self.total_usable_margin

    def gross_annual_yield(self) -> float:
        """Expected gross annual interest/NAV appreciation on fund + cash."""
        # Fund yields annual_yield_pct; cash buffer in bank sweeps yields ~3.0%
        fund_yield = self.cfg.fund_allocation * self.cfg.annual_yield_pct
        cash_yield = self.cfg.cash_buffer * 0.030
        return fund_yield + cash_yield

    def gross_monthly_yield(self) -> float:
        """Expected average monthly gross return."""
        return self.gross_annual_yield() / 12.0

    def net_annual_yield(self, tax_bracket: float = 0.30) -> float:
        """Expected net annual yield after debt-fund slab taxation (post-Apr 2023 rules)."""
        gross = self.gross_annual_yield()
        return gross * (1.0 - tax_bracket)

    def check_margin_requirement(
        self,
        required_margin: float,
        requires_cash_ratio: float = 0.50,
    ) -> Tuple[bool, str, Dict[str, float]]:
        """Validates if an order's margin requirement is supported under SEBI rules.

        SEBI requires at least 50% of the margin for F&O positions to come from cash
        or cash-equivalents (Liquid/Overnight funds qualify as cash-equivalents).
        """
        usable = self.total_usable_margin
        if required_margin > usable:
            shortfall = required_margin - usable
            return (
                False,
                f"Margin shortfall: Order requires ₹{required_margin:,.2f}, usable is ₹{usable:,.2f} (short by ₹{shortfall:,.2f})",
                {"required": required_margin, "usable": usable, "shortfall": shortfall},
            )

        # Cash-equivalent component check
        required_cash = required_margin * requires_cash_ratio
        available_cash_equiv = self.cash_equivalent_margin

        if required_cash > available_cash_equiv:
            return (
                False,
                f"SEBI 50:50 cash violation: Required cash-equiv ₹{required_cash:,.2f} exceeds available ₹{available_cash_equiv:,.2f}",
                {"required_cash": required_cash, "available_cash": available_cash_equiv},
            )

        headroom = usable - required_margin
        return (
            True,
            f"Approved: Required ₹{required_margin:,.2f} <= Usable ₹{usable:,.2f} (Headroom ₹{headroom:,.2f})",
            {"required": required_margin, "usable": usable, "headroom": headroom},
        )

    @staticmethod
    def estimate_straddle_margin(
        spot: float = 24_500.0,
        lot_size: Optional[int] = None,
        margin_pct: float = 0.0784,
    ) -> float:
        """Estimates SPAN + Exposure required margin for 1 short ATM straddle.

        With exchange spread margin benefit, short ATM straddle requires approx
        7.8% - 8.0% of total contract value (e.g. ~₹1,25,000 for Nifty spot 24,500
        in current regulatory Era 65).
        """
        qty = lot_size if lot_size is not None else config.get_nifty_lot_size()
        contract_value = spot * qty
        return round(contract_value * margin_pct, 2)


if __name__ == "__main__":
    mgr = CollateralManager()
    cfg = mgr.cfg
    print("=" * 65)
    print("  PHASE 1 COLLATERAL & CAPITAL OPTIMIZATION DASHBOARD (Rs. 2L BANKROLL)")
    print("=" * 65)
    print(f"Total Bankroll Capital:        Rs. {cfg.total_capital:>10,.2f}")
    print(f"  |-- Overnight Fund (Growth): Rs. {cfg.fund_allocation:>10,.2f} (90.0%)")
    print(f"  +-- Cash Buffer (Sweeps):    Rs. {cfg.cash_buffer:>10,.2f} (10.0%)")
    print("-" * 65)
    print("SEBI COLLATERAL MARGIN ACCOUNTING:")
    print(f"  Fund Haircut (10% standard): Rs. {cfg.fund_allocation * cfg.haircut_pct:>10,.2f}")
    print(f"  Pledged Collateral Margin:   Rs. {mgr.pledged_margin_value:>10,.2f}")
    print(f"  Unpledged Cash Buffer:       Rs. {cfg.cash_buffer:>10,.2f}")
    print(f"  Total Usable Margin:         Rs. {mgr.total_usable_margin:>10,.2f} (91.0% efficiency)")
    print(f"  SEBI Cash-Equivalent Margin: Rs. {mgr.cash_equivalent_margin:>10,.2f} (100% compliant)")
    print("-" * 65)
    print("YIELD PROJECTIONS (OCT-2026 RATES, ~5.3% GROSS):")
    gross_yr = mgr.gross_annual_yield()
    print(f"  Gross Annual Yield:          Rs. {gross_yr:>10,.2f} (~Rs. {mgr.gross_monthly_yield():.2f}/mo)")
    for slab in (0.30, 0.20, 0.05):
        net_yr = mgr.net_annual_yield(tax_bracket=slab)
        print(f"  Net Post-Tax ({slab*100:2.0f}% slab):     Rs. {net_yr:>10,.2f} (~Rs. {net_yr/12.0:.2f}/mo)")
    print("-" * 65)
    print("EXECUTION HEADROOM (1-LOT NIFTY ATM STRADDLE, ERA 65):")
    nifty_margin_req = mgr.estimate_straddle_margin(spot=24_500.0, lot_size=65)
    approved, msg, data = mgr.check_margin_requirement(nifty_margin_req)
    print(f"  Estimated Margin (1-lot):    Rs. {nifty_margin_req:>10,.2f}")
    print(f"  Status:                      {'APPROVED' if approved else 'REJECTED'}")
    print(f"  Available Headroom:          Rs. {data.get('headroom', 0.0):>10,.2f} ({data.get('headroom', 0.0)/nifty_margin_req*100:.1f}% surplus)")
    print("=" * 65)


