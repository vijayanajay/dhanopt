"""Exit-aware gating: re-run e002's selector with e005's real intraday condor PnLs.

The dte gating numbers price condor trades with e001's open->close proxy (no SL/target).
This script replaces the condor PnL column with e005's exit-aware outcomes — under both
exit configs (documented SL+50% target; and the recommended drop-the-target variant
reconstructed as SL+EOD) — then re-runs the frozen gating machinery unchanged.

Fallback: on days e005 did not simulate (NOSIM/NOLEG, 88 of 1,409), the e001 open->close
label is kept. Bull/bear PnLs stay on e001 labels (e004 validated them directionally;
e005 replayed the condor only) — mixed exit worlds, noted in the README.

Run: python -m experiments.e002_regime_models.gating_exit_aware
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from experiments.e002_regime_models import walkforward as W
from experiments.e002_regime_models.gating_variants import run_variants, payoff_multipliers

HERE = Path(__file__).resolve().parent
DTE = HERE / "artifacts_dte"
E5 = HERE.parent / "e005_theta_condor" / "artifacts" / "theta_condor.csv"
E1 = HERE.parent / "e001_leakfree_replay" / "artifacts" / "labels_daily.csv"
CONDOR_PNL_COL = "Iron_Condor_net"


def e005_pnls() -> tuple[pd.Series, pd.Series]:
    """(documented-exit PnL, drop-target PnL) indexed by date string."""
    df = pd.read_csv(E5)
    df["date"] = df["date"].str[:10]
    sim = df[df["exit_reason"].isin(["TARGET", "EOD", "STOP"])].set_index("date")["net_pnl"]
    # Drop-target counterfactual: TARGET days exit at EOD == the e001 endpoint for that day.
    e1 = pd.read_csv(E1)
    e1["date"] = e1["date"].astype(str)
    endpoint = e1[(e1["archetype"] == "Iron Condor") & (e1["simulated"] == True)].set_index("date")["net_pnl"]
    drop_target = sim.copy()
    tgt = df[df["exit_reason"] == "TARGET"]["date"]
    drop_target.loc[tgt] = endpoint.reindex(tgt)
    return sim, drop_target


def main() -> int:
    preds = pd.read_parquet(DTE / "oos_predictions.parquet")
    preds["date"] = pd.to_datetime(preds["date"])
    preds = preds.copy()

    documented, drop_target = e005_pnls()
    key = preds["date"].dt.strftime("%Y-%m-%d")
    for name, series in (("documented", documented), ("drop_target", drop_target)):
        preds[f"condor_net_{name}"] = key.map(series).fillna(preds[CONDOR_PNL_COL])

    n_doc = int((preds["condor_net_documented"] != preds[CONDOR_PNL_COL]).sum())
    n_tgt = int((preds["condor_net_drop_target"] != preds[CONDOR_PNL_COL]).sum())
    fallback = int((key.isin(documented.index) == False).sum())
    print(f"condor PnLs swapped: documented={n_doc} rows | drop_target={n_tgt} rows | "
          f"e001-fallback days (no e005 sim)={fallback}")

    results: dict = {}
    for name, col in (("documented", "condor_net_documented"), ("drop_target", "condor_net_drop_target")):
        frame = preds.copy()
        frame[CONDOR_PNL_COL] = frame[col]
        gate = W.gating_simulation(frame)
        variants = run_variants(frame, payoff_multipliers(E1, preds["date"].min()))
        results[name] = {"gating": gate, "variants": variants}

    with open(DTE / "gating_exit_aware.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    with open(DTE / "gating_sim.json") as f:
        base = json.load(f)

    print("\n=== GATING, open->close labels (frozen) vs exit-aware condor PnLs ===")
    print(f"{'policy':<34}{'net':>11}{'wr':>7}{'pf':>7}{'maxDD':>9}")
    for policy in ("baseline", "ml_lgbm", "ml_logistic"):
        r = base[policy]
        print(f"{'open->close ' + policy:<34}{r['net_total']:>11,.0f}{r['win_rate']:>7.3f}"
              f"{r['pf']:>7.2f}{r['max_dd']:>9,.0f}")
        for name in results:
            r = results[name]["gating"][policy]
            print(f"{name + ' ' + policy:<34}{r['net_total']:>11,.0f}{r['win_rate']:>7.3f}"
                  f"{r['pf']:>7.2f}{r['max_dd']:>9,.0f}")
        print()

    print("=== EV-ranked and condor-only variants (condor PnLs exit-aware) ===")
    for name in results:
        v = results[name]["variants"]
        for key2, label in (("ml_ev", "EV lgbm"), ("condor_ml", "condor ML")):
            r = v[key2]
            print(f"{name + ' ' + label:<34}{r['net_total']:>11,.0f}{r['win_rate']:>7.3f}"
                  f"{r['pf']:>7.2f}{r['max_dd']:>9,.0f}")

    print(f"\nwritten: {DTE / 'gating_exit_aware.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
