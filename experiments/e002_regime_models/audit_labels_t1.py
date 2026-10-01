"""E002 leak audit: features are strictly t-1, but the condor LABELS are not.

`features.py` shift(1)-discipline is pinned by tests — pcr_t1, wall_*_t1, straddle_pct
are all yesterday's values. The leak sits one layer down: the Iron Condor labels the
models predict come from e001's day-t-wall book, whose walls are day-t EOD OI — 6 hours
future-relative to the entry (paper_trade Add. 8). On wall-breach days the label knows
the day's wall side before the model would.

This audit keeps the frozen feature set, rebuilds ONLY the condor labels on t-1 walls
(the wall source observable before 09:15, from paper_trade.csv), and re-runs the frozen
walkforward_dte protocol. Comparing gating vs artifacts_dte/ answers: how much of the
selector's +793,906 is real signal vs labeling leakage.

Run: python -m experiments.e002_regime_models.audit_labels_t1 [--skip-walkforward]
Writes artifacts_t1labels/ (never touches artifacts/ or artifacts_dte/).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

from experiments.e002_regime_models import features as F
from experiments.e002_regime_models import walkforward as W
from experiments.e002_regime_models import walkforward_dte as WD
from experiments.e005_theta_condor.replay_theta import (
    TARGET_FRAC, _chain_view, _condor_legs_unconditional, _partition_calendar, _safe_exp,
    simulate_theta_condor)
from experiments.e005_theta_condor.paper_trade import _px_map
from core.feeds.intraday import available_dates, load_intraday_candles
from experiments.common.lots import lot_for_date

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "artifacts_t1labels"
PT_CSV = HERE.parent / "e005_theta_condor" / "artifacts" / "paper_trade.csv"


def t1_walls() -> pd.DataFrame:
    df = pd.read_csv(PT_CSV)
    df["d"] = pd.to_datetime(df["date"]).dt.date
    return df.set_index("d")[["put_wall_t1", "call_wall_t1", "signal"]]


def rebuild_condor_labels_t1(historical_dir: Path, cal: Dict) -> pd.DataFrame:
    """e005's condor book priced with t-1 walls: same legs/anchors/exits, only the wall
    source changes. Rows mirror e001's label semantics (net_pnl, win, simulated)."""
    walls = t1_walls()
    rows: List[dict] = []
    for d in available_dates():
        ts = pd.Timestamp(d)
        d_date = ts.date() if hasattr(d, "date") else d
        base = {"date": ts, "simulated": False, "net_pnl": 0.0, "win": False}
        w = walls.loc[d_date] if d_date in walls.index else None
        if w is None or pd.isna(w["put_wall_t1"]) or pd.isna(w["call_wall_t1"]):
            rows.append({**base, "skip": "NOWALLS"})
            continue
        try:
            candles = load_intraday_candles(d)
        except FileNotFoundError:
            rows.append({**base, "skip": "NODATA"})
            continue
        own_path = cal.get(d_date)
        if own_path is None:
            rows.append({**base, "skip": "NODATA"})
            continue
        own_df = pd.read_parquet(own_path)
        nifty = own_df[(own_df["symbol"] == "NIFTY") & (own_df["instrument"].isin(["OPTIDX", "IDO"]))]
        exps = [x for x in (_safe_exp(e) for e in nifty["expiry"].unique()) if x and x >= d_date]
        if not exps:
            rows.append({**base, "skip": "NODATA"})
            continue
        expiry = min(exps)
        dte0 = max((expiry - d_date).days, 0.5)
        pe, ce = _chain_view(own_df, expiry)
        if pe.empty or ce.empty:
            rows.append({**base, "skip": "NOLEG"})
            continue
        open_map = _px_map(pd.concat([pe, ce]), "open")
        exit_map = _px_map(pd.concat([pe, ce]), "close")
        legs = _condor_legs_unconditional(float(w["put_wall_t1"]), float(w["call_wall_t1"]))
        entry = [open_map.get((float(l["strike"]), "CE" if l["is_call"] else "PE")) for l in legs]
        exits = [exit_map.get((float(l["strike"]), "CE" if l["is_call"] else "PE")) for l in legs]
        if any(c is None or c <= 0 for c in entry) or any(c is None or c < 0 for c in exits):
            rows.append({**base, "skip": "NOLEG"})
            continue
        qty = lot_for_date(d_date)
        credit = sum(entry[i] * qty for i, l in enumerate(legs) if l["action"] == "SELL") \
            - sum(entry[i] * qty for i, l in enumerate(legs) if l["action"] == "BUY")
        if credit <= 0:
            rows.append({**base, "skip": "NOSIM"})
            continue
        sim = simulate_theta_condor(candles, legs, entry, exits, qty, dte0,
                                    float(candles.iloc[0]["open"]), target_frac=TARGET_FRAC)
        rows.append({"date": ts, "simulated": True, "net_pnl": sim["net_pnl"],
                     "win": sim["win"], "skip": "", "credit": sim["credit"],
                     "exit_reason": sim["exit_reason"]})
    return pd.DataFrame(rows)


def main() -> int:
    import config

    ap = argparse.ArgumentParser(description="e002 t-1-label leak audit")
    ap.add_argument("--skip-walkforward", action="store_true")
    args = ap.parse_args()

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    cache = ARTIFACTS / "condor_labels_t1.csv"
    if cache.exists():
        condor = pd.read_csv(cache, parse_dates=["date"])
        print(f"loaded cached t-1 condor labels: {len(condor)} rows")
    else:
        cal = _partition_calendar(config.HISTORICAL_DATA_DIR)
        print("rebuilding condor labels on t-1 walls (one pass over all sessions)...")
        condor = rebuild_condor_labels_t1(config.HISTORICAL_DATA_DIR, cal)
        condor.to_csv(cache, index=False)
    sim = condor[condor["simulated"]]
    print(f"t-1 condor book: {len(sim)} simulated days, net {sim['net_pnl'].sum():,.0f}, "
          f"wr {(sim['net_pnl'] > 0).mean():.3f} | skips: {condor['skip'].value_counts().to_dict()}")

    if args.skip_walkforward:
        return 0

    ds = F.build_dataset(config.HISTORICAL_DATA_DIR, HERE.parent)  # frozen features + labels
    # Overwrite ONLY the condor label columns with the t-1 book; bull/bear stay frozen.
    c = condor.set_index("date")
    # Days outside the t-1 book are not simulated -> False, matching e001's semantics
    # (pandas BooleanExtension NA breaks walkforward's `not r[col]` checks).
    ds["Iron_Condor_sim"] = ds["date"].map(c["simulated"]).fillna(False).astype("boolean")
    ds["Iron_Condor_won"] = ds["date"].map(c["win"]).fillna(False).astype("boolean")
    ds["Iron_Condor_net"] = ds["date"].map(c["net_pnl"]).fillna(0.0)

    # Frozen dte protocol, unchanged (same patch walkforward_dte applies).
    W.FEATURE_COLUMNS = WD.FEATURE_COLUMNS_DTE
    cal_dte = WD.expiry_calendar(config.HISTORICAL_DATA_DIR)
    ds = ds.merge(cal_dte, on="date", how="left")
    if "rule_signal" not in ds.columns:
        from experiments.e001_leakfree_replay.replay import TREND_THRESHOLD_PCT
        ds["rule_signal"] = np.where(ds["fut_prev_ret"] >= TREND_THRESHOLD_PCT, "UP",
                              np.where(ds["fut_prev_ret"] <= -TREND_THRESHOLD_PCT, "DOWN", "FLAT"))

    print("running the frozen walkforward on t-1 labels...")
    preds, folds = W.run_walkforward(ds, verbose=False)
    if preds.empty:
        print("No folds produced.")
        return 1
    preds["rule_signal"] = preds["date"].map(ds.set_index("date")["rule_signal"])

    preds.to_parquet(ARTIFACTS / "oos_predictions.parquet", index=False)
    cal_sum = W.summarize_calibration(preds)
    cal_sum.to_csv(ARTIFACTS / "calibration_summary.csv", index=False)
    gate = W.gating_simulation(preds)
    with open(ARTIFACTS / "gating_sim.json", "w") as f:
        json.dump(gate, f, indent=2, default=str)

    with open(HERE / "artifacts_dte" / "gating_sim.json") as f:
        base_gate = json.load(f)
    print("\n=== GATING: frozen condor labels (day-t walls) vs t-1-wall labels ===")
    for policy in ("baseline", "ml_lgbm", "ml_logistic"):
        r, rb = gate[policy], base_gate[policy]
        print(f"{policy:<12} net {rb['net_total']:>10,.0f} -> {r['net_total']:>10,.0f} | "
              f"pf {rb['pf']:.2f} -> {r['pf']:.2f} | wr {rb['win_rate']:.3f} -> {r['win_rate']:.3f} | "
              f"dd {rb['max_dd']:>8,.0f} -> {r['max_dd']:>8,.0f}")
        for arch in W.ARCH_KEYS:
            print(f"    {arch:<18} n {rb.get(f'n_{arch}', 0):>4} -> {r.get(f'n_{arch}', 0):>4} | "
                  f"net {rb.get(f'net_{arch}', 0):>10,.0f} -> {r.get(f'net_{arch}', 0):>10,.0f}")
    print(f"\nartifacts written to {ARTIFACTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
