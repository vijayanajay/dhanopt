"""Self-checks: carry-forward walls from sporadic per-bar chains, flip detection with
the t+1-fill hard rule, and the fillability counters that judge kill criterion 3."""
from __future__ import annotations

import unittest

from experiments.e008_wall_flip.build_signal import _spread_at, _wall_of, day_signal


def _bar(ts: str, spot, chain: list) -> dict:
    return {"ts": ts, "spot": spot,
            "chain": [{"strike": float(s), "side": sd, "oi": oi, "open": px} for s, sd, oi, px in chain]}


def _session(bars: list) -> dict:
    return {"date": "2026-10-06", "status": "OK", "bars": bars}


class TestCarryForwardWalls(unittest.TestCase):
    def test_wall_is_freshest_observed_oi(self):
        bars = [
            _bar("2026-10-06 09:15:00", 24100, [(24000, "PE", 500, 55), (24200, "CE", 400, 50)]),
            _bar("2026-10-06 09:20:00", 24090, [(24000, "PE", None, None)]),   # no fresh PE
            _bar("2026-10-06 09:25:00", 24080, [(24200, "CE", 600, 45)]),      # CE wall flips here
        ]
        self.assertEqual(_wall_of(bars, 1, "PE")["strike"], 24000.0)  # carried forward
        self.assertEqual(_wall_of(bars, 2, "CE")["strike"], 24200.0)  # updated OI
        self.assertEqual(_wall_of(bars, 2, "CE")["age_min"], 0.0)
        self.assertEqual(_wall_of(bars, 1, "CE")["age_min"], 5.0)     # 09:15 obs at 09:20

    def test_quote_freshness_window(self):
        bars = [
            _bar("2026-10-06 09:15:00", 24100, [(24200, "CE", 400, 100), (24350, "CE", 400, 40)]),
            _bar("2026-10-06 09:25:00", 24090, []),  # 10 min later: beyond the 5-min fill window
        ]
        self.assertIsNone(_spread_at(bars, 1, 24200, is_call=True))       # too stale
        self.assertEqual(_spread_at(bars, 0, 24200, is_call=True)["sell"], 100.0)  # fresh: OK


class TestFlipSignal(unittest.TestCase):
    def test_flip_fires_and_fills_next_bar(self):
        # 09:20-09:30: valid structure (put 24000 / call 24200). 09:35: spot 24250 ->
        # call breach (flip). Fill at 09:40 on both CE legs (quoted at 09:35).
        bars = [
            _bar("2026-10-06 09:15:00", 24100, [(24000, "PE", 500, 55), (24200, "CE", 400, 50)]),
            _bar("2026-10-06 09:20:00", 24100, [(24000, "PE", 505, 54), (24200, "CE", 405, 49)]),
            _bar("2026-10-06 09:25:00", 24110, [(24000, "PE", 510, 53), (24200, "CE", 400, 48)]),
            _bar("2026-10-06 09:30:00", 24115, [(24000, "PE", 508, 52), (24200, "CE", 398, 47)]),
            _bar("2026-10-06 09:35:00", 24250, [(24000, "PE", 500, 40), (24200, "CE", 390, 100),
                                                (24350, "CE", 380, 40)]),
            _bar("2026-10-06 09:40:00", 24245, [(24200, "CE", 395, 95), (24350, "CE", 385, 38)]),
            _bar("2026-10-06 09:45:00", 24240, [(24200, "CE", 393, 93), (24350, "CE", 383, 37)]),
            _bar("2026-10-06 09:50:00", 24235, [(24200, "CE", 391, 91), (24350, "CE", 381, 36)]),
            _bar("2026-10-06 09:55:00", 24230, [(24200, "CE", 390, 90), (24350, "CE", 380, 35)]),
            _bar("2026-10-06 10:00:00", 24225, [(24200, "CE", 389, 89), (24350, "CE", 379, 34)]),
        ]

        import pandas as pd
        candles = pd.DataFrame({
            "timestamp": pd.date_range("2026-10-06 09:40", periods=5, freq="5min"),
            "open": [24245] * 5, "high": [24250] * 5, "low": [24200] * 5,
            "close": [24245, 24240, 24235, 24230, 24225],
        })
        trades = day_signal(_session(bars), candles, pd.Timestamp("2026-10-06").date())
        self.assertEqual(len(trades), 1)
        tr = trades[0]
        self.assertEqual(tr["side"], "call")
        self.assertEqual(tr["wall"], 24200.0)
        self.assertEqual(tr["signal_bar"], "2026-10-06 09:35:00")   # flip bar
        self.assertEqual(tr["fill_bar"], "2026-10-06 09:40:00")     # t+1 fill
        self.assertEqual(tr["credit_pts"], 57.0)                    # 95 sell - 38 buy at the fill bar
        self.assertTrue(tr["fillable"])
        self.assertIn(tr["exit_reason"], {"TARGET", "STOP", "EOD"})

    def test_unfillable_flip_is_counted_not_traded(self):
        # Flip at 09:35, but the fill bar quotes nothing (sporadic API bars).
        bars = [
            _bar("2026-10-06 09:15:00", 24100, [(24000, "PE", 500, 55), (24200, "CE", 400, 50)]),
            _bar("2026-10-06 09:20:00", 24105, [(24000, "PE", 502, 54), (24200, "CE", 402, 49)]),
            _bar("2026-10-06 09:30:00", 24250, [(24000, "PE", 498, 44), (24200, "CE", 392, 98)]),
            _bar("2026-10-06 09:35:00", 24245, []),
            _bar("2026-10-06 09:40:00", 24240, []),
            _bar("2026-10-06 09:45:00", 24235, [(24200, "CE", 390, 90)]),
            _bar("2026-10-06 09:50:00", 24230, []),
            _bar("2026-10-06 09:55:00", 24225, [(24200, "CE", 389, 89)]),
            _bar("2026-10-06 10:00:00", 24220, []),
            _bar("2026-10-06 10:05:00", 24215, [(24200, "CE", 388, 88)]),
        ]
        import pandas as pd
        candles = pd.DataFrame({
            "timestamp": pd.date_range("2026-10-06 09:35", periods=8, freq="5min"),
            "open": [24245] * 8, "high": [24250] * 8, "low": [24200] * 8,
            "close": [24245, 24240, 24235, 24230, 24225, 24220, 24215, 24210],
        })
        trades = day_signal(_session(bars), candles, pd.Timestamp("2026-10-06").date())
        self.assertEqual(len(trades), 1)
        self.assertFalse(trades[0]["fillable"])
        self.assertNotIn("net_pnl", trades[0])

    def test_flip_on_last_bar_is_unfillable_not_crash(self):
        # Flip at the session's final bar: no t+1 bar exists -> unfillable event
        # (hard rule: entry only at t+1 open, never deferred).
        import pandas as pd
        bars = [
            _bar("2026-10-06 09:15:00", 24100, [(24000, "PE", 500, 55), (24200, "CE", 400, 50)]),
            _bar("2026-10-06 09:20:00", 24105, [(24000, "PE", 502, 54), (24200, "CE", 402, 49)]),
        ]
        # flat middle so the session passes the >=10-bar gate
        base = pd.Timestamp("2026-10-06 09:25:00")
        for i in range(8):
            ts = (base + pd.Timedelta(minutes=5 * i)).strftime("%Y-%m-%d %H:%M:%S")
            bars.append(_bar(ts, 24110, [(24000, "PE", 500, 53), (24200, "CE", 400, 48)]))
        bars.append(_bar("2026-10-06 10:05:00", 24250,
                         [(24000, "PE", 498, 44), (24200, "CE", 392, 98)]))  # flip on the LAST bar
        candles = pd.DataFrame({
            "timestamp": pd.date_range("2026-10-06 09:20", periods=2, freq="5min"),
            "open": [24105] * 2, "high": [24110] * 2, "low": [24100] * 2,
            "close": [24105, 24100],
        })
        trades = day_signal(_session(bars), candles, pd.Timestamp("2026-10-06").date())
        self.assertEqual(len(trades), 1)
        self.assertFalse(trades[0]["fillable"])
        self.assertIsNone(trades[0]["fill_bar"])
        self.assertEqual(trades[0]["side"], "call")


if __name__ == "__main__":
    unittest.main()
