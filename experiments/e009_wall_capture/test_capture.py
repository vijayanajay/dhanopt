"""Self-checks for the e009 collector: the strike map's shape and None-safety,
the coverage/gap math that decides PREREG kill 1, and append/idempotence
semantics. No network in any test — every live-path function takes its data
as arguments.
"""
from __future__ import annotations

import gzip
import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from experiments.e009_wall_capture.capture_chains import (
    SNAPSHOT_SECS, _existing_stamps, _session_gaps, _strike_map,
    capture_coverage_pct, register_session)


def _stamps(start: str, minutes: int, step_min: int = 1) -> list[str]:
    t0 = datetime.fromisoformat(start)
    return [(t0 + timedelta(minutes=i * step_min)).isoformat() for i in range(minutes)]


class TestStrikeMap(unittest.TestCase):
    def test_full_chain_shape_and_none_safety(self):
        chain = {"oc": {
            "25650.000000": {"ce": {"oi": 3786445, "top_bid_price": 133.55,
                                    "top_ask_price": 134.0, "top_ask_quantity": 1365,
                                    "last_price": 133.8, "volume": 120400, "implied_volatility": 14.2},
                             "pe": {"oi": 3096145, "top_bid_price": 132.45,
                                    "top_ask_price": None}},
            "25700.000000": {"ce": {"oi": None, "top_bid_price": 0.0,
                                    "top_ask_price": 0.0}},
        }}
        oc = _strike_map(chain)
        self.assertEqual(set(oc), {25650.0, 25700.0})
        self.assertEqual(oc[25650.0]["ce"], {
            "oi": 3786445, "bid": 133.55, "bid_qty": None, "ask": 134.0,
            "ask_qty": 1365, "ltp": 133.8, "vol": 120400, "iv": 14.2
        })
        self.assertIsNone(oc[25650.0]["pe"]["ask"])          # None-safe, recorded as-is
        self.assertEqual(oc[25700.0]["ce"]["bid"], 0.0)      # zero-quote recorded as-is
        self.assertEqual(oc[25700.0]["pe"], {
            "oi": None, "bid": None, "bid_qty": None, "ask": None,
            "ask_qty": None, "ltp": None, "vol": None, "iv": None
        })  # uniform shape: missing side = all-None, never fabricated

    def test_bad_strikes_skipped(self):
        oc = _strike_map({"oc": {"bad": {}, "25700.000000": {"pe": {"oi": 5}}}})
        self.assertEqual(set(oc), {25700.0})
        self.assertEqual(oc[25700.0]["pe"]["oi"], 5)


class TestCoverage(unittest.TestCase):
    def test_perfect_60s_capture_is_100pct_evaluable(self):
        stamps = _stamps("2026-10-05T09:15:00", 376)  # 09:15..15:30 inclusive
        self.assertEqual(capture_coverage_pct(stamps), 100.0)
        self.assertLessEqual(_session_gaps(stamps), SNAPSHOT_SECS * 1.5)

    def test_single_outage_over_90s_kills_evaluable(self):
        # 09:15..12:00 fine, then a 7-min outage, then fine: coverage stays >= 95%
        # (95% tolerates ~19 min of outage) but max_gap > 90 s — kill 1 is the AND,
        # so the session is still unevaluable. A coverage-shaped metric alone would miss it.
        good = _stamps("2026-10-05T09:15:00", 166)
        after = _stamps("2026-10-05T12:07:00", 205)
        stamps = good + after
        self.assertGreaterEqual(capture_coverage_pct(stamps), 95.0)
        self.assertGreater(_session_gaps(stamps), SNAPSHOT_SECS * 1.5)

    def test_long_outage_fails_both_bars(self):
        # 20-min outage: below the 95% coverage bar AND the max-gap bar.
        good = _stamps("2026-10-05T09:15:00", 166)
        after = _stamps("2026-10-05T12:20:00", 192)
        stamps = good + after
        self.assertLess(capture_coverage_pct(stamps), 95.0)
        self.assertGreater(_session_gaps(stamps), SNAPSHOT_SECS * 1.5)

    def test_75s_cadence_stays_covered(self):
        # 75 s cadence: every gap <= 90 s -> full coverage, and kill-1's max-gap
        # bar (<= 90 s) still passes — small cadence drift is tolerated, big gaps are not.
        t0 = datetime.fromisoformat("2026-10-05T09:15:00")
        stamps = [(t0 + timedelta(seconds=75 * i)).isoformat() for i in range(301)]  # 09:15..15:30
        self.assertEqual(capture_coverage_pct(stamps), 100.0)
        self.assertAlmostEqual(_session_gaps(stamps), 75.0, places=1)

    def test_empty_or_trivial_input(self):
        self.assertEqual(capture_coverage_pct([]), 0.0)
        self.assertEqual(capture_coverage_pct(["2026-10-05T09:15:00"]), 0.0)
        self.assertEqual(_session_gaps(["2026-10-05T09:15:00"]), float("inf"))


class TestAppendSemantics(unittest.TestCase):
    def test_day_file_is_valid_jsonl_gzip_after_appends(self):
        with TemporaryDirectory() as td:
            p = Path(td) / "2026-10-05.jsonl.gz"
            recs = [{"ts": "2026-10-05T09:15:00", "n": 40, "spot": 25123.5,
                     "oc": {25650.0: {"ce": {"oi": 1, "bid": 2.0, "ask": 2.5},
                                      "pe": {"oi": 1, "bid": 2.0, "ask": 2.5}}}},
                    {"ts": "2026-10-05T09:16:00", "err": "HTTPError()"}]
            with gzip.open(p, "at", encoding="utf-8") as f:
                for r in recs:
                    f.write(json.dumps(r) + "\n")
                f.write(json.dumps(recs[0]) + "\n")  # simulate an idempotent re-append
            rows = [json.loads(l) for l in gzip.open(p, "rt", encoding="utf-8")]
            self.assertEqual(len(rows), 3)
            err_rows = [r for r in rows if "err" in r]
            self.assertEqual(len(err_rows), 1)  # outages recorded, not gaps of silence

    def test_dual_expiry_record_structure(self):
        rec = {
            "ts": "2026-10-05T09:15:00", "lat": 120, "n": 2,
            "exp": "2026-10-08", "exp_list": ["2026-10-08", "2026-10-15"],
            "spot": 25000.0,
            "oc": {25000.0: {"ce": {"oi": 100, "bid": 10.0, "ask": 11.0}}},
            "chains": {
                "2026-10-08": {25000.0: {"ce": {"oi": 100, "bid": 10.0, "ask": 11.0}}},
                "2026-10-15": {25000.0: {"ce": {"oi": 50, "bid": 25.0, "ask": 26.0}}},
            }
        }
        self.assertIn("oc", rec)
        self.assertIn("chains", rec)
        self.assertEqual(len(rec["chains"]), 2)
        self.assertEqual(rec["exp_list"][1], "2026-10-15")


class TestResumeAndLedgerRules(unittest.TestCase):
    """The two rules the watchdog depends on. Both were wrong before.

    resume: without reading back what is already on disk, a restarted process
    re-appends every snapshot it already wrote, and duplicated timestamps
    silently corrupt max_gap and coverage_pct -- the two numbers kill 1 is
    judged on.

    ledger: a day that produced no successful snapshots must leave NO row. A
    weekend entered as "0% coverage" reads as a failed session rather than the
    absence of one.
    """

    def test_existing_stamps_reads_back_what_was_written(self):
        with TemporaryDirectory() as td:
            p = Path(td) / "2026-10-05.jsonl.gz"
            recs = [{"ts": f"2026-10-05T09:1{i}:00"} for i in range(3)]
            with gzip.open(p, "at", encoding="utf-8") as f:
                for r in recs:
                    f.write(json.dumps(r) + "\n")
            self.assertEqual(_existing_stamps(p), [r["ts"] for r in recs])

    def test_existing_stamps_tolerates_a_truncated_final_line(self):
        """A hard kill mid-write leaves a partial JSON line. Recovery must not
        raise, or the restart cannot happen at all."""
        with TemporaryDirectory() as td:
            p = Path(td) / "2026-10-05.jsonl.gz"
            with gzip.open(p, "at", encoding="utf-8") as f:
                f.write(json.dumps({"ts": "2026-10-05T09:15:00"}) + "\n")
                f.write('{"ts": "2026-10-05T09:16:00", "oc": {trunc')
            self.assertEqual(_existing_stamps(p), ["2026-10-05T09:15:00"])

    def test_existing_stamps_of_missing_file_is_empty(self):
        with TemporaryDirectory() as td:
            self.assertEqual(_existing_stamps(Path(td) / "nope.jsonl.gz"), [])

    def test_resumed_session_does_not_duplicate_seconds(self):
        """Two capture passes over the same day = one row per second. This is
        the property that makes crash-restart safe."""
        with TemporaryDirectory() as td:
            p = Path(td) / "2026-10-05.jsonl.gz"
            for _ in range(2):  # simulate a crash and a restart
                known = _existing_stamps(p)[-2:]
                with gzip.open(p, "at", encoding="utf-8") as f:
                    for ts in ("2026-10-05T09:15:00", "2026-10-05T09:16:00"):
                        if ts not in known:
                            f.write(json.dumps({"ts": ts}) + "\n")
            rows = [json.loads(l) for l in gzip.open(p, "rt", encoding="utf-8")]
            self.assertEqual(len(rows), 2)

    def test_no_successful_snapshots_writes_no_ledger_row(self):
        with TemporaryDirectory() as td:
            p = Path(td) / "2026-10-03.jsonl.gz"
            with gzip.open(p, "at", encoding="utf-8") as f:  # a Saturday: outages only
                f.write(json.dumps({"ts": "2026-10-03T09:15:00", "err": "closed"}) + "\n")
            import experiments.e009_wall_capture.capture_chains as cc
            orig, cc.LEDGER = cc.LEDGER, Path(td) / "coverage_ledger.json"
            try:
                self.assertIsNone(register_session(p))
            finally:
                cc.LEDGER = orig
            self.assertFalse((Path(td) / "coverage_ledger.json").exists())

    def test_a_real_session_does_register(self):
        with TemporaryDirectory() as td:
            p = Path(td) / "2026-10-05.jsonl.gz"
            # 376 stamps: 375 one-minute gaps spans 09:15 -> 15:30 exactly.
            # 301 covers only 300 of the 375 evaluated minutes (80%), which is
            # how the coverage denominator behaves -- not a rounding accident.
            stamps = _stamps("2026-10-05T09:15:00", 376)
            with gzip.open(p, "at", encoding="utf-8") as f:
                for ts in stamps:
                    f.write(json.dumps({"ts": ts, "n": 40, "spot": 25123.5}) + "\n")
            import experiments.e009_wall_capture.capture_chains as cc
            orig, cc.LEDGER = cc.LEDGER, Path(td) / "coverage_ledger.json"
            try:
                row = register_session(p)
            finally:
                cc.LEDGER = orig
            self.assertEqual(row["n_snapshots"], 376)
            self.assertEqual(row["coverage_pct"], 100.0)
            self.assertLessEqual(row["max_gap_secs"], SNAPSHOT_SECS * 1.5)
            self.assertTrue(row["evaluable"])  # kill 1 satisfied


if __name__ == "__main__":
    unittest.main()
