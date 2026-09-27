"""Open Interest (OI) Microstructure and Dealer Walls Signal.

Identifies Call/Put Dealer Walls within +/- 300 pts of ATM, calculates PCR (OI and Volume),
and tracks delta PCR momentum to uncover institutional order positioning.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.feeds.base import OptionChainSnapshot


@dataclass(slots=True)
class OIMicroSignal:
    """Quantitative snapshot of strike-level dealer positioning and OI walls."""
    call_wall: float
    put_wall: float
    pcr_oi: float
    pcr_volume: float
    delta_pcr: float
    total_call_oi: int
    total_put_oi: int
    net_bias: str         # "BULLISH_FLOOR", "BEARISH_CAP", "NEUTRAL"
    spot_price: float
    atm_strike: float

    @property
    def is_bullish_bias(self) -> bool:
        return self.net_bias == "BULLISH_FLOOR"

    @property
    def is_bearish_bias(self) -> bool:
        return self.net_bias == "BEARISH_CAP"


def calculate_oi_micro(
    chain: OptionChainSnapshot,
    pcr_0930: Optional[float] = None,
    window: float = 300.0,
) -> OIMicroSignal:
    """Computes dealer walls, PCR, and delta PCR from OptionChainSnapshot.
    
    chain: OptionChainSnapshot object containing point-in-time option contracts.
    pcr_0930: Benchmark PCR_OI recorded at 09:30 AM. If None, delta_pcr defaults to 0.0.
    window: Strike filter distance around ATM (default +/- 300 points).
    """
    call_wall = chain.call_wall(window=window)
    put_wall = chain.put_wall(window=window)
    pcr_oi = chain.pcr_oi(window=window)
    pcr_vol = chain.pcr_volume(window=window)
    total_call = chain.total_call_oi(window=window)
    total_put = chain.total_put_oi(window=window)
    atm = chain.atm_strike()

    # Calculate change in PCR: Delta PCR = PCR(t) - PCR(09:30)
    if pcr_0930 is not None:
        delta_pcr = round(pcr_oi - pcr_0930, 3)
    else:
        delta_pcr = 0.0

    # Institutional Bias Determination (BRD 3.4):
    # Delta PCR > +0.15: Heavy institutional put writing (bullish floor)
    # Delta PCR < -0.15: Heavy call writing / put unwinding (bearish cap)
    if delta_pcr > 0.15:
        net_bias = "BULLISH_FLOOR"
    elif delta_pcr < -0.15:
        net_bias = "BEARISH_CAP"
    else:
        net_bias = "NEUTRAL"

    return OIMicroSignal(
        call_wall=call_wall,
        put_wall=put_wall,
        pcr_oi=pcr_oi,
        pcr_volume=pcr_vol,
        delta_pcr=delta_pcr,
        total_call_oi=total_call,
        total_put_oi=total_put,
        net_bias=net_bias,
        spot_price=chain.spot_price,
        atm_strike=atm,
    )
