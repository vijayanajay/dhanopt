"""30-Minute Opening Range Breakout (ORB-30) and Range Compression Signal.

Defines morning boundaries established between 09:15 and 09:45 AM, computes
compression ratio (width / spot < 0.35%), and verifies breakouts using 5-min close
and institutional volume multiplier (>= 1.4x).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Optional

import pandas as pd


@dataclass(slots=True)
class ORBSignal:
    """Quantitative snapshot of 30-minute opening range and breakout status."""
    orh: float
    orl: float
    width: float
    width_pct: float
    is_compressed: bool
    status: str  # "BULLISH_BREAKOUT", "BEARISH_BREAKDOWN", "UNCONFIRMED_BREAKOUT", "INSIDE_RANGE", "FORMING"
    breakout_time: Optional[datetime] = None
    breakout_price: Optional[float] = None
    breakout_volume: Optional[int] = None
    volume_ratio: float = 0.0

    @property
    def is_breakout(self) -> bool:
        return self.status in ("BULLISH_BREAKOUT", "BEARISH_BREAKDOWN")

    @property
    def is_inside(self) -> bool:
        return self.status in ("INSIDE_RANGE", "FORMING")


def _extract_time(ts) -> time:
    if isinstance(ts, datetime):
        return ts.time()
    if isinstance(ts, str):
        # Format might be "HH:MM", "HH:MM:SS", or "YYYY-MM-DD HH:MM:SS"
        if " " in ts:
            ts = ts.split(" ")[1]
        parts = ts.split(":")
        return time(int(parts[0]), int(parts[1]))
    if isinstance(ts, pd.Timestamp):
        return ts.time()
    if isinstance(ts, time):
        return ts
    raise ValueError(f"Unsupported timestamp type: {type(ts)}")


def calculate_orb(
    df: pd.DataFrame,
    spot_price: Optional[float] = None,
    volume_multiplier: float = 1.4,
    baseline_volume: Optional[float] = None,
) -> ORBSignal:
    """Calculates 30-Minute Opening Range Breakout and compression metrics.
    
    df: DataFrame containing intraday candles with 'timestamp', 'high', 'low', 'close', 'volume'.
    spot_price: Current index spot price. If None, uses latest candle close.
    volume_multiplier: Minimum volume expansion factor required for breakout confirmation (1.4x).
    baseline_volume: Benchmark volume. If None, computes average volume of 09:15-09:45 candles.
    """
    if df.empty:
        raise ValueError("Candles DataFrame cannot be empty for ORB calculation.")

    # Sort by timestamp
    res = df.copy()
    if "timestamp" in res.columns:
        times = [_extract_time(t) for t in res["timestamp"]]
        res["_time"] = times
    else:
        raise ValueError("DataFrame must contain 'timestamp' column.")

    spot = float(spot_price if spot_price is not None else res.iloc[-1]["close"])

    # Determine timestamp convention: if earliest candle is 09:15, candles are labeled by start-time,
    # meaning the 30-min window (09:15-09:45) is covered by candles with timestamp < 09:45 (e.g. 09:15, 09:20, 09:25, 09:30, 09:35, 09:40).
    # The candle timestamped 09:45 is the first candle outside the opening range (09:45-09:50).
    earliest_time = min(times) if times else time(9, 15)
    if earliest_time <= time(9, 15):
        orb_mask = res["_time"].apply(lambda t: time(9, 15) <= t < time(9, 45))
        post_orb_mask = res["_time"].apply(lambda t: t >= time(9, 45))
    else:
        # Labeled by end-time (e.g. 09:20 to 09:45)
        orb_mask = res["_time"].apply(lambda t: time(9, 15) < t <= time(9, 45))
        post_orb_mask = res["_time"].apply(lambda t: t > time(9, 45))

    orb_window = res[orb_mask]

    if orb_window.empty:
        # Before or at market open
        return ORBSignal(
            orh=spot,
            orl=spot,
            width=0.0,
            width_pct=0.0,
            is_compressed=False,
            status="FORMING",
        )

    orh = float(orb_window["high"].max())
    orl = float(orb_window["low"].min())
    width = round(orh - orl, 2)
    width_pct = round((width / spot) * 100.0, 4) if spot > 0 else 0.0
    is_compressed = width_pct < 0.35

    # Determine baseline volume for breakout validation
    if baseline_volume is not None and baseline_volume > 0:
        base_vol = float(baseline_volume)
    else:
        # ponytail: Baseline volume falls back to average volume of morning 09:15-09:45 candles
        # when external 20-day historical interval profile is not supplied.
        base_vol = float(orb_window["volume"].mean()) if not orb_window.empty else 1.0

    # Post-ORB candles evaluation for breakout
    post_orb = res[post_orb_mask]

    if post_orb.empty:
        # Still within morning opening window
        return ORBSignal(
            orh=orh,
            orl=orl,
            width=width,
            width_pct=width_pct,
            is_compressed=is_compressed,
            status="FORMING",
        )

    # Scan sequentially for first confirmed breakout or evaluate latest candle
    status = "INSIDE_RANGE"
    breakout_dt = None
    breakout_px = None
    breakout_vol = None
    vol_ratio = 0.0

    for _, bar in post_orb.iterrows():
        c_close = float(bar["close"])
        c_vol = int(bar["volume"])
        ratio = round(c_vol / base_vol, 2) if base_vol > 0 else 1.0

        if c_close > orh:
            vol_ratio = ratio
            breakout_px = c_close
            breakout_vol = c_vol
            breakout_dt = bar["timestamp"] if "timestamp" in bar else None
            if ratio >= volume_multiplier:
                status = "BULLISH_BREAKOUT"
            else:
                status = "UNCONFIRMED_BREAKOUT"
            # Once confirmed breakout occurs, keep it
            if status == "BULLISH_BREAKOUT":
                break
        elif c_close < orl:
            vol_ratio = ratio
            breakout_px = c_close
            breakout_vol = c_vol
            breakout_dt = bar["timestamp"] if "timestamp" in bar else None
            if ratio >= volume_multiplier:
                status = "BEARISH_BREAKDOWN"
            else:
                status = "UNCONFIRMED_BREAKOUT"
            if status == "BEARISH_BREAKDOWN":
                break

    return ORBSignal(
        orh=orh,
        orl=orl,
        width=width,
        width_pct=width_pct,
        is_compressed=is_compressed,
        status=status,
        breakout_time=breakout_dt,
        breakout_price=breakout_px,
        breakout_volume=breakout_vol,
        volume_ratio=vol_ratio,
    )
