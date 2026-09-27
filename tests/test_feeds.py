"""Unit tests for Market Data Feeds (Candle, OptionChainSnapshot, DhanFeed, Bhavcopy)."""

import io
import tempfile
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pandas as pd

from core.feeds.base import Candle, OptionChainSnapshot, OptionContract
from core.feeds.bhavcopy import (
    filter_nifty_options,
    load_fo_bhavcopy,
    normalize_bhavcopy_df,
    parse_date,
)
from core.feeds.dhan import DhanFeed, generate_mock_candles, generate_mock_option_chain


class TestFeedContracts(unittest.TestCase):
    def test_candle_dataclass(self):
        now = datetime.now()
        c = Candle(timestamp=now, open=25200.0, high=25250.0, low=25190.0, close=25240.0, volume=15000)
        self.assertEqual(c.timestamp, now)
        self.assertEqual(c.high, 25250.0)
        d = c.to_dict()
        self.assertIn("close", d)
        self.assertEqual(d["close"], 25240.0)

    def test_option_contract_properties(self):
        opt = OptionContract(
            symbol="NIFTY25250CE",
            strike=25250.0,
            option_type="CE",
            expiry="2026-10-01",
            ltp=110.0,
            bid=109.80,
            ask=110.20,
            oi=150000,
            prev_oi=120000,
            volume=45000,
            iv=13.2,
            delta=0.52,
        )
        self.assertEqual(opt.delta_oi, 30000)
        self.assertAlmostEqual(opt.bid_ask_spread, 0.40)

    def test_option_chain_snapshot_diagnostics(self):
        ts = datetime.now()
        contracts = {
            (25100.0, "PE"): OptionContract("N25100PE", 25100.0, "PE", "2026-10-01", ltp=45.0, bid=44.8, ask=45.2, oi=350000, volume=60000, iv=14.0),
            (25200.0, "PE"): OptionContract("N25200PE", 25200.0, "PE", "2026-10-01", ltp=75.0, bid=74.8, ask=75.2, oi=180000, volume=40000, iv=13.5),
            (25250.0, "CE"): OptionContract("N25250CE", 25250.0, "CE", "2026-10-01", ltp=110.0, bid=109.8, ask=110.2, oi=120000, volume=50000, iv=13.0, delta=0.51),
            (25250.0, "PE"): OptionContract("N25250PE", 25250.0, "PE", "2026-10-01", ltp=105.0, bid=104.8, ask=105.2, oi=140000, volume=55000, iv=13.4, delta=-0.49),
            (25400.0, "CE"): OptionContract("N25400CE", 25400.0, "CE", "2026-10-01", ltp=35.0, bid=34.8, ask=35.2, oi=420000, volume=80000, iv=13.1),
        }
        snap = OptionChainSnapshot(
            timestamp=ts,
            spot_price=25240.50,
            contracts=contracts,
            expiry="2026-10-01",
        )

        # ATM Strike for 25240.50 should be 25250
        self.assertEqual(snap.atm_strike(), 25250.0)

        # Walls
        self.assertEqual(snap.call_wall(), 25400.0)  # max Call OI (420000)
        self.assertEqual(snap.put_wall(), 25100.0)   # max Put OI (350000)

        # PCR OI
        total_calls = 120000 + 420000  # 540000
        total_puts = 350000 + 180000 + 140000  # 670000
        expected_pcr = round(total_puts / total_calls, 3)
        self.assertAlmostEqual(snap.pcr_oi(), expected_pcr)

        # ATM Straddle IV
        self.assertAlmostEqual(snap.atm_straddle_iv(), (13.0 + 13.4) / 2.0)


class TestDhanFeed(unittest.TestCase):
    def setUp(self):
        self.feed = DhanFeed(mock=True)

    def test_fetch_intraday_candles(self):
        df = self.feed.fetch_intraday_candles(
            symbol="NIFTY",
            from_time="09:15",
            to_time="10:15",
            interval=5,
        )
        self.assertIsInstance(df, pd.DataFrame)
        self.assertFalse(df.empty)
        expected_cols = {"timestamp", "open", "high", "low", "close", "volume"}
        self.assertTrue(expected_cols.issubset(set(df.columns)))

        # 09:15 to 10:15 in 5-min intervals inclusive = 13 candles
        self.assertEqual(len(df), 13)
        self.assertEqual(df.iloc[0]["timestamp"].time(), time(9, 15))
        self.assertEqual(df.iloc[-1]["timestamp"].time(), time(10, 15))

        # Check OHLC validity
        for _, row in df.iterrows():
            self.assertGreaterEqual(row["high"], row["low"])
            self.assertGreaterEqual(row["high"], row["open"])
            self.assertGreaterEqual(row["high"], row["close"])
            self.assertLessEqual(row["low"], row["open"])
            self.assertLessEqual(row["low"], row["close"])

    def test_fetch_option_chain(self):
        chain = self.feed.fetch_option_chain(symbol="NIFTY")
        self.assertIsInstance(chain, OptionChainSnapshot)
        self.assertGreater(len(chain.contracts), 0)

        atm = chain.atm_strike()
        self.assertEqual(atm, 25250.0)

        # Check ATM CE and PE exist
        ce = chain.get_contract(atm, "CE")
        pe = chain.get_contract(atm, "PE")
        self.assertIsNotNone(ce)
        self.assertIsNotNone(pe)
        self.assertAlmostEqual(ce.delta, 0.50, delta=0.10)
        self.assertAlmostEqual(pe.delta, -0.50, delta=0.10)

        # Check Call and Put walls exist
        self.assertGreater(chain.call_wall(), atm)
        self.assertLess(chain.put_wall(), atm)

    def test_spot_and_vix(self):
        spot = self.feed.fetch_spot_price("NIFTY")
        vix = self.feed.fetch_vix()
        self.assertGreater(spot, 20000.0)
        self.assertGreater(vix, 5.0)


class TestBhavcopy(unittest.TestCase):
    def test_parse_date(self):
        d1 = parse_date("2026-09-28")
        d2 = parse_date("28-09-2026")
        d3 = parse_date("28-Sep-2026")
        self.assertEqual(d1, date(2026, 9, 28))
        self.assertEqual(d2, date(2026, 9, 28))
        self.assertEqual(d3, date(2026, 9, 28))

    def test_normalize_legacy_bhavcopy(self):
        legacy_csv = """INSTRUMENT,SYMBOL,EXPIRY_DT,STRIKE_PR,OPTION_TYP,OPEN,HIGH,LOW,CLOSE,SETTLE_PR,CONTRACTS,VAL_INLAKH,OPEN_INT,CHG_IN_OI,TIMESTAMP
OPTIDX,NIFTY,01-Oct-2026,25200,CE,120.0,140.0,110.0,135.0,135.0,5000,1250.0,250000,15000,28-Sep-2026
OPTIDX,NIFTY,01-Oct-2026,25200,PE,65.0,75.0,50.0,55.0,55.0,4200,950.0,310000,-8000,28-Sep-2026
FUTIDX,NIFTY,29-Oct-2026,0,XX,25300.0,25380.0,25270.0,25350.0,25350.0,12000,3200.0,850000,25000,28-Sep-2026
"""
        df_raw = pd.read_csv(io.StringIO(legacy_csv))
        df_norm = normalize_bhavcopy_df(df_raw)

        self.assertEqual(len(df_norm), 3)
        self.assertIn("strike", df_norm.columns)
        self.assertIn("option_type", df_norm.columns)
        self.assertIn("open_interest", df_norm.columns)

        # Test filtering
        nifty_opts = filter_nifty_options(df_norm, strike=25200.0, option_type="CE")
        self.assertEqual(len(nifty_opts), 1)
        self.assertEqual(nifty_opts.iloc[0]["close"], 135.0)
        self.assertEqual(nifty_opts.iloc[0]["open_interest"], 250000)

    def test_parquet_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sample_csv = """INSTRUMENT,SYMBOL,EXPIRY_DT,STRIKE_PR,OPTION_TYP,OPEN,HIGH,LOW,CLOSE,SETTLE_PR,CONTRACTS,VAL_INLAKH,OPEN_INT,CHG_IN_OI,TIMESTAMP
OPTIDX,NIFTY,01-Oct-2026,25250,CE,105.0,125.0,95.0,115.0,115.0,3000,800.0,180000,12000,28-Sep-2026
"""
            df_norm = normalize_bhavcopy_df(pd.read_csv(io.StringIO(sample_csv)))
            target_date = date(2026, 9, 28)
            month_dir = Path(tmpdir) / f"year={target_date.year}" / f"month={target_date.month:02d}"
            month_dir.mkdir(parents=True, exist_ok=True)
            p_file = month_dir / f"fo_{target_date.strftime('%Y%m%d')}.parquet"
            df_norm.to_parquet(p_file, index=False)

            loaded = load_fo_bhavcopy(target_date, data_dir=tmpdir)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded.iloc[0]["symbol"], "NIFTY")
            self.assertEqual(loaded.iloc[0]["strike"], 25250.0)


if __name__ == "__main__":
    unittest.main()
