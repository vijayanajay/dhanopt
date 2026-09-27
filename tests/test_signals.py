"""Unit tests for Pragmatic Market Microstructure Signals.

Verifies exact numerical calculations and edge behavior for:
- VWAP & Dynamic Slope (vwap.py)
- 30-Minute Opening Range Breakout (orb.py)
- India VIX & Parkinson Volatility (vix_iv.py)
- Open Interest Microstructure & Dealer Walls (oi_micro.py)
- Kaufman Efficiency Ratio (ker.py)
- Consolidated MarketSignals composite
"""

import math
import unittest
from datetime import date, datetime, time, timedelta

import numpy as np
import pandas as pd

from core.feeds.base import OptionChainSnapshot, OptionContract
from core.signals.ker import KERSignal, calculate_ker
from core.signals.oi_micro import OIMicroSignal, calculate_oi_micro
from core.signals.orb import ORBSignal, calculate_orb
from core.signals.vix_iv import (
    VIXIVSignal,
    calculate_parkinson_volatility,
    calculate_vix_iv_signal,
)
from core.signals.vwap import (
    VWAPSignal,
    calculate_vwap_signal,
    compute_vwap_series,
)
from core.signals import generate_market_signals, MarketSignals


def _generate_synthetic_100_bar_ohlcv(
    start_dt: datetime = datetime(2026, 9, 28, 9, 15),
    base_price: float = 25000.0,
    interval_mins: int = 5,
) -> pd.DataFrame:
    """Generates a reproducible 100-bar synthetic OHLCV DataFrame for testing."""
    records = []
    price = base_price
    dt = start_dt

    for i in range(100):
        # First 6 bars (09:15 - 09:45): tight range [24980, 25020]
        if i < 6:
            c_open = 25000.0 + (i % 2) * 5.0
            c_close = 25000.0 + ((i + 1) % 2) * 5.0
            c_high = 25020.0
            c_low = 24980.0
            vol = 10000
        # Bar 6 (09:45-09:50): Breakout candle
        elif i == 6:
            c_open = 25010.0
            c_close = 25060.0  # Above ORH (25020)
            c_high = 25070.0
            c_low = 25005.0
            vol = 25000  # 2.5x volume
        # Remaining bars: trend continuation
        else:
            drift = 6.0
            c_open = price
            c_close = c_open + drift
            c_high = c_close + 5.0
            c_low = c_open - 3.0
            vol = 12000

        records.append({
            "timestamp": dt,
            "open": round(c_open, 2),
            "high": round(c_high, 2),
            "low": round(c_low, 2),
            "close": round(c_close, 2),
            "volume": int(vol),
        })

        price = c_close
        dt += timedelta(minutes=interval_mins)

    return pd.DataFrame(records)


class TestVWAPSignal(unittest.TestCase):
    def test_exact_vwap_and_bands(self):
        # Hand-crafted 3-bar dataset to verify exact math
        data = pd.DataFrame([
            {"high": 102.0, "low": 98.0, "close": 100.0, "volume": 100},  # typical price = 100, PV = 10,000, PV2 = 1,000,000
            {"high": 106.0, "low": 102.0, "close": 104.0, "volume": 200}, # typical price = 104, PV = 20,800, PV2 = 2,163,200
            {"high": 110.0, "low": 106.0, "close": 108.0, "volume": 100}, # typical price = 108, PV = 10,800, PV2 = 1,166,400
        ])
        # Bar 1: vwap = 10000/100 = 100.0, var = 0, std = 0
        # Bar 2: cum_vol = 300, cum_pv = 30800 -> vwap = 30800/300 = 102.6667
        #        cum_pv2 = 3,163,200 + 1,000,000 = 3,163,200 / 300 = 10544 - 102.6667^2 = 3.5555 -> std = 1.8856
        # Bar 3: cum_vol = 400, cum_pv = 41600 -> vwap = 41600/400 = 104.0
        #        cum_pv2 = 4,329,600 -> 4329600/400 = 10824 - 104^2 = 8.0 -> std = sqrt(8) = 2.8284

        enriched = compute_vwap_series(data, k_bars=2, num_std=1.5)
        self.assertAlmostEqual(enriched.iloc[0]["vwap"], 100.0, places=1)
        self.assertAlmostEqual(enriched.iloc[2]["vwap"], 104.0, places=1)
        self.assertAlmostEqual(enriched.iloc[2]["std_vwap"], round(math.sqrt(8.0), 2), places=1)
        self.assertAlmostEqual(enriched.iloc[2]["vwap_upper"], round(104.0 + 1.5 * math.sqrt(8.0), 2), places=1)
        self.assertAlmostEqual(enriched.iloc[2]["vwap_lower"], round(104.0 - 1.5 * math.sqrt(8.0), 2), places=1)

    def test_vwap_signal_regimes(self):
        df = _generate_synthetic_100_bar_ohlcv()
        sig = calculate_vwap_signal(df, k_bars=3)

        # On the 100-bar upward trending series, price and slope should be bullish
        self.assertGreater(sig.price, sig.vwap)
        self.assertGreater(sig.slope_15m, 0.02)
        self.assertEqual(sig.regime, "BULLISH")
        self.assertTrue(sig.is_bullish)

        # Create chop series where price stays tight within 0.5 sigma and slope is near 0
        chop_df = pd.DataFrame([
            {
                "high": 25000.0 + (8.0 if i % 2 == 0 else -8.0) + 5.0,
                "low": 25000.0 + (8.0 if i % 2 == 0 else -8.0) - 5.0,
                "close": 25000.0 + (1.0 if i % 2 == 0 else -1.0),
                "volume": 10000,
            }
            for i in range(20)
        ])
        chop_sig = calculate_vwap_signal(chop_df, k_bars=3)
        self.assertEqual(chop_sig.regime, "CHOP")
        self.assertTrue(chop_sig.is_chop)


class TestORBSignal(unittest.TestCase):
    def test_orb_detection_and_breakout(self):
        df = _generate_synthetic_100_bar_ohlcv()
        sig = calculate_orb(df, spot_price=25060.0)

        # First 6 bars: high=25020, low=24980 -> width=40.0
        self.assertEqual(sig.orh, 25020.0)
        self.assertEqual(sig.orl, 24980.0)
        self.assertEqual(sig.width, 40.0)

        # Compression: 40 / 25060 = ~0.16% < 0.35% -> compressed
        self.assertTrue(sig.is_compressed)

        # Bar 6 (09:45-09:50) closed at 25060 > 25020 with 25k volume (2.5x of 10k baseline)
        self.assertEqual(sig.status, "BULLISH_BREAKOUT")
        self.assertTrue(sig.is_breakout)
        self.assertGreaterEqual(sig.volume_ratio, 1.4)

    def test_orb_unconfirmed_breakout_on_low_volume(self):
        # Create dataset where price closes outside range but volume is weak
        records = []
        dt = datetime(2026, 9, 28, 9, 15)
        for i in range(6):
            records.append({
                "timestamp": dt,
                "high": 25050.0,
                "low": 24950.0,
                "close": 25000.0,
                "volume": 20000,
            })
            dt += timedelta(minutes=5)

        # 09:45-09:50 candle breaks out with only 10,000 volume (0.5x baseline)
        records.append({
            "timestamp": dt,
            "high": 25080.0,
            "low": 25000.0,
            "close": 25070.0,
            "volume": 10000,
        })
        df = pd.DataFrame(records)

        sig = calculate_orb(df, baseline_volume=20000)
        self.assertEqual(sig.status, "UNCONFIRMED_BREAKOUT")
        self.assertFalse(sig.is_breakout)

    def test_orb_inside_range(self):
        records = []
        dt = datetime(2026, 9, 28, 9, 15)
        for i in range(12):
            records.append({
                "timestamp": dt,
                "high": 25100.0,
                "low": 24900.0,
                "close": 25000.0,
                "volume": 15000,
            })
            dt += timedelta(minutes=5)
        df = pd.DataFrame(records)
        sig = calculate_orb(df)
        self.assertEqual(sig.status, "INSIDE_RANGE")
        self.assertTrue(sig.is_inside)


class TestVIXIVSignal(unittest.TestCase):
    def test_parkinson_volatility_exact_math(self):
        # 20 identical daily bars where High/Low ratio is 1.01 (1% intraday range)
        # log(1.01) ~= 0.00995033
        # factor = 252 / (4 * ln(2) * 20) = 252 / (80 * 0.693147) = 4.5445
        # sigma_P = sqrt( 4.5445 * 20 * 0.00995033^2 ) * 100
        # = sqrt( 4.5445 * 20 * 0.000099009 ) * 100 ~= sqrt(0.00900) * 100 ~= 9.49%
        ratio = 1.01
        daily_records = [
            {"high": 25000.0 * ratio, "low": 25000.0}
            for _ in range(20)
        ]
        daily_df = pd.DataFrame(daily_records)
        p_vol = calculate_parkinson_volatility(daily_df, window=20)

        expected = math.sqrt((252.0 / (4.0 * math.log(2.0))) * (math.log(ratio) ** 2)) * 100.0
        self.assertAlmostEqual(p_vol, round(expected, 2), places=1)

    def test_vix_iv_dynamics_and_spread(self):
        # VIX rises from 13.0 to 14.5 (+11.54% -> EXPANSION)
        sig = calculate_vix_iv_signal(
            vix=14.5,
            prev_vix=13.0,
            atm_iv=15.0,
            parkinson_vol=11.0,
        )

        self.assertAlmostEqual(sig.delta_vix, 11.54, places=1)
        self.assertEqual(sig.regime, "NORMAL_VOL")
        self.assertEqual(sig.shift, "EXPANSION")
        self.assertEqual(sig.iv_spread, 4.0)  # 15.0 - 11.0 = +4.0
        self.assertTrue(sig.is_rich)
        self.assertTrue(sig.favors_credit_spread)

    def test_vix_low_vol_debit(self):
        sig = calculate_vix_iv_signal(
            vix=11.5,
            prev_vix=11.8,
            atm_iv=12.0,
            parkinson_vol=11.0,
        )
        self.assertEqual(sig.regime, "LOW_VOL")
        self.assertEqual(sig.shift, "STABLE")
        self.assertTrue(sig.favors_debit_spread)


class TestOIMicroSignal(unittest.TestCase):
    def test_dealer_walls_and_pcr_bias(self):
        ts = datetime.now()
        contracts = {
            (24900.0, "PE"): OptionContract("N24900PE", 24900.0, "PE", "2026-10-01", oi=400000, volume=80000),
            (25000.0, "PE"): OptionContract("N25000PE", 25000.0, "PE", "2026-10-01", oi=250000, volume=50000),
            (25000.0, "CE"): OptionContract("N25000CE", 25000.0, "CE", "2026-10-01", oi=150000, volume=40000),
            (25200.0, "CE"): OptionContract("N25200CE", 25200.0, "CE", "2026-10-01", oi=500000, volume=90000),
        }
        chain = OptionChainSnapshot(
            timestamp=ts,
            spot_price=25040.0,
            contracts=contracts,
            expiry="2026-10-01",
        )

        # Call wall: 25200 (500k), Put wall: 24900 (400k)
        # Total Put OI = 650k, Total Call OI = 650k -> PCR = 1.0
        # If PCR at 09:30 was 0.80, delta PCR = +0.20 (> +0.15 -> BULLISH_FLOOR)
        sig = calculate_oi_micro(chain, pcr_0930=0.80, window=300.0)

        self.assertEqual(sig.call_wall, 25200.0)
        self.assertEqual(sig.put_wall, 24900.0)
        self.assertEqual(sig.pcr_oi, 1.0)
        self.assertEqual(sig.delta_pcr, 0.20)
        self.assertEqual(sig.net_bias, "BULLISH_FLOOR")
        self.assertTrue(sig.is_bullish_bias)


class TestKERSignal(unittest.TestCase):
    def test_ker_perfect_trend(self):
        # Monotonically increasing prices: net_change == total_path -> KER = 1.0
        prices = [100.0 + i * 2.0 for i in range(25)]
        sig = calculate_ker(prices, n=20)
        self.assertEqual(sig.ker, 1.0)
        self.assertTrue(sig.is_trending)
        self.assertFalse(sig.is_noisy)
        self.assertTrue(sig.allows_directional)

    def test_ker_pure_chop_noise(self):
        # Alternating prices: net_change near 0, large total_path -> KER near 0
        prices = [100.0 if i % 2 == 0 else 110.0 for i in range(25)]
        sig = calculate_ker(prices, n=20)
        self.assertLess(sig.ker, 0.10)
        self.assertTrue(sig.is_noisy)
        self.assertFalse(sig.is_trending)
        self.assertTrue(sig.allows_condor)

    def test_ker_dynamic_warmup_short_series(self):
        # When series has fewer than 20 bars, should still compute cleanly
        prices = [100.0, 102.0, 104.0, 106.0]
        sig = calculate_ker(prices, n=20)
        self.assertEqual(sig.ker, 1.0)


class TestCompositeMarketSignals(unittest.TestCase):
    def test_generate_market_signals(self):
        candles = _generate_synthetic_100_bar_ohlcv()
        contracts = {
            (25000.0, "PE"): OptionContract("N25000PE", 25000.0, "PE", "2026-10-01", oi=300000, volume=40000, iv=13.0),
            (25000.0, "CE"): OptionContract("N25000CE", 25000.0, "CE", "2026-10-01", oi=200000, volume=35000, iv=13.0),
            (25200.0, "CE"): OptionContract("N25200CE", 25200.0, "CE", "2026-10-01", oi=450000, volume=60000, iv=12.8),
            (24800.0, "PE"): OptionContract("N24800PE", 24800.0, "PE", "2026-10-01", oi=380000, volume=50000, iv=13.2),
        }
        chain = OptionChainSnapshot(
            timestamp=datetime(2026, 9, 28, 10, 15),
            spot_price=25060.0,
            contracts=contracts,
        )

        signals = generate_market_signals(
            candles=candles,
            chain=chain,
            vix=13.5,
            prev_vix=13.2,
            pcr_0930=0.90,
            parkinson_vol=11.5,
        )

        self.assertIsInstance(signals, MarketSignals)
        self.assertEqual(signals.spot_price, 25060.0)
        self.assertEqual(signals.vwap.regime, "BULLISH")
        self.assertEqual(signals.orb.status, "BULLISH_BREAKOUT")
        self.assertEqual(signals.oi.call_wall, 25200.0)
        self.assertEqual(signals.oi.put_wall, 24800.0)
        self.assertAlmostEqual(signals.vix_iv.iv_spread, 1.5, places=1)

        summary = signals.summary()
        self.assertIn("spot_price", summary)
        self.assertIn("vwap_regime", summary)
        self.assertIn("orb_status", summary)
        self.assertIn("ker", summary)


if __name__ == "__main__":
    unittest.main()
