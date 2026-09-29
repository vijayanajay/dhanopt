"""Exit-rule sweep: Kailash's decay-trailing exit vs target/no-cap rows (real data).

Decay-trailing rule (his proposal, continuous form): from `trail_time` onward, close as
soon as MTM >= trail_frac x entry credit — locks in decay and dodges the 14:30-15:15
expiry gamma spike. All trail configs keep the 1.4x credit SL and have NO profit cap
(the cap is what we are trying to beat). Reference rows: documented (SL + 50% target),
100% target (sweep optimum), no cap.

Run: python -m experiments.e005_theta_condor.exit_sweep
"""
from __future__ import annotations

import json
from datetime import time
from pathlib import Path

import pandas as pd

from experiments.e005_theta_condor.replay_theta import (
    ARTIFACTS, _partition_calendar, prepare_day, simulate_theta_condor)
from experiments.e005_theta_condor.target_sweep import stats

HERE = Path(__file__).resolve().parent

CONFIGS = [
    ("documented_50pct", dict(target_frac=0.50)),
    ("target_100pct", dict(target_frac=1.00)),
    ("no_cap", dict(target_frac=None)),
    ("trail_75pct_1400", dict(target_frac=None, trail_time=time(14, 0), trail_frac=0.75)),
    ("trail_80pct_1400", dict(target_frac=None, trail_time=time(14, 0), trail_frac=0.80)),
    ("trail_75pct_1330", dict(target_frac=None, trail_time=time(13, 30), trail_frac=0.75)),
    ("trail_80pct_1430", dict(target_frac=None, trail_time=time(14, 30), trail_frac=0.80)),
]


def main() -> int:
    import config
    from core.feeds.intraday import available_dates

    dates = available_dates()
    labels = pd.read_csv(HERE.parent / "e001_leakfree_replay" / "artifacts" / "labels_daily.csv")
    labels["date"] = labels["date"].astype(str)
    rule_days = set(labels[(labels["archetype"] == "Iron Condor") & (labels["selected_by_rule"] == True)]["date"])

    print(f"running {len(CONFIGS)} exit configs over {len(dates)} sessions...")
    cal = _partition_calendar(config.HISTORICAL_DATA_DIR)
    frames: dict[str, list] = {name: [] for name, _ in CONFIGS}
    for d in dates:
        prep = prepare_day(d, cal, rule_days)
        if prep is None:
            continue
        skip = "exit_reason" in prep
        for name, kw in CONFIGS:
            if skip:
                frames[name].append(prep)
                continue
            sim = simulate_theta_condor(prep["candles"], prep["legs"], prep["entry"], prep["exit"],
                                        prep["lot"], prep["dte0"], prep["spot_open"], **kw)
            row = {k: v for k, v in prep.items() if k not in ("candles", "legs", "entry", "exit")} | sim
            frames[name].append(row)

    out = {}
    print(f"\n{'config':<20}{'wr':>7}{'net':>11}{'pf':>7}{'maxDD':>9}  exits")
    for name, _ in CONFIGS:
        df = pd.DataFrame(frames[name])
        s = stats(df)
        out[name] = s
        exits = " / ".join(f"{k} {v}" for k, v in s["exits"].items())
        print(f"{name:<20}{s['wr']:>7.3f}{s['net']:>11,.0f}{str(s['pf']):>7}{s['max_dd']:>9,.0f}  {exits}")
        df.to_csv(ARTIFACTS / f"exit_sweep_{name}.csv", index=False)

    # Sanity: shared prep must reproduce the committed artifact and the target sweep rows.
    committed = pd.read_csv(ARTIFACTS / "theta_condor.csv")
    ref = stats(committed)
    assert out["documented_50pct"]["net"] == ref["net"] and out["documented_50pct"]["n"] == ref["n"], \
        f"documented row {out['documented_50pct']} != committed {ref}"
    sweep = json.load(open(ARTIFACTS / "target_sweep.json"))
    assert out["target_100pct"]["net"] == sweep["1.00"]["net"], "100% row drifted from target sweep"
    assert out["no_cap"]["net"] == sweep["no_cap"]["net"], "no-cap row drifted from target sweep"
    print("\nsanity OK: documented/100%/no-cap rows reproduce committed artifacts")

    with open(ARTIFACTS / "exit_sweep.json", "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"written: {ARTIFACTS / 'exit_sweep.json'} (+ per-config CSVs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
