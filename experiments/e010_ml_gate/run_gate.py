"""e010 Phase 2: the FROZEN LightGBM when-to-trade gate (PREREG §3).

One model, e002's 16 test-pinned t-1 features, label = the frozen credit
spread's own daily net_pnl (wall-free). Walkforward: expanding window,
yearly refits, first OOS year = the second year of data. Trade day t iff
P(win) >= 0.55 — frozen in the PREREG from calibration reasoning alone,
never tuned on OOS PnL. No feature selection, no early stopping on OOS, no
variants (PREREG §4: one run, as frozen).

Leak registry: info "t-1" / live True — features are e002's shift(1)-pinned
rows (test_day_t_feature_row_never_sees_day_t); the label is wall-free and
its structure has no day-t OI input; fills are the 09:15 open of the traded
day (observable at entry time). First commit declares this before any PnL
number is committed, per the registry's contract.

Kill bars (PREREG §4, fail-only): OOS net > 0; PF >= 1.5 with n >= 30;
OOS Brier strictly better than base rate; OOS net >= always-on and >=
random-2-per-month baseline; >= 1 OOS trade/year.
Run: python -m experiments.e010_ml_gate.run_gate
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.e002_regime_models.features import FEATURE_COLUMNS, build_feature_rows

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "artifacts"
OUT = ARTIFACTS / "gate_oos.json"
PRED = ARTIFACTS / "gate_oos_trades.csv"

THRESHOLD = 0.55          # frozen
LGBM_PARAMS = dict(n_estimators=400, learning_rate=0.05, num_leaves=31,
                   min_child_samples=40, verbose=-1)  # frozen (e002 defaults)
MIN_N = 30                # frozen PF bar
PF_MIN = 1.5              # frozen PF bar


def _walkforward(features: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    df = features.merge(labels[["date", "net_pnl", "win"]], on="date", how="inner")
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    import lightgbm as lgb
    oos_rows: list[dict] = []
    years = sorted(df["date"].dt.year.unique())
    for oos_year in years[1:]:  # first OOS year = second year of data
        tr = df[df["date"].dt.year < oos_year]
        te = df[df["date"].dt.year == oos_year]
        if tr.empty or te.empty or tr["win"].nunique() < 2:
            continue
        model = lgb.LGBMClassifier(**LGBM_PARAMS)
        model.fit(tr[FEATURE_COLUMNS], tr["win"])
        proba = model.predict_proba(te[FEATURE_COLUMNS])[:, 1]
        for (_, row), p in zip(te.iterrows(), proba):
            oos_rows.append({"date": row["date"].date().isoformat(),
                             "year": oos_year, "p_win": round(float(p), 4),
                             "trade": bool(p >= THRESHOLD),
                             "net_pnl": float(row["net_pnl"]),
                             "win": int(row["win"])})
    return pd.DataFrame(oos_rows)


def _pf(pnl: pd.Series) -> float:
    gl = abs(pnl[pnl <= 0].sum())
    return float("inf") if gl == 0 else float(pnl[pnl > 0].sum() / gl)


def _verdict(oos: pd.DataFrame, n_years_oos: int) -> dict:
    trades = oos[oos["trade"]]
    win01 = oos["win"].astype(int)
    # kill 3, exactly as frozen: the gate's Brier on ALL OOS days must beat the
    # majority-class predictor on the same days (the toughest fair baseline).
    brier_model = float(((oos["p_win"] - win01).pow(2)).mean())
    majority = max(float(win01.mean()), 1 - float(win01.mean()))
    brier_majority = float(((majority - win01).pow(2)).mean())

    k1 = bool(len(trades) and trades["net_pnl"].sum() > 0)
    pf = _pf(trades["net_pnl"]) if len(trades) else None
    k2 = bool(pf is not None and pf >= PF_MIN and len(trades) >= MIN_N)
    k3 = bool(brier_model < brier_majority)
    # kill 4b: 2 random trade-days per OOS month (the owner's stated cadence), seed 42
    rng = np.random.default_rng(42)
    rand_days = sorted(rng.choice(oos["date"].unique(), size=24 * n_years_oos, replace=False)) \
        if len(oos) >= 24 * n_years_oos else []
    rand_net = float(oos[oos["date"].isin(rand_days)]["net_pnl"].sum()) if len(rand_days) else 0.0
    always_net = float(oos["net_pnl"].sum())
    gated_net = float(trades["net_pnl"].sum()) if len(trades) else 0.0
    k4 = bool(gated_net >= always_net and gated_net >= rand_net)
    per_year = trades.groupby("year")["date"].nunique() if len(trades) else pd.Series(dtype=int)
    k5 = bool(len(per_year) > 0 and (per_year >= 1).all() and len(per_year) == n_years_oos)

    verdict = {
        "threshold": THRESHOLD, "n_oos_days": len(oos), "n_trades": len(trades),
        "trades_per_year_expected": round(len(trades) / max(n_years_oos, 1), 1),
        "gated_net": round(gated_net, 0), "always_on_net": round(always_net, 0),
        "random_2pm_net": round(rand_net, 0), "pf": round(pf, 2) if pf not in (None, float("inf")) else pf,
        "wr": round(float((trades["net_pnl"] > 0).mean()), 3) if len(trades) else None,
        "brier_model": round(brier_model, 4), "brier_majority": round(brier_majority, 4),
        "per_year_trades": {str(k): int(v) for k, v in per_year.items()},
        "kill_criteria": {"1_net_gt_0": k1, "2_pf_ge_1p5_n_ge_30": k2,
                          "3_brier_beats_base": k3, "4_beats_baselines": k4,
                          "5_capacity_1_per_year": k5},
        "verdict": "PASS" if all([k1, k2, k3, k4, k5]) else "FAIL",
    }
    return verdict


def main() -> int:
    import argparse

    import config

    ap = argparse.ArgumentParser(description="e010 frozen ML gate — walkforward verdict")
    ap.add_argument("--limit", type=int, default=None, help="limit feature days (debug only)")
    args = ap.parse_args()
    features = build_feature_rows(config.HISTORICAL_DATA_DIR, limit=args.limit)
    labels = pd.read_csv(HERE / "artifacts" / "credit_labels.csv", parse_dates=["date"])
    oos = _walkforward(features, labels)
    if oos.empty:
        print(json.dumps({"verdict": "NO-OOS", "note": "no walkforward folds produced"}, indent=1))
        return 1
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    oos.to_csv(PRED, index=False)
    n_years_oos = oos["year"].nunique()
    verdict = _verdict(oos, n_years_oos)
    OUT.write_text(json.dumps(verdict, indent=1))
    print(json.dumps(verdict, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
