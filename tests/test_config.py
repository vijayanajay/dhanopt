"""Unit tests for engine configuration and weekday schedule matrix."""

import unittest
from datetime import datetime, time
import config


class TestConfig(unittest.TestCase):
    def test_capital_constants(self):
        self.assertEqual(config.TOTAL_CAPITAL, 200_000.0)
        self.assertEqual(config.MAX_DAILY_LOSS, 2_500.0)
        self.assertEqual(config.MONTHLY_DRAWDOWN_CAP, 10_000.0)
        self.assertAlmostEqual(config.MAX_DAILY_LOSS / config.TOTAL_CAPITAL, 0.0125)
        self.assertAlmostEqual(config.MONTHLY_DRAWDOWN_CAP / config.TOTAL_CAPITAL, 0.05)
        self.assertGreaterEqual(config.TARGET_PAYOFF_RATIO, 1.40)
        self.assertGreaterEqual(config.MIN_WIN_RATE, 0.55)

    def test_contract_specs(self):
        self.assertEqual(config.NIFTY_LOT_SIZE, 65)  # current era (FAOP70616, since 2025-12-30)
        self.assertEqual(config.STRIKE_INTERVAL, 50)
        self.assertEqual(config.STRIKE_WINDOW, 300)
        self.assertEqual(config.NIFTY_SECURITY_ID, 13)

    def test_fee_rates_post_oct_2024(self):
        self.assertEqual(config.BROKERAGE_PER_LEG_PER_SIDE, 20.0)
        self.assertEqual(config.STT_SELL_RATE, 0.001)  # 0.1% post-Oct 2024
        self.assertEqual(config.EXCHANGE_TURNOVER_RATE, 0.000505)
        self.assertEqual(config.SEBI_TURNOVER_RATE, 0.000001)
        self.assertEqual(config.STAMP_DUTY_BUY_RATE, 0.00003)
        self.assertEqual(config.GST_RATE, 0.18)
        self.assertEqual(config.SLIPPAGE_POINTS_PER_LEG, 1.5)

    def test_weekday_schedule_matrix(self):
        # Verify all 5 weekdays (0=Mon to 4=Fri) are present
        for day in range(5):
            schedule = config.WEEKDAY_SCHEDULES.get(day)
            self.assertIsNotNone(schedule, f"Missing schedule for day {day}")
            self.assertIsNotNone(schedule.primary_window)

        # Tuesday (day 1) is weekly expiry day (since 2025-09-01): 14:45 gamma cutoff
        tue_schedule = config.WEEKDAY_SCHEDULES[1]
        self.assertEqual(tue_schedule.square_off_time, time(14, 45))

        # Thursday must have no secondary window (no longer expiry day)
        thu_schedule = config.WEEKDAY_SCHEDULES[3]
        self.assertIsNone(thu_schedule.secondary_window)

    def test_window_evaluations(self):
        # Synthetic Monday 10:15 -> Inside primary window (10:00 - 10:45)
        mon_in = datetime(2026, 9, 28, 10, 15)  # 2026-09-28 is Monday
        in_win, reason = config.is_optimal_window(mon_in)
        self.assertTrue(in_win)
        self.assertIn("Primary", reason)

        # Synthetic Monday 11:30 -> Outside window
        mon_out = datetime(2026, 9, 28, 11, 30)
        in_win, reason = config.is_optimal_window(mon_out)
        self.assertFalse(in_win)
        self.assertIn("Outside", reason)

        # Synthetic Tuesday 14:45 square-off check (expiry day)
        tue = datetime(2026, 10, 6, 10, 0)  # Tuesday
        self.assertEqual(config.get_square_off_time(tue), time(14, 45))

        # Weekend test (Sunday)
        sun = datetime(2026, 9, 27, 10, 0)
        in_win, reason = config.is_optimal_window(sun)
        self.assertFalse(in_win)
        self.assertIn("weekend", reason.lower())

    def test_paths_and_env_defaults(self):
        self.assertTrue(config.DATA_DIR.exists())
        self.assertTrue(config.HISTORICAL_DATA_DIR.exists())
        self.assertIsInstance(config.MOCK_MODE, bool)


if __name__ == "__main__":
    unittest.main()
