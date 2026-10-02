"""E011 Sensitivity Engine: Parameter sweeps across estimators, windows, and hedge thresholds.

Reproduces Section 2.6 and Section 2.7 of actionplan.md:
1. Volatility Estimator Window Comparison (GK 5d, 10d, 20d; Parkinson 5d, 10d, 20d).
2. Delta Rebalancing Threshold Sweep (0.10, 0.15, 0.20, 0.25).
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Dict, List

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from core.feeds.intraday import load_intraday_candles
from experiments.e011_vrp_delta_hedge.replay_vrp import run_vrp_replay
from experiments.e011_vrp_delta_hedge.volatility import get_vrp_signal, load_or_compute_volatility

ARTIFACTS = HERE / "artifacts"


def warm_candle_cache(vdf: pd.DataFrame) -> Dict:
    """Pre-loads candles for all unique signal dates into memory once."""
    all_dates = set()
    for est in ("gk", "parkinson"):
        for w in (5, 10, 20):
            sig = get_vrp_signal(vdf, estimator=est, window=w)
            all_dates.update(vdf[sig == True]["date"].tolist())

    print(f"Pre-warming candle cache for {len(all_dates)} unique sessions...")
    cache = {}
    for d in sorted(all_dates):
        try:
            cache[d] = load_intraday_candles(d)
        except Exception:
            pass
    print(f"Candle cache ready with {len(cache)} sessions.")
    return cache


def sweep_volatility_estimators(vdf: pd.DataFrame, cache: Dict) -> List[Dict]:
    """Sweeps Garman-Klass vs Parkinson across 5d, 10d, 20d rolling windows."""
    configs = [
        ("Garman-Klass", "gk", 5),
        ("Garman-Klass", "gk", 10),
        ("Garman-Klass", "gk", 20),
        ("Parkinson", "parkinson", 5),
        ("Parkinson", "parkinson", 10),
        ("Parkinson", "parkinson", 20),
    ]

    results = []
    print("\n" + "=" * 90)
    print("  SECTION 2.6: VOLATILITY ESTIMATOR WINDOW SENSITIVITY MATRIX")
    print("=" * 90)
    print(f"{'Estimator':<15} {'Window':<8} {'Trades':<8} {'Net PnL (Rs)':<16} {'PF':<8} {'Win Rate':<10} {'Sharpe':<8} {'Max DD (Rs)':<14}")
    print("-" * 90)

    for name, est, w in configs:
        _, m = run_vrp_replay(
            slippage_mult=1.0,
            threshold=0.15,
            estimator=est,
            window=w,
            candle_cache=cache,
        )
        res_entry = {
            "name": name,
            "estimator": est,
            "window": w,
            "trades": m["total_trades"],
            "net_pnl": m["total_net_pnl"],
            "profit_factor": m["profit_factor"],
            "win_rate": m["win_rate"],
            "sharpe": m["sharpe_ratio"],
            "max_drawdown": m["max_drawdown_inr"],
        }
        results.append(res_entry)
        print(f"{name:<15} {f'{w}-day':<8} {m['total_trades']:<8} Rs. {m['total_net_pnl']:>10,.2f} {m['profit_factor']:<8.2f} {m['win_rate']*100:<9.1f}% {m['sharpe_ratio']:<8.2f} Rs. {m['max_drawdown_inr']:>10,.2f}")

    print("=" * 90)

    with open(ARTIFACTS / "sensitivity_volatility.json", "w") as f:
        json.dump(results, f, indent=2)

    return results


def sweep_thresholds(vdf: pd.DataFrame, cache: Dict) -> List[Dict]:
    """Sweeps delta rebalance thresholds from 0.10 to 0.25 on base GK 10d."""
    thresholds = [0.10, 0.15, 0.20, 0.25]
    results = []

    print("\n" + "=" * 95)
    print("  SECTION 2.7: DELTA REBALANCING THRESHOLD SENSITIVITY MATRIX")
    print("=" * 95)
    print(f"{'Threshold':<12} {'Hedges/Day':<12} {'Friction/Trade':<16} {'Net PnL (Rs)':<16} {'PF':<8} {'Win Rate':<10} {'Sharpe':<8} {'Max DD (Rs)':<14}")
    print("-" * 95)

    for th in thresholds:
        _, m = run_vrp_replay(
            slippage_mult=1.0,
            threshold=th,
            estimator="gk",
            window=10,
            candle_cache=cache,
        )
        res_entry = {
            "threshold": th,
            "avg_hedges_per_day": m["avg_hedges_per_day"],
            "avg_friction_per_trade": m["avg_friction_per_trade"],
            "trades": m["total_trades"],
            "net_pnl": m["total_net_pnl"],
            "profit_factor": m["profit_factor"],
            "win_rate": m["win_rate"],
            "sharpe": m["sharpe_ratio"],
            "max_drawdown": m["max_drawdown_inr"],
        }
        results.append(res_entry)
        label = f"{th:.2f}" + (" (Tight)" if th == 0.10 else " (Base)" if th == 0.15 else " (Optimal)" if th == 0.20 else " (Loose)")
        print(f"{label:<12} {m['avg_hedges_per_day']:<12.1f} Rs. {m['avg_friction_per_trade']:>10,.2f}  Rs. {m['total_net_pnl']:>10,.2f} {m['profit_factor']:<8.2f} {m['win_rate']*100:<9.1f}% {m['sharpe_ratio']:<8.2f} Rs. {m['max_drawdown_inr']:>10,.2f}")

    print("=" * 95)

    with open(ARTIFACTS / "sensitivity_threshold.json", "w") as f:
        json.dump(results, f, indent=2)

    return results


def run_all_sensitivities():
    vdf = load_or_compute_volatility()
    cache = warm_candle_cache(vdf)
    sweep_volatility_estimators(vdf, cache)
    sweep_thresholds(vdf, cache)


if __name__ == "__main__":
    run_all_sensitivities()
