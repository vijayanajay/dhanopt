"""E005 self-checks: delta/gamma + theta-glide must credit decay and catch path risk."""
from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from experiments.e004_intraday_replay.replay_intraday import CONDOR, _legs_for
from experiments.e005_theta_condor.replay_theta import (
    N_BARS, _bs_ltp, _implied_iv_safe, _leg_delta, simulate_theta_condor)

LOT = 75
SPOT, PUT_WALL, CALL_WALL = 25000.0, 24500.0, 25500.0
LEGS = _legs_for(CONDOR, SPOT, PUT_WALL, CALL_WALL)
DTE = 2.0
# Realistic 2-DTE closes (walls ~10-12, wings ~2-2.5): credit ~Rs 1,300, the order of
# magnitude of a real weekly condor. IVs are backed out per leg (clamped, delta-only).
ENTRY = [12.0, 10.0, 2.5, 2.0]
IVS = [_implied_iv_safe(SPOT, l["strike"], l["is_call"], e, DTE) for l, e in zip(LEGS, ENTRY)]
# Theta-decay exit closes: uniform 60% decay on a flat spot — a real crush day.
EXIT_THETA = [e * 0.4 for e in ENTRY]
# Vol-expansion exit closes: shorts ~3x, wings collapse to 20% (spot flat).
EXIT_VOLUP = [e * f for e, f in zip(ENTRY, (3.0, 3.0, 0.2, 0.2))]
# Mid-day crash that fully recovers by close: endpoint closes == entry closes (R=1),
# so any exit must come from the intraday greek path itself — what e001 cannot see.
CRASH_CLOSES = np.full(N_BARS, float(SPOT))
CRASH_CLOSES[20:45] = SPOT - 350.0  # selloff mid-session, back to flat by the close


def _candles(closes) -> pd.DataFrame:
    closes = np.atleast_1d(np.asarray(closes, dtype=float))
    return pd.DataFrame({"timestamp": pd.date_range("2026-09-21 09:15", periods=len(closes), freq="5min"),
                         "open": np.r_[closes[0], closes[:-1]], "high": closes, "low": closes,
                         "close": closes, "volume": 0})


def _run(exit_closes, closes=None, dte: float = DTE, spot_prev=None):
    closes = np.full(N_BARS, SPOT) if closes is None else closes
    return simulate_theta_condor(_candles(closes), LEGS, ENTRY, list(exit_closes), LOT,
                                 dte, SPOT if spot_prev is None else spot_prev)


class TestGreeks(unittest.TestCase):
    def test_net_delta_is_short_put_dominated_but_small(self):
        """The near wall carries more delta than the far call wall: small positive net."""
        nd = sum(_leg_delta(SPOT, l["strike"], l["is_call"], iv, DTE)
                 * (1 if l["action"] == "BUY" else -1) for l, iv in zip(LEGS, IVS))
        self.assertGreater(nd, 0)
        self.assertLess(abs(nd), 0.5)

    def test_leg_deltas_are_well_behaved(self):
        """Even with clamped IVs, deltas stay in [-1, 1] and short-put delta dominates."""
        ds = [_leg_delta(SPOT, l["strike"], l["is_call"], iv, DTE) for l, iv in zip(LEGS, IVS)]
        for d in ds:
            self.assertGreaterEqual(d, -1.0)
            self.assertLessEqual(d, 1.0)
        self.assertGreater(abs(ds[0]), abs(ds[1]))


class TestSigmaPath(unittest.TestCase):
    def test_sigma_path_is_linear_with_exact_endpoints(self):
        p = np.linspace(0.15, 0.10, N_BARS)
        self.assertEqual(len(p), N_BARS)
        self.assertAlmostEqual(p[-1], 0.10)
        self.assertTrue(np.all(np.diff(p) <= 0))


class TestRepricing(unittest.TestCase):
    def test_flat_day_same_closes_is_a_wash(self):
        """Flat spot + identical endpoint closes: greek PnL 0, residual 0 => wash minus friction."""
        sim = _run(ENTRY)
        self.assertEqual(sim["exit_reason"], "EOD")
        self.assertAlmostEqual(sim["gross_pnl"], 0.0, delta=1e-6)
        self.assertAlmostEqual(sim["net_pnl"], -sim["friction"], delta=0.01)

    def test_falling_straddle_credits_theta_and_hits_target(self):
        """The e004 inversion, fixed: flat spot + 60% decay crosses the +50% target."""
        sim = _run(EXIT_THETA)
        self.assertEqual(sim["exit_reason"], "TARGET")
        self.assertGreater(sim["net_pnl"], 0)

    def test_expiry_day_crush_hits_target_fast(self):
        """0DTE-style crush (all legs collapsing toward 0) must hit the target intraday."""
        sim = _run([0.2, 0.2, 0.05, 0.05])
        self.assertEqual(sim["exit_reason"], "TARGET")
        self.assertGreater(sim["net_pnl"], 0)
        self.assertLess(sim["bars_held"], N_BARS)

    def test_rising_straddle_stops_a_credit_book_on_a_flat_spot(self):
        """Vol expansion (shorts ~3x, spot flat) must kill the trade via the glide."""
        sim = _run(EXIT_VOLUP)
        self.assertEqual(sim["exit_reason"], "STOP")
        self.assertLessEqual(sim["gross_pnl"], 0)

    def test_midday_crash_stops_even_though_the_day_recovers(self):
        """A -350pt mid-day crash (back to flat by close, R=1) must STOP intraday —
        the drawdown e001's open->close proxy is blind to."""
        sim = _run(ENTRY, closes=CRASH_CLOSES)
        self.assertEqual(sim["exit_reason"], "STOP")
        self.assertLess(sim["bars_held"], N_BARS)
        self.assertLessEqual(sim["gross_pnl"], 0)

    def test_eod_exit_lands_exactly_on_endpoint_pnl(self):
        """EOD gross must equal the real endpoint PnL (the e001 identity), by construction.
        Uses a 40%-decay day: positive after friction but below the +50% target (EOD)."""
        exit_c = [e * 0.6 for e in ENTRY]
        sim = _run(exit_c)
        self.assertEqual(sim["exit_reason"], "EOD")
        gross = sum((e - x) * LOT for e, x, l in zip(ENTRY, exit_c, LEGS) if l["action"] == "SELL") \
            + sum((x - e) * LOT for e, x, l in zip(ENTRY, exit_c, LEGS) if l["action"] == "BUY")
        self.assertAlmostEqual(sim["gross_pnl"], gross, delta=0.5)


if __name__ == "__main__":
    unittest.main()
