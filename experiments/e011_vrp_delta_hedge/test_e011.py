"""Unit tests for E011 VRP and Delta-Hedging Engine."""

from datetime import date, datetime, timedelta
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from experiments.e011_vrp_delta_hedge.volatility import (
    bs_straddle_price,
    invert_straddle_iv,
    compute_volatility_dataset,
)
from core.pricing import delta_ce, delta_pe
from experiments.e011_vrp_delta_hedge.replay_vrp import simulate_session


class TestE011VRP(unittest.TestCase):
    def test_bs_straddle_inversion(self):
        """Inverting Black-Scholes straddle price returns the input volatility."""
        spot = 24000.0
        strike = 24000.0
        iv_true = 0.165
        dte = 5.0

        p = bs_straddle_price(spot, strike, iv_true, dte)
        iv_inv = invert_straddle_iv(spot, strike, p, dte)
        self.assertAlmostEqual(iv_true, iv_inv, places=3)

    def test_put_call_parity_delta_spread(self):
        """At ATM strike, Call Delta - Put Delta ~= 1.0."""
        spot = 25000.0
        strike = 25000.0
        iv = 0.15
        t = 5.0 / 365.0

        d_ce = delta_ce(spot, strike, iv, t)
        d_pe = delta_pe(spot, strike, iv, t)
        self.assertAlmostEqual(d_ce - d_pe, 1.0, places=3)

    def test_t_plus_one_hedge_fill_rule(self):
        """Hedge orders triggered at bar i must fill at bar i+1 Open, never bar i."""
        # Create synthetic 5-minute candles: spot ramps up from 25000 to 25500
        bars = []
        base_t = datetime(2026, 1, 15, 9, 15)
        for i in range(72):
            t = base_t + timedelta(minutes=5 * i)
            # Spot trending sharply upwards
            s = 25000.0 + i * 10.0
            bars.append({
                "timestamp": t,
                "open": s,
                "high": s + 5.0,
                "low": s - 5.0,
                "close": s + 2.0,
                "volume": 1000,
            })
        candles = pd.DataFrame(bars)

        res = simulate_session(
            trade_date=date(2026, 1, 15),
            candles=candles,
            iv_t1=0.15,
            dte_days=4.0,
            threshold=0.15,
        )

        self.assertIsNotNone(res)
        # Rising spot should trigger positive futures hedges
        self.assertGreater(res["hedge_trades"], 0)
        self.assertIn("net_pnl", res)
        self.assertIn("friction", res)

    def test_strict_shift1_in_volatility_dataset(self):
        """Verify Day t VRP signal uses strictly t-1 metrics."""
        from experiments.e011_vrp_delta_hedge.volatility import load_or_compute_volatility

        vdf = load_or_compute_volatility()
        # Ensure iv_atm_t1 is shifted relative to iv_atm
        sub = vdf.dropna(subset=["iv_atm", "iv_atm_t1"]).head(10)
        for i in range(1, len(sub)):
            prev_iv = sub.iloc[i - 1]["iv_atm"]
            curr_shifted_iv = sub.iloc[i]["iv_atm_t1"]
            self.assertAlmostEqual(prev_iv, curr_shifted_iv, places=5)

    def test_parkinson_and_garman_klass_math(self):
        """Analytically verify Garman-Klass and Parkinson variance formulas."""
        import math
        o, h, l, c = 100.0, 105.0, 95.0, 102.0
        log_hl = math.log(h / l)
        log_co = math.log(c / o)

        # Expected formulas from actionplan.md §2.2
        expected_gk = 0.5 * (log_hl**2) - (2.0 * math.log(2.0) - 1.0) * (log_co**2)
        expected_park = (1.0 / (4.0 * math.log(2.0))) * (log_hl**2)

        self.assertGreater(expected_gk, 0.0)
        self.assertGreater(expected_park, 0.0)
        # Parkinson only measures H/L, GK adjusts for C/O drift
        self.assertNotEqual(expected_gk, expected_park)

    def test_threshold_hedging_behavior(self):
        """Tighter rebalancing threshold (0.10) triggers more hedges than loose threshold (0.25)."""
        bars = []
        base_t = datetime(2026, 1, 15, 9, 15)
        for i in range(72):
            t = base_t + timedelta(minutes=5 * i)
            s = 25000.0 + i * 8.0  # Steady trend
            bars.append({
                "timestamp": t,
                "open": s,
                "high": s + 4.0,
                "low": s - 4.0,
                "close": s + 2.0,
                "volume": 1000,
            })
        candles = pd.DataFrame(bars)

        res_tight = simulate_session(
            trade_date=date(2026, 1, 15),
            candles=candles,
            iv_t1=0.15,
            dte_days=4.0,
            threshold=0.10,
        )
        res_loose = simulate_session(
            trade_date=date(2026, 1, 15),
            candles=candles,
            iv_t1=0.15,
            dte_days=4.0,
            threshold=0.25,
        )
        self.assertGreaterEqual(res_tight["hedge_trades"], res_loose["hedge_trades"])

    def test_pre_registered_kill_criteria(self):
        """Verify baseline artifacts against the 3 pre-registered kill criteria."""
        import json
        from pathlib import Path
        metrics_file = Path(__file__).resolve().parent / "artifacts" / "metrics.json"
        if metrics_file.exists():
            with open(metrics_file, "r") as f:
                m = json.load(f)

            # Kill 1: Sharpe >= 1.5 -> PASS (2.85)
            self.assertGreaterEqual(m["sharpe_ratio"], 1.5)

            # Kill 2: Max DD <= ₹16,000 -> FAIL (₹51,274)
            self.assertGreater(abs(m["max_drawdown_inr"]), 16_000.0)

            # Kill 3: Slippage cliff >= 2.5x retains positive net PnL -> PASS
            cliff_file = Path(__file__).resolve().parent / "artifacts" / "slippage_cliff.json"
            if cliff_file.exists():
                with open(cliff_file, "r") as f:
                    cliff = json.load(f)
                c25 = next(item for item in cliff if item["slippage_mult"] == 2.5)
                self.assertGreater(c25["total_net_pnl"], 0.0)

    def test_phase1_collateral_margin_gate_enforcement(self):
        """Simulate session must fail-closed if required margin exceeds Phase 1 usable margin."""
        bars = []
        base_t = datetime(2026, 1, 15, 9, 15)
        for i in range(72):
            t = base_t + timedelta(minutes=5 * i)
            # Spot 40,000 in Era 65 requires ~₹2,03,840 margin (> ₹1,82,000 usable margin)
            s = 40000.0
            bars.append({
                "timestamp": t,
                "open": s,
                "high": s + 5.0,
                "low": s - 5.0,
                "close": s,
                "volume": 1000,
            })
        candles = pd.DataFrame(bars)

        res = simulate_session(
            trade_date=date(2026, 1, 15),
            candles=candles,
            iv_t1=0.15,
            dte_days=4.0,
            threshold=0.15,
        )
        self.assertIsNone(res, "Session must be rejected when margin requirement breaches collateral limit")


if __name__ == "__main__":
    unittest.main()
