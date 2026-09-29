"""Breached-wall credit spread backtest (Kailash's Idea 3, formalized).

Strategy: on dte<=1 days where spot has gapped over the prior-day max-OI wall, do NOT
trade the 4-leg condor (valid-structure days lose, PF 0.78). Instead sell ONLY the
breached wall as a defined-risk credit spread (wall + the existing 150-pt wing):
  - call wall breached (call_wall <= spot open): SELL CE wall / BUY CE wall+150
  - put wall breached  (put_wall  >= spot open): SELL PE wall / BUY PE wall-150
  - valid structure: no trade. Both-breached (crossed walls): none observed in data.
Exit rules as production: 1.4x credit SL, target = 100% of credit (sweep pick), plus a
no-cap reference. Reuses e005's identity-validated plumbing — the spread legs are a
2-leg subset of the condor legs prepare_day already anchors to real opens/closes.

Run: python -m experiments.e005_theta_condor.breach_spread
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from experiments.e005_theta_condor.replay_theta import (
    ARTIFACTS, _partition_calendar, prepare_day, simulate_theta_condor)
from experiments.e005_theta_condor.target_sweep import stats as _base_stats


def stats(df: pd.DataFrame) -> dict:
    """target_sweep.stats + per-trade average."""
    s = _base_stats(df)
    sim = df[~df["exit_reason"].isin(["NOSIM", "NOLEG"])]
    s["avg"] = round(float(sim.net_pnl.mean()), 1) if len(sim) else None
    return s

HERE = Path(__file__).resolve().parent
WIDTH = 150  # the condor's wing offset — now the spread width
CONFIGS = [("target_100", dict(target_frac=1.0)), ("no_cap", dict(target_frac=None))]


def spread_legs(prep: Dict, side: str):
    """The breached-side 2-leg subset of the condor legs (indices per _condor_legs_unconditional:
    0 = SELL put wall, 1 = SELL call wall, 2 = BUY put wing, 3 = BUY call wing)."""
    idx = [1, 3] if side == "call" else [0, 2]
    return ([prep["legs"][i] for i in idx], [prep["entry"][i] for i in idx],
            [prep["exit"][i] for i in idx])


def main() -> int:
    import config
    from core.feeds.intraday import available_dates

    dates = available_dates()
    labels = pd.read_csv(HERE.parent / "e001_leakfree_replay" / "artifacts" / "labels_daily.csv")
    labels["date"] = labels["date"].astype(str)
    rule_days = set(labels[(labels["archetype"] == "Iron Condor") & (labels["selected_by_rule"] == True)]["date"])

    print(f"screening {len(dates)} sessions for dte<=1 breached-wall days...")
    cal = _partition_calendar(config.HISTORICAL_DATA_DIR)
    frames: Dict[str, List] = {name: [] for name, _ in CONFIGS}
    n_screen = n_valid_skip = 0
    for d in dates:
        prep = prepare_day(d, cal, rule_days)
        if prep is None or "exit_reason" in prep:
            continue
        n_screen += 1
        if prep["dte0"] > 1.0:
            continue
        spot = prep["spot_open"]
        if prep["call_wall"] <= spot:
            side = "call"
        elif prep["put_wall"] >= spot:
            side = "put"
        else:
            n_valid_skip += 1
            continue  # valid structure: the strategy stands down
        legs2, entry2, exit2 = spread_legs(prep, side)
        base = {"date": prep["date"], "is_rule_day": prep["is_rule_day"], "side": side,
                "dte0": prep["dte0"], "spot_open": spot, "wall": prep["call_wall"] if side == "call" else prep["put_wall"]}
        for name, kw in CONFIGS:
            sim = simulate_theta_condor(prep["candles"], legs2, entry2, exit2,
                                        prep["lot"], prep["dte0"], prep["spot_open"], **kw)
            frames[name].append({**base, **sim})

    out = {}
    print(f"simulated spread days: {len(frames['target_100'])} "
          f"(of {n_screen} dte<=1 sim-able days; {n_valid_skip} valid-structure stand-downs)")
    for name, _ in CONFIGS:
        df = pd.DataFrame(frames[name])
        s = stats(df)
        s["by_side"] = {side: stats(sub) for side, sub in df.groupby("side")}
        # worst-5% day tail
        tail = np.percentile(df.net_pnl, 5)
        worst = df.nsmallest(10, "net_pnl")[["date", "side", "exit_reason", "net_pnl", "credit"]]
        s["tail_p5"] = round(float(tail), 0)
        s["worst_day"] = round(float(df.net_pnl.min()), 0)
        out[name] = s
        print(f"\n[{name}] wr={s['wr']} net={s['net']:,.0f} pf={s['pf']} maxDD={s['max_dd']:,.0f} "
              f"exits={s['exits']}")
        print(f"  tail: p5={tail:,.0f} worst={s['worst_day']:,.0f} "
              f"(defined max loss/lot = ({WIDTH} - credit) x lot; credit/leg avg "
              f"{df.credit.mean():,.0f})")
        for side, r in s["by_side"].items():
            print(f"  {side:>4} breach: n={r['n']:>3} net={r['net']:>10,.0f} avg={r['avg']:>8.1f} "
                  f"wr={r['wr']} pf={r['pf']}")
        print("  worst 10 days:")
        print(worst.to_string(index=False))
        df.to_csv(ARTIFACTS / f"breach_spread_{name}.csv", index=False)

    # Comparison: the 4-leg condor (documented exits) on the SAME breached dte<=1 days.
    breach_dates = pd.read_csv(ARTIFACTS / "breach_spread_target_100.csv")["date"].tolist()
    condor = pd.read_csv(ARTIFACTS / "theta_condor.csv")
    condor["date"] = condor["date"].str[:10]
    same = condor[condor.date.isin(breach_dates)]
    same = same[~same.exit_reason.isin(["NOSIM", "NOLEG"])]
    if len(same):
        print(f"\nreference — 4-leg condor (documented exits) on the same days: "
              f"n={len(same)} net={same.net_pnl.sum():,.0f} wr={(same.net_pnl > 0).mean():.3f}")

    with open(ARTIFACTS / "breach_spread.json", "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nwritten: {ARTIFACTS / 'breach_spread.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
