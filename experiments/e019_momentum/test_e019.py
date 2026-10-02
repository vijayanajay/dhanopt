"""E019 tests. Small, cheap, and aimed at the failure modes this repo keeps hitting:
look-ahead, survivorship, and a cost model that quietly stops costing anything.
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
    CLEAN_RATIOS,
    Costs,
    LOOKBACK,
    MIN_TURNOVER,
    SPLIT_THRESHOLD,
    corporate_action_adjust,
    load_panel,
    momentum_rank,
    point_in_time_universe,
    precompute_liquidity,
    run_backtest,
)


def toy_panel(n=700, n_sym=40, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-01", periods=n)
    cols = [f"S{i:02d}" for i in range(n_sym)]
    close = pd.DataFrame(
        100 * np.cumprod(1 + rng.normal(0.0005, 0.02, (n, n_sym)), axis=0),
        index=idx, columns=cols,
    )
    turn = pd.DataFrame(rng.uniform(1e7, 1e8, (n, n_sym)), index=idx, columns=cols)
    return close, turn


class TestNoLookahead(unittest.TestCase):
    def test_momentum_uses_only_data_before_as_of(self):
        close, _ = toy_panel()
        i = 500
        uni = list(close.columns)
        base = momentum_rank(close, i, uni)
        # corrupt every price AFTER i: the rank must not move
        close2 = close.copy()
        close2.iloc[i + 1:] *= 3.0
        after = momentum_rank(close2, i, uni)
        self.assertTrue(np.allclose(base.values, after.values))

    def test_rank_skips_the_most_recent_month(self):
        """12-1 momentum must ignore the last SKIP sessions entirely."""
        close, _ = toy_panel(n=700)
        i = 500
        uni = list(close.columns)
        base = momentum_rank(close, i, uni)
        close2 = close.copy()
        close2.iloc[i - 5: i + 1] *= 2.0      # the skipped month only
        after = momentum_rank(close2, i, uni)
        self.assertTrue(np.allclose(base.values, after.values))

    def test_universe_is_backward_looking(self):
        close, turn = toy_panel(n=700)
        i = 500
        med = precompute_liquidity(turn)
        base = point_in_time_universe(turn, i, med)
        turn2 = turn.copy()
        turn2.iloc[i + 1:] *= 1000.0          # future liquidity must not help
        med2 = precompute_liquidity(turn2)
        after = point_in_time_universe(turn2, i, med2)
        self.assertEqual(sorted(base), sorted(after))


class TestPointInTimeUniverse(unittest.TestCase):
    def test_precomputed_median_matches_direct_computation(self):
        close, turn = toy_panel(n=700, n_sym=12)
        med = precompute_liquidity(turn)
        for i in (400, 500, 650):
            direct = turn.iloc[max(0, i - LOOKBACK): i + 1].median()
            a = set(point_in_time_universe(turn, i, med))
            b = set(direct[direct >= MIN_TURNOVER].index)
            self.assertEqual(a & set(turn.columns), b & set(turn.columns), f"mismatch at {i}")

    def test_illiquid_names_are_excluded(self):
        close, turn = toy_panel(n=700, n_sym=10)
        turn.iloc[:, 0] = 1.0                # no liquidity at all
        med = precompute_liquidity(turn)
        self.assertNotIn(close.columns[0], point_in_time_universe(turn, 600, med))

    def test_no_index_membership_list_is_used(self):
        """Survivorship control: the universe must track the trading record, not a
        fixed list of 'current' constituents."""
        src = (HERE / "engine.py").read_text()
        self.assertNotIn("nifty50", src.lower())
        self.assertNotIn("midcap150", src.lower())


class TestCorporateActions(unittest.TestCase):
    def test_bonus_step_is_adjusted_not_dropped(self):
        idx = pd.bdate_range("2020-01-01", periods=400)
        px = pd.Series(100.0, index=idx)
        px.iloc[200:] = 50.0                  # a 1:1 bonus
        close = pd.DataFrame({"X": px.values}, index=idx)
        adj, stats = corporate_action_adjust(close)
        self.assertEqual(stats["corporate_actions_adjusted"], 1)
        r = adj["X"].pct_change(fill_method=None)
        self.assertLess(abs(float(r.iloc[201])), 0.02)   # step is gone

    def test_a_real_crash_is_left_alone(self):
        idx = pd.bdate_range("2020-01-01", periods=400)
        px = pd.Series(100.0, index=idx)
        px.iloc[200:] = 55.0                  # a real 45% crash, not a clean ratio
        close = pd.DataFrame({"X": px.values}, index=idx)
        adj, stats = corporate_action_adjust(close)
        self.assertEqual(stats["corporate_actions_adjusted"], 0)
        r = adj["X"].pct_change(fill_method=None)
        self.assertLess(float(r.iloc[200]), -0.40)   # the crash day itself survives

    def test_engine_never_forward_fills_prices(self):
        """pct_change() padded NaN in older pandas, inventing returns across gaps
        in a sparse panel. Pin the call sites rather than the pandas version."""
        src = (HERE / "engine.py").read_text()
        self.assertNotIn(".pct_change()", src)
        self.assertIn("pct_change(fill_method=None)", src)


class TestCostModel(unittest.TestCase):
    def test_stamp_duty_is_charged_on_buys_only(self):
        c = Costs()
        self.assertGreater(c.per_side(100000, True), c.per_side(100000, False))

    def test_stt_is_charged_on_both_sides(self):
        c = Costs()
        stt = c.stt * 100000 * (1 + c.gst)
        self.assertAlmostEqual(stt, 118.0, delta=0.01)   # 0.1% of 1L, +18% GST
        # and it is the same on the sell leg (delivery STT is both sides)
        self.assertAlmostEqual(c.per_side(100000, True) - c.per_side(100000, False),
                               c.stamp_buy * 100000 * (1 + c.gst), delta=1e-6)

    def test_flat_brokerage_makes_costs_sublinear_in_size(self):
        """Doubling the notional does NOT double the cost: Rs 20/order is flat.
        This is why small tickets are punished and large ones are not."""
        c = Costs()
        one = c.round_trip(100000)
        two = c.round_trip(200000)
        self.assertLess(two, 2 * one)
        self.assertGreater(two / one, 1.9)

    def test_round_trip_is_buy_plus_sell(self):
        c = Costs()
        self.assertAlmostEqual(c.round_trip(100000),
                               c.per_side(100000, True) + c.per_side(100000, False), delta=1e-9)

    def test_a_full_turnover_costs_something_real(self):
        """The experiment's premise is that costs matter; prove the model charges them."""
        c = Costs()
        cost = c.round_trip(CAPITAL)
        self.assertGreater(cost / CAPITAL, 0.002)      # >0.2% per full round trip
        self.assertLess(cost / CAPITAL, 0.02)

    def test_no_mult_parameter_can_zero_the_notional(self):
        """A former `mult` argument multiplied the NOTIONAL too, so passing 0
        silently modelled a free trade. The parameter is gone."""
        import inspect
        self.assertEqual(list(inspect.signature(Costs.per_side).parameters), ["self", "notional", "is_buy"])
        self.assertEqual(list(inspect.signature(Costs.round_trip).parameters), ["self", "notional"])


class TestBacktestMechanics(unittest.TestCase):
    def test_zero_cost_beats_positive_cost(self):
        close, turn = toy_panel(n=700, n_sym=30)
        c = Costs()
        _, paid = run_backtest(close, turn, 21, top_n=5, costs=c,
                               cost_mult=1.0, start_idx=300, end_idx=650)
        _, free = run_backtest(close, turn, 21, top_n=5, costs=c,
                               cost_mult=0.0, start_idx=300, end_idx=650)
        self.assertGreater(free["cagr"], paid["cagr"])

    def test_higher_cost_multiplier_cannot_help(self):
        close, turn = toy_panel(n=700, n_sym=30)
        c = Costs()
        _, one = run_backtest(close, turn, 21, top_n=5, costs=c, cost_mult=1.0,
                              start_idx=300, end_idx=650)
        _, two = run_backtest(close, turn, 21, top_n=5, costs=c, cost_mult=2.0,
                              start_idx=300, end_idx=650)
        self.assertLessEqual(two["cagr"], one["cagr"] + 1e-9)

    def test_rebalance_count_matches_schedule(self):
        close, turn = toy_panel(n=700, n_sym=30)
        df, m = run_backtest(close, turn, 21, top_n=5, costs=Costs(),
                             cost_mult=1.0, start_idx=300, end_idx=650)
        self.assertGreater(m["rebalances"], 5)
        self.assertLess(m["rebalances"], 25)

    def test_daily_costs_more_than_monthly(self):
        close, turn = toy_panel(n=700, n_sym=30)
        _, mo = run_backtest(close, turn, 21, top_n=5, costs=Costs(),
                             cost_mult=1.0, start_idx=300, end_idx=650)
        _, dy = run_backtest(close, turn, 1, top_n=5, costs=Costs(),
                             cost_mult=1.0, start_idx=300, end_idx=650)
        self.assertGreater(dy["total_cost_inr"], mo["total_cost_inr"])


if __name__ == "__main__":
    unittest.main()