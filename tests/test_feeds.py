"""Unit tests for Market Data Feeds (Candle, OptionChainSnapshot, DhanFeed, Bhavcopy)."""

import io
import tempfile
import unittest
from collections import Counter
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pandas as pd

from core.feeds.base import Candle, OptionChainSnapshot, OptionContract
from core.feeds.bhavcopy import (
    filter_nifty_options,
    front_expiry,
    load_fo_bhavcopy,
    normalize_bhavcopy_df,
    parse_date,
    with_expiry_date,
)
from core.feeds.dhan import DhanFeed, generate_mock_candles, generate_mock_option_chain

import config


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

    def test_both_store_encodings_resolve_to_the_same_expiry(self):
        """The e028 defect in miniature, and it costs nothing to run.

        The store holds `04-Feb-2021` (legacy) and `2025-01-02` (UDiff) in the
        SAME column. Any lookup that compares a formatted date against that raw
        string matches one era and returns an empty frame on the other, which
        the caller cannot distinguish from a session with no data. Both rows
        below must be found by one call.
        """
        legacy_csv = """INSTRUMENT,SYMBOL,EXPIRY_DT,STRIKE_PR,OPTION_TYP,OPEN,HIGH,LOW,CLOSE,SETTLE_PR,CONTRACTS,VAL_INLAKH,OPEN_INT,CHG_IN_OI,TIMESTAMP
OPTIDX,NIFTY,04-Feb-2021,13500,CE,120.0,140.0,110.0,135.0,135.0,5000,1250.0,250000,15000,01-Feb-2021
"""
        modern_csv = """FININSTRMACTLNM,FININSTRMTP,XPRYDT,STRIKPRIC,OPTNTP,OPNPRIC,HGHPRIC,LWPRIC,CLSPRIC,STTLMPRIC,CONTRACTS,OPNINTRST,CHNGINOPNINTRST,TRADDT
NIFTY,IDO,02-Jan-2025,13500,CE,120.0,140.0,110.0,135.0,135.0,5000,250000,15000,01-Jan-2025
"""
        legacy = normalize_bhavcopy_df(pd.read_csv(io.StringIO(legacy_csv)))
        modern = normalize_bhavcopy_df(pd.read_csv(io.StringIO(modern_csv)))

        # The legacy frame keeps the raw NSE string; the modern frame is written
        # ISO at the boundary. One typed lookup must survive both.
        self.assertEqual(len(filter_nifty_options(legacy, expiry=date(2021, 2, 4))), 1)
        self.assertEqual(len(filter_nifty_options(modern, expiry=date(2025, 1, 2))), 1)

        # And the string comparison the bug used must still find nothing on the
        # legacy frame -- if this starts passing, the format changed under us.
        self.assertEqual(len(legacy[legacy["expiry"] == str(date(2021, 2, 4))]), 0)

    def test_with_expiry_date_refuses_a_frame_with_no_expiry(self):
        """A lookup that cannot type its key must raise, not guess."""
        with self.assertRaises(ValueError):
            with_expiry_date(pd.DataFrame({"symbol": ["NIFTY"]}))

    def test_front_expiry_takes_the_contract_expiring_today(self):
        """Contract identity (invariant 5.6): on an expiry day the front contract
        is the one expiring THAT day, not tomorrow's."""
        d = date(2023, 12, 20)
        self.assertEqual(front_expiry({date(2023, 12, 21), date(2023, 12, 28)}, d),
                         date(2023, 12, 21))
        self.assertEqual(front_expiry({date(2023, 12, 21)}, date(2023, 12, 21)),
                         date(2023, 12, 21))
        self.assertIsNone(front_expiry({date(2023, 12, 19)}, d))

    def test_front_expiry_refuses_to_guess(self):
        """Without a trade date there is no 'front' to resolve, and guessing
        would quietly break contract identity (invariant 5.6)."""
        with self.assertRaises(ValueError):
            front_expiry({date(2023, 12, 21)}, None)


def _store_partitions():
    """Every `fo_YYYYMMDD.parquet` on disk. Filenames are authoritative."""
    root = Path(config.HISTORICAL_DATA_DIR)
    if not root.exists():
        return []
    out = []
    for f in root.glob("**/*.parquet"):
        s = f.stem
        if s.startswith("fo_") and len(s) == 11 and s[3:].isdigit():
            out.append(f)
    return sorted(out)


class TestBhavcopyStoreCoverage(unittest.TestCase):
    """The repo-wide guard against silent-empty lookups (invariant 5.13).

    e028 emptied 356 of 576 sessions because a loader compared a `date` to a raw
    string, and the fail-closed rule dropped each one as `NO TRADE` with nothing
    logged. Nothing in the suite asked whether a lookup that CAN return an empty
    frame ever does. This does, on every partition, every run, in ~8 seconds.

    Coverage is asserted PER YEAR. That is not decoration: the bug was invisible
    in aggregate (40% of sessions) and obvious as a curve (100% in 2025, 0% in
    2023). An aggregate coverage number hides exactly the shape that betrays an
    encoding, a partition, or a wall convention.
    """

    # Only what filter_nifty_options actually reads. Reading the full partition
    # costs ~3s more per full walk for columns nothing here touches.
    COLUMNS = ["symbol", "expiry", "option_type"]

    @classmethod
    def setUpClass(cls):
        cls.partitions = _store_partitions()

    def setUp(self):
        if not self.partitions:
            self.skipTest(f"no bhavcopy store at {config.HISTORICAL_DATA_DIR}")

    def test_every_partition_resolves_a_non_empty_front_chain(self):
        empty: dict[int, list[str]] = {}
        n_nifty = 0

        for p in self.partitions:
            trade_date = datetime.strptime(p.stem[3:], "%Y%m%d").date()
            df = pd.read_parquet(p, columns=self.COLUMNS)
            nifty = filter_nifty_options(df)          # no expiry key: no parse
            if nifty.empty:
                empty.setdefault(str(trade_date.year), []).append(f"{trade_date}:no-nifty")
                continue
            n_nifty += 1
            fe = front_expiry(with_expiry_date(nifty)["expiry_date"], trade_date)
            if fe is None:
                empty.setdefault(str(trade_date.year), []).append(f"{trade_date}:no-front-expiry")
                continue
            if filter_nifty_options(nifty, expiry=fe).empty:
                empty.setdefault(str(trade_date.year), []).append(f"{trade_date}:empty@fe={fe}")

        if not empty:
            self.assertGreater(n_nifty, 0)
            return

        per_year = Counter(p.stem[3:7] for p in self.partitions)
        report = ["front-chain coverage by year (empty lookups listed):"]
        for y in sorted(per_year):
            bad = empty.get(y, [])
            report.append(f"  {y}: {per_year[y] - len(bad):>4}/{per_year[y]:<4} "
                          f"resolved ({100 * (per_year[y] - len(bad)) / per_year[y]:.1f}%)"
                          + (f"  e.g. {bad[:3]}" if bad else ""))
        self.fail("a lookup returned an empty frame without saying why:\n"
                  + "\n".join(report))

    def test_the_store_is_present_and_spans_multiple_eras(self):
        """Guards the guard. A walk that silently covers one file, or one era,
        is the same failure wearing a test's clothes."""
        years = {p.stem[3:7] for p in self.partitions}
        self.assertGreater(len(self.partitions), 1000, f"only {len(self.partitions)} partitions")
        self.assertGreaterEqual(len(years), 2, f"single era only: {years}")
        # Both expiry encodings must be present on disk -- if a backfill ever
        # normalises the legacy files, this test stops covering the case it exists for.
        legacy = modern = 0
        for p in self.partitions[:: max(1, len(self.partitions) // 12)]:
            v = pd.read_parquet(p, columns=["expiry"])["expiry"].astype(str)
            legacy += int(v.str.match(r"^\d{2}-[A-Za-z]{3}-\d{4}$").any())
            modern += int(v.str.match(r"^\d{4}-\d{2}-\d{2}$").any())
        self.assertGreater(legacy, 0, "no legacy DD-Mon-YYYY encoding found on disk")
        self.assertGreater(modern, 0, "no ISO encoding found on disk")


if __name__ == "__main__":
    unittest.main()
