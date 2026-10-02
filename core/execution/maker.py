"""Maker (passive limit-order) execution engine — Phase 5 Execution Microstructure & TCA.

Implements the three components pre-registered in actionplan.md §5.2:

1. **Passive limit placement**: mid = (bid + ask) / 2; BUY posts at bid + 1 tick,
   SELL posts at ask - 1 tick.
2. **Queue & fill simulator** (bar data): an order fills ONLY when
   (a) trades print *strictly through* the limit price — bar low < limit for a BUY,
       bar high > limit for a SELL — meaning the sweep crossed our price, OR
   (b) the limit is *touched* (low <= limit <= high) AND bar volume traded is at
       least 3x our order quantity, proxying "the queue ahead of us cleared".
   A touch alone never fills: we are modeled at the back of the queue.
   Instruments without a volume tape (modeled option mid paths) disable clause (b)
   — fail-closed per actionplan Rulebook #5. Never interpolate a fill.
3. **Adverse selection**: a fill followed by an adverse 5-minute reference move of
   more than 0.20% is flagged, and the backtest strips the passive improvement for
   that fill (it is re-priced at the contemporaneous taker price). The price damage
   of the move itself is already in the mark-to-market; re-pricing only removes the
   captured spread edge so passive PnL is not double-counted.

# ponytail: bar-level queue model. Clause (b) uses total bar volume, not
# volume-at-price (no such tape on disk); options have no tape at all, so they run
# clause (a) only. Upgrade path: e009 60-second full-chain captures (Phase 6) give
# real top-of-book depth and per-minute prints.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

TICK_SIZE = 0.05  # NIFTY options/futures tick
VOLUME_MULTIPLE = 3.0  # clause (b): bar volume >= 3x order quantity
ADVERSE_MOVE_PCT = 0.002  # 0.20% reference move threshold


@dataclass(frozen=True, slots=True)
class Bar:
    """One bar of a tradable price path.

    For real instruments (futures/spot) this is the OHLCV bar. For modeled option
    mid paths the caller builds open/high/low/close from the underlying bar via
    Black-Scholes and leaves volume=None (clause (b) disabled, fail-closed).
    """
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None


def mid_price(bid: float, ask: float) -> float:
    """Mid price = (bid + ask) / 2."""
    return 0.5 * (bid + ask)


def passive_limit_price(bid: float, ask: float, side: str, tick: float = TICK_SIZE) -> float:
    """Passive placement per actionplan §5.2: BUY at bid + 1 tick, SELL at ask - 1 tick."""
    s = side.strip().upper()
    if s == "BUY":
        return bid + tick
    if s == "SELL":
        return ask - tick
    raise ValueError(f"side must be BUY or SELL, got {side!r}")


@dataclass(frozen=True, slots=True)
class PassiveOrder:
    """A resting passive limit order."""
    side: str  # "BUY" | "SELL"
    limit_price: float
    quantity: int
    posted_bar: int
    tag: str = ""


@dataclass(frozen=True, slots=True)
class Fill:
    """A simulated passive fill. fill_price is always the limit (no improvement modeled)."""
    side: str
    limit_price: float
    fill_price: float
    fill_bar: int
    quantity: int
    posted_bar: int
    taker_price: float  # contemporaneous crossing price, used to strip passive edge on adverse fills
    tag: str = ""

    @property
    def bars_resting(self) -> int:
        return self.fill_bar - self.posted_bar


class QueueFillSimulator:
    """Bar-based queue model implementing the actionplan §5.2 fill rule."""

    def __init__(self, volume_multiple: float = VOLUME_MULTIPLE) -> None:
        self.volume_multiple = volume_multiple

    def try_fill(
        self,
        order: PassiveOrder,
        bar: Bar,
        bar_index: int,
        taker_price: float,
    ) -> Optional[Fill]:
        """Evaluates one bar against a resting order. Returns a Fill or None."""
        s = order.side.strip().upper()
        if s == "BUY":
            touched = bar.low <= order.limit_price <= bar.high
            through = bar.low < order.limit_price  # prints strictly below our bid
        elif s == "SELL":
            touched = bar.low <= order.limit_price <= bar.high
            through = bar.high > order.limit_price  # prints strictly above our ask
        else:
            raise ValueError(f"side must be BUY or SELL, got {order.side!r}")

        volume_ok = (
            bar.volume is not None
            and bar.volume >= self.volume_multiple * order.quantity
        )
        if not (through or (touched and volume_ok)):
            return None

        return Fill(
            side=s,
            limit_price=order.limit_price,
            fill_price=order.limit_price,
            fill_bar=bar_index,
            quantity=order.quantity,
            posted_bar=order.posted_bar,
            taker_price=taker_price,
            tag=order.tag,
        )


def fill_in_window(
    order: PassiveOrder,
    bars: Mapping[int, Bar],
    window: Sequence[int],
    sim: Optional[QueueFillSimulator] = None,
    taker_price_by_bar: Optional[Mapping[int, float]] = None,
) -> Optional[Fill]:
    """Resting order walk: first bar in `window` that fills the order wins."""
    s = sim or QueueFillSimulator()
    for b in window:
        bar = bars.get(b)
        if bar is None:
            continue
        taker = (taker_price_by_bar or {}).get(b, bar.close)
        fill = s.try_fill(order, bar, b, taker_price=taker)
        if fill is not None:
            return fill
    return None


@dataclass(frozen=True, slots=True)
class AdverseSelectionEvent:
    """A fill followed by an adverse reference move beyond the frozen threshold."""
    fill: Fill
    reference_move_pct: float  # signed reference (underlying) move over the 5-min horizon
    penalty_rupees: float      # passive improvement stripped: |taker - limit| * quantity


def is_adverse(side: str, move_pct: float, threshold_pct: float = ADVERSE_MOVE_PCT) -> bool:
    """True when the reference move ran against the fill's direction beyond threshold.

    SELL fill is adversely selected when the reference rose; BUY when it fell.
    """
    s = side.strip().upper()
    if s == "SELL":
        return move_pct >= threshold_pct
    if s == "BUY":
        return move_pct <= -threshold_pct
    raise ValueError(f"side must be BUY or SELL, got {side!r}")


def apply_adverse_selection(
    fills: Sequence[Fill],
    reference_move_by_fill_bar: Mapping[int, float],
    threshold_pct: float = ADVERSE_MOVE_PCT,
) -> Tuple[List[Fill], List[AdverseSelectionEvent]]:
    """Strips passive improvement from adversely selected fills.

    Returns (adjusted_fills, events). Adjusted fills are re-priced at taker_price;
    unflagged fills pass through untouched. Penalty = captured improvement removed.
    """
    adjusted: List[Fill] = []
    events: List[AdverseSelectionEvent] = []
    for f in fills:
        move = reference_move_by_fill_bar.get(f.fill_bar, 0.0)
        if is_adverse(f.side, move, threshold_pct):
            penalty = abs(f.taker_price - f.fill_price) * f.quantity
            adjusted.append(
                Fill(
                    side=f.side,
                    limit_price=f.limit_price,
                    fill_price=f.taker_price,
                    fill_bar=f.fill_bar,
                    quantity=f.quantity,
                    posted_bar=f.posted_bar,
                    taker_price=f.taker_price,
                    tag=f.tag,
                )
            )
            events.append(
                AdverseSelectionEvent(fill=f, reference_move_pct=move, penalty_rupees=penalty)
            )
        else:
            adjusted.append(f)
    return adjusted, events


def reference_moves(
    candles_close_open: Mapping[int, Tuple[float, float]],
) -> Dict[int, float]:
    """Signed close-to-close reference move for each bar index.

    move[b] = close[b+1] / close[b] - 1 (the 5-minute window *after* bar b). For the
    final bar without a successor, falls back to that bar's own open->close move.
    Input maps bar index -> (open, close) of the reference series (underlying spot).
    """
    bars = sorted(candles_close_open)
    out: Dict[int, float] = {}
    for i, b in enumerate(bars):
        op, cl = candles_close_open[b]
        if i + 1 < len(bars):
            nxt_close = candles_close_open[bars[i + 1]][1]
            out[b] = (nxt_close - cl) / cl if cl > 0 else 0.0
        else:
            out[b] = (cl - op) / op if op > 0 else 0.0
    return out
