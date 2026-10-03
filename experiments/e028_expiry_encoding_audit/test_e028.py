"""E028 tests.

One bug, one class. Every test below fails if a typed date is ever compared
against a raw string again, or if a chain lookup is allowed to return an empty
frame without saying why.

The load-bearing ones are the cheap ones:

  - `test_both_encodings_resolve_to_the_same_date` — the specimen, without
    touching 935 MB of data. It is the whole defect in four lines.
  - `test_legacy_partition_has_a_front_chain` — the failure the defect caused,
    asserted against the 2021 store, because this is the session class that was
    silently empty for four years.
  - `test_with_expiry_date_refuses_a_frame_with_no_expiry` — the structural
    half: §5.5's fail-closed rule cannot tell "no data" from "wrong lookup",
    so the lookup has to say which.

The heavy control test runs the full audit once and is cached.
"""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from core.feeds.bhavcopy import parse_date, with_expiry_date
from experiments.e026_realmark_audit.audit_realmark import (
    _vol_frame, build_bhavcopy_calendar, check_identity, check_impossibility,
    collect_trades, load_front_chain, load_front_chain_string_eq,
)

LEGACY = "04-Feb-2021"
MODERN = "2021-02-04"


class TestExpiryEncoding(unittest.TestCase):
    """The specimen. No data required."""

    def test_both_encodings_resolve_to_the_same_date(self):
        self.assertEqual(parse_date(LEGACY), parse_date(MODERN))
        self.assertEqual(parse_date(LEGACY), date(2021, 2, 4))

    def test_a_formatted_date_is_not_the_stored_string(self):
        """The exact comparison e026 made. It is False for the legacy era.

        If a future NSE format makes these agree, this test will start failing
        and that failure is the signal to delete the string-equality loader.
        """
        self.assertNotEqual(str(parse_date(LEGACY)), LEGACY)
        self.assertEqual(str(parse_date(MODERN)), MODERN)

    def test_with_expiry_date_types_the_column(self):
        df = pd.DataFrame({"expiry": [LEGACY, MODERN], "close": [1.0, 2.0]})
        out = with_expiry_date(df)
        self.assertEqual(list(out["expiry_date"]), [date(2021, 2, 4)] * 2)

    def test_with_expiry_date_refuses_a_frame_with_no_expiry(self):
        with self.assertRaises(ValueError):
            with_expiry_date(pd.DataFrame({"close": [1.0]}))


class TestStoreCoverage(unittest.TestCase):
    """Against the real store. These are the sessions the bug emptied."""

    @classmethod
    def setUpClass(cls):
        cls.cal = build_bhavcopy_calendar()
        cls.legacy_days = [d for d in cls.cal if d.year <= 2023]

    def test_legacy_partitions_exist(self):
        self.assertGreater(len(self.legacy_days), 100, "no legacy partitions found")

    def test_legacy_partition_has_a_front_chain(self):
        """2023-12-20, the day of the one arithmetic-bound breach e028 surfaced.

        Its front chain has 96 strikes and multi-million volume. It read as
        EMPTY under the string comparison.
        """
        d = date(2023, 12, 20)
        self.assertIn(d, self.cal)
        chain, fe = load_front_chain(self.cal, d)
        self.assertIsNotNone(chain, "corrected loader found no chain on a legacy partition")
        self.assertGreater(len(chain), 100)
        self.assertEqual(fe, date(2023, 12, 21))

    def test_corrected_loader_finds_chains_the_string_loader_could_not(self):
        d = date(2023, 12, 20)
        bad, _ = load_front_chain_string_eq(self.cal, d)
        good, _ = load_front_chain(self.cal, d)
        self.assertEqual(bad is None or len(bad) == 0, True,
                         "the string loader is expected to find nothing here")
        self.assertGreater(len(good), 100)

    def test_every_partition_with_a_symbol_resolves_a_chain(self):
        """Coverage as a per-year report, which is how this was caught.

        A lookup that may return an empty frame without saying why is the
        structural defect; this asserts the corrected one never does.
        """
        empty = {}
        for d in sorted(self.cal):
            if d.weekday() >= 5:
                continue
            chain, _ = load_front_chain(self.cal, d)
            if chain is None or len(chain) == 0:
                empty.setdefault(d.year, []).append(d)
        self.assertEqual(
            {y: len(v) for y, v in empty.items()}, {},
            f"corrected loader returned an empty chain on: "
            f"{ {y: v[:3] for y, v in empty.items()} }")


class TestControl(unittest.TestCase):
    """The control that makes the finding attributable."""

    @classmethod
    def setUpClass(cls):
        from experiments.e028_expiry_encoding_audit import audit_encoding
        cls.v = audit_encoding.run()[1]

    def test_control_reproduces_e026_to_the_paisa(self):
        self.assertEqual(self.v["metrics"]["arm_A_control_as_published"]["trades"], 64)
        self.assertAlmostEqual(
            self.v["metrics"]["arm_A_control_as_published"]["total_net_pnl"],
            61842.51, places=2)

    def test_control_reproduces_e027_breakeven(self):
        self.assertAlmostEqual(self.v["breakeven_pts_per_leg"]["arm_A"], 2.64, places=2)

    def test_corrected_loader_only_adds_sessions_never_changes_a_mark(self):
        self.assertTrue(self.v["marks_identical_where_shared"])
        self.assertGreater(self.v["usable_arm_B"], self.v["usable_arm_A"])

    def test_contract_identity_holds_on_the_recovered_sample(self):
        vol, _ = _vol_frame()
        n, bad = check_identity(collect_trades(vol, build_bhavcopy_calendar()),
                                build_bhavcopy_calendar())
        self.assertEqual(n, 0, bad[:3])

    def test_no_impossibility_violation_on_trustworthy_marks(self):
        vol, _ = _vol_frame()
        n, bad, _ = check_impossibility(collect_trades(vol, build_bhavcopy_calendar()))
        self.assertEqual(n, 0, bad[:3])


class TestVerdict(unittest.TestCase):
    """The decision, pinned so it cannot be quietly restated."""

    @classmethod
    def setUpClass(cls):
        from experiments.e028_expiry_encoding_audit import audit_encoding
        cls.v = audit_encoding.run()[1]

    def test_verdict_is_recorded(self):
        self.assertEqual(self.v["verdict"], "DEAD_AT_REALISTIC_FILL")

    def test_the_edge_gate_fails_on_the_full_sample(self):
        g = self.v["gates"]["4_edge_at_realistic_fill"]
        self.assertFalse(g["pass"])
        self.assertLess(g["observed"], 400.0)

    def test_no_session_before_2024_is_missing_a_mark_any_more(self):
        """The claim RETROSPECTIVE s5.11 used to make is now false, by data."""
        self.assertEqual(self.v["era_cut"]["arm_B"]["by_year"]["2021"]["sessions"], 19)
        self.assertEqual(self.v["era_cut"]["arm_B"]["by_year"]["2022"]["sessions"], 21)
        self.assertEqual(self.v["era_cut"]["arm_B"]["by_year"]["2023"]["sessions"], 18)


if __name__ == "__main__":
    unittest.main(verbosity=2)
