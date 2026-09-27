"""Volume-Weighted Average Price (VWAP) and Dynamic Slope Signal.

Computes cumulative intraday VWAP, standard deviation bands (+/- 1.5 sigma),
15-minute rolling slope, and institutional regime classification.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass(slots=True)
class VWAPSignal:
    """Quantitative snapshot of intraday VWAP microstructure."""
    vwap: float
    upper_band: float
    lower_band: float
    std_dev: float
    slope_15m: float
    regime: str  # "BULLISH", "BEARISH", "CHOP", "NEUTRAL"
    price: float
    price_vs_vwap_pct: float

    @property
    def is_bullish(self) -> bool:
        return self.regime == "BULLISH"

    @property
    def is_bearish(self) -> bool:
        return self.regime == "BEARISH"

    @property
    def is_chop(self) -> bool:
        return self.regime == "CHOP"


def compute_vwap_series(
    df: pd.DataFrame,
    k_bars: int = 3,
    num_std: float = 1.5,
) -> pd.DataFrame:
    """Enriches intraday candles DataFrame with running VWAP, bands, and slope.

    Expects DataFrame with columns: ['volume'] and either ['close'] or (['high', 'low', 'close']).
    """
    if df.empty:
        raise ValueError("Cannot compute VWAP on empty DataFrame.")

    res = df.copy()

    # Determine representative price per candle: typical price (H+L+C)/3 if available
    if {"high", "low", "close"}.issubset(res.columns):
        price = (res["high"] + res["low"] + res["close"]) / 3.0
    elif "close" in res.columns:
        price = res["close"].astype(float)
    else:
        raise ValueError("DataFrame must contain 'close' or 'high','low','close' columns.")

    volume = res["volume"].astype(float)

    # Prevent zero-volume division
    vol_safe = volume.replace(0.0, 1e-6)

    # Running cumulative sums
    cum_vol = vol_safe.cumsum()
    cum_pv = (price * vol_safe).cumsum()
    cum_pv2 = (price * price * vol_safe).cumsum()

    vwap = cum_pv / cum_vol

    # Volume-weighted variance: E[P^2] - (E[P])^2
    var_vwap = (cum_pv2 / cum_vol) - (vwap * vwap)
    # Clamp negative numbers caused by floating precision
    var_vwap = var_vwap.clip(lower=0.0)
    std_vwap = np.sqrt(var_vwap)

    upper_band = vwap + num_std * std_vwap
    lower_band = vwap - num_std * std_vwap

    # 15-minute rolling slope (k_bars = 3 for 5-min interval)
    # Slope = (VWAP_t - VWAP_{t-k}) / VWAP_{t-k} * 100
    vwap_shifted = vwap.shift(k_bars)
    # For early bars where shift is NaN, compare to bar 0
    vwap_shifted = vwap_shifted.fillna(vwap.iloc[0])
    slope_15m = np.where(
        vwap_shifted > 0,
        ((vwap - vwap_shifted) / vwap_shifted) * 100.0,
        0.0,
    )

    res["vwap"] = vwap.round(2)
    res["std_vwap"] = std_vwap.round(2)
    res["vwap_upper"] = upper_band.round(2)
    res["vwap_lower"] = lower_band.round(2)
    res["vwap_slope_15m"] = np.round(slope_15m, 4)

    return res


def calculate_vwap_signal(
    df: pd.DataFrame,
    k_bars: int = 3,
    num_std: float = 1.5,
) -> VWAPSignal:
    """Calculates the latest point-in-time VWAPSignal from intraday candles."""
    if df.empty:
        raise ValueError("Candles DataFrame is empty.")

    enriched = compute_vwap_series(df, k_bars=k_bars, num_std=num_std)
    latest = enriched.iloc[-1]

    price = float(latest["close"])
    vwap = float(latest["vwap"])
    upper_band = float(latest["vwap_upper"])
    lower_band = float(latest["vwap_lower"])
    std_dev = float(latest["std_vwap"])
    slope_15m = float(latest["vwap_slope_15m"])

    price_diff_pct = round(((price - vwap) / vwap) * 100.0, 4) if vwap > 0 else 0.0

    # Institutional Regime Classification (BRD 3.1):
    # Bullish: Price > VWAP and Slope > +0.02% / 15m
    # Bearish: Price < VWAP and Slope < -0.02% / 15m
    # Chop: |Price - VWAP| <= 0.5 * sigma and |Slope| <= 0.01% / 15m
    # Neutral otherwise
    if price > vwap and slope_15m > 0.02:
        regime = "BULLISH"
    elif price < vwap and slope_15m < -0.02:
        regime = "BEARISH"
    elif abs(price - vwap) <= (0.5 * std_dev) and abs(slope_15m) <= 0.01:
        regime = "CHOP"
    else:
        regime = "NEUTRAL"

    return VWAPSignal(
        vwap=vwap,
        upper_band=upper_band,
        lower_band=lower_band,
        std_dev=std_dev,
        slope_15m=slope_15m,
        regime=regime,
        price=price,
        price_vs_vwap_pct=price_diff_pct,
    )
