"""Unit tests for Phase 7: SQLite Trade Journal & Walk-Forward Engine.

Verifies:
- SQLite Journal: Table initialization, trade entry, trade exit, MAE/MFE, net PnL math.
- Attribution Logic: Correct classification (CLEAN_WIN, SLIPPAGE_DRAG, REGIME_MISCLASSIFIED).
- Circuit Breaker Queries: Daily loss calculation, monthly PnL, consecutive loss streak.
- Walk-Forward Engine: 16-fold temporal boundary generation, OOS metrics, and JSON export.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

from backtest.engine import WalkForwardEngine, generate_16_folds
from core.journal.recorder import TradeJournal, TradeRecord


class TestTradeJournal(unittest.TestCase):
    """Test suite for SQLite Trade Journal telemetry."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_journal.sqlite"
        self.journal = TradeJournal(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_journal_initialization(self):
        """Action Plan Task 7.1: Verify SQLite schema is created successfully."""
        self.assertTrue(self.db_path.exists())
        with self.journal._get_connection() as conn:
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
            names = [t[0] for t in tables]
            self.assertIn("trade_journal", names)

    def test_record_entry_and_exit_clean_win(self):
        """Action Plan Task 7.1: Verify entry, exit, MAE, MFE, and CLEAN_WIN attribution."""
        trade_id = self.journal.record_entry(
            strategy="Debit Spread",
            fill_price=76.0,
            lots=1,
            action="SPREAD",
            trade_date="2026-09-30",
            entry_time="10:15:00",
        )
        self.assertIsNotNone(trade_id)

        # Record winning exit: target hit
        record = self.journal.record_exit(
            trade_id=trade_id,
            exit_price=124.0,     # Profit of (124 - 76) * 75 = 3,600
            charges=188.40,
            exit_reason="TARGET_HIT",
            exit_time="11:30:00",
            mae=-10.0,
            mfe=48.0,
            slippage=1.5,
        )

        self.assertEqual(record.trade_id, trade_id)
        self.assertEqual(record.gross_pnl, 3600.0)
        self.assertEqual(record.charges, 188.40)
        self.assertEqual(record.net_pnl, 3411.60)
        self.assertEqual(record.attribution, "CLEAN_WIN")
        self.assertEqual(record.exit_reason, "TARGET_HIT")

    def test_slippage_drag_attribution(self):
        """Action Plan Task 7.1: Verify SLIPPAGE_DRAG classification when slippage turns trade red."""
        trade_id = self.journal.record_entry(
            strategy="Debit Spread",
            fill_price=100.0,
            lots=1,
            trade_date="2026-09-30",
        )
        # Small loss primarily caused by massive slippage
        record = self.journal.record_exit(
            trade_id=trade_id,
            exit_price=99.0,      # Gross loss: -75.0
            charges=190.0,        # Charges: 190.0
            exit_reason="MANUAL",
            slippage=300.0,       # High slippage
            mae=-5.0,
            mfe=10.0,
        )
        self.assertEqual(record.attribution, "SLIPPAGE_DRAG")

    def test_regime_misclassified_attribution(self):
        """Action Plan Task 7.1: Verify REGIME_MISCLASSIFIED on stop loss."""
        trade_id = self.journal.record_entry(
            strategy="Debit Spread",
            fill_price=100.0,
            lots=1,
            trade_date="2026-09-30",
        )
        record = self.journal.record_exit(
            trade_id=trade_id,
            exit_price=72.0,      # Hit stop-loss
            charges=190.0,
            exit_reason="STOP_LOSS",
            slippage=1.0,
            mae=-28.0,
            mfe=5.0,
        )
        self.assertEqual(record.attribution, "REGIME_MISCLASSIFIED")

    def test_daily_and_monthly_pnl_aggregation(self):
        """Action Plan Task 7.1: Verify daily and monthly PnL computation."""
        self.journal.log_completed_trade(
            strategy="Debit Spread",
            fill_price=100.0,
            exit_price=130.0,
            charges=190.0,
            exit_reason="TARGET_HIT",
            trade_date="2026-09-30",
        )
        self.journal.log_completed_trade(
            strategy="Credit Spread",
            fill_price=50.0,
            exit_price=20.0,
            charges=190.0,
            exit_reason="TARGET_HIT",
            trade_date="2026-09-30",
        )

        daily = self.journal.get_daily_pnl("2026-09-30")
        monthly = self.journal.get_monthly_pnl("2026-09")

        # Trade 1 net: (30 * 75) - 190 = 2250 - 190 = 2060
        # Trade 2 net (credit): (50 - 20) * 75 - 190 = 2250 - 190 = 2060
        # Total = 4120
        self.assertEqual(daily, 4120.0)
        self.assertEqual(monthly, 4120.0)

    def test_consecutive_losses_streak(self):
        """Action Plan Task 7.1: Verify tracking of losing streaks for circuit breaker."""
        # 1 win followed by 3 consecutive losses
        self.journal.log_completed_trade("Debit Spread", 100.0, 140.0, 190.0, "TARGET_HIT", trade_date="2026-09-25")
        self.journal.log_completed_trade("Debit Spread", 100.0, 70.0, 190.0, "STOP_LOSS", trade_date="2026-09-26")
        self.journal.log_completed_trade("Debit Spread", 100.0, 70.0, 190.0, "STOP_LOSS", trade_date="2026-09-27")
        self.journal.log_completed_trade("Debit Spread", 100.0, 70.0, 190.0, "STOP_LOSS", trade_date="2026-09-28")

        streak = self.journal.get_consecutive_losses()
        self.assertEqual(streak, 3)


class TestWalkForwardEngine(unittest.TestCase):
    """Test suite for Phase 7 Walk-Forward engine and parameter calibration."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.params_path = Path(self.temp_dir.name) / "calibrated_params.json"
        self.engine = WalkForwardEngine(calibrated_params_path=self.params_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_generate_16_folds_structure(self):
        """Action Plan Task 7.2: Verify 16 rolling folds are generated with valid boundaries."""
        folds = generate_16_folds(start_year=2021, end_year=2026)
        self.assertEqual(len(folds), 16)
        for i, f in enumerate(folds):
            self.assertEqual(f.fold_index, i + 1)
            self.assertLess(f.train_start, f.train_end)
            self.assertLess(f.train_end, f.test_start)
            self.assertLess(f.test_start, f.test_end)

    def test_walk_forward_backtest_execution_and_export(self):
        """Action Plan Task 7.2: Verify 16-fold backtest runs and exports calibrated params."""
        summary = self.engine.run_backtest(num_folds=16)

        self.assertEqual(summary.total_folds, 16)
        self.assertGreaterEqual(summary.overall_win_rate, 0.40)  # Honest leak-free OOS win rate
        self.assertGreaterEqual(summary.overall_profit_factor, 1.40)
        self.assertLessEqual(summary.overall_max_drawdown_pct, 20.00)
        self.assertGreater(summary.overall_net_ev, 0.0)

        # Assert JSON file was written
        self.assertTrue(self.params_path.exists())
        with open(self.params_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertIn("parameters", data)
        self.assertIn("aggregate_oos_metrics", data)
        self.assertIn("folds", data)
        self.assertEqual(len(data["folds"]), 16)
        self.assertGreaterEqual(data["aggregate_oos_metrics"]["win_rate"], 0.40)


if __name__ == "__main__":
    unittest.main()
