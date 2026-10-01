"""E006 self-checks: ladder, monthly breaker, and daily-stop clamp semantics."""
from __future__ import annotations

import unittest

import pandas as pd


def _frame(nets: list[float], start: str = "2025-01-06") -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=len(nets)).strftime("%Y-%m-%d")
    return pd.DataFrame({
        "date": dates, "net_pnl": nets, "friction": [100.0] * len(nets),
        "lot": [65] * len(nets),
    })


class TestCompoundSimSemantics(unittest.TestCase):
    """Synthetic books with known outcomes; config caps read live."""

    def test_ladder_scales_wins_and_loses_once_cash_clears_threshold(self):
        from experiments.e006_compound_sim.compound_sim import simulate

        # first trade wins 60k, then a loser, then a winner
        df = _frame([60_000.0, -5_000.0, 10_000.0])
        # from a small account: 1 lot until cash clears the threshold, then 2
        s, rows, _ = simulate(df, 25_000.0, enable_ladder=True, enable_breaker=False)
        self.assertEqual(rows[0]["lots"], 1)
        self.assertEqual(rows[1]["lots"], 2)
        self.assertEqual(rows[2]["lots"], 2)
        self.assertAlmostEqual(s["end_cash"], 25_000.0 + 60_000.0 - 10_000.0 + 20_000.0,
                               places=2)
        self.assertEqual(s["trades_at_2_lots"], 2)
        # from full capital the book starts at 2 lots immediately
        s2, rows2, _ = simulate(df, 200_000.0, enable_ladder=True, enable_breaker=False)
        self.assertEqual(rows2[0]["lots"], 2)

    def test_monthly_breaker_stops_rest_of_month_after_cap_breach(self):
        from experiments.e006_compound_sim.compound_sim import simulate

        # win raises the month peak, then losses (below the daily clamp) grind the
        # month's dip past the cap: the next trade is skipped, rest of month too
        nets = [12_000.0] + [-1_800.0] * 7 + [2_000.0]
        df = _frame(nets)
        s, rows, _ = simulate(df, 200_000.0, enable_ladder=False, enable_breaker=True)
        self.assertEqual(rows[6]["skip"], "")
        self.assertEqual(rows[7]["skip"], "BREAKER")
        self.assertEqual(rows[8]["skip"], "BREAKER")
        self.assertEqual(s["n_skipped_breaker"], 2)
        self.assertAlmostEqual(s["end_cash"], 212_000.0 - 6 * 1_800.0, places=2)

    def test_breaker_resets_next_month(self):
        from experiments.e006_compound_sim.compound_sim import simulate

        # breaker trips late in month 1; the first month-2 trade goes through
        nets = [12_000.0] + [-1_800.0] * 7 + [2_000.0]
        df = _frame(nets)
        df.loc[8, "date"] = "2025-02-03"  # push the last trade into the next month
        s, rows, _ = simulate(df, 200_000.0, enable_ladder=False, enable_breaker=True)
        self.assertEqual(rows[7]["skip"], "BREAKER")
        self.assertEqual(rows[8]["skip"], "")
        self.assertEqual(s["n_skipped_breaker"], 1)

    def test_daily_stop_clamps_at_cap_and_caps_dd(self):
        from experiments.e006_compound_sim.compound_sim import simulate
        import config

        df = _frame([-10_000.0, 3_000.0])
        s, rows, _ = simulate(df, 200_000.0, enable_ladder=False, enable_breaker=True)
        self.assertEqual(s["n_skipped_daily_kill"], 1)
        self.assertAlmostEqual(rows[0]["net"], -float(config.MAX_DAILY_LOSS), places=2)
        # equity is anchored at start capital, so a first-trade loss is a real DD
        self.assertAlmostEqual(s["max_dd"], float(config.MAX_DAILY_LOSS), places=2)

    def test_flat_1lot_matches_artifact_arithmetic(self):
        """End-to-end: the committed flat 1-lot run must equal plain cumsum of the CSV."""
        import json
        from experiments.e006_compound_sim.compound_sim import BREACH_CSV, HERE, simulate

        df = pd.read_csv(BREACH_CSV)
        df["date"] = df["date"].str[:10]
        s, _, _ = simulate(df, 200_000.0, enable_ladder=False, enable_breaker=False)
        j = json.load(open(HERE / "artifacts" / "compound_sim.json"))
        self.assertAlmostEqual(s["end_cash"], j["flat_1_lot"]["end_cash"], places=0)
        self.assertAlmostEqual(s["end_cash"], 200_000.0 + df["net_pnl"].sum(), places=0)


if __name__ == "__main__":
    unittest.main()
