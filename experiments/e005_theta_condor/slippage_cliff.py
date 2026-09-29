"""Slippage cliff: where does the breach-spread book's edge break at size?

The core friction model charges slippage = pts_per_leg x qty x num_legs (linear).
Charging k x the modeled 1.5 pts/leg on every breach-spread trade and finding the k
where net breaks gives the cliff in *points*, which is lot-invariant under linear
scaling — the real capacity limit is non-linear impact (book walking), which needs
LOB data and is out of scope. This test says how much slippage deterioration the
2-leg structure's edge can absorb before going negative.

Run: python -m experiments.e005_theta_condor.slippage_cliff
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from experiments.common.lots import lot_for_date
from experiments.e005_theta_condor.replay_theta import ARTIFACTS
from experiments.e005_theta_condor.target_sweep import stats

HERE = Path(__file__).resolve().parent
MODEL_PTS = 1.5  # config.SLIPPAGE_POINTS_PER_LEG
SPREAD_LEGS = 2
MULTIPLIERS = [1, 3, 5, 8, 12, 16, 20]


def main() -> int:
    df = pd.read_csv(ARTIFACTS / "breach_spread_target_100.csv")
    df["date"] = df["date"].str[:10]
    # Core formula: slippage_1x = MODEL_PTS x qty x num_legs, qty = lot per leg.
    from datetime import datetime
    df["slip_1x"] = df["date"].map(lambda d: MODEL_PTS * lot_for_date(
        datetime.strptime(d, "%Y-%m-%d").date()) * SPREAD_LEGS)

    out = {}
    print(f"{'mult':>5}{'pts/leg':>9}{'net':>11}{'wr':>7}{'pf':>7}{'maxDD':>9}  extra slippage/trade")
    for k in MULTIPLIERS:
        stressed = df.copy()
        stressed["net_pnl"] = stressed["net_pnl"] - (k - 1) * stressed["slip_1x"]
        s = stats(stressed)
        out[f"{k}x"] = s
        print(f"{k:>4}x{MODEL_PTS * k:>8.1f}{s['net']:>11,.0f}{s['wr']:>7.3f}{str(s['pf']):>7}"
              f"{s['max_dd']:>9,.0f}  {(k - 1) * stressed['slip_1x'].mean():>8.1f}")

    # Exact breakeven multiplier: net_breaks where net_1x - (k*-1) * sum(slip_1x) = 0.
    base = df["net_pnl"].sum()
    slip_sum = df["slip_1x"].sum()
    k_star = 1.0 + base / slip_sum
    out["breakeven_multiplier"] = round(k_star, 1)
    out["breakeven_pts_per_leg"] = round(MODEL_PTS * k_star, 1)
    print(f"\nbreakeven: {k_star:.1f}x modeled slippage = {MODEL_PTS * k_star:.1f} pts/leg "
          f"(net hits 0). Per-trade avg net {base / len(df):,.0f} vs avg 1x slippage "
          f"{df['slip_1x'].mean():,.0f}.")

    # Lot-invariance note: PnL and slippage both scale linearly with lots in the core
    # model, so the cliff multiplier is the same at N lots; non-linear impact is the
    # real capacity constraint and needs LOB data.
    with open(ARTIFACTS / "slippage_cliff.json", "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"written: {ARTIFACTS / 'slippage_cliff.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
