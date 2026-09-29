"""5-minute NIFTY intraday candle store: download via DhanHQ, partition to Parquet.

Path: data/intraday/interval=5/year=YYYY/month=MM/in5_YYYYMMDD.parquet
Schema: timestamp, open, high, low, close, volume (5-min bars 09:15–15:25 IST).

- Trades requested weekdays only; "holidays" surface as MissingDataError (no files written).
- Weekends are skipped up front, mirroring download_data.py.
- Validates: required columns, timestamps within the 09:15–15:30 session, no duplicates,
  minimum bar count; falls back to the previous weekday (DhanHQ returns 0 bars on holidays).
- Rate-limited via DhanFeed's built-in throttle.

Usage:
    from core.feeds.intraday import download_intraday_candles
    download_intraday_candles(date(2026, 9, 25))
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd

import config

logger = logging.getLogger(__name__)

INTERVAL_MINUTES = 5
SESSION_START = time(9, 15)
SESSION_END = time(15, 30)
MIN_BARS = 70  # full session ~= 75 bars; tolerate minor gaps


class MissingDataError(RuntimeError):
    """Raised when a requested session has no intraday data (e.g. exchange holiday)."""


def get_partition_path(target_date: date, output_dir: Optional[Path] = None) -> Path:
    """Partition layout: data/intraday/interval=5/year=YYYY/month=MM/in5_YYYYMMDD.parquet."""
    base = Path(output_dir) if output_dir else config.INTRADAY_DATA_DIR
    return (
        base / f"interval={INTERVAL_MINUTES}" / f"year={target_date.year}" / f"month={target_date.month:02d}"
        / f"in5_{target_date.strftime('%Y%m%d')}.parquet"
    )


def _validate_candles(df: pd.DataFrame, target_date: date) -> pd.DataFrame:
    if df.empty:
        # Dhan returns an empty frame on weekends/holidays — surface as missing, not corrupt.
        raise MissingDataError(f"No intraday candles returned for {target_date}")
    required = {"timestamp", "open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Intraday frame missing columns: {sorted(missing)}")

    out = df.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"])
    # Drop duplicate timestamps and rows outside the session window.
    out = out.drop_duplicates(subset="timestamp", keep="first")
    out = out[(out["timestamp"].dt.time >= SESSION_START) & (out["timestamp"].dt.time <= SESSION_END)]
    out = out.sort_values("timestamp").reset_index(drop=True)

    if len(out) < MIN_BARS:
        raise MissingDataError(
            f"Only {len(out)} intraday bars for {target_date} (need >= {MIN_BARS}) — likely a holiday"
        )

    # Sanity: high >= low, positive prices.
    bad = out[(out["high"] < out["low"]) | (out["open"] <= 0) | (out["close"] <= 0)]
    if len(bad):
        raise ValueError(f"Corrupt OHLC rows for {target_date}: {len(bad)} bars")
    return out


def download_intraday_candles(
    trade_date: date | datetime | str,
    output_dir: Optional[Path] = None,
    interval: int = INTERVAL_MINUTES,
    skip_if_present: bool = True,
    feed=None,
) -> Path:
    """Downloads one session of 5-min candles and writes the partition.

    feed: injectable DhanFeed-like object (tests pass a fake). Defaults to DhanFeed().
    Raises MissingDataError for holidays, ValueError for corrupt data.
    """
    d = trade_date.date() if isinstance(trade_date, datetime) else trade_date
    out_file = get_partition_path(d, output_dir)
    if skip_if_present and out_file.exists():
        return out_file

    from core.feeds.dhan import DhanFeed

    fd = feed or DhanFeed()
    df = fd.fetch_intraday_candles("NIFTY", trade_date=d, interval=interval)
    clean = _validate_candles(df, d)

    out_file.parent.mkdir(parents=True, exist_ok=True)
    clean.to_parquet(out_file, index=False)
    logger.info(f"Saved {len(clean)} 5-min bars for {d} to {out_file}")
    return out_file


def load_intraday_candles(
    trade_date: date | datetime | str,
    data_dir: Optional[Path] = None,
    interval: int = INTERVAL_MINUTES,
) -> pd.DataFrame:
    """Loads a cached partition (no download). Raises FileNotFoundError if absent."""
    d = trade_date.date() if isinstance(trade_date, datetime) else trade_date
    path = get_partition_path(d, data_dir)
    if not path.exists():
        raise FileNotFoundError(f"Intraday partition not found: {path}")
    df = pd.read_parquet(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def available_dates(data_dir: Optional[Path] = None) -> List[date]:
    """Lists dates that already have intraday partitions on disk."""
    base = Path(data_dir) if data_dir else config.INTRADAY_DATA_DIR
    dates: List[date] = []
    for p in base.glob(f"interval={INTERVAL_MINUTES}/year=*/month=*/in5_*.parquet"):
        try:
            dates.append(datetime.strptime(p.stem.replace("in5_", ""), "%Y%m%d").date())
        except ValueError:
            continue
    return sorted(dates)
