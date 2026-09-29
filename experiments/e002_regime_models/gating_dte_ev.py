"""EV ranking (P(win) x payoff) on the dte feature set — does it beat logistic+dte (+653k)?

Reuses gating_variants.run_variants unchanged on artifacts_dte/oos_predictions.parquet
(same frozen payoffs, same matched-count gating). Run:
    python -m experiments.e002_regime_models.gating_dte_ev
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from experiments.e002_regime_models.gating_variants import (
    ARTIFACTS, CAPITAL, ARCH_KEYS, payoff_multipliers, run_variants)

HERE = Path(__file__).resolve().parent
DTE = HERE / "artifacts_dte"


def main() -> int:
    preds = pd.read_parquet(DTE / "oos_predictions.parquet")
    preds["date"] = pd.to_datetime(preds["date"])
    payoff = payoff_multipliers(
        HERE.parent / "e001_leakfree_replay" / "artifacts" / "labels_daily.csv", preds["date"].min())
    res = run_variants(preds, payoff)
    order = [("ml_pwin_repro", "dte P(win) lgbm"), ("ml_ev", "dte EV lgbm"),
             ("condor_rule", "dte condor rule days"), ("condor_ml", "dte condor ML"),
             ("condor_ml_ev", "dte condor ML+EV")]
    print(f"{'policy':<26}{'n':>5}{'net':>11}{'avg':>8}{'wr':>7}{'pf':>7}{'maxDD':>9}{'DD%':>7}")
    for key, label in order:
        r = res[key]
        print(f"{label:<26}{r['n']:>5}{r['net_total']:>11,.0f}{r['avg_net']:>8.1f}"
              f"{r['win_rate']:>7.3f}{r['pf']:>7.2f}{r['max_dd']:>9,.0f}{r['max_dd_pct']:>6.1f}%")
        for arch in ARCH_KEYS:
            print(f"    {arch:<22} n={r[f'n_{arch}']:>4} net={r[f'net_{arch}']:>10,.0f}")

    import json
    with open(DTE / "gating_variants.json", "w") as f:
        json.dump({"payoff_multipliers": payoff, "policies": res}, f, indent=2, default=str)
    print(f"\nreference: logistic+dte P(win) policy = +653,520 (walkforward_dte gating_sim.json); "
          f"cap {CAPITAL:,.0f}")
    print(f"written: {DTE / 'gating_variants.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
