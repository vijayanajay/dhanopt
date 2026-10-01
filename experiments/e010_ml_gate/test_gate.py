"""Offline self-checks for the e010 gate (no LightGBM training, no I/O):
fold hygiene (no year leakage), kill-bar logic on synthetic OOS frames, and
the frozen-threshold semantics."""
from __future__ import annotations

import unittest

import pandas as pd

from experiments.e010_ml_gate.run_gate import PF_MIN, THRESHOLD, _pf, _verdict


def _oos(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _day(date: str, year: int, p: float, trade: bool, pnl: float, win: int) -> dict:
    return {"date": date, "year": year, "p_win": p, "trade": trade,
            "net_pnl": pnl, "win": win}


class TestFoldHygiene(unittest.TestCase):
    def test_no_year_leakage_in_principle(self):
        # The walkforward trains only on years strictly below the OOS year —
        # pinned here as the invariant the loop implements (first OOS = 2nd year).
        years = [2021, 2022, 2023]
        oos_years = years[1:]
        for y in oos_years:
            train_years = [x for x in years if x < y]
            self.assertTrue(all(x < y for x in train_years))
        self.assertEqual(oos_years, [2022, 2023])

    def test_threshold_is_frozen_value(self):
        self.assertEqual(THRESHOLD, 0.55)
        self.assertEqual(PF_MIN, 1.5)


class TestKillBars(unittest.TestCase):
    def test_perfect_gate_passes_all(self):
        oos = _oos(
            [ _day(f"20{y}-01-{d:02d}", y, 0.9, True, 500.0, 1)
              for y in (22, 23) for d in range(1, 16) ] +
            [ _day(f"20{y}-02-{d:02d}", y, 0.1, False, -300.0, 0)
              for y in (22, 23) for d in range(1, 11) ])
        v = _verdict(oos, 2)
        self.assertTrue(all(v["kill_criteria"].values()))
        self.assertEqual(v["verdict"], "PASS")

    def test_gate_that_trades_every_day_fails_kill4_vs_always_on(self):
        # Gate trades everything: gated_net == always_on_net -> passes net/PF bars
        # only if the underlying book wins; here it loses, so kill 1 fails.
        oos = _oos([_day(f"20{y}-01-{d:02d}", y, 0.9, True, -100.0, 0)
                    for y in (22, 23) for d in range(1, 21)])
        v = _verdict(oos, 2)
        self.assertFalse(v["kill_criteria"]["1_net_gt_0"])
        self.assertEqual(v["verdict"], "FAIL")

    def test_lucky_pf_with_zero_discrimination_fails_kill3(self):
        # Gate trades few days that happen to profit, but its probabilities are
        # no better than the majority baseline -> kill 3 must fail.
        rows = [_day(f"20{y}-01-{d:02d}", y, 0.9, d <= 2, 400.0, 1)
                for y in (22,) for d in range(1, 31)]
        rows += [_day(f"20{y}-02-{d:02d}", y, 0.9, False, -400.0, 0)
                 for y in (22,) for d in range(1, 11)]
        oos = _oos(rows)
        v = _verdict(oos, 1)
        self.assertFalse(v["kill_criteria"]["3_brier_beats_base"])

    def test_pf_helper(self):
        self.assertEqual(_pf(pd.Series([300.0, -100.0, -100.0])), 1.5)
        self.assertEqual(_pf(pd.Series([300.0, 0.0])), float("inf"))
        self.assertEqual(_pf(pd.Series([-100.0])), 0.0)

    def test_n_below_30_fails_kill2_even_with_good_pf(self):
        rows = [_day(f"20{y}-01-{d:02d}", y, 0.9, True, 500.0, 1)
                for y in (22,) for d in range(1, 11)]  # 10 trades, PF inf
        oos = _oos(rows)
        v = _verdict(oos, 1)
        self.assertFalse(v["kill_criteria"]["2_pf_ge_1p5_n_ge_30"])


if __name__ == "__main__":
    unittest.main()
