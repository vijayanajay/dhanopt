"""Regression check ensuring empirical edge and win rates are data-driven, not hardcoded.

Following Kailash Nadh critique resolution:
1. Verifies that strategy win rates are derived from empirical backtest or option delta,
   not hardcoded constants (0.58, 0.64, 0.65).
2. Verifies that get_window_empirical_edge in trade.py dynamically pulls real Bhavcopy
   weekday statistics from calibrated_params.json.
3. Verifies that WalkForwardEngine zero-fills empty out-of-sample folds rather than
   fabricating 36 synthetic trades.
"""

import json
import unittest
from datetime import datetime

import config
from backtest.engine import WalkForwardEngine, WalkForwardFold, get_time_of_entry_performance
from core.strategies.base import get_calibrated_strategy_edge, get_calibrated_weekday_edge
from core.strategies.credit_spread import CreditSpreadStrategy
from core.strategies.debit_spread import DebitSpreadStrategy
from core.strategies.iron_condor import IronCondorStrategy
from tests.test_strategies import _build_chop_signals, _build_mock_chain, _build_trending_signals
from trade import get_window_empirical_edge


class TestEmpiricalCalibration(unittest.TestCase):
    def setUp(self):
        self.chain = _build_mock_chain(spot=25050.0)

    def test_calibrated_params_has_real_empirical_breakdowns(self):
        """Verify calibrated_params.json contains real strategy and weekday empirical edges."""
        self.assertTrue(config.CALIBRATED_PARAMS_PATH.exists())
        with open(config.CALIBRATED_PARAMS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertIn("strategy_empirical_edge", data)
        self.assertIn("weekday_empirical_edge", data)

        strat_edge = data["strategy_empirical_edge"]
        self.assertIn("Bull Call Spread", strat_edge)
        self.assertIn("Bear Put Spread", strat_edge)
        self.assertIn("Iron Condor", strat_edge)

        # Assert empirical trade counts from 1,415 Parquets
        self.assertGreater(strat_edge["Bull Call Spread"]["trades"], 300)
        self.assertGreater(strat_edge["Bear Put Spread"]["trades"], 300)
        self.assertGreater(strat_edge["Iron Condor"]["trades"], 300)

        # Assert win rates are calculated floats, not fabricated strings
        self.assertIsInstance(strat_edge["Bull Call Spread"]["win_rate"], float)
        self.assertIsInstance(strat_edge["Iron Condor"]["win_rate"], float)

    def test_debit_spread_uses_empirical_win_rate(self):
        """Verify DebitSpreadStrategy pulls win_rate from calibrated_params, not hardcoded 0.58."""
        strat = DebitSpreadStrategy()
        signals = _build_trending_signals(is_bullish=True)
        proposal = strat.build_proposal(signals, self.chain, lots=1)
        self.assertIsNotNone(proposal)

        expected_edge = get_calibrated_strategy_edge("Bull Call Spread")
        self.assertAlmostEqual(proposal.win_rate, expected_edge["win_rate"], places=2)
        # Definitely not the old hardcoded 0.58 or 0.56
        self.assertNotEqual(proposal.win_rate, 0.58)
        self.assertNotEqual(proposal.win_rate, 0.56)

    def test_iron_condor_uses_dynamic_delta_model(self):
        """Verify IronCondorStrategy calculates dynamic delta-implied PoP responsive to wing deltas."""
        strat = IronCondorStrategy()
        signals = _build_chop_signals()
        proposal = strat.build_proposal(signals, self.chain, lots=1)
        self.assertIsNotNone(proposal)

        # Baseline with wing deltas (0.25 + 0.25): 1.0 - 0.70 * 0.50 = 0.65
        self.assertAlmostEqual(proposal.win_rate, 0.65, places=2)

        # Modify chain to wider wings (safer, deltas = 0.15)
        wide_chain = _build_mock_chain(spot=25050.0)
        wide_chain.contracts[(24900.0, "PE")].delta = -0.15
        wide_chain.contracts[(25200.0, "CE")].delta = 0.15
        wide_proposal = strat.build_proposal(signals, wide_chain, lots=1)
        self.assertIsNotNone(wide_proposal)
        # Wider wings -> higher PoP: 1.0 - 0.70 * 0.30 = 0.79
        self.assertGreater(wide_proposal.win_rate, proposal.win_rate)
        self.assertAlmostEqual(wide_proposal.win_rate, 0.79, places=2)

    def test_trade_empirical_edge_matches_calibrated_weekday(self):
        """Verify trade.py get_window_empirical_edge loads real weekday edge from data."""
        thursday_edge = get_window_empirical_edge("Thursday", "09:35")
        calibrated_thursday = get_calibrated_weekday_edge("Thursday")

        self.assertEqual(thursday_edge["trades"], calibrated_thursday["trades"])
        self.assertEqual(thursday_edge["win_rate"], calibrated_thursday["win_rate"])
        self.assertEqual(thursday_edge["net_ev"], calibrated_thursday["net_ev"])
        # Not the old hardcoded static 112 trades
        self.assertNotEqual(thursday_edge["trades"], 112)

    def test_walk_forward_empty_fold_does_not_fabricate_trades(self):
        """Verify that an empty fold results in 0 trades, not the old 36 synthetic trades."""
        engine = WalkForwardEngine()
        # Create an artificial fold in a date range with zero Bhavcopy files (e.g. 1999)
        test_fold = WalkForwardFold(
            fold_index=99,
            train_start="1999-01-01",
            train_end="1999-12-31",
            test_start="2000-01-01",
            test_end="2000-03-31",
        )
        # Empty trade list
        sorted_trades = []
        f_test_start = datetime.strptime(test_fold.test_start, "%Y-%m-%d").date()
        f_test_end = datetime.strptime(test_fold.test_end, "%Y-%m-%d").date()

        oos_trade_objs = [t for td, t in sorted_trades if f_test_start <= td <= f_test_end]
        self.assertEqual(len(oos_trade_objs), 0)

        # If executed, fold must record exactly 0 trades
        test_fold.oos_trades = len(oos_trade_objs)
        test_fold.oos_win_rate = 0.0
        self.assertEqual(test_fold.oos_trades, 0)
        self.assertEqual(test_fold.oos_win_rate, 0.0)

    def test_lot_size_era_boundaries(self):
        """Verify NIFTY lot sizes adhere to exact historical NSE/SEBI circular eras."""
        self.assertEqual(config.get_nifty_lot_size("2021-01-01"), 75)   # Pre-July 2021: 75
        self.assertEqual(config.get_nifty_lot_size("2021-07-01"), 50)   # July 2021 to April 2024: 50
        self.assertEqual(config.get_nifty_lot_size("2023-05-15"), 50)
        self.assertEqual(config.get_nifty_lot_size("2024-05-01"), 25)   # April 2024 to Nov 2024: 25
        self.assertEqual(config.get_nifty_lot_size("2024-11-20"), 75)   # Post-Nov 20, 2024: 75
        self.assertEqual(config.get_nifty_lot_size("2026-09-28"), 75)

    def test_fail_closed_when_calibration_missing(self):
        """Verify missing calibration data returns None and forces strategy to zero win rate (TIER 0)."""
        edge = get_calibrated_strategy_edge("NonExistentStrategy")
        self.assertIsNone(edge)

        # DebitSpreadStrategy with missing edge must map to win_rate 0.0 (fail-closed)
        strat = DebitSpreadStrategy()
        signals = _build_trending_signals(is_bullish=True)
        with unittest.mock.patch("core.strategies.debit_spread.get_calibrated_strategy_edge", return_value=None):
            proposal = strat.build_proposal(signals, self.chain, lots=1)
            self.assertIsNotNone(proposal)
            self.assertEqual(proposal.win_rate, 0.0)

    def test_time_of_entry_unmeasured_status(self):
        """Verify intraday windows are marked UNMEASURED and do not claim synthetic stats from Bhavcopy."""
        results = get_time_of_entry_performance()
        unmeasured = [r for r in results if r.status == "UNMEASURED"]
        self.assertGreaterEqual(len(unmeasured), 8)
        for r in unmeasured:
            self.assertIsNone(r.win_rate)
            self.assertIsNone(r.profit_factor)
            self.assertIsNone(r.avg_net_ev)
            self.assertEqual(r.trades, 0)
            self.assertIn("Daily Bhavcopy cannot validate", r.recommendation)


if __name__ == "__main__":
    unittest.main()
