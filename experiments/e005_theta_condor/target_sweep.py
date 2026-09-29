"""Target-level sweep: 50% -> no-cap, net/PF/DD at each level (one prep per day).

Picks the production exit rule with real data instead of a two-point comparison.
Run: python -m experiments.e005_theta_condor.target_sweep
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from experiments.e005_theta_condor.replay_theta import ARTIFACTS, _partition_calendar, run_days_multi_target

HERE = Path(__file__).resolve().parent
TARGETS = [0.50, 0.75, 1.00, 1.50, 2.00, None]  # None = no cap (SL + EOD only)


def stats(df: pd.DataFrame) -> dict:
    sim = df[~df["exit_reason"].isin(["NOSIM", "NOLEG"])]
    gp = sim.loc[sim.net_pnl > 0, "net_pnl"].sum()
    gl = abs(sim.loc[sim.net_pnl <= 0, "net_pnl"].sum())
    daily = sim.groupby("date")["net_pnl"].sum().sort_index().cumsum()
    dd = float((daily - daily.cummax()).min())
    return {"n": len(sim), "wr": round(float((sim.net_pnl > 0).mean()), 3),
            "net": round(float(sim.net_pnl.sum()), 0), "pf": round(float(gp / gl), 2) if gl else None,
            "max_dd": round(dd, 0),
            "exits": sim.exit_reason.value_counts().to_dict()}


def main() -> int:
    import config

    dates = __import__("core.feeds.intraday", fromlist=["available_dates"]).available_dates()
    labels = pd.read_csv(HERE.parent / "e001_leakfree_replay" / "artifacts" / "labels_daily.csv")
    labels["date"] = labels["date"].astype(str)
    rule_days = set(labels[(labels["archetype"] == "Iron Condor") & (labels["selected_by_rule"] == True)]["date"])

    print(f"sweeping {len(TARGETS)} target levels over {len(dates)} sessions...")
    cal = _partition_calendar(config.HISTORICAL_DATA_DIR)
    res = run_days_multi_target(dates, cal, rule_days, TARGETS)

    out = {}
    print(f"\n{'target':>8}{'n':>6}{'wr':>7}{'net':>11}{'pf':>7}{'maxDD':>9}  exits")
    for tf in TARGETS:
        df = pd.DataFrame(res[tf])
        s = stats(df)
        out["no_cap" if tf is None else f"{tf:.2f}"] = s
        label = "no cap" if tf is None else f"{tf*100:.0f}%"
        print(f"{label:>8}{s['n']:>6}{s['wr']:>7.3f}{s['net']:>11,.0f}{str(s['pf']):>7}"
              f"{s['max_dd']:>9,.0f}  {s['exits']}")
        df.to_csv(ARTIFACTS / f"target_sweep_{('no_cap' if tf is None else f'{tf:.2f}')}.csv", index=False)

    # Sanity: 50% row must reproduce the committed full-run artifact.
    committed = pd.read_csv(ARTIFACTS / "theta_condor.csv")
    ref = stats(committed)
    assert abs(out["0.50"]["net"] - ref["net"]) < 1.0 and out["0.50"]["n"] == ref["n"], \
        f"50% row {out['0.50']} != committed {ref}"
    print("\nsanity OK: 50% row reproduces the committed full-run artifact")

    with open(ARTIFACTS / "target_sweep.json", "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"written: {ARTIFACTS / 'target_sweep.json'} (+ per-level CSVs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
