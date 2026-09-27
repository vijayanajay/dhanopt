"""Zerodha & Regulatory Friction Accounting Engine (Post-Oct 2024 SEBI Norms).

Calculates exact institutional friction breakdown for N-leg Nifty options trades:
- Brokerage: flat ₹20 per leg per executed order (round-trip: 2 * N * ₹20)
- STT: 0.1% on sell-side option premium turnover (revised Oct 1, 2024)
- Exchange Turnover: 0.0505% on total premium turnover
- SEBI Charges: ₹10 per crore (0.0001%) on total turnover
- Stamp Duty: 0.003% on buy-side premium turnover
- GST: 18% on (Brokerage + Exchange Turnover + SEBI)
- Slippage: 1.5 index points modeled buffer per leg
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

import config


@dataclass(slots=True)
class OptionLeg:
    """Represents an individual leg within an option strategy."""
    strike: float
    option_type: str      # "CE" or "PE"
    action: str           # "BUY" or "SELL"
    entry_price: float
    target_price: float = 0.0
    stop_price: float = 0.0
    lot_size: int = config.NIFTY_LOT_SIZE
    lots: int = 1
    iv: float = 0.0
    delta: float = 0.0
    symbol: str = ""

    @property
    def quantity(self) -> int:
        return self.lots * self.lot_size

    @property
    def is_buy(self) -> bool:
        return self.action.upper() == "BUY"

    @property
    def is_sell(self) -> bool:
        return self.action.upper() == "SELL"


@dataclass(slots=True)
class FrictionBreakdown:
    """Itemized transaction costs and regulatory friction."""
    brokerage: float
    stt: float
    exchange_turnover: float
    sebi_turnover: float
    stamp_duty: float
    gst: float
    slippage: float
    total_rupees: float
    points_equivalent: float

    def summary(self) -> dict:
        return {
            "brokerage": round(self.brokerage, 2),
            "stt": round(self.stt, 2),
            "exchange_turnover": round(self.exchange_turnover, 2),
            "sebi_turnover": round(self.sebi_turnover, 2),
            "stamp_duty": round(self.stamp_duty, 2),
            "gst": round(self.gst, 2),
            "slippage": round(self.slippage, 2),
            "total_rupees": round(self.total_rupees, 2),
            "points_equivalent": round(self.points_equivalent, 2),
        }


def calculate_friction(
    legs: Sequence[OptionLeg],
    slippage_pts_per_leg: float = config.SLIPPAGE_POINTS_PER_LEG,
) -> FrictionBreakdown:
    """Calculates exact post-Oct 2024 round-trip friction for a list of option legs."""
    if not legs:
        return FrictionBreakdown(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    num_legs = len(legs)
    total_qty = sum(leg.quantity for leg in legs)
    primary_qty = legs[0].quantity if legs else config.NIFTY_LOT_SIZE

    # 1. Brokerage: ₹20 per leg per executed side (entry + exit = 2 orders per leg)
    brokerage = num_legs * 2 * config.BROKERAGE_PER_LEG_PER_SIDE

    # Calculate buy and sell premium turnovers:
    # Every option position is round-trip:
    # - Long leg: BUY at entry, SELL at exit (modeled at target or entry)
    # - Short leg: SELL at entry, BUY at exit (modeled at target or entry)
    buy_turnover = 0.0
    sell_turnover = 0.0

    for leg in legs:
        entry_val = leg.entry_price * leg.quantity
        exit_val = (leg.target_price if leg.target_price > 0 else leg.entry_price) * leg.quantity

        if leg.is_buy:
            buy_turnover += entry_val
            sell_turnover += exit_val
        else:
            sell_turnover += entry_val
            buy_turnover += exit_val

    total_premium_turnover = buy_turnover + sell_turnover

    # 2. STT: 0.1% on sell-side option premium turnover (post-Oct 2024 SEBI)
    stt = sell_turnover * config.STT_SELL_RATE

    # 3. Exchange Turnover: 0.0505% on total premium turnover
    exchange = total_premium_turnover * config.EXCHANGE_TURNOVER_RATE

    # 4. SEBI Turnover: ₹10 per crore (0.0001%)
    sebi = total_premium_turnover * config.SEBI_TURNOVER_RATE

    # 5. Stamp Duty: 0.003% on buy-side turnover
    stamp = buy_turnover * config.STAMP_DUTY_BUY_RATE

    # 6. GST: 18% on (Brokerage + Exchange + SEBI)
    gst = (brokerage + exchange + sebi) * config.GST_RATE

    # 7. Modeled Slippage: 1.5 pts per leg on index quantity
    slippage = slippage_pts_per_leg * primary_qty * num_legs

    total_rupees = brokerage + stt + exchange + sebi + stamp + gst + slippage
    pts_equivalent = total_rupees / primary_qty if primary_qty > 0 else 0.0

    return FrictionBreakdown(
        brokerage=round(brokerage, 2),
        stt=round(stt, 2),
        exchange_turnover=round(exchange, 2),
        sebi_turnover=round(sebi, 2),
        stamp_duty=round(stamp, 2),
        gst=round(gst, 2),
        slippage=round(slippage, 2),
        total_rupees=round(total_rupees, 2),
        points_equivalent=round(pts_equivalent, 2),
    )


def estimate_spread_friction(
    num_legs: int,
    avg_premium: float = 80.0,
    lots: int = 1,
    slippage_pts: float = config.SLIPPAGE_POINTS_PER_LEG,
) -> FrictionBreakdown:
    """Fast estimation of friction for standard N-leg spreads."""
    qty = lots * config.NIFTY_LOT_SIZE
    dummy_legs = [
        OptionLeg(
            strike=25000.0 + i * 50,
            option_type="CE",
            action="BUY" if i % 2 == 0 else "SELL",
            entry_price=avg_premium,
            target_price=avg_premium * 0.7,
            lots=lots,
        )
        for i in range(num_legs)
    ]
    return calculate_friction(dummy_legs, slippage_pts_per_leg=slippage_pts)
