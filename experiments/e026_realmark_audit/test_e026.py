"""E026 tests.

Two jobs, in priority order.

1. Pin the invariants that keep e013's revival honest: the control must
   reproduce the predecessor to the paisa, the exit mark's contract identity
   must hold per trade, and the arithmetic-impossibility bound must never be
   breached on a trustworthy mark.

2. Pin the traps this audit walked into, because each one produced a
   WRONG VERDICT on its first run and would do so again silently:
     - the `fly_value` sign convention (Gate 0 caught it: -Rs 20.9L vs +Rs 4.1L);
     - treating the arithmetic bound as if it applied at intraday marks;
     - collapsing "bound applies here" into "price is trustworthy here",
       which hid an expiry-day stale close;
     - pooling expiry-day marks into the verdict.

The heavy audit runs once per module and is cached. The pure-math tests are
instant and need no data.
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

from experiments.e026_realmark_audit.audit_realmark import (
    WING_WIDTH,
    build_bhavcopy_calendar,
    check_identity,
    check_impossibility,
    collect_trades,
    e013_credit,
    fly_price,
    front_expiry,
    intrinsic_debit,
    iron_fly_bounds,
    leg_close,
    load_front_chain,
    run,
    stats,
)

_AUDIT: dict = {}


def audit_once():
    """Run the full audit once. ~3 min. Shared by every integration test."""
    if "result" not in _AUDIT:
        _AUDIT["result"] = run()
    return _AUDIT["result"]


# --------------------------------------------------------------- pure math ---
class TestFlyValueConvention(unittest.TestCase):
    """e013's `fly_value` is ATM straddle MINUS wings, and the book profits when
    that value DECAYS. Getting this sign wrong is not detectable from a
    plausible-looking PnL column — it produced -Rs 20,94,065 here — which is
    exactly why Gate 0 exists. These tests make the sign a fact, not a habit."""

    def test_atm_fly_value_is_straddle_minus_wings(self):
        from core.pricing import bs_call, bs_put
        spot, atm, iv, t = 25000.0, 25000.0, 0.15, 0.01
        v = fly_price(spot, atm, atm + WING_WIDTH, atm - WING_WIDTH, iv, t)
        straddle = bs_call(spot, atm, iv, t) + bs_put(spot, atm, iv, t)
        wings = (bs_call(spot, atm + WING_WIDTH, iv, t)
                 + bs_put(spot, atm - WING_WIDTH, iv, t))
        self.assertAlmostEqual(v, straddle - wings, places=9)
        self.assertGreater(v, 0.0)
        self.assertLess(v, straddle)

    def test_credit_is_not_negated(self):
        """e013's `credit` variable is POSITIVE fly value, not a negative.
        `e013_credit` must therefore return fly_price unmodified."""
        v = e013_credit(25000.0, 25000.0, 25150.0, 24850.0, 0.15, 2.0)
        self.assertGreater(v, 0.0, "e013_credit inverted the sign; see Gate 0")

    def test_intrinsic_debit_is_capped_at_wing_width(self):
        """The closed-form fact Gate 5 rests on: an iron fly's payoff at
        expiry is min(|S-K|, 150), for ANY spot."""
        atm = 25000.0
        for spot in (20000.0, 24000.0, 25000.0, 25100.0, 30000.0):
            d = intrinsic_debit(spot, atm, atm + WING_WIDTH, atm - WING_WIDTH)
            self.assertGreaterEqual(d, -1e-9, f"negative payoff at S={spot}")
            self.assertLessEqual(d, WING_WIDTH + 1e-9, f"payoff exceeds wing width at S={spot}")

    def test_iron_fly_bounds_bracket_the_expiry_payoff(self):
        entry, lot = 42.0, 65
        lo, hi = iron_fly_bounds(entry, lot)
        for exit_val in (0.0, 10.0, WING_WIDTH):
            gross = (entry - exit_val) * lot
            self.assertGreaterEqual(gross, lo - 1e-6)
            self.assertLessEqual(gross, hi + 1e-6)


class TestFrontExpiry(unittest.TestCase):
    """Contract identity, in isolation. On an expiry day the contract expiring
    THAT DAY is the front contract — not tomorrow's. This is the e011 bug."""

    def test_expiry_day_selects_todays_contract(self):
        exps = [date(2026, 1, 20), date(2026, 1, 27)]
        self.assertEqual(front_expiry(exps, date(2026, 1, 20)), date(2026, 1, 20))
        self.assertEqual(front_expiry(exps, date(2026, 1, 21)), date(2026, 1, 27))

    def test_past_expiries_are_never_selected(self):
        exps = [date(2026, 1, 13), date(2026, 1, 20), date(2026, 1, 27)]
        self.assertEqual(front_expiry(exps, date(2026, 1, 21)), date(2026, 1, 27))

    def test_no_front_expiry_returns_none(self):
        self.assertIsNone(front_expiry([date(2026, 1, 13)], date(2026, 1, 20)))


class TestFailClosed(unittest.TestCase):
    """Section 5.5: missing data is NO TRADE, never a fabricated default."""

    def test_missing_leg_returns_none_not_zero(self):
        chain = pd.DataFrame([
            {"strike": 25000.0, "option_type": "CE", "close": 100.0},
        ])
        self.assertEqual(leg_close(chain, 25000.0, "CE"), 100.0)
        self.assertIsNone(leg_close(chain, 25000.0, "PE"), "absent leg must be None")
        self.assertIsNone(leg_close(chain, 26000.0, "CE"), "absent strike must be None")

    def test_nan_close_is_none(self):
        chain = pd.DataFrame([{"strike": 25000.0, "option_type": "CE", "close": float("nan")}])
        self.assertIsNone(leg_close(chain, 25000.0, "CE"))


# ------------------------------------------------------------- integration ---
class TestAuditGates(unittest.TestCase):
    """Every gate the PREREG froze, asserted against the recorded run."""

    @classmethod
    def setUpClass(cls):
        cls.df, cls.metrics = audit_once()

    def test_gate0_control_reproduces_e013_to_the_paisa(self):
        """THE load-bearing test. If this drifts, e026 says nothing about e013
        and every other number here is void."""
        arm = self.metrics["arms"]["A_control_published_convention"]
        self.assertEqual(arm["trades"], 193)
        self.assertAlmostEqual(arm["total_net_pnl"], 414721.03, delta=1.0)
        self.assertAlmostEqual(arm["profit_factor"], 9.41, delta=0.01)
        self.assertAlmostEqual(arm["win_rate"], 0.8394, delta=0.0001)
        self.assertTrue(self.metrics["gates"]["0_control_reproduces_predecessor"]["pass"])

    def test_gate1_contract_identity_zero_mismatches(self):
        self.assertEqual(self.metrics["gates"]["1_contract_identity_of_exit_mark"]["observed"], 0)
        self.assertEqual(self.metrics["diagnostics"]["identity_failures"], [])

    def test_gate5_impossibility_zero_violations_on_trusted_marks(self):
        self.assertEqual(self.metrics["gates"]["5_arithmetic_impossibility"]["observed"], 0)
        self.assertEqual(self.metrics["diagnostics"]["impossibility_failures"], [])

    def test_expiry_day_marks_are_never_pooled_into_the_verdict(self):
        """Arm C exists to be reported, not believed. If a change ever let
        expiry-day marks into Arm B, this is the test that should break."""
        b = self.metrics["arms"]["B_real_marks_valid_sample"]["trades"]
        c = self.metrics["arms"]["C_real_marks_expiry_day_EXCLUDED_FROM_VERDICT"]["trades"]
        self.assertGreater(c, 0, "Arm C must exist for the exclusion to mean anything")
        self.assertLess(b, b + c)
        # every Arm B row must have a non-expiry front expiry
        valid = self.df[self.df["mark_valid"]]
        self.assertTrue((~valid["expiry_is_trade_date"].fillna(True)).all())

    def test_stale_close_artifact_is_recorded_not_silently_dropped(self):
        """e018 measured expiry-day `close` as a stale last trade. e026 hit it
        again independently. It must be surfaced as evidence, not discarded —
        otherwise the next reader re-derives it from scratch."""
        d = self.metrics["diagnostics"]
        self.assertGreaterEqual(
            d["expiry_day_close_violation_count"], 1,
            "the 2026-01-20 stale close should still be detected")

    def test_gate2_real_mark_coverage(self):
        self.assertTrue(self.metrics["gates"]["2_real_mark_coverage"]["pass"])
        self.assertGreaterEqual(self.metrics["gates"]["2_real_mark_coverage"]["observed_pct"], 50.0)

    def test_real_marked_arm_beats_its_kill_bars(self):
        """Pinned at the CORRECTED verdict, not the pre-e028 one.

        When e028 fixed this experiment's loader, gate 3 stopped passing: arm
        B's EV fell from +966 to +353 on the recovered 129-session sample,
        because the 64 sessions the encoding bug had hidden were half the book
        and the worse half. Asserting `pass` here would pin the bug in place.
        """
        self.assertFalse(self.metrics["gates"]["3_edge_survives_real_marks"]["pass"])
        self.assertLess(self.metrics["gates"]["3_edge_survives_real_marks"]["observed"], 600.0)
        self.assertTrue(self.metrics["gates"]["4_profit_factor_survives_real_marks"]["pass"])

    def test_real_marks_are_a_haircut_not_an_inflation(self):
        """The direction of the finding, pinned. A future change that makes the
        real mark BETTER than the model is the suspicious outcome."""
        gap = self.metrics["gap_decomposition"]
        self.assertGreater(gap["gap_from_modelling"], 0.0)
        self.assertLess(gap["real_1530"], gap["bs_1515"])

    def test_verdict_is_not_the_published_number(self):
        """Whatever the verdict, the published +4,14,721 must not be the
        figure the audit endorses. `struck` (post-e028) or `restate`
        (pre-e028) both satisfy this; a bare "SURVIVES" would not."""
        v = self.metrics["verdict"].lower()
        self.assertTrue("struck" in v or "restate" in v, v)
        self.assertNotEqual(
            self.metrics["arms"]["B_real_marks_valid_sample"]["total_net_pnl"],
            self.metrics["arms"]["A_control_published_convention"]["total_net_pnl"])


class TestCompositionClaim(unittest.TestCase):
    """e013 is labelled a 0DTE book. It is not, and the roadmap depends on
    knowing that."""

    @classmethod
    def setUpClass(cls):
        cls.df, cls.metrics = audit_once()

    def test_majority_of_trades_are_not_zero_dte(self):
        c = self.metrics["composition"]
        self.assertLess(c["sessions_dte_le_1"], c["trades"] if "trades" in c else 193)
        self.assertGreater(c["sessions_dte_ge_2"], 100)

    def test_dte_ge_two_carries_the_majority_of_pnl(self):
        self.assertGreater(self.metrics["composition"]["pct_pnl_from_dte_ge_2"], 50.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)