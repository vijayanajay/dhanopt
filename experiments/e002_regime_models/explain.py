"""E002 SHAP explanations: what drives each archetype's win-probability model?

- Refits one LightGBM per archetype on ALL purged-usable history (same frozen params) —
  SHAP here explains the fitted model, it is NOT an OOS performance claim.
- Global: mean |SHAP| importance per feature -> importance_<arch>.csv
- Per-day: waterfall-style force data for the WORST predicted days -> force_<arch>_<date>.json
- Artifact flag: P(win) by weekday from the OOS predictions + SHAP weekday attribution;
  flags weekday dependence that may just be the 2025-09 Thursday->Tuesday expiry change.

Usage: python -m experiments.e002_regime_models.explain
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

from experiments.e002_regime_models.features import FEATURE_COLUMNS, build_dataset

HERE = Path(__file__).resolve().parent
from experiments.e002_regime_models.walkforward import (
    ARCH_KEYS,
    ARTIFACTS,
    LGB_PARAMS,
    N_ESTIMATORS,
    TARGETS,
)

PREDICTIONS = ARTIFACTS / "oos_predictions.parquet"
WEEKDAY_FLAG_THRESHOLD = 0.15  # max spread in mean P(win) across weekdays


def fit_pooled(ds: pd.DataFrame, target: str, sim_col: str):
    usable = ds[sim_col].fillna(False).astype(bool) & ds[target].notna()
    X = ds.loc[usable, FEATURE_COLUMNS].apply(pd.to_numeric, errors="coerce")
    y = ds.loc[usable, target].astype(float).to_numpy()
    from lightgbm import LGBMClassifier
    model = LGBMClassifier(n_estimators=N_ESTIMATORS, **LGB_PARAMS)
    model.fit(X, y)
    return model, X


def shap_importance(model, X: pd.DataFrame) -> pd.DataFrame:
    import shap
    explainer = shap.TreeExplainer(model)
    sv = explainer.shap_values(X)  # (n, features) for binary LightGBM
    if isinstance(sv, list):       # older shap returns [class0, class1]
        sv = sv[1]
    mean_abs = np.abs(sv).mean(axis=0)
    imp = pd.DataFrame({"feature": FEATURE_COLUMNS, "mean_abs_shap": mean_abs})
    return imp.sort_values("mean_abs_shap", ascending=False).reset_index(drop=True)


def worst_day_force(model, ds: pd.DataFrame, target: str, sim_col: str, top_k: int = 5) -> List[Dict]:
    import shap
    usable = ds[sim_col].fillna(False).astype(bool) & ds[target].notna()
    X = ds.loc[usable, FEATURE_COLUMNS].apply(pd.to_numeric, errors="coerce")
    explainer = shap.TreeExplainer(model)
    sv = explainer.shap_values(X)
    if isinstance(sv, list):
        sv = sv[1]
    p = model.predict_proba(X)[:, 1]
    y = ds.loc[usable, target].astype(float).to_numpy()
    # Worst calls: model most confidently wrong (high P, actual loss), then lowest P among wins.
    err = (p - y)
    worst_idx = np.argsort(-err)[:top_k]
    base = float(explainer.expected_value[1] if isinstance(explainer.expected_value, (list, np.ndarray)) else explainer.expected_value)
    out: List[Dict] = []
    for i in worst_idx:
        contrib = sorted(zip(FEATURE_COLUMNS, sv[i]), key=lambda t: -abs(t[1]))
        out.append({
            "date": str(ds.loc[usable, "date"].iloc[i].date()),
            "p_model": round(float(p[i]), 3),
            "actual_win": float(y[i]),
            "base_value": round(base, 4),
            "top_contributions": [{"feature": f, "shap": round(float(v), 4)} for f, v in contrib[:8]],
        })
    return out


def weekday_dependence(ds: pd.DataFrame, preds: pd.DataFrame, importances: Dict[str, pd.DataFrame]) -> List[Dict]:
    """Flags weekday artifacts: big spread in OOS mean P(win) by weekday + high dow SHAP rank."""
    flags: List[Dict] = []
    for arch in ARCH_KEYS:
        sim_col = arch.replace(" ", "_") + "_sim"
        sub = preds[preds[sim_col]].copy()
        sub["wd"] = sub["date"].dt.weekday
        by_wd = sub.groupby("wd")[f"lgbm__{arch}"].mean()
        spread = float(by_wd.max() - by_wd.min()) if len(by_wd) else float("nan")
        imp = importances[arch]
        dow_rank = int(imp.index[imp["feature"] == "dow"][0]) + 1 if (imp["feature"] == "dow").any() else -1
        dow_shap = float(imp.loc[imp["feature"] == "dow", "mean_abs_shap"].iloc[0]) if (imp["feature"] == "dow").any() else 0.0
        flags.append({
            "archetype": arch,
            "mean_p_by_weekday": {int(k): round(float(v), 3) for k, v in by_wd.items()},
            "weekday_spread": round(spread, 3),
            "dow_importance_rank": dow_rank,
            "dow_mean_abs_shap": round(dow_shap, 4),
            "flagged": bool(spread > WEEKDAY_FLAG_THRESHOLD and dow_rank <= 6),
            "note": "Nifty weekly expiry moved Thursday->Tuesday on 2025-09-01; weekday effects "
                    "that survive both eras are structural, ones concentrated in one era are artifacts."
        })
    return flags


def era_split_weekday_check(ds: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """Mean condor net PnL by weekday, split at the 2025-09-01 expiry change."""
    col = "Iron_Condor_net"
    sim = "Iron_Condor_sim"
    sub = ds[ds[sim].fillna(False).astype(bool)].copy()
    out: Dict[str, Dict[str, float]] = {}
    for label, mask in (("thursday_era", sub["date"] < "2025-09-01"),
                        ("tuesday_era", sub["date"] >= "2025-09-01")):
        s = sub[mask]
        by_wd = s.groupby(s["date"].dt.weekday)[col].mean()
        out[label] = {int(k): round(float(v), 1) for k, v in by_wd.items()}
    return out


def main() -> int:
    import config
    ds = build_dataset(config.HISTORICAL_DATA_DIR, HERE.parent)
    if "rule_signal" not in ds.columns:
        from experiments.e001_leakfree_replay.replay import TREND_THRESHOLD_PCT
        ds["rule_signal"] = np.where(ds["fut_prev_ret"] >= TREND_THRESHOLD_PCT, "UP",
                              np.where(ds["fut_prev_ret"] <= -TREND_THRESHOLD_PCT, "DOWN", "FLAT"))
    preds = pd.read_parquet(PREDICTIONS)
    preds["date"] = pd.to_datetime(preds["date"])
    if "rule_signal" not in preds.columns:
        preds["rule_signal"] = preds["date"].map(ds.set_index("date")["rule_signal"])

    out_dir = ARTIFACTS / "shap"
    out_dir.mkdir(parents=True, exist_ok=True)

    importances: Dict[str, pd.DataFrame] = {}
    for arch in ARCH_KEYS:
        target = TARGETS[arch]
        sim_col = arch.replace(" ", "_") + "_sim"
        model, X = fit_pooled(ds, target, sim_col)
        imp = shap_importance(model, X)
        importances[arch] = imp
        imp.to_csv(out_dir / f"importance_{arch.replace(' ', '_').lower()}.csv", index=False)
        forces = worst_day_force(model, ds, target, sim_col)
        with open(out_dir / f"force_{arch.replace(' ', '_').lower()}.json", "w") as f:
            json.dump(forces, f, indent=2)
        top3 = ", ".join(f"{r.feature}={r.mean_abs_shap:.3f}" for r in imp.head(3).itertuples())
        print(f"{arch:<18} top features: {top3}")

    flags = weekday_dependence(ds, preds, importances)
    era = era_split_weekday_check(ds)
    with open(out_dir / "weekday_artifact_flags.json", "w") as f:
        json.dump({"flags": flags, "condor_net_pnl_by_weekday_by_era": era}, f, indent=2)
    print("\nWeekday-dependence flags:")
    for fl in flags:
        print(f"  {fl['archetype']:<18} spread={fl['weekday_spread']:.3f} dow_rank={fl['dow_importance_rank']} flagged={fl['flagged']}")
    print("\nCondor net PnL by weekday, thursday-era vs tuesday-era written to weekday_artifact_flags.json")
    print(f"\nSHAP artifacts written to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
