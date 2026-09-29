"""IV-regime buckets: does the condor edge concentrate in high-IV regimes?

Merges e005's per-day condor PnLs (clean artifact) with the e002 feature frame's
`straddle_pct` (t-1 ATM straddle / futures close, % — the IV proxy the sizing rule would
condition on live). Quintiles are ranked WITHIN each calendar year so era level shifts
(IV was structurally higher in 2021-22) don't fake a regime effect; each day's bucket is
thus "high IV relative to that year so far". Expiry-day-only buckets reported separately
(the actionable book is expiry-centric).

Run: python -m experiments.e005_theta_condor.iv_regimes
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.e005_theta_condor.replay_theta import ARTIFACTS

HERE = Path(__file__).resolve().parent
E2_CACHE = HERE.parent / "e002_regime_models" / "artifacts" / "dataset_cache.parquet"


def main() -> int:
    e5 = pd.read_csv(ARTIFACTS / "theta_condor.csv")
    e5["date"] = e5["date"].str[:10]
    sim = e5[~e5["exit_reason"].isin(["NOSIM", "NOLEG"])].copy()
    sim["year"] = sim["date"].str[:4]
    sim["is_expiry"] = sim["date"] == sim["expiry"]

    feats = pd.read_parquet(E2_CACHE, columns=["date", "straddle_pct"])
    feats["date"] = feats["date"].astype(str).str[:10]
    m = sim.merge(feats, on="date", how="inner")
    print(f"merged {len(m)}/{len(sim)} days with the IV feature")

    # Within-year expanding percentile: each day ranked against that year's PRIOR days
    # (no look-ahead; a live trader knows the year's history so far).
    m["iv_pctile"] = (
        m.sort_values("date").groupby("year")["straddle_pct"].expanding(min_periods=20).rank(pct=True)
    ).reset_index(level=0, drop=True)
    m["iv_bucket"] = pd.cut(m["iv_pctile"], bins=[0, 0.2, 0.4, 0.6, 0.8, 1.0],
                            labels=["q1_low", "q2", "q3", "q4", "q5_high"])

    def stats(sub: pd.DataFrame) -> dict:
        if not len(sub):
            return {"n": 0}
        gp = sub.loc[sub.net_pnl > 0, "net_pnl"].sum()
        gl = abs(sub.loc[sub.net_pnl <= 0, "net_pnl"].sum())
        return {"n": int(len(sub)), "net": round(float(sub.net_pnl.sum()), 0),
                "avg": round(float(sub.net_pnl.mean()), 1),
                "wr": round(float((sub.net_pnl > 0).mean()), 3),
                "pf": round(float(gp / gl), 2) if gl else None}

    out = {"all_days": {}, "expiry_days": {}}
    for label, sub in (("all_days", m), ("expiry_days", m[m.is_expiry])):
        for b, s in sub.groupby("iv_bucket", observed=True):
            out[label][str(b)] = stats(s)
        out[label]["_median_straddle_by_bucket"] = {
            str(b): round(float(g.straddle_pct.median()), 3)
            for b, g in sub.groupby("iv_bucket", observed=True)}

    print(f"\n{'bucket':<10}{'n':>6}{'net':>11}{'avg':>8}{'wr':>7}{'pf':>7}")
    for label in ("all_days", "expiry_days"):
        print(f"-- {label} --")
        for b, s in out[label].items():
            if b.startswith("_"):
                continue
            print(f"{b:<10}{s['n']:>6}{s['net']:>11,.0f}{s['avg']:>8.1f}{s['wr']:>7.3f}{str(s['pf']):>7}")

    with open(ARTIFACTS / "iv_regimes.json", "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nwritten: {ARTIFACTS / 'iv_regimes.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
