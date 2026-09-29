"""E002: Purged monthly walk-forward for the three archetype win-probability models.

Protocol (frozen in experiment.md):
- Train: trailing N months (default 24). Embargo: 5 calendar days. Test: next calendar month.
- Refit every fold. Hyperparameters frozen (num_leaves=15, min_data_in_leaf=100, lr=0.05,
  feature_fraction=0.7, bagging_fraction=0.8); no per-fold tuning.
- Three models: P(Bull Call Spread wins), P(Bear Put Spread wins), P(Iron Condor wins).
- Baselines on identical folds: logistic regression (same features) and persistence
  (mean of the last 5 same-archetype outcomes).
- Calibration reported (Brier score vs base rate), not just accuracy.

Gating simulation ("fewer losses, same number of trades"):
- Baseline policy = the e001 t-1 rule: pick ONE archetype per day (UP->bull, DOWN->bear,
  FLAT->condor), one trade per day (BRD rule). Days with no signal are not traded.
- ML policy takes the SAME NUMBER of trades as baseline in each test month
  (one trade per day), but may choose WHICH days and WHICH archetype via the ensemble:
      score(day, archetype) = P_model(archetype wins on that day)
  It takes the K highest-scoring day-slots, K = baseline trade count that month.
  # ponytail: score is P(win) only; proper EV needs per-archetype target/max-loss which
  # daily open->close replay cannot pin down. Upgrade path: per-archetype EV means from e001.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from experiments.e002_regime_models.features import FEATURE_COLUMNS, build_dataset

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "artifacts"

TRAIN_MONTHS = 24
EMBARGO_DAYS = 5

TARGETS: Dict[str, str] = {
    "Bull Call Spread": "Bull_Call_Spread_won",
    "Bear Put Spread": "Bear_Put_Spread_won",
    "Iron Condor": "Iron_Condor_won",
}
PNL_COLUMNS: Dict[str, str] = {
    "Bull Call Spread": "Bull_Call_Spread_net",
    "Bear Put Spread": "Bear_Put_Spread_net",
    "Iron Condor": "Iron_Condor_net",
}
ARCH_KEYS = list(TARGETS.keys())
MODEL_NAMES = ("lgbm", "logistic", "persistence")
RULE_TO_ARCH = {"UP": "Bull Call Spread", "DOWN": "Bear Put Spread", "FLAT": "Iron Condor"}

LGB_PARAMS = dict(
    objective="binary",
    num_leaves=15,
    min_data_in_leaf=100,
    learning_rate=0.05,
    feature_fraction=0.7,
    bagging_fraction=0.8,
    bagging_freq=1,
    verbose=-1,
    seed=42,
)
N_ESTIMATORS = 300


def brier(p, y) -> float:
    p, y = np.asarray(p, dtype=float), np.asarray(y, dtype=float)
    return float(np.mean((p - y) ** 2)) if len(y) else float("nan")


@dataclass(slots=True)
class FoldResult:
    fold: int
    test_start: str
    test_end: str
    n_test: int
    metrics: Dict[str, Dict[str, float]] = field(default_factory=dict)


def month_starts(dates: pd.Series) -> List[pd.Timestamp]:
    months = sorted(dates.dt.to_period("M").unique())
    return [pd.Period(m).to_timestamp() for m in months]


def make_folds(dates: pd.Series, train_months: int = TRAIN_MONTHS) -> List[Tuple[pd.Timestamp, pd.Timestamp]]:
    starts = month_starts(dates)
    return [(starts[i - train_months], starts[i]) for i in range(train_months, len(starts))]


def _fit_predict(train: pd.DataFrame, test: pd.DataFrame, target: str, sim_col: str) -> Dict[str, np.ndarray]:
    """OOS probabilities per model for one archetype on one fold."""
    usable_tr = train[sim_col].fillna(False).astype(bool) & train[target].notna()
    Xtr = train.loc[usable_tr, FEATURE_COLUMNS].apply(pd.to_numeric, errors="coerce")
    ytr = train.loc[usable_tr, target].astype(float).to_numpy()

    Xte = test[FEATURE_COLUMNS].apply(pd.to_numeric, errors="coerce")
    n = len(test)

    if len(ytr) < 200 or ytr.sum() < 20:
        base = float(np.mean(ytr)) if len(ytr) else 0.5
        return {m: np.full(n, base) for m in MODEL_NAMES}

    from lightgbm import LGBMClassifier
    lgb = LGBMClassifier(n_estimators=N_ESTIMATORS, **LGB_PARAMS)
    lgb.fit(Xtr, ytr)
    p_lgb = lgb.predict_proba(Xte)[:, 1]

    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    pipe = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                         LogisticRegression(max_iter=2000, C=0.5))
    pipe.fit(Xtr, ytr)
    p_log = pipe.predict_proba(Xte)[:, 1]

    # Persistence: mean of last 5 same-archetype outcomes strictly before each test day.
    ser = train[target].astype(float)
    pers = []
    for d in test["date"]:
        prior = ser[train["date"] < d]
        pers.append(float(prior.tail(5).mean()) if len(prior) else float(np.mean(ytr)))
    p_pers = np.array(pers)

    return {"lgbm": p_lgb, "logistic": p_log, "persistence": p_pers}


def run_walkforward(ds: pd.DataFrame, verbose: bool = True) -> Tuple[pd.DataFrame, List[FoldResult]]:
    ds = ds.sort_values("date").reset_index(drop=True)
    folds = make_folds(ds["date"])

    pred_frames: List[pd.DataFrame] = []
    fold_results: List[FoldResult] = []

    for k, (train_start, test_start) in enumerate(folds, 1):
        test_end = test_start + pd.offsets.MonthEnd(0)
        embargo_end = test_start - pd.Timedelta(days=EMBARGO_DAYS)
        train = ds[(ds["date"] >= train_start) & (ds["date"] < embargo_end)]
        test = ds[(ds["date"] >= test_start) & (ds["date"] <= test_end)].copy()
        if test.empty:
            continue

        prob_by_arch: Dict[str, Dict[str, np.ndarray]] = {}
        for arch in ARCH_KEYS:
            sim_col = arch.replace(" ", "_") + "_sim"
            prob_by_arch[arch] = _fit_predict(train, test, TARGETS[arch], sim_col)

        keep_cols = ["date", "dow", "rule_signal"] + list(PNL_COLUMNS.values()) \
            + list(TARGETS.values()) + [a.replace(" ", "_") + "_sim" for a in ARCH_KEYS]
        block = test[keep_cols].reset_index(drop=True).copy()
        for arch in ARCH_KEYS:
            for model in MODEL_NAMES:
                block[f"{model}__{arch}"] = prob_by_arch[arch][model]
        pred_frames.append(block)

        fr = FoldResult(fold=k, test_start=str(test_start.date()),
                        test_end=str(test_end.date()), n_test=len(test))
        for arch in ARCH_KEYS:
            target = TARGETS[arch]
            # NA-safe: nullable boolean labels -> float array with NaN for missing sims
            y = test[target].to_numpy(dtype="float", na_value=np.nan)
            mask = ~np.isnan(y)
            y_clean = y[mask]
            m: Dict[str, float] = {"base_rate": round(float(np.mean(y_clean)), 3) if len(y_clean) else float("nan")}
            for model in MODEL_NAMES:
                p = np.asarray(prob_by_arch[arch][model], dtype=float)[mask]
                m[f"{model}_brier"] = round(brier(p, y_clean), 4) if len(y_clean) else float("nan")
                m[f"{model}_acc"] = round(float(np.mean((p > 0.5) == (y_clean == 1))), 3) if len(y_clean) else float("nan")
            fr.metrics[arch] = m
        fold_results.append(fr)
        if verbose:
            print(f"fold {k:02d} {test_start.date()} n={len(test):3d} | " + " | ".join(
                f"{a.split()[0][:4]}:{fr.metrics[a]['lgbm_brier']:.3f}" for a in ARCH_KEYS))

    return (pd.concat(pred_frames, ignore_index=True) if pred_frames else pd.DataFrame()), fold_results


def summarize_calibration(preds: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for arch in ARCH_KEYS:
        sim_col = arch.replace(" ", "_") + "_sim"
        sub = preds[preds[sim_col] & preds[TARGETS[arch]].notna()]
        y = sub[TARGETS[arch]].astype(float).to_numpy()
        row: Dict = {"archetype": arch, "n": len(y),
                     "base_rate": round(float(np.mean(y)), 3) if len(y) else float("nan")}
        for model in MODEL_NAMES:
            p = sub[f"{model}__{arch}"].to_numpy()
            row[f"{model}_brier"] = round(brier(p, y), 4) if len(y) else float("nan")
            row[f"{model}_acc"] = round(float(np.mean((p > 0.5) == (y == 1))), 3) if len(y) else float("nan")
        rows.append(row)
    return pd.DataFrame(rows)


def _max_drawdown(eq: pd.Series) -> float:
    if eq.empty:
        return 0.0
    return float((eq.cummax() - eq).max())


def _policy_stats(pnl: pd.Series) -> Dict[str, float]:
    pnl = pnl.dropna()
    gp = float(pnl[pnl > 0].sum())
    gl = float(abs(pnl[pnl <= 0].sum()))
    return {
        "n": int(len(pnl)),
        "net_total": round(float(pnl.sum()), 0),
        "avg_net": round(float(pnl.mean()), 1) if len(pnl) else 0.0,
        "win_rate": round(float((pnl > 0).mean()), 3) if len(pnl) else 0.0,
        "pf": round(gp / gl, 2) if gl > 0 else float("inf"),
        "max_dd": round(_max_drawdown(pnl.sort_index().cumsum()), 0),
    }


def _pick_ml_trades(month: pd.DataFrame, model: str, k: int) -> pd.DataFrame:
    """Chooses k (day, archetype) slots, one trade per day, by model probability."""
    scored: List[Tuple[float, pd.Timestamp, str]] = []
    for _, r in month.iterrows():
        for arch in ARCH_KEYS:
            if not r[arch.replace(" ", "_") + "_sim"]:
                continue
            p = r[f"{model}__{arch}"]
            if pd.notna(p):
                scored.append((float(p), r["date"], arch))
    scored.sort(key=lambda t: (-t[0], t[1]))
    chosen_days: set = set()
    rows = []
    for p, d, arch in scored:
        if d in chosen_days:
            continue
        chosen_days.add(d)
        rows.append({"date": d, "archetype": arch, "pnl": None})
        if len(rows) == k:
            break
    if not rows:
        return pd.DataFrame(columns=["date", "archetype", "pnl"])
    out = pd.DataFrame(rows)
    pnl_map = {}
    for arch in ARCH_KEYS:
        sub = month[month[arch.replace(" ", "_") + "_sim"]]
        pnl_map[arch] = sub.set_index("date")[PNL_COLUMNS[arch]]
    out["pnl"] = [pnl_map[r["archetype"]].get(r["date"], np.nan) for _, r in out.iterrows()]
    return out


def gating_simulation(preds: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """Baseline (e001 rule) vs ML-ensemble vs logistic-ensemble at MATCHED monthly count."""
    baseline_trades: List[Tuple[pd.Timestamp, str, float]] = []
    ml_trades: Dict[str, List[Tuple[pd.Timestamp, str, float]]] = {"lgbm": [], "logistic": []}

    for _, month in preds.groupby(preds["date"].dt.to_period("M")):
        base = month[month["rule_signal"].isin(RULE_TO_ARCH)]
        # one trade per day: the rule's archetype, its realized PnL
        for _, r in base.iterrows():
            arch = RULE_TO_ARCH[r["rule_signal"]]
            baseline_trades.append((r["date"], arch, r[PNL_COLUMNS[arch]]))

        k = len(base)
        if k <= 0:
            continue
        for model in ("lgbm", "logistic"):
            picked = _pick_ml_trades(month, model, k)
            for _, r in picked.iterrows():
                ml_trades[model].append((r["date"], r["archetype"], r["pnl"]))

    def summarize(trades: List[Tuple[pd.Timestamp, str, float]]) -> Dict[str, float]:
        if not trades:
            return {"n": 0, "net_total": 0.0, "avg_net": 0.0, "win_rate": 0.0, "pf": 0.0, "max_dd": 0.0}
        df = pd.DataFrame(trades, columns=["date", "archetype", "pnl"]).sort_values("date")
        out = _policy_stats(df["pnl"])
        for arch in ARCH_KEYS:
            sub = df[df["archetype"] == arch]["pnl"]
            out[f"n_{arch}"] = int(len(sub))
            out[f"net_{arch}"] = round(float(sub.sum()), 0) if len(sub) else 0.0
        return out

    return {
        "baseline": summarize(baseline_trades),
        "ml_lgbm": summarize(ml_trades["lgbm"]),
        "ml_logistic": summarize(ml_trades["logistic"]),
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="E002 walk-forward regime models")
    parser.add_argument("--limit", type=int, default=None, help="Smoke test: last N parquet days")
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()

    import config
    if args.no_cache:
        cache = ARTIFACTS / "dataset_cache.parquet"
        if cache.exists():
            cache.unlink()

    ds = build_dataset(config.HISTORICAL_DATA_DIR, HERE.parent, limit=args.limit)
    if "rule_signal" not in ds.columns:
        from experiments.e001_leakfree_replay.replay import TREND_THRESHOLD_PCT
        ds["rule_signal"] = np.where(ds["fut_prev_ret"] >= TREND_THRESHOLD_PCT, "UP",
                              np.where(ds["fut_prev_ret"] <= -TREND_THRESHOLD_PCT, "DOWN", "FLAT"))

    print(f"dataset rows: {len(ds)} | feature cols: {len(FEATURE_COLUMNS)} + gap_open_pct")
    preds, folds = run_walkforward(ds, verbose=True)
    if preds.empty:
        print("No folds produced — not enough data.")
        return 1

    sig_map = ds.set_index("date")["rule_signal"]
    preds["rule_signal"] = preds["date"].map(sig_map)

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    preds.to_parquet(ARTIFACTS / "oos_predictions.parquet", index=False)

    cal = summarize_calibration(preds)
    cal.to_csv(ARTIFACTS / "calibration_summary.csv", index=False)
    print("\n=== OOS CALIBRATION (pooled) ===")
    print(cal.to_string(index=False))

    gate = gating_simulation(preds)
    with open(ARTIFACTS / "gating_sim.json", "w") as f:
        json.dump(gate, f, indent=2, default=str)
    print("\n=== GATING SIM (matched monthly trade count) ===")
    for policy in ("baseline", "ml_lgbm", "ml_logistic"):
        r = gate[policy]
        print(f"{policy:<12} n={r['n']:>4} net={r['net_total']:>10,.0f} avg={r['avg_net']:>8.1f} "
              f"wr={r['win_rate']:.3f} pf={r['pf']:>6} dd={r['max_dd']:>8,.0f}")
        for arch in ARCH_KEYS:
            print(f"    {arch:<18} n={r.get(f'n_{arch}', 0):>4} net={r.get(f'net_{arch}', 0):>10,.0f}")

    with open(ARTIFACTS / "folds.json", "w") as f:
        json.dump([{"fold": fr.fold, "test": f"{fr.test_start}..{fr.test_end}", "n": fr.n_test,
                    "metrics": fr.metrics} for fr in folds], f, indent=2)
    print(f"\nartifacts written to {ARTIFACTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
