"""Self-checks for e030. No network; every function takes its data as arguments.

The single most important thing this suite pins is a NEGATIVE result: the
calendar spread §7.3 proposes is a DEBIT on every one of 1,415 sessions. If
that ever becomes positive, this file fails and the plan must be revisited —
which is the point of freezing the measurement before trusting it.
"""
from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path

from experiments.e030_calendar_credit.calendar_credit import (
    ARTIFACTS,
    CLEAR_RATE_BAR,
    COVER_BAR,
    _atm_strike,
    _leg_close,
    gate0_control,
    run,
)

HERE = Path(__file__).resolve().parent
PREREG = HERE / "PREREG.md"


class TestPreregFrozen(unittest.TestCase):
    """The PREREG must be frozen BEFORE the code, and must still describe what
    the code actually does. If a bar is edited here and not in the PREREG, or
    vice versa, this fails — that is the whole anti-post-hoc mechanism."""

    def test_prereg_exists_and_declares_every_gate(self):
        txt = PREREG.read_text(encoding="utf-8")
        self.assertIn("PREREG-frozen", txt)
        for gate in ("**0**", "**1**", "**2**", "**3**", "**4**"):
            self.assertIn(gate, txt)

    def test_code_bars_match_the_prereg_text(self):
        """If someone loosens CLEAR_RATE_BAR in code without touching the PREREG,
        the gate is no longer the one that was frozen. Fail."""
        txt = PREREG.read_text(encoding="utf-8")
        self.assertIn("> 50%", txt)                    # gate 3
        self.assertIn("3 × median(friction_pts)", txt)  # gate 4
        self.assertEqual(CLEAR_RATE_BAR, 0.50)
        self.assertEqual(COVER_BAR, 3.0)

    # NOTE: there is deliberately no mtime "PREREG is older than the code"
    # test. Fixing a typo in the PREREG is legitimate and would fail it, so it
    # punishes the wrong action and proves nothing. The content check above is
    # the real freeze mechanism -- it compares the bars themselves, which is
    # what "frozen before the numbers were seen" has to mean.


class TestFrictionControl(unittest.TestCase):
    def test_gate0_handles_the_shared_engine(self):
        g = gate0_control()
        self.assertTrue(g["pass"])
        # 4 legs x 2 sides x Rs 20, and 1.5 pts x lot 65 x 4 legs
        self.assertAlmostEqual(g["observed_brokerage"], 160.0, places=6)
        self.assertAlmostEqual(g["observed_slippage"], 390.0, places=6)


class TestSignConvention(unittest.TestCase):
    """The credit sign is the whole experiment. A flipped convention would
    report a large positive edge on a structure that in fact costs money."""

    def test_credit_is_front_minus_back(self):
        import pandas as pd
        chain = pd.DataFrame([
            {"expiry_date": date(2025, 3, 13), "strike": 22500.0,
             "option_type": "CE", "close": 60.0},
            {"expiry_date": date(2025, 3, 13), "strike": 22500.0,
             "option_type": "PE", "close": 55.0},
            {"expiry_date": date(2025, 3, 20), "strike": 22500.0,
             "option_type": "CE", "close": 80.0},
            {"expiry_date": date(2025, 3, 20), "strike": 22500.0,
             "option_type": "PE", "close": 75.0},
        ])
        front, nxt = date(2025, 3, 13), date(2025, 3, 20)
        front_legs = (_leg_close(chain, front, 22500.0, "CE")
                      + _leg_close(chain, front, 22500.0, "PE"))
        back_legs = (_leg_close(chain, nxt, 22500.0, "CE")
                     + _leg_close(chain, nxt, 22500.0, "PE"))
        credit = front_legs - back_legs
        self.assertAlmostEqual(credit, 115.0 - 155.0, places=6)
        self.assertLess(credit, 0)  # back richer -> short-front is a debit

    def test_missing_leg_is_none_never_interpolated(self):
        import pandas as pd
        chain = pd.DataFrame([
            {"expiry_date": date(2025, 3, 20), "strike": 22500.0,
             "option_type": "CE", "close": 80.0},
        ])
        self.assertIsNone(_leg_close(chain, date(2025, 3, 20), 22500.0, "PE"))

    def test_zero_close_is_treated_as_missing(self):
        import pandas as pd
        chain = pd.DataFrame([
            {"expiry_date": date(2025, 3, 20), "strike": 22500.0,
             "option_type": "CE", "close": 0.0},
        ])
        self.assertIsNone(_leg_close(chain, date(2025, 3, 20), 22500.0, "CE"))


class TestResult(unittest.TestCase):
    """Runs the full store once (class-level) and pins the verdict."""

    @classmethod
    def setUpClass(cls):
        cls.df, cls.metrics = run()

    def test_coverage_is_complete_and_published_per_year(self):
        cov = self.metrics["coverage"]
        self.assertEqual(cov["overall_pct"], 100.0)
        self.assertEqual(cov["excluded"], 0)
        years = {r["year"] for r in cov["per_year"]}
        self.assertEqual(years, {2021, 2022, 2023, 2024, 2025, 2026})
        for r in cov["per_year"]:
            self.assertEqual(r["coverage_pct"], 100.0)

    def test_contract_identity_holds(self):
        self.assertTrue(self.metrics["gates"]["1_contract_identity"]["pass"])
        self.assertEqual(self.metrics["gates"]["1_contract_identity"]["front_equals_next"], 0)

    def test_no_session_has_positive_credit(self):
        """THE FINDING. Short-front / long-back is a debit on every session in
        six years. p90 is still negative, so there is no tail that pays."""
        dist = self.metrics["credit_distribution_pts"]
        self.assertEqual(dist["frac_positive"], 0.0)
        self.assertLess(dist["p90"], 0.0)
        self.assertLess(dist["median"], 0.0)

    def test_phase_73_is_struck(self):
        self.assertIn("STRUCK", self.metrics["verdict"])
        self.assertFalse(self.metrics["gates"]["3_kill_gate_credit_clears_costs"]["pass"])
        self.assertFalse(self.metrics["gates"]["4_cover_at_reasonable_hit_rate"]["pass"])

    def test_it_claims_no_pnl(self):
        self.assertTrue(self.metrics["claims_no_pnl"])

    def test_artifacts_written(self):
        self.assertTrue((ARTIFACTS / "verdict.json").exists())
        self.assertTrue((ARTIFACTS / "session_credit.csv").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
