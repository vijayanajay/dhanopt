"""India VIX and Option Implied Volatility (IV) Dynamics Signal.

Calculates intraday Delta VIX, 20-day Parkinson Realized Volatility,
IV Spread (ATM Straddle IV minus Parkinson Volatility), and vol regime classifications.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass(slots=True)
class VIXIVSignal:
    """Quantitative snapshot of index volatility and options pricing richness."""
    vix: float
    prev_vix: float
    delta_vix: float
    regime: str           # "LOW_VOL", "NORMAL_VOL", "ELEVATED_VOL"
    shift: str            # "EXPANSION", "CRUSH", "STABLE"
    atm_iv: float
    parkinson_vol: float
    iv_spread: float
    is_rich: bool         # iv_spread > 3.0

    @property
    def favors_debit_spread(self) -> bool:
        return self.vix <= 16.0 or self.iv_spread <= 2.0

    @property
    def favors_credit_spread(self) -> bool:
        return self.vix >= 13.0 and self.iv_spread >= 1.5


def calculate_parkinson_volatility(
    daily_df: pd.DataFrame,
    window: int = 20,
) -> float:
    """Calculates annualized Parkinson Realized Volatility (%) over rolling window.
    
    Formula:
        sigma_P = sqrt( (252 / (4 * ln(2) * N)) * sum( (ln(H_i / L_i))^2 ) ) * 100
    """
    if daily_df.empty:
        raise ValueError("Daily DataFrame cannot be empty for Parkinson calculation.")

    # Normalize column names to lowercase
    cols = {col.lower(): col for col in daily_df.columns}
    if "high" not in cols or "low" not in cols:
        raise ValueError("DataFrame must contain 'high' and 'low' columns.")

    highs = daily_df[cols["high"]].tail(window).astype(float).values
    lows = daily_df[cols["low"]].tail(window).astype(float).values

    n = len(highs)
    if n == 0:
        return 0.0

    # Guard against non-positive prices and zero range
    safe_lows = np.where(lows > 0, lows, 1e-4)
    safe_highs = np.maximum(highs, safe_lows)
    log_hl = np.log(safe_highs / safe_lows)

    sum_sq = np.sum(log_hl ** 2)
    factor = 252.0 / (4.0 * math.log(2.0) * n)
    parkinson = math.sqrt(factor * sum_sq) * 100.0

    return round(parkinson, 2)


def calculate_vix_iv_signal(
    vix: float,
    prev_vix: float,
    atm_iv: float,
    daily_df: Optional[pd.DataFrame] = None,
    parkinson_vol: Optional[float] = None,
) -> VIXIVSignal:
    """Evaluates India VIX and option volatility dynamics against market regimes.
    
    vix: Current live India VIX value.
    prev_vix: Previous day's closing India VIX.
    atm_iv: Current ATM Straddle implied volatility (in %).
    daily_df: Optional DataFrame of daily OHLC bars to compute Parkinson volatility.
    parkinson_vol: Optional precomputed Parkinson volatility.
    """
    if prev_vix <= 0:
        delta_vix = 0.0
    else:
        delta_vix = round(((vix - prev_vix) / prev_vix) * 100.0, 2)

    # 1. Absolute VIX Regime (BRD 3.3)
    if vix < 12.5:
        regime = "LOW_VOL"
    elif vix <= 16.5:
        regime = "NORMAL_VOL"
    else:
        regime = "ELEVATED_VOL"

    # 2. Intraday VIX Delta Shift
    if delta_vix > 4.0:
        shift = "EXPANSION"
    elif delta_vix < -3.0:
        shift = "CRUSH"
    else:
        shift = "STABLE"

    # 3. Realized Parkinson Volatility
    if parkinson_vol is not None:
        p_vol = parkinson_vol
    elif daily_df is not None and not daily_df.empty:
        p_vol = calculate_parkinson_volatility(daily_df, window=20)
    else:
        # ponytail: Fallback to nominal historical Nifty baseline 12.5% when daily archive is omitted.
        p_vol = 12.5

    # 4. IV Spread = ATM Straddle IV - Parkinson Realized Vol
    iv_spread = round(atm_iv - p_vol, 2)
    is_rich = iv_spread > 3.0

    return VIXIVSignal(
        vix=round(vix, 2),
        prev_vix=round(prev_vix, 2),
        delta_vix=delta_vix,
        regime=regime,
        shift=shift,
        atm_iv=round(atm_iv, 2),
        parkinson_vol=p_vol,
        iv_spread=iv_spread,
        is_rich=is_rich,
    )
