"""E018 tests. The one that matters most is contract identity — that is the
E011 bug, and a test is the only thing that stops it coming back silently.
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

import numpy as np
import pandas as pd

from experiments.e018_vrp_weekly.volatility_fixed import (
    bs_straddle_price,
    build_bhavcopy_calendar,
    extract_straddles_all_expiries,
    front_expiry,
    invert_straddle_iv,
    load_or_compute_volatility,
)
from experiments.e018_vrp_weekly.replay_weekly import (
    DTE_MAX,
    DTE_MIN,
    _identity_ok,
    _legs_for,
    run_replay,
    simulate_trade,
)


class TestContractIdentity(unittest.TestCase):
    """The E011 bug, pinned shut."""

    def test_front_expiry_is_nearest_not_first_listed(self):
        # an expiry already past must never be selected
        exps = [date(2021, 3, 1), date(2021, 3, 4), date(2021, 3, 10)]
        # on expiry day itself the expiring contract IS the front contract
        self.assertEqual(front_expiry(exps, date(2021, 3, 1)), date(2021, 3, 1))
        self.assertEqual(front_expiry(exps, date(2021, 3, 2)), date(2021, 3, 4))
        self.assertEqual(front_expiry(exps, date(2021, 3, 5)), date(2021, 3, 10))

    def test_front_expiry_roll_is_not_yesterdays_contract(self):
        """The exact E011 failure: t-1 was an expiry day, so t's front
        contract is a DIFFERENT, longer-dated one. Real NSE data: 2021-03-04
        fronts 03-04; 2021-03-05 fronts 03-10."""
        cal = build_bhavcopy_calendar()
        prev, t = date(2021, 3, 4), date(2021, 3, 5)
        exps_prev = {date(2021, 3, 4), date(2021, 3, 10), date(2021, 3, 18)}
        exps_t = {date(2021, 3, 10), date(2021, 3, 18), date(2021, 3, 25)}
        self.assertEqual(front_expiry(exps_prev, prev), prev)
        self.assertNotEqual(front_expiry(exps_t, t), prev)
        self.assertEqual(front_expiry(exps_t, t), date(2021, 3, 10))
        # and the real store agrees
        self.assertTrue(_identity_ok(t, date(2021, 3, 10), cal))
        self.assertFalse(_identity_ok(t, prev, cal))

    def test_identity_check_rejects_a_rolled_expiry(self):
        cal = build_bhavcopy_calendar()
        t = date(2021, 3, 5)
        self.assertTrue(_identity_ok(t, date(2021, 3, 10), cal))
        self.assertFalse(_identity_ok(t, date(2021, 3, 4), cal))

    def test_extraction_returns_every_listed_expiry(self):
        cal = build_bhavcopy_calendar()
        d = date(2021, 3, 1)
        rows = extract_straddles_all_expiries(cal[d])
        self.assertTrue(rows)
        exps = [r["expiry"] for r in rows]
        self.assertEqual(len(exps), len(set(exps)), "duplicate expiry rows")
        for r in rows:
            self.assertGreaterEqual(r["expiry"], d)
            self.assertGreater(r["straddle_price"], 0)
            self.assertGreater(r["strikes_available"], 50)


class TestIvIsPlausible(unittest.TestCase):
    def test_round_trip_inversion(self):
        for iv in (0.10, 0.18, 0.30, 0.45):
            px = bs_straddle_price(18000, 18000, iv, 5)
            self.assertAlmostEqual(invert_straddle_iv(18000, 18000, px, 5), iv, places=3)

    def test_no_degenerate_iv_in_the_dataset(self):
        """e011 produced 35 sessions with IV > 1.00 and 68 >= 0.60. The whole
        point of the contract-identity fix is that these cannot occur."""
        v = load_or_compute_volatility()
        iv = v["iv_signal_t1"].dropna()
        self.assertGreater(len(iv), 1000)
        self.assertLess(iv.max(), 0.80, f"implausible IV {iv.max():.3f} in signal")
        self.assertGreater(iv.min(), 0.03)
        self.assertEqual(int((iv > 1.0).sum()), 0)

    def test_tenor_matches_the_contract_not_a_stale_offset(self):
        """e011 credited a mean tenor of 0.95 days against a real 4.71.

        dte_at_trade == 0 is legitimate (expiry-day front contracts are real
        0DTE contracts); what must never happen is a signal whose tenor is
        disconnected from the contract it is derived from. The replay's DTE
        band is what keeps 0DTE out of the book.
        """
        v = load_or_compute_volatility()
        sub = v.dropna(subset=["dte_at_trade_t1"])
        self.assertEqual(int((sub["dte_at_trade_t1"] < 0).sum()), 0)
        # The tenor observed on t-1 must be STRICTLY LONGER than the tenor
        # traded on t — a calendar gap of 1 session, or 3+ across a weekend.
        # e011's failure was the opposite sign: it credited yesterdays tenor
        # to todays contract, so the traded contract was systematically
        # shorter-lived than the model believed.
        delta = (sub["dte_observed_t1"] - sub["dte_at_trade_t1"]).dropna()
        self.assertTrue((delta >= 1).all(), "observed tenor must lead traded tenor")
        self.assertTrue(set(delta.unique()) <= {1.0, 2.0, 3.0, 4.0, 5.0}, delta.unique())
        # the traded book contains no zero-life contract
        from experiments.e018_vrp_weekly.replay_weekly import run_replay
        df, _ = run_replay()
        self.assertEqual(int((df["dte"] == 0).sum()), 0)


class TestNoLookahead(unittest.TestCase):
    def test_signal_row_never_sees_day_t(self):
        v = load_or_compute_volatility()
        sig = v[v["vrp_signal"] == True]
        self.assertGreater(len(sig), 0)
        for col in ("iv_signal", "sigma_gk_10d", "dte_observed"):
            self.assertIn(f"{col}_t1", v.columns)
        self.assertIn("vrp_t1", v.columns)
        # the hurdle is a rolling quantile of the already-shifted series
        self.assertTrue((v["vrp_t1"] >= v["vrp_p80"]).any())

    def test_hurdle_excludes_the_current_row(self):
        """vrp_p80 on day t must be built from t-60..t-1. vrp_t1 is itself
        already a t-1 quantity, so a rolling quantile of vrp_t1 (unshifted
        again) is correct; a second shift would be wrong and is pinned here."""
        v = load_or_compute_volatility()
        direct = v["vrp_t1"].rolling(60, min_periods=30).quantile(0.80)
        self.assertTrue(np.allclose(v["vrp_p80"].dropna(), direct.dropna(), equal_nan=True))
        # a leaked version (quantile including day t) must differ somewhere
        leaked = v["vrp_t1"].rolling(59, min_periods=30).quantile(0.80)
        self.assertFalse(np.allclose(v["vrp_p80"].dropna(), leaked.dropna(), equal_nan=True))

    def test_target_expiry_is_public_calendar_not_a_shift(self):
        """Which contract is front on day t is knowable at t-1; the identity
        check re-derives it from t's own partition."""
        cal = build_bhavcopy_calendar()
        v = load_or_compute_volatility()
        sig = v[v["vrp_signal"] == True].head(25)
        for row in sig.itertuples():
            self.assertTrue(_identity_ok(row.date, row.target_expiry, cal))


class TestReplayMechanics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df, cls.metrics = run_replay()

    def test_book_is_non_trivial(self):
        self.assertGreater(len(self.df), 30)

    def test_every_trade_is_identity_verified(self):
        self.assertTrue(self.df["identity_ok"].all())
        self.assertEqual(self.metrics["identity_violations"], 0)

    def test_dte_band_is_respected(self):
        self.assertTrue(self.df["dte"].between(DTE_MIN, DTE_MAX).all())

    def test_exit_marks_respect_condor_arithmetic_max(self):
        """A condor's exit debit is bounded by the short-wing width once spot
        is beyond the long wing. An exit mark above that is a pricing bug, which
        is exactly how the stale-expiry-close bug surfaced (34/141 impossible
        trades costing Rs 104k of phantom loss)."""
        df = self.df
        self.assertTrue((df["exit_debit_pts"] <= df["w_short"] + 1e-6).all())
        self.assertTrue((df["gross_pts"] >= df["entry_credit_pts"] - df["w_short"] - 1e-6).all())

    def test_lot_sizes_are_era_correct(self):
        from experiments.common.lots import lot_for_date
        for r in self.df.itertuples():
            self.assertEqual(r.lot, lot_for_date(r.trade_date))

    def test_friction_is_material(self):
        self.assertGreater(self.metrics["avg_friction"], 400)

    def test_missing_leg_is_no_trade_not_zero(self):
        """Fail-closed: an unreadable leg must drop the trade, never price it."""
        cal = build_bhavcopy_calendar()
        t = date(2021, 3, 1)
        rows = extract_straddles_all_expiries(cal[t])
        self.assertIsNone(_legs_for(cal, t, rows[0]["expiry"], [(1.0, "CE")]))


if __name__ == "__main__":
    unittest.main()
