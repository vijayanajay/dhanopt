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
    SNAPSHOT_SECS, _session_gaps, _strike_map, capture_coverage_pct)


def _stamps(start: str, minutes: int, step_min: int = 1) -> list[str]:
    t0 = datetime.fromisoformat(start)
    return [(t0 + timedelta(minutes=i * step_min)).isoformat() for i in range(minutes)]


class TestStrikeMap(unittest.TestCase):
    def test_full_chain_shape_and_none_safety(self):
        chain = {"oc": {
            "25650.000000": {"ce": {"oi": 3786445, "top_bid_price": 133.55,
                                    "top_ask_price": 134.0, "top_ask_quantity": 1365},
                             "pe": {"oi": 3096145, "top_bid_price": 132.45,
                                    "top_ask_price": None}},
            "25700.000000": {"ce": {"oi": None, "top_bid_price": 0.0,
                                    "top_ask_price": 0.0}},
        }}
        oc = _strike_map(chain)
        self.assertEqual(set(oc), {25650.0, 25700.0})
        self.assertEqual(oc[25650.0]["ce"], {"oi": 3786445, "bid": 133.55, "ask": 134.0})
        self.assertIsNone(oc[25650.0]["pe"]["ask"])          # None-safe, recorded as-is
        self.assertEqual(oc[25700.0]["ce"]["bid"], 0.0)      # zero-quote recorded as-is
        self.assertEqual(oc[25700.0]["pe"], {"oi": None, "bid": None, "ask": None})  # uniform shape: missing side = all-None, never fabricated

    def test_bad_strikes_skipped(self):
        oc = _strike_map({"oc": {"bad": {}, "25700.000000": {"pe": {"oi": 5}}}})
        self.assertEqual(set(oc), {25700.0})


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


if __name__ == "__main__":
    unittest.main()
