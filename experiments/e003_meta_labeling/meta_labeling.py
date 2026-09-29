"""E003: Meta-labeling (Lopez de Prado style) on the e001 rule's own trades.

Difference vs e002: e002 trains one model PER ARCHETYPE on all days and lets the ensemble
pick day AND archetype. Meta-labeling trains ONE model ONLY on the trades the rule engine
would actually take (rule-selected day+archetype), predicting P(this rule trade wins).
The production policy is then: take the rule trade, but skip it when P < threshold and
redeploy that slot on the next-best rule trade day of the month.

- Same purged monthly folds as e002 (24m train, 5d embargo, 1m test, frozen params).
- Policy comparison at MATCHED monthly trade count:
    baseline   : every rule trade
    meta       : top-K rule trades by P(win), K = baseline count
    e002-style : day/archetype selector from e002's per-archetype LGBM ensemble
      # ponytail: the e002 comparator here re-uses its pooled OOS predictions file
      # (same test months) — a fair-enough in-sandbox comparison, not a joint refit.
- Calibration: Brier vs base rate on rule trades only.

Usage: python -m experiments.e003_meta_labeling.meta_labeling
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from experiments.e002_regime_models.features import FEATURE_COLUMNS, build_dataset
from experiments.e002_regime_models.walkforward import (
    ARTIFACTS as E002_ARTIFACTS,
    LGB_PARAMS,
    N_ESTIMATORS,
    PNL_COLUMNS,
    RULE_TO_ARCH,
    brier,
)

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "artifacts"
TRAIN_MONTHS = 24
EMBARGO_DAYS = 5


def rule_trades(ds: pd.DataFrame) -> pd.DataFrame:
    """The trades the e001 rule takes: one per signal day, archetype fixed by the rule."""
    sub = ds[ds["rule_signal"].isin(RULE_TO_ARCH)].copy()
    sub["archetype"] = sub["rule_signal"].map(RULE_TO_ARCH)
    sub["target"] = sub["archetype"].map(
        {"Bull Call Spread": "Bull_Call_Spread_won", "Bear Put Spread": "Bear_Put_Spread_won",
         "Iron Condor": "Iron_Condor_won"})
    sub["sim"] = sub.apply(lambda r: bool(r[r["archetype"].replace(" ", "_") + "_sim"]), axis=1)
    sub["pnl"] = sub.apply(lambda r: r[PNL_COLUMNS[r["archetype"]]], axis=1)
    return sub[sub["sim"] & sub["target"].notna()].reset_index(drop=True)


def run_walkforward(trades: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Dict[str, float]]]:
    from lightgbm import LGBMClassifier

    trades = trades.sort_values("date").reset_index(drop=True)
    months = sorted(trades["date"].dt.to_period("M").unique())
    starts = [pd.Period(m).to_timestamp() for m in months]

    preds: List[pd.DataFrame] = []
    cal = {"brier": 0.0, "acc": 0.0, "base_rate": 0.0, "n": 0}

    all_p, all_y = [], []
    for i in range(TRAIN_MONTHS, len(starts)):
        train_start, test_start = starts[i - TRAIN_MONTHS], starts[i]
        test_end = test_start + pd.offsets.MonthEnd(0)
        train = trades[(trades["date"] >= train_start) & (trades["date"] < test_start - pd.Timedelta(days=EMBARGO_DAYS))]
        test = trades[(trades["date"] >= test_start) & (trades["date"] <= test_end)].copy()
        if test.empty:
            continue

        Xtr = train[FEATURE_COLUMNS].apply(pd.to_numeric, errors="coerce")
        # y per-row from that row's own target column (rule fixes the archetype per day)
        ytr = train.apply(lambda r: float(r[r["target"]]), axis=1).to_numpy()
        Xte = test[FEATURE_COLUMNS].apply(pd.to_numeric, errors="coerce")

        if len(ytr) < 150 or ytr.sum() < 30:
            test["p_meta"] = float(np.mean(ytr)) if len(ytr) else 0.5
        else:
            m = LGBMClassifier(n_estimators=N_ESTIMATORS, **LGB_PARAMS)
            m.fit(Xtr, ytr)
            test["p_meta"] = m.predict_proba(Xte)[:, 1]

        preds.append(test[["date", "archetype", "pnl", "p_meta"]])
        all_p.extend(test["p_meta"].tolist())
        all_y.extend(test.apply(lambda r: float(r[r["target"]]), axis=1).tolist())

    if not preds:
        return pd.DataFrame(), cal
    out = pd.concat(preds, ignore_index=True)
    y = np.array(all_y)
    p = np.array(all_p)
    cal = {
        "brier": round(brier(p, y), 4),
        "acc": round(float(np.mean((p > 0.5) == (y == 1))), 3),
        "base_rate": round(float(np.mean(y)), 3),
        "n": len(y),
    }
    return out, cal


def _stats(pnl: pd.Series) -> Dict[str, float]:
    pnl = pnl.dropna()
    gp, gl = float(pnl[pnl > 0].sum()), float(abs(pnl[pnl <= 0].sum()))
    eq = pnl.sort_index().cumsum()
    return {
        "n": int(len(pnl)),
        "net_total": round(float(pnl.sum()), 0),
        "avg_net": round(float(pnl.mean()), 1) if len(pnl) else 0.0,
        "win_rate": round(float((pnl > 0).mean()), 3) if len(pnl) else 0.0,
        "pf": round(gp / gl, 2) if gl > 0 else float("inf"),
        "max_dd": round(float((eq.cummax() - eq).max()), 0),
    }


def compare_policies(meta_preds: pd.DataFrame, e002_preds: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """baseline (all rule trades) vs meta (top-K by P) vs e002-style selector, matched count."""
    e002_preds = e002_preds.copy()
    e002_preds["date"] = pd.to_datetime(e002_preds["date"])

    base_rows, meta_rows, sel_rows = [], [], []
    for month_key, month in meta_preds.groupby(meta_preds["date"].dt.to_period("M")):
        k = len(month)  # rule trades this month = baseline count
        base_rows.append(month)

        # meta policy: top-K of the SAME rule trades. # ponytail: with K = the full rule set,
        # this has zero freedom by construction — the real meta-labeling operating point is a
        # probability THRESHOLD (trades fewer, nominally better trades), reported separately.
        meta_rows.append(month.nlargest(k, "p_meta").sort_values("date") if k > 0 else month)

        # e002-style: same K trades, pick best (day, archetype) slots from e002 OOS preds
        m2 = e002_preds[e002_preds["date"].dt.to_period("M") == month_key]
        scored: List[Tuple[float, pd.Timestamp, str]] = []
        for _, r in m2.iterrows():
            for arch, pcol in (("Bull Call Spread", "lgbm__Bull Call Spread"),
                               ("Bear Put Spread", "lgbm__Bear Put Spread"),
                               ("Iron Condor", "lgbm__Iron Condor")):
                sim_col = arch.replace(" ", "_") + "_sim"
                if r.get(sim_col, False) and pd.notna(r.get(pcol, np.nan)):
                    scored.append((float(r[pcol]), r["date"], arch))
        scored.sort(key=lambda t: (-t[0], t[1]))
        days_seen = set()
        chosen: List[Tuple[pd.Timestamp, str]] = []
        for p, d, arch in scored:
            if d in days_seen:
                continue
            days_seen.add(d)
            chosen.append((d, arch))
            if len(chosen) == k:
                break
        for d, arch in chosen:
            r = m2[m2["date"] == d].iloc[0]
            sel_rows.append({"date": d, "archetype": arch,
                             "pnl": r[arch.replace(" ", "_") + "_net"]})

    def agg(frames, pnl_col: str) -> Dict[str, float]:
        if not frames:
            return _stats(pd.Series(dtype=float))
        if isinstance(frames[0], dict):
            df = pd.DataFrame(frames)
        else:
            df = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
        return _stats(df[pnl_col])

    return {
        "baseline_rule": agg(base_rows, "pnl"),
        "meta_filtered": agg(meta_rows, "pnl"),
        "e002_style_selector": agg(sel_rows, "pnl"),
    }


def threshold_sweep(meta_preds: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """Meta-labeling's natural operating point: skip rule trades with P < tau."""
    out: Dict[str, Dict[str, float]] = {}
    for tau in (0.40, 0.45, 0.50, 0.55):
        sub = meta_preds[meta_preds["p_meta"] >= tau]
        st = _stats(sub["pnl"])
        st["keep_rate"] = round(len(sub) / len(meta_preds), 3) if len(meta_preds) else 0.0
        out[f"tau_{tau:.2f}"] = st
    return out


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="E003 meta-labeling")
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()

    import config
    if args.no_cache:
        cache = E002_ARTIFACTS / "dataset_cache.parquet"
        if cache.exists():
            cache.unlink()

    ds = build_dataset(config.HISTORICAL_DATA_DIR, HERE.parent)
    if "rule_signal" not in ds.columns:
        from experiments.e001_leakfree_replay.replay import TREND_THRESHOLD_PCT
        ds["rule_signal"] = np.where(ds["fut_prev_ret"] >= TREND_THRESHOLD_PCT, "UP",
                              np.where(ds["fut_prev_ret"] <= -TREND_THRESHOLD_PCT, "DOWN", "FLAT"))

    trades = rule_trades(ds)
    print(f"rule trades: {len(trades)} | base rate by archetype:")
    print(trades.groupby("archetype").apply(lambda g: round(g.apply(lambda r: float(r[r['target']]), axis=1).mean(), 3)))

    meta_preds, cal = run_walkforward(trades)
    if meta_preds.empty:
        print("Not enough rule trades for walk-forward.")
        return 1
    print(f"\nmeta-model calibration (OOS): {cal}")

    e002_preds = pd.read_parquet(E002_ARTIFACTS / "oos_predictions.parquet")
    policies = compare_policies(meta_preds, e002_preds)
    sweep = threshold_sweep(meta_preds)

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    meta_preds.to_parquet(ARTIFACTS / "meta_oos_predictions.parquet", index=False)
    with open(ARTIFACTS / "policy_comparison.json", "w") as f:
        json.dump({"calibration": cal, "policies": policies, "threshold_sweep": sweep}, f, indent=2, default=str)

    print("\n=== POLICY COMPARISON (matched monthly trade count) ===")
    for name, st in policies.items():
        print(f"{name:<22} n={st['n']:>4} net={st['net_total']:>10,.0f} avg={st['avg_net']:>8.1f} "
              f"wr={st['win_rate']:.3f} pf={st['pf']:>6} dd={st['max_dd']:>8,.0f}")
    print("\n=== THRESHOLD SWEEP (meta natural operating point: skip P < tau) ===")
    for tau, st in sweep.items():
        print(f"{tau:<10} n={st['n']:>4} keep={st['keep_rate']:.2f} net={st['net_total']:>10,.0f} "
              f"avg={st['avg_net']:>8.1f} wr={st['win_rate']:.3f} pf={st['pf']:>6}")
    print(f"\nartifacts written to {ARTIFACTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
