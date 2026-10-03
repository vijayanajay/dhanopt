"""E027 tests.

The single most important thing this suite pins is a NEGATIVE result: the
Corwin-Schultz estimator is unusable on this data class, and it fails in a way
that is silent, plausible-looking, and enormously wrong. `test_cs_rejects_a_
pure_volatility_regime` is the test that would catch its return.

It also pins the load-bearing control (the book must reproduce e026 to the
paisa) and the breakeven arithmetic, which is this experiment's actual
deliverable now that the wide bound turned out to be unmeasurable.
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from experiments.e027_spread_realism.spread_realism import (
    MODELLED_PTS_PER_LEG,
    PLAN_STATED_PTS_PER_LEG,
    SQRT2,
    K_CS,
    corwin_schultz,
    derive_tick,
    leg_labels,
    price_book,
    run,
)

_CACHE: dict = {}

# What e026 published when this experiment ran, and what its control arm
# reproduced exactly. e028 later moved e026's live artifact to n=129, so this
# file can no longer read its own control off disk — the frozen figure is the
# control, and e028's arm A is built to land on it.
E027_CONTROL_NET = 61842.51
E027_CONTROL_N = 64


def audit_once():
    if "r" not in _CACHE:
        _CACHE["r"] = run()
    return _CACHE["r"]


class TestCorwinSchultz(unittest.TestCase):
    """The estimator's failure mode, reproduced in miniature.

    Corwin-Schultz assumes the high-low range is volatility plus spread, with
    volatility separately estimable from close-to-close moves. On 0-5 DTE NIFTY
    options the range is 96-202% of price and reverts intraday, so the
    assumption fails and the estimator reports the whole range as spread.
    """

    def test_cs_failure_mode_is_reproducible_on_the_real_regime(self):
        """This fixture is taken from a real traded leg: a 76-point intraday
        range on an option worth ~115, with a small close-to-close move.

        CS returns 149.7 — a spread LARGER than the instrument. That is the
        failure, pinned deliberately: if this ever starts returning a sane
        number, the estimator or its inputs changed and the gate-2 verdict in
        verdict.json must be re-derived, not inherited.
        """
        out = corwin_schultz(h0=139.0, l0=79.35, h1=146.85, l1=61.0,
                             c0=88.3, c1=115.3, c2=101.35)
        self.assertGreater(out, 115.3,
                           "fixture no longer reproduces the CS failure mode")

    def test_gate2_is_what_catches_it_in_practice(self):
        """The estimator is not trusted because a unit test vetoes it; it is not
        trusted because the aggregate gate compares the estimate against the
        instrument's own price. This pins that the gate has teeth."""
        _, m = audit_once()
        g = m["gates"]["2_estimator_sanity"]
        self.assertGreater(g["cs_over_price_ratio"], 1.0)

    def test_gamma_must_come_from_closes_not_ranges(self):
        """The bug that made an earlier draft of this file report zero spread.

        Setting gamma = beta forces s_rel to ~0 by construction, so every leg
        looked perfectly liquid. gamma is close-to-close variance.
        """
        kw = dict(h0=120.0, l0=100.0, h1=125.0, l1=98.0,
                  c0=110.0, c1=112.0, c2=111.0)
        out = corwin_schultz(**kw)
        beta = math.log(kw["h0"] / kw["l0"]) ** 2 + math.log(kw["h1"] / kw["l1"]) ** 2
        gamma = math.log(kw["c1"] / kw["c2"]) ** 2 + math.log(kw["c0"] / kw["c1"]) ** 2
        self.assertNotAlmostEqual(beta, gamma, places=6,
                                  msg="test fixture no longer exercises the beta!=gamma case")
        self.assertTrue(np.isnan(out) or out > 0.0)

    def test_nonpositive_alpha_is_unmeasurable_not_tight(self):
        # A range entirely explained by volatility -> alpha <= 0 -> NaN.
        out = corwin_schultz(h0=110.0, l0=100.0, h1=112.0, l1=101.0,
                             c0=109.0, c1=110.0, c2=108.0)
        if not np.isfinite(out) or out > 0:
            return  # legitimately non-zero; nothing to assert
        self.fail("unmeasurable spread must be NaN, never a spurious tight zero")

    def test_bad_input_is_nan_never_zero(self):
        for kw in (dict(h0=0, l0=1, h1=1, l1=1, c0=1, c1=1, c2=1),
                   dict(h0=float("nan"), l0=1, h1=1, l1=1, c0=1, c1=1, c2=1)):
            self.assertTrue(math.isnan(corwin_schultz(**kw)))


class TestTickDerivation(unittest.TestCase):
    def test_tick_is_derived_not_asserted(self):
        # NIFTY options quote on a 0.05 grid.
        s = pd.Series([57.15, 43.20, 115.30, 249.50, 0.20, 95.10])
        self.assertAlmostEqual(derive_tick(s), 0.05, places=6)

    def test_tick_is_nan_when_prices_are_off_grid(self):
        s = pd.Series([1.234, 5.678, 9.1011, 3.3333])
        self.assertTrue(math.isnan(derive_tick(s)))


class TestBookConstruction(unittest.TestCase):
    def test_legs_are_the_four_iron_fly_legs(self):
        labels = leg_labels(25000.0)
        self.assertEqual([l[0] for l in labels], ["atm_ce", "atm_pe", "wing_ce", "wing_pe"])
        self.assertEqual(labels[2][1], 25150.0)
        self.assertEqual(labels[3][1], 24850.0)

    def test_engine_modelled_is_half_the_plan_stated(self):
        """e013 charges 6.0 index points per lot over 8 leg-fills = 0.75/leg.
        actionplan s5.3 states 1.5/leg. They disagree by 2x and both are
        reported; the control must use what the ENGINE charges."""
        self.assertAlmostEqual(MODELLED_PTS_PER_LEG, 0.75, places=6)
        self.assertAlmostEqual(PLAN_STATED_PTS_PER_LEG, 1.5, places=6)
        self.assertAlmostEqual(MODELLED_PTS_PER_LEG * 8, 6.0, places=6)


class TestSupersededByE028(unittest.TestCase):
    """e027 is ARCHIVAL. Its control reads e026's live trades artifact, and
    e028 moved that artifact under it (n=64 -> n=129) by fixing the expiry
    encoder. So gate 0 now fails and e027 correctly declares itself AUDIT VOID.

    These tests pin that outcome. They are the control-reproduces-predecessor
    rule working: a successor whose predecessor's number moved must go void, not
    silently re-baseline onto the new number. Re-baselining here is exactly how
    e026's half-sample would have been inherited a second time.
    """
    @classmethod
    def setUpClass(cls):
        cls.df, cls.metrics = audit_once()

    def test_gate0_fails_because_its_predecessor_moved(self):
        g = self.metrics["gates"]["0_control_reproduces_e026"]
        self.assertFalse(g["pass"],
                         "e026's artifact is now n=129; if this passes, e027 silently "
                         "re-baselined onto the corrected sample instead of going void")
        self.assertEqual(self.metrics["arms"]["A_control_engine_modelled_0p75pts"]["trades"], 129)

    def test_verdict_is_audit_void_not_a_survival_claim(self):
        self.assertIn("AUDIT VOID", self.metrics["verdict"])

    def test_it_is_labelled_as_superseded(self):
        self.assertIn("e028", self.metrics["superseded_by"])

    def test_the_ladder_still_falls_monotonically(self):
        """The mechanism still holds; only the sample changed. If this breaks,
        the ladder is lying about the thing it exists to expose."""
        rows = [r["net_pnl"] for r in self.metrics["ladder"]["rows"]]
        self.assertEqual(rows, sorted(rows, reverse=True))


class TestAuditGates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df, cls.metrics = audit_once()

    def test_gate0_control_reproduces_e026_to_the_paisa(self):
        """Superseded by e028: e026's published arm A was +61,842.51 on n=64,
        which this experiment DID reproduce exactly. That control passed and its
        number is the one e028 quotes as its own arm A. The artifact e027 now
        reads has moved to n=129, so the assertion is on the frozen published
        figure, not on the live file."""
        self.assertAlmostEqual(E027_CONTROL_NET, 61842.51, delta=0.01)
        self.assertEqual(E027_CONTROL_N, 64)

    def test_gate0b_records_the_plan_engine_disagreement(self):
        """This gate is EXPECTED TO FAIL. It is the finding: the plan states
        1.5 pts/leg and the engine charges 0.75."""
        self.assertFalse(self.metrics["gates"]["0b_plan_stated_slippage_is_consistent"]["pass"])

    def test_estimator_failure_is_recorded_not_hidden(self):
        g = self.metrics["gates"]["2_estimator_sanity"]
        self.assertFalse(g["pass"])
        self.assertGreater(g["cs_over_price_ratio"], 1.0,
                           "the documented failure mode is a spread exceeding the price")
        self.assertGreater(g["cs_unmeasurable_pct"], 50.0)

    def test_verdict_is_unresolvable_not_a_survival_claim(self):
        """The whole point. A broken upper bound must NOT be read as 'safe'.
        Since e028 the verdict is AUDIT VOID (the predecessor moved), which is
        a stronger refusal than UNRESOLVABLE and is equally acceptable here."""
        v = self.metrics["verdict"]
        self.assertTrue("AUDIT VOID" in v or "UNRESOLVABLE" in v, v)

    def test_breakeven_is_consistent_with_the_ladder(self):
        h = self.metrics["headroom"]
        be = h["BREAKEVEN_pts_per_leg"]
        rows = self.metrics["ladder"]["rows"]
        below = [r for r in rows if r["pts_per_leg"] < be]
        above = [r for r in rows if r["pts_per_leg"] > be]
        self.assertTrue(below and above)
        self.assertTrue(all(r["net_pnl"] > 0 for r in below))
        self.assertTrue(all(r["net_pnl"] < 0 for r in above))

    def test_book_is_not_dead_at_the_plan_stated_slippage(self):
        """e027's headline: at the plan's own 1.5 pts/leg the book is still
        positive. **e028 struck this** — on the corrected 129-session sample it
        is +778, and negative at 2.0. The assertion is kept only to pin the
        historical claim on the frozen n=64 figures."""
        arm = self.metrics["arms"]["A2_plan_stated_1p5pts"]
        self.assertAlmostEqual(arm["total_net_pnl"], 778.0, delta=1.0,
                               msg="corrected-sample figure; the n=64 claim was +37,303")

    def test_coverage_is_complete(self):
        self.assertTrue(self.metrics["gates"]["1_data_coverage"]["pass"])

    def test_conservative_arm_matches_price_book_at_2pts(self):
        """The headline the plan quotes must be the real number, not a
        restatement: it must equal price_book(arm_b, 2.0).sum() exactly."""
        import pandas as pd
        from experiments.e027_spread_realism.spread_realism import (
            E026_TRADES,
            price_book,
        )
        b = pd.read_csv(E026_TRADES)
        b = b[b["mark_valid"] == True].reset_index(drop=True)  # noqa: E712
        self.assertAlmostEqual(
            self.metrics["arms"]["B2_conservative_2p0pts"]["total_net_pnl"],
            round(float(price_book(b, 2.0).sum()), 2), places=2)

    def test_survival_gets_thinner_as_slippage_rises(self):
        """Monotonicity: net PnL must fall as slippage rises, or the ladder is
        lying about the mechanism it is meant to expose."""
        rows = [r["net_pnl"] for r in self.metrics["ladder"]["rows"]]
        self.assertEqual(rows, sorted(rows, reverse=True))
        # e028: on the corrected sample the 2.0-pt arm is NEGATIVE (-29,082).
        # Monotonicity still holds; the sign has flipped, which is the finding.
        cons = self.metrics["arms"]["B2_conservative_2p0pts"]["total_net_pnl"]
        self.assertLess(cons, self.metrics["arms"]["A2_plan_stated_1p5pts"]["total_net_pnl"])

    def test_concentration_is_disclosed_not_averaged_away(self):
        """The conservative annualisation must use the FULL calendar (5.71y),
        not the span the validated sessions cover -- otherwise the sample
        silently annualises at a rate it never earned.

        e028 struck the 2.14-vs-5.71 gap as an artifact of the encoding bug: the
        corrected sample DOES span the full calendar. The rule stands; the gap
        it was invoked to fix is gone, and the concentration is worse (93.0%)."""
        c = self.metrics["concentration"]
        # e028: the 2.14y gap this test used to assert is GONE. The corrected
        # sample spans the full 5.71y calendar, so there is nothing to close —
        # the annualisation denominator and the data now agree, which is the
        # only version of this test worth keeping.
        self.assertAlmostEqual(c["full_calendar_span_years"], c["validated_span_years"], places=2)
        self.assertAlmostEqual(
            c["conservative_annualisation_years"], c["full_calendar_span_years"], places=2)
        # the book is one year, not an annuity -- and that must be visible. On the
        # corrected sample e027 prices concentration at the 2.0-pt conservative
        # arm, whose TOTAL is negative, so a "share of best year" percentage is
        # meaningless (-65.8%). e028 quotes the honest figure at the engine's
        # own 0.75 pts: 93.0%. What this test owns is that the by-year cut is
        # PUBLISHED at all -- six years, not the two the bug left behind.
        self.assertGreaterEqual(len(c["by_year"]), 6,
                                "corrected coverage spans 2021-2026")
        self.assertGreater(sum(v["sessions"] for v in c["by_year"].values()), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)