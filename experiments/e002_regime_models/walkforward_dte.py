"""E002 variant: days-to-expiry replaces `dow` (the SHAP addendum's recommendation).

Motivation (e002 addendum): the condor model's #1 feature was raw weekday, but its
"edge" is an expiry-day 0DTE effect that MIGRATED Thu->Tue when NSE moved the weekly
expiry (2025-09-01). days-to-expiry survives any future expiry change without relearning.

Protocol: identical to the frozen e002 walk-forward (same folds, embargo, LGBM params,
gating) — ONLY the feature set changes: dow out, dte + is_expiry in. Leakage note:
the expiry calendar of day t is public schedule information, fully known at t-1 close.

Run: python -m experiments.e002_regime_models.walkforward_dte
Writes artifacts_dte/ (never touches the frozen run's artifacts/).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from core.feeds.bhavcopy import parse_date
from experiments.e002_regime_models import features as F
from experiments.e002_regime_models import walkforward as W

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "artifacts_dte"

FEATURE_COLUMNS_DTE: List[str] = [c for c in F.FEATURE_COLUMNS if c != "dow"] + ["dte", "is_expiry"]


def expiry_calendar(historical_dir: Path) -> pd.DataFrame:
    """One row per trade day: days to the nearest expiry (>= today) and is_expiry flag."""
    nearest: Dict = {}
    for f in sorted(historical_dir.glob("**/*.parquet")):
        stem = f.stem
        if not (stem.startswith("fo_") and len(stem) == 11 and stem[3:].isdigit()):
            continue
        try:
            td = datetime.strptime(stem[3:], "%Y%m%d").date()
        except ValueError:
            continue
        try:
            opts = pd.read_parquet(f, columns=["symbol", "instrument", "expiry"])
        except Exception:
            continue
        nifty = opts[(opts["symbol"] == "NIFTY") & (opts["instrument"].isin(["OPTIDX", "IDO"]))]
        if nifty.empty:
            continue
        exps = []
        for e in nifty["expiry"].unique():
            try:
                exps.append(parse_date(str(e).strip()))
            except Exception:
                continue
        future = [e for e in exps if e >= td]
        if future:
            nearest[td] = min(future)
    rows = [{"date": pd.Timestamp(d), "dte": (e - d).days, "is_expiry": int((e - d).days == 0)}
            for d, e in sorted(nearest.items())]
    return pd.DataFrame(rows)


def build_dataset_dte(historical_dir: Path, experiment_root: Path) -> pd.DataFrame:
    ds = F.build_dataset(historical_dir, experiment_root)  # frozen cache, includes dow
    cal = expiry_calendar(historical_dir)
    ds = ds.merge(cal, on="date", how="left")
    return ds


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="E002 variant: days-to-expiry feature set")
    parser.parse_args()

    import config

    # Patch the frozen module's feature list for this process, then reuse everything
    # (_fit_predict reads FEATURE_COLUMNS from its module namespace).
    W.FEATURE_COLUMNS = FEATURE_COLUMNS_DTE

    ds = build_dataset_dte(config.HISTORICAL_DATA_DIR, HERE.parent)
    if "rule_signal" not in ds.columns:
        from experiments.e001_leakfree_replay.replay import TREND_THRESHOLD_PCT
        ds["rule_signal"] = np.where(ds["fut_prev_ret"] >= TREND_THRESHOLD_PCT, "UP",
                              np.where(ds["fut_prev_ret"] <= -TREND_THRESHOLD_PCT, "DOWN", "FLAT"))
    print(f"dataset rows: {len(ds)} | features: {len(FEATURE_COLUMNS_DTE)} (dow -> dte + is_expiry)")
    print("dte distribution (OOS window):")
    print(ds.loc[ds["date"] >= "2023-01-01", "dte"].value_counts().sort_index().to_string())

    preds, folds = W.run_walkforward(ds, verbose=False)
    if preds.empty:
        print("No folds produced.")
        return 1

    sig_map = ds.set_index("date")["rule_signal"]
    preds["rule_signal"] = preds["date"].map(sig_map)

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    preds.to_parquet(ARTIFACTS / "oos_predictions.parquet", index=False)

    cal = W.summarize_calibration(preds)
    cal.to_csv(ARTIFACTS / "calibration_summary.csv", index=False)

    # Compare against the frozen run's calibration.
    with open(HERE / "artifacts" / "calibration_summary.csv") as f:
        base_cal = pd.read_csv(f)
    print("\n=== OOS CALIBRATION: frozen (dow) vs dte variant ===")
    for col in ["lgbm_brier", "logistic_brier"]:
        b = base_cal.set_index("archetype")[col]
        d = cal.set_index("archetype")[col]
        for arch in b.index:
            mark = "BETTER" if d[arch] < b[arch] else "worse"
            print(f"{arch:<18} {col}: {b[arch]:.4f} -> {d[arch]:.4f} ({mark})")

    gate = W.gating_simulation(preds)
    with open(ARTIFACTS / "gating_sim.json", "w") as f:
        json.dump(gate, f, indent=2, default=str)
    with open(HERE / "artifacts" / "gating_sim.json") as f:
        base_gate = json.load(f)
    print("\n=== GATING: frozen (dow) vs dte variant (matched monthly count) ===")
    for policy in ("baseline", "ml_lgbm", "ml_logistic"):
        r, rb = gate[policy], base_gate[policy]
        print(f"{policy:<12} net {rb['net_total']:>10,.0f} -> {r['net_total']:>10,.0f} | "
              f"pf {rb['pf']:.2f} -> {r['pf']:.2f} | wr {rb['win_rate']:.3f} -> {r['win_rate']:.3f} | "
              f"dd {rb['max_dd']:>8,.0f} -> {r['max_dd']:>8,.0f}")
        for arch in W.ARCH_KEYS:
            print(f"    {arch:<18} n {rb.get(f'n_{arch}', 0):>4} -> {r.get(f'n_{arch}', 0):>4} | "
                  f"net {rb.get(f'net_{arch}', 0):>10,.0f} -> {r.get(f'net_{arch}', 0):>10,.0f}")

    with open(ARTIFACTS / "folds.json", "w") as f:
        json.dump([{"fold": fr.fold, "test": f"{fr.test_start}..{fr.test_end}", "n": fr.n_test,
                    "metrics": fr.metrics} for fr in folds], f, indent=2)
    print(f"\nartifacts written to {ARTIFACTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
