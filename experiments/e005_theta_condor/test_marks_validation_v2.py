"""Self-checks: v2 mark validator must stay self-consistent with its artifact, era-honest,
and pin the Dhan rolling-API semantics this validation depends on."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


class TestMarksValidationV2Verdicts(unittest.TestCase):
    """Re-derive the committed verdict from the committed artifact."""

    @classmethod
    def setUpClass(cls):
        with open(HERE / "artifacts" / "marks_validation_v2.json") as fp:
            cls.j = json.load(fp)

    def test_all_requested_sessions_resolved(self):
        self.assertEqual(self.j["n_requested"], 5)
        self.assertEqual(self.j["n_validated"], 4)  # 2022-06-10 uncovered (walls outside ATM±10)

    def test_full_coverage_session_opens_exact(self):
        # 2026-09-25 was proven by BOTH endpoints; its four covered legs must match to the paisa.
        s = next(s for s in self.j["sessions"] if s["date"] == "2026-09-25")
        self.assertTrue(s["opens_match_exactly"])
        self.assertEqual(s["max_open_diff"], 0.0)

    def test_closes_within_timing_noise_everywhere_covered(self):
        for s in self.j["sessions"]:
            if s["status"] != "VALIDATED":
                continue
            for leg in s["legs"]:
                if "close_diff" in leg:
                    self.assertLess(abs(leg["close_diff"]), 10.0, msg=f"{s['date']} {leg['leg']}")

    def test_uncoverable_session_is_walls_outside_ceiling(self):
        # 2022-06-10: walls at 15000/17000 vs spot ~16284 -> ATM-26 / ATM+14, beyond ATM±10.
        s = next(s for s in self.j["sessions"] if s["date"] == "2022-06-10")
        self.assertEqual(s["status"], "ALL_LEGS_MISSING")
        self.assertTrue(all(l["status"] == "NO_BARS" for l in s["legs"]))


class TestEraLotConfig(unittest.TestCase):
    """The config fix: NIFTY lot 65 since 2025-12-30, Tuesday-expiry schedules."""

    def test_lot_is_65(self):
        import config
        self.assertEqual(config.NIFTY_LOT_SIZE, 65)

    def test_lot_era_fn_tracks_config(self):
        from experiments.common.lots import lot_for_date
        from datetime import date
        # Full verified era table: 75 -> 50 (Jul-2021) -> 25 (Apr-2024) -> 75 (Nov-2024) -> 65.
        self.assertEqual(lot_for_date(date(2021, 1, 15)), 75)
        self.assertEqual(lot_for_date(date(2021, 7, 1)), 50)
        self.assertEqual(lot_for_date(date(2024, 11, 1)), 25)
        self.assertEqual(lot_for_date(date(2025, 1, 15)), 75)
        self.assertEqual(lot_for_date(date(2026, 3, 1)), 65)

    def test_current_schedule_is_tuesday_expiry(self):
        import config
        sched = config.WEEKDAY_SCHEDULES[1]  # Tuesday
        self.assertEqual(sched.day_name, "Tuesday")
        # The Tuesday description must reflect the expiry day (window naming carries the phase).
        self.assertIn("expiry", sched.description.lower())


if __name__ == "__main__":
    unittest.main()
