"""Pragmatic Market Microstructure Signals Package.

Provides deterministic mathematical signals:
1. VWAP & Dynamic Slope (vwap.py)
2. 30-Minute Opening Range Breakout (orb.py)
3. India VIX & Option IV Dynamics (vix_iv.py)
4. Open Interest Microstructure & Dealer Walls (oi_micro.py)
5. Kaufman Efficiency Ratio (ker.py)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pandas as pd

from core.feeds.base import OptionChainSnapshot
from core.signals.ker import KERSignal, calculate_ker
from core.signals.oi_micro import OIMicroSignal, calculate_oi_micro
from core.signals.orb import ORBSignal, calculate_orb
from core.signals.vix_iv import (
    VIXIVSignal,
    calculate_parkinson_volatility,
    calculate_vix_iv_signal,
)
from core.signals.vwap import VWAPSignal, calculate_vwap_signal, compute_vwap_series


@dataclass(slots=True)
class MarketSignals:
    """Consolidated market microstructure telemetry snapshot."""
    timestamp: datetime
    spot_price: float
    vwap: VWAPSignal
    orb: ORBSignal
    vix_iv: VIXIVSignal
    oi: OIMicroSignal
    ker: KERSignal

    def summary(self) -> dict:
        """Returns clean telemetry dict for diagnostic printing."""
        return {
            "timestamp": self.timestamp.strftime("%Y-%m-%d %H:%M:%S") if isinstance(self.timestamp, datetime) else str(self.timestamp),
            "spot_price": self.spot_price,
            "vwap": self.vwap.vwap,
            "vwap_slope_15m": f"{self.vwap.slope_15m:+.3f}%",
            "vwap_regime": self.vwap.regime,
            "orb_status": self.orb.status,
            "orb_width_pts": self.orb.width,
            "orb_compressed": self.orb.is_compressed,
            "vix": self.vix_iv.vix,
            "delta_vix": f"{self.vix_iv.delta_vix:+.2f}%",
            "iv_spread": self.vix_iv.iv_spread,
            "call_wall": self.oi.call_wall,
            "put_wall": self.oi.put_wall,
            "pcr_oi": self.oi.pcr_oi,
            "delta_pcr": self.oi.delta_pcr,
            "ker": self.ker.ker,
            "ker_trending": self.ker.is_trending,
            "ker_noisy": self.ker.is_noisy,
        }


def generate_market_signals(
    candles: pd.DataFrame,
    chain: OptionChainSnapshot,
    vix: float,
    prev_vix: float,
    daily_df: Optional[pd.DataFrame] = None,
    pcr_0930: Optional[float] = None,
    parkinson_vol: Optional[float] = None,
    baseline_volume: Optional[float] = None,
) -> MarketSignals:
    """Generates the unified MarketSignals composite from active market data feeds."""
    if candles.empty:
        raise ValueError("Cannot generate signals from empty candles DataFrame.")

    latest_bar = candles.iloc[-1]
    ts = latest_bar["timestamp"] if "timestamp" in latest_bar else chain.timestamp
    spot = chain.spot_price

    # 1. VWAP & Slope
    vwap_sig = calculate_vwap_signal(candles)

    # 2. ORB-30
    orb_sig = calculate_orb(
        candles,
        spot_price=spot,
        volume_multiplier=1.4,
        baseline_volume=baseline_volume,
    )

    # 3. VIX & IV Dynamics
    atm_iv = chain.atm_straddle_iv()
    vix_sig = calculate_vix_iv_signal(
        vix=vix,
        prev_vix=prev_vix,
        atm_iv=atm_iv,
        daily_df=daily_df,
        parkinson_vol=parkinson_vol,
    )

    # 4. OI Microstructure & Dealer Walls
    oi_sig = calculate_oi_micro(chain, pcr_0930=pcr_0930)

    # 5. Kaufman Efficiency Ratio
    ker_sig = calculate_ker(candles, n=20)

    return MarketSignals(
        timestamp=ts if isinstance(ts, datetime) else chain.timestamp,
        spot_price=spot,
        vwap=vwap_sig,
        orb=orb_sig,
        vix_iv=vix_sig,
        oi=oi_sig,
        ker=ker_sig,
    )


__all__ = [
    "VWAPSignal",
    "calculate_vwap_signal",
    "compute_vwap_series",
    "ORBSignal",
    "calculate_orb",
    "VIXIVSignal",
    "calculate_vix_iv_signal",
    "calculate_parkinson_volatility",
    "OIMicroSignal",
    "calculate_oi_micro",
    "KERSignal",
    "calculate_ker",
    "MarketSignals",
    "generate_market_signals",
]
