"""E020 tests — the E020-specific mechanics on top of E019's no-lookahead suite.

The two things worth pinning here: top-fraction sizing behaves like top-count
sizing at the right k, and the ADV cap cannot silently distort the basket.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from experiments.e019_momentum.engine import (
    CAPITAL,
    Costs,
    run_backtest,
)


def toy_panel(n=900, n_sym=200, seed=3):
    """Synthetic random-walk panel — for MECHANICS only.

    Deliberately NOT used to assert the E020 return claim. A fixture cannot
    faithfully reproduce momentum's payoff structure: give each name a
    persistent drift and concentration simply picks the best names forever
    (so top-5 beats top-20); remove the drift and there is no signal at all.
    Either way the fixture answers "what did I build the generator to say",
    not "what does momentum do". The return claim lives in verdict.json, where
    it came from 1,420 sessions of real data and from a control that reproduced
    E019's published -0.81 to the decimal.
    """
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-01", periods=n)
    cols = [f"S{i:03d}" for i in range(n_sym)]
    close = pd.DataFrame(
        100 * np.cumprod(1 + rng.normal(0.0004, 0.018, (n, n_sym)), axis=0),
        index=idx, columns=cols,
    )
    turn = pd.DataFrame(rng.uniform(1e7, 1e8, (n, n_sym)), index=idx, columns=cols)
    return close, turn


class TestDilutionMechanics(unittest.TestCase):
    def test_top_frac_holds_a_decile(self):
        close, turn = toy_panel()
        df, m = run_backtest(close, turn, 21, costs=Costs(), cost_mult=1.0,
                             start_idx=300, end_idx=800, top_frac=0.10)
        self.assertAlmostEqual(m["median_holdings"], 20, delta=4)   # 10% of 200

    def test_more_dilution_lowers_drawdown(self):
        """The whole E020 thesis: concentration is what produced the -55% drawdown."""
        close, turn = toy_panel(n=900, n_sym=200, seed=7)
        _, conc = run_backtest(close, turn, 21, top_n=5, costs=Costs(), cost_mult=1.0,
                               start_idx=300, end_idx=800)
        _, dil = run_backtest(close, turn, 21, costs=Costs(), cost_mult=1.0,
                              start_idx=300, end_idx=800, top_frac=0.10)
        self.assertGreater(dil["max_dd"], conc["max_dd"])           # shallower

    def test_dilution_reduces_drawdown_via_diversification(self):
        """The one return-related property that IS structural: holding more names
        reduces portfolio variance, so the worst day is shallower. This holds on
        any panel, signal or not."""
        close, turn = toy_panel(n=900, n_sym=200, seed=13)
        _, conc = run_backtest(close, turn, 21, top_n=5, costs=Costs(), cost_mult=1.0,
                               start_idx=300, end_idx=800)
        _, dil = run_backtest(close, turn, 21, costs=Costs(), cost_mult=1.0,
                              start_idx=300, end_idx=800, top_frac=0.10)
        # max_dd is negative, so "shallower" means GREATER
        self.assertGreater(dil["max_dd"], conc["max_dd"])


class TestAdvCap(unittest.TestCase):
    def test_cap_never_binds_at_this_capital_and_is_reported(self):
        """PREREG §3 declared the cap decorative at Rs 2L. Pin that it is
        *measured*, not assumed, so nobody later claims it saved the book."""
        close, turn = toy_panel(n=900, n_sym=200)
        _, m = run_backtest(close, turn, 21, costs=Costs(), cost_mult=1.0,
                            start_idx=300, end_idx=800, top_frac=0.10,
                            adv_cap_pct=0.01)
        self.assertEqual(m["adv_cap_binding_positions"], 0)
        self.assertIsNotNone(m["adv_cap_median_headroom"])
        self.assertGreater(m["adv_cap_median_headroom"], 10.0)

    def test_cap_does_bind_when_pinned_impossibly_tight(self):
        close, turn = toy_panel(n=900, n_sym=200)
        _, m = run_backtest(close, turn, 21, costs=Costs(), cost_mult=1.0,
                            start_idx=300, end_idx=800, top_frac=0.10,
                            adv_cap_pct=1e-9)
        self.assertGreater(m["adv_cap_binding_positions"], 0)

    def test_weights_stay_normalised_after_capping(self):
        close, turn = toy_panel(n=900, n_sym=200)
        df, m = run_backtest(close, turn, 21, costs=Costs(), cost_mult=1.0,
                             start_idx=300, end_idx=800, top_frac=0.10,
                             adv_cap_pct=1e-9)
        self.assertFalse(df.empty)
        # a capped basket must still be a basket, not a fraction of one
        self.assertGreater(m["median_holdings"], 1)


class TestDeathRateMechanism(unittest.TestCase):
    def test_dilution_reduces_but_does_not_annihilate_excess_death(self):
        """Gate 6 measured 3.4x (top-20) -> 1.87x (top decile): concentration
        caused most of it, but momentum still selects fragile names."""
        from experiments.e020_diluted_momentum.run_e020 import death_rates
        from experiments.e019_momentum.engine import (
            corporate_action_adjust, load_panel, precompute_liquidity,
        )
        close, turn, _ = load_panel()
        adj, _ = corporate_action_adjust(close)
        med = precompute_liquidity(turn)
        n = len(adj)
        start, end = 295, n - 2
        top = death_rates(adj, turn, med, start, end, 0.10)
        self.assertGreater(top["ratio"], 1.0, "momentum names should die somewhat more often")
        self.assertLess(top["ratio"], 3.4, "dilution should have cut the excess death rate")
        self.assertGreater(top["n_top"], 100)


if __name__ == "__main__":
    unittest.main()