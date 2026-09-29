"""Unit tests for the 5-minute intraday candle store (core.feeds.intraday)."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from core.feeds.intraday import (
    MissingDataError,
    _validate_candles,
    available_dates,
    download_intraday_candles,
    get_partition_path,
    load_intraday_candles,
)


class _FakeFeed:
    """Returns a synthetic 75-bar session; empty frame on 'holiday' dates (day >= 28),
    mirroring DhanHQ's real holiday behavior (success + 0 bars)."""

    def __init__(self, n_bars: int = 75, start: time = time(9, 15)):
        self.n_bars = n_bars
        self.start = start

    def fetch_intraday_candles(self, symbol, trade_date=None, interval=5, **kw):
        if trade_date.day >= 28:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        ts = [datetime.combine(trade_date, self.start) + timedelta(minutes=5 * i) for i in range(self.n_bars)]
        rng = np.random.default_rng(trade_date.day)
        close = 25000 + np.cumsum(rng.normal(0, 5, self.n_bars))
        return pd.DataFrame({
            "timestamp": ts,
            "open": close + 2,
            "high": close + 8,
            "low": close - 8,
            "close": close,
            "volume": 1000,
        })


class TestIntradayStore(unittest.TestCase):
    def test_partition_layout(self):
        p = get_partition_path(date(2026, 9, 25))
        self.assertIn("interval=5", str(p))
        self.assertIn("year=2026", str(p))
        self.assertIn("month=09", str(p))
        self.assertTrue(p.name.startswith("in5_20260925"))

    def test_download_writes_partition_and_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = date(2026, 9, 23)
            path = download_intraday_candles(d, output_dir=Path(tmp), feed=_FakeFeed())
            self.assertTrue(path.exists())
            df = load_intraday_candles(d, data_dir=Path(tmp))
            self.assertEqual(len(df), 75)
            self.assertEqual(df["timestamp"].dt.time.min(), time(9, 15))
            # skip_if_present short-circuits a second call
            again = download_intraday_candles(d, output_dir=Path(tmp), feed=_FakeFeed())
            self.assertEqual(again, path)
            self.assertEqual(available_dates(Path(tmp)), [d])

    def test_holiday_raises_missing_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(MissingDataError):
                download_intraday_candles(date(2026, 9, 29), output_dir=Path(tmp), feed=_FakeFeed())
            self.assertEqual(list(Path(tmp).glob("**/*.parquet")), [])

    def test_validate_strips_duplicates_and_out_of_session(self):
        d = date(2026, 9, 23)
        ts = [datetime.combine(d, time(9, 15)) + timedelta(minutes=5 * i) for i in range(75)]
        df = pd.DataFrame({
            "timestamp": ts + [ts[0], datetime.combine(d, time(8, 0))],
            "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1,
        })
        clean = _validate_candles(df, d)
        self.assertEqual(len(clean), 75)  # dup + 08:00 bar removed

    def test_validate_rejects_corrupt_ohlc(self):
        d = date(2026, 9, 23)
        ts = [datetime.combine(d, time(9, 15)) + timedelta(minutes=5 * i) for i in range(75)]
        df = pd.DataFrame({
            "timestamp": ts, "open": 100.0, "high": 99.0, "low": 101.0, "close": 100.0, "volume": 1,
        })
        with self.assertRaises(ValueError):
            _validate_candles(df, d)

    def test_validate_rejects_short_session(self):
        d = date(2026, 9, 23)
        ts = [datetime.combine(d, time(9, 15)) + timedelta(minutes=5 * i) for i in range(10)]
        df = pd.DataFrame({"timestamp": ts, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1})
        with self.assertRaises(MissingDataError):
            _validate_candles(df, d)

    def test_weekday_range_skips_weekends(self):
        from download_intraday import weekday_range
        days = weekday_range("2026-09-21", "2026-09-27")  # Mon..Sun
        self.assertEqual(len(days), 5)
        self.assertTrue(all(d.weekday() < 5 for d in days))


if __name__ == "__main__":
    unittest.main()
