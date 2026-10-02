"""Unit tests for core/execution/maker.py — Phase 5 Maker Execution Engine.

Verifies the three pre-registered components:
1. Passive limit placement (bid+1 tick / ask-1 tick around the mid).
2. Queue & fill simulator: strict-through prints OR touch + 3x-volume; touch alone
   never fills; no volume tape disables the volume clause (fail-closed).
3. Adverse selection: flagging, improvement stripping, penalty accounting.
"""

import unittest

from core.execution.maker import (
    Bar,
    PassiveOrder,
    QueueFillSimulator,
    apply_adverse_selection,
    fill_in_window,
    is_adverse,
    mid_price,
    passive_limit_price,
    reference_moves,
)


class TestPassivePlacement(unittest.TestCase):
    def test_mid_and_tick_placement(self):
        bid, ask = 99.0, 101.0
        self.assertEqual(mid_price(bid, ask), 100.0)
        self.assertAlmostEqual(passive_limit_price(bid, ask, "BUY"), 99.05)
        self.assertAlmostEqual(passive_limit_price(bid, ask, "SELL"), 100.95)
        self.assertAlmostEqual(passive_limit_price(bid, ask, "buy"), 99.05)  # case-insensitive

    def test_bad_side_raises(self):
        with self.assertRaises(ValueError):
            passive_limit_price(99.0, 101.0, "HOLD")


class TestQueueFillSimulator(unittest.TestCase):
    def setUp(self):
        self.sim = QueueFillSimulator(volume_multiple=3.0)

    def _bar(self, low, high, volume=None, close=None):
        return Bar(open=high, high=high, low=low, close=close if close is not None else high, volume=volume)

    def test_buy_strict_through_fills_at_limit(self):
        order = PassiveOrder(side="BUY", limit_price=100.0, quantity=65, posted_bar=0)
        bar = self._bar(low=99.5, high=101.0)  # prints strictly below 100
        fill = self.sim.try_fill(order, bar, 1, taker_price=100.05)
        self.assertIsNotNone(fill)
        self.assertEqual(fill.fill_price, 100.0)  # always filled at the limit
        self.assertEqual(fill.fill_bar, 1)
        self.assertEqual(fill.bars_resting, 1)

    def test_touch_without_volume_does_not_fill(self):
        order = PassiveOrder(side="BUY", limit_price=100.0, quantity=65, posted_bar=0)
        bar = self._bar(low=100.0, high=101.0)  # touch only (low == limit), no volume tape
        self.assertIsNone(self.sim.try_fill(order, bar, 1, taker_price=100.05))

    def test_touch_with_sufficient_volume_fills(self):
        order = PassiveOrder(side="BUY", limit_price=100.0, quantity=65, posted_bar=0)
        bar = self._bar(low=100.0, high=101.0, volume=3 * 65)  # exactly 3x
        fill = self.sim.try_fill(order, bar, 2, taker_price=100.05)
        self.assertIsNotNone(fill)
        self.assertEqual(fill.fill_bar, 2)

    def test_touch_with_insufficient_volume_does_not_fill(self):
        order = PassiveOrder(side="BUY", limit_price=100.0, quantity=65, posted_bar=0)
        bar = self._bar(low=100.0, high=101.0, volume=3 * 65 - 1)
        self.assertIsNone(self.sim.try_fill(order, bar, 2, taker_price=100.05))

    def test_sell_mirror_semantics(self):
        order = PassiveOrder(side="SELL", limit_price=100.95, quantity=65, posted_bar=0)
        through = self._bar(low=99.0, high=101.5)  # prints strictly above 100.95
        touch = self._bar(low=100.0, high=100.95)
        self.assertIsNotNone(self.sim.try_fill(order, through, 1, taker_price=101.0))
        self.assertIsNone(self.sim.try_fill(order, touch, 1, taker_price=101.0))  # touch only, no volume tape

    def test_fill_in_window_walks_bars(self):
        order = PassiveOrder(side="SELL", limit_price=50.0, quantity=65, posted_bar=3)
        bars = {
            3: self._bar(low=49.0, high=49.5),               # no touch
            4: self._bar(low=49.5, high=50.0),               # touch only, no volume
            5: self._bar(low=49.0, high=50.5, volume=500),   # through
        }
        fill = fill_in_window(order, bars, window=[3, 4, 5])
        self.assertIsNotNone(fill)
        self.assertEqual(fill.fill_bar, 5)

    def test_fill_in_window_returns_none_when_never_eligible(self):
        order = PassiveOrder(side="BUY", limit_price=10.0, quantity=65, posted_bar=0)
        bars = {0: self._bar(low=10.0, high=11.0), 1: self._bar(low=10.0, high=11.0)}
        self.assertIsNone(fill_in_window(order, bars, window=[0, 1]))


class TestAdverseSelection(unittest.TestCase):
    def test_is_adverse_direction_and_threshold(self):
        self.assertTrue(is_adverse("SELL", 0.003))
        self.assertFalse(is_adverse("SELL", 0.001))
        self.assertFalse(is_adverse("SELL", -0.01))
        self.assertTrue(is_adverse("BUY", -0.0025))
        self.assertFalse(is_adverse("BUY", 0.001))
        self.assertFalse(is_adverse("BUY", 0.01))
        with self.assertRaises(ValueError):
            is_adverse("HOLD", 0.0)

    def test_apply_strips_improvement_only_on_flagged_fills(self):
        from core.execution.maker import Fill

        adverse = Fill(side="SELL", limit_price=100.95, fill_price=100.95, fill_bar=1,
                       quantity=65, posted_bar=0, taker_price=101.0)
        clean = Fill(side="BUY", limit_price=99.05, fill_price=99.05, fill_bar=2,
                     quantity=65, posted_bar=0, taker_price=99.0)
        adjusted, events = apply_adverse_selection([adverse, clean], {1: 0.005, 2: 0.001})

        # Flagged fill re-priced at the taker price; improvement stripped as penalty.
        self.assertEqual(len(events), 1)
        self.assertAlmostEqual(adjusted[0].fill_price, 101.0)
        self.assertAlmostEqual(events[0].penalty_rupees, (101.0 - 100.95) * 65)
        # Clean fill passes through untouched.
        self.assertAlmostEqual(adjusted[1].fill_price, 99.05)
        self.assertEqual(len(adjusted), 2)

    def test_reference_moves_close_to_close_and_last_bar_fallback(self):
        series = {0: (100.0, 100.0), 1: (100.0, 101.0), 2: (101.0, 100.0)}
        moves = reference_moves(series)
        self.assertAlmostEqual(moves[0], 0.01)          # 101/100 - 1
        self.assertAlmostEqual(moves[1], (100.0 - 101.0) / 101.0)
        self.assertAlmostEqual(moves[2], (100.0 - 101.0) / 101.0)  # last bar: own open->close


if __name__ == "__main__":
    unittest.main()
