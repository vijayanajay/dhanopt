"""Kaufman Efficiency Ratio (KER) Signal.

Quantifies price path efficiency versus noise over a rolling n-bar window
to prevent taking directional trades during choppy oscillations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, Union

import numpy as np
import pandas as pd


@dataclass(slots=True)
class KERSignal:
    """Quantitative snapshot of path efficiency versus noise."""
    ker: float
    is_trending: bool     # KER > 0.55 (directional trades approved)
    is_noisy: bool        # KER < 0.35 (veto directional; chop/iron condor only)
    net_change: float
    total_path: float

    @property
    def allows_directional(self) -> bool:
        return self.is_trending

    @property
    def allows_condor(self) -> bool:
        return self.is_noisy


def calculate_ker(
    prices: Union[pd.Series, Sequence[float], pd.DataFrame],
    n: int = 20,
) -> KERSignal:
    """Calculates Kaufman Efficiency Ratio over the last n bars.
    
    Formula:
        KER = |Price_t - Price_{t-n}| / sum_{i=0}^{n-1} |Price_{t-i} - Price_{t-i-1}|
        
    prices: Series, list of prices, or DataFrame with 'close' column.
    n: Rolling lookback period in bars (default: 20 bars / 100 mins on 5-min chart).
    """
    if isinstance(prices, pd.DataFrame):
        if "close" in prices.columns:
            arr = prices["close"].astype(float).values
        else:
            raise ValueError("DataFrame must contain 'close' column.")
    elif isinstance(prices, pd.Series):
        arr = prices.astype(float).values
    else:
        arr = np.array(prices, dtype=float)

    total_len = len(arr)
    if total_len < 2:
        return KERSignal(
            ker=0.0,
            is_trending=False,
            is_noisy=True,
            net_change=0.0,
            total_path=0.0,
        )

    # Use up to n bars
    window_len = min(n, total_len - 1)
    # ponytail: Dynamic warm-up window allows KER calculation during early morning sessions
    # before full 20 bars (100 mins) are formed.
    window_prices = arr[-(window_len + 1):]

    net_change = abs(float(window_prices[-1] - window_prices[0]))
    step_diffs = np.abs(np.diff(window_prices))
    total_path = float(np.sum(step_diffs))

    if total_path < 1e-9:
        ker = 0.0
    else:
        ker = min(1.0, max(0.0, net_change / total_path))

    ker_rounded = round(ker, 4)
    is_trending = ker_rounded > 0.55
    is_noisy = ker_rounded < 0.35

    return KERSignal(
        ker=ker_rounded,
        is_trending=is_trending,
        is_noisy=is_noisy,
        net_change=round(net_change, 2),
        total_path=round(total_path, 2),
    )
